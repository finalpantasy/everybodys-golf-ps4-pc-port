"""Room state for the localhost lobby service. The caller holds the roster lock."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from hashlib import sha256
from http import HTTPStatus
from itertools import islice
from operator import eq, ge, gt, le, lt, ne
from struct import Struct
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lobby_registry import Member

ROOM_PATH = "/nmg-us/local-lobby/v1/rooms"
ROOM_MESSAGE_PATH = "/nmg-us/local-lobby/v1/room-messages"
ROOM_MESSAGE_REQUEST = Struct("<BBH16sQQ")
ROOM_MESSAGE_SEND = Struct("<BBH")
ROOM_MESSAGE_COUNT = Struct("<H")
ROOM_MESSAGE_ROW = Struct("<QHBBH")
MESSAGE_SEND, MESSAGE_POLL = 1, 2
MESSAGE_BROADCAST, MESSAGE_UNICAST, MESSAGE_MULTICAST = 1, 2, 3
MAX_ROOM_MESSAGE = 1024
MAX_MESSAGE_QUEUE = 32
MESSAGES_PER_POLL = 8
ROOM_HEADER = Struct("<BBH16s")
CREATE_ROOM = Struct("<QHIBHH")
SEARCH_ROOMS = Struct("<IIIIBBH")
UPDATE_ROOM = Struct("<QIIH")
ROOM_ID = Struct("<Q")
ROOM_VIEW = Struct("<QQIHHHHH")
ROOM_MEMBER = Struct("<H16s")
ROOM_SIGNALING = Struct("<BBH")
ROOM_INTERNAL_SIZE = Struct("<H")
MESH, STAR = 1, 2
ROOM_LIST = Struct("<III")
ROOM_LIST_ROW = Struct("<QQIHHHH16s")
INTEGER_ATTR = Struct("<HI")
INTEGER_FILTER = Struct("<HBBI")
MAX_ROOM_MEMBERS = 50
MAX_ROOM_RESULTS = 20
MAX_ROOM_ATTRIBUTE = 256
SEARCH_ATTR_IDS = range(0x4c, 0x54)
LEGACY_ROOM_REQUEST_MAX = (ROOM_HEADER.size + CREATE_ROOM.size + len(SEARCH_ATTR_IDS) * INTEGER_ATTR.size
                           + 2 * MAX_ROOM_ATTRIBUTE)
ROOM_REQUEST_MAX = LEGACY_ROOM_REQUEST_MAX + ROOM_SIGNALING.size
ROOM_MESSAGE_REQUEST_MAX = (ROOM_MESSAGE_REQUEST.size + ROOM_MESSAGE_SEND.size
                            + 2 * (MAX_ROOM_MEMBERS - 1) + MAX_ROOM_MESSAGE)
CREATE, JOIN, VIEW, LEAVE, SEARCH, EXTERNAL, UPDATE, UPDATE_INTERNAL = range(1, 9)
OWNER_AUTO_GRANT = 0x80000000
CLOSED = 0x40000000
FULL = 0x20000000
HIDDEN = 0x10000000
NAT_RESTRICTION = 0x04000000
MUTABLE_FLAGS = CLOSED | HIDDEN
CREATE_FLAGS = OWNER_AUTO_GRANT | MUTABLE_FLAGS | NAT_RESTRICTION
COMPARE = {1: eq, 2: ne, 3: lt, 4: le, 5: gt, 6: ge}


@dataclass
class RoomMessageInbox:
    queue: deque[tuple[int, int, int, bytes]] = field(default_factory=deque)
    next_sequence: int = 1
    ack: int = 0
    advertised: int = 0
    last_send: tuple[int, bytes] = (0, b"")

    def poll(self, ack: int) -> tuple[HTTPStatus, bytes]:
        if not self.ack <= ack <= self.advertised:
            return HTTPStatus.CONFLICT, b""
        self.ack = ack
        while self.queue and self.queue[0][0] <= ack:
            self.queue.popleft()
        batch = list(islice(self.queue, MESSAGES_PER_POLL))
        if batch:
            self.advertised = max(self.advertised, batch[-1][0])
        return HTTPStatus.OK, ROOM_MESSAGE_COUNT.pack(len(batch)) + b"".join(
            ROOM_MESSAGE_ROW.pack(seq, sender, cast, 0, len(data)) + data
            for seq, sender, cast, data in batch
        )


@dataclass
class Room:
    room_id: int
    capacity: int
    flags: int
    owner: bytes
    search_integers: dict[int, int]
    search_binary: bytes
    listing: bytes
    internal: bytes
    members: dict[bytes, None] = field(default_factory=dict)
    signaling: int = 0
    revision: int = 1
    messages: dict[bytes, RoomMessageInbox] = field(default_factory=dict)

    @property
    def current_flags(self) -> int:
        return self.flags | (FULL if len(self.members) == self.capacity else 0)

    def view(self, roster: dict[bytes, Member], token: bytes, extended: bool) -> bytes:
        header = ROOM_VIEW.pack(self.room_id, self.revision, self.current_flags, self.capacity, len(self.members),
                                roster[self.owner].member_id, roster[token].member_id, len(self.listing))
        members = (roster[key] for key in self.members)
        rows = b"".join(ROOM_MEMBER.pack(member.member_id, member.name) for member in members)
        signaling = ROOM_SIGNALING.pack(self.signaling, 0, self.signaling_hub(roster)) if self.signaling or extended else b""
        internal = ROOM_INTERNAL_SIZE.pack(len(self.internal)) + self.internal if extended else b""
        return header + rows + self.listing + signaling + internal

    def signaling_hub(self, roster: dict[bytes, Member]) -> int:
        return roster[self.owner].member_id if self.signaling == STAR else 0

    def exchange_messages(self, roster: dict[bytes, Member], token: bytes, operation: int,
                          cursor: int, body: bytes) -> tuple[HTTPStatus, bytes]:
        inbox = self.messages.setdefault(token, RoomMessageInbox())
        if operation == MESSAGE_POLL:
            if body:
                return HTTPStatus.BAD_REQUEST, b""
            return inbox.poll(cursor)
        if operation != MESSAGE_SEND or not cursor or len(body) < ROOM_MESSAGE_SEND.size:
            return HTTPStatus.BAD_REQUEST, b""
        cast, count, size = ROOM_MESSAGE_SEND.unpack_from(body)
        end = ROOM_MESSAGE_SEND.size + ROOM_MESSAGE_COUNT.size * count
        if (cast not in (MESSAGE_BROADCAST, MESSAGE_UNICAST, MESSAGE_MULTICAST)
                or (cast == MESSAGE_BROADCAST and count) or (cast == MESSAGE_UNICAST and count != 1)
                or (cast == MESSAGE_MULTICAST and not 1 <= count < MAX_ROOM_MEMBERS)
                or not 1 <= size <= MAX_ROOM_MESSAGE or end + size != len(body)):
            return HTTPStatus.BAD_REQUEST, b""
        ids = {member_id for (member_id,) in ROOM_MESSAGE_COUNT.iter_unpack(body[ROOM_MESSAGE_SEND.size:end])}
        sender = roster[token].member_id
        if 0 in ids or sender in ids or len(ids) != count:
            return HTTPStatus.BAD_REQUEST, b""
        digest = sha256(body).digest()
        if cursor <= inbox.last_send[0]:
            return (HTTPStatus.OK if (cursor, digest) == inbox.last_send else HTTPStatus.CONFLICT), b""
        recipients = [key for key in self.members if key != token
                      and (cast == MESSAGE_BROADCAST or roster[key].member_id in ids)]
        if cast != MESSAGE_BROADCAST and len(recipients) != count:
            return HTTPStatus.NOT_FOUND, b""
        queues = [self.messages.setdefault(key, RoomMessageInbox()) for key in recipients]
        if any(len(queue.queue) >= MAX_MESSAGE_QUEUE for queue in queues):
            return HTTPStatus.TOO_MANY_REQUESTS, b""
        payload = body[end:]
        for queue in queues:
            queue.queue.append((queue.next_sequence, sender, cast, payload))
            queue.next_sequence += 1
        inbox.last_send = (cursor, digest)
        return HTTPStatus.OK, b""

    def row(self, roster: dict[bytes, Member]) -> bytes:
        owner = roster[self.owner]
        return ROOM_LIST_ROW.pack(self.room_id, self.revision, self.current_flags, self.capacity,
                                  len(self.members), owner.member_id, len(self.listing), owner.name) + self.listing


class RoomRegistry:
    def __init__(self, world: int):
        self.world = world
        self.rooms: dict[int, Room] = {}
        self.next_id = 1

    def leave(self, roster: dict[bytes, Member], token: bytes):
        member = roster[token]
        if not member.room_id:
            return
        room = self.rooms[member.room_id]
        member.room_id = 0
        del room.members[token]
        room.messages.pop(token, None)
        for inbox in room.messages.values():
            inbox.queue = deque(message for message in inbox.queue if message[1] != member.member_id)
        if not room.members or (token == room.owner and not room.flags & OWNER_AUTO_GRANT):
            del self.rooms[room.room_id]
            for key in room.members:
                roster[key].room_id = 0
            return
        if token == room.owner:
            room.owner = next(iter(room.members))
        room.revision += 1

    def create(self, roster: dict[bytes, Member], token: bytes, body: bytes,
               extended: bool) -> tuple[HTTPStatus, bytes]:
        if len(body) < CREATE_ROOM.size:
            return HTTPStatus.BAD_REQUEST, b""
        nonce, capacity, flags, count, bin_size, listing_size = CREATE_ROOM.unpack_from(body)
        attr_end = CREATE_ROOM.size + count * INTEGER_ATTR.size
        binary_end = attr_end + bin_size
        listing_end = binary_end + listing_size
        if (not nonce or not 1 <= capacity <= MAX_ROOM_MEMBERS or flags & ~CREATE_FLAGS
                or count > len(SEARCH_ATTR_IDS) or max(bin_size, listing_size) > MAX_ROOM_ATTRIBUTE
                or len(body) not in (listing_end, listing_end + ROOM_SIGNALING.size)):
            return HTTPStatus.BAD_REQUEST, b""
        signaling = 0
        if len(body) > listing_end:
            signaling, flag, hub = ROOM_SIGNALING.unpack_from(body, listing_end)
            if signaling not in (MESH, STAR) or flag or hub:
                return HTTPStatus.BAD_REQUEST, b""
        values = dict(INTEGER_ATTR.iter_unpack(body[CREATE_ROOM.size:attr_end]))
        if len(values) != count or any(key not in SEARCH_ATTR_IDS for key in values):
            return HTTPStatus.BAD_REQUEST, b""

        member = roster[token]
        digest = sha256(body).digest()
        last_nonce, last_room, last_digest = member.last_room_create
        if nonce <= last_nonce:
            if nonce == last_nonce and last_room == member.room_id and digest == last_digest:
                return HTTPStatus.OK, self.rooms[last_room].view(roster, token, extended)
            return HTTPStatus.CONFLICT, b""
        if member.room_id:
            return HTTPStatus.CONFLICT, b""
        room_id = self.world << 56 | self.next_id
        self.next_id += 1
        listing = body[binary_end:listing_end]
        room = Room(room_id, capacity, flags, token, values, body[attr_end:binary_end],
                    listing, internal=listing, members={token: None}, signaling=signaling)
        self.rooms[room_id] = room
        member.room_id = room_id
        member.last_room_create = (nonce, room_id, digest)
        return HTTPStatus.OK, room.view(roster, token, extended)

    def search(self, roster: dict[bytes, Member], body: bytes) -> tuple[HTTPStatus, bytes]:
        if len(body) < SEARCH_ROOMS.size:
            return HTTPStatus.BAD_REQUEST, b""
        start, limit, mask, value, count, bin_op, bin_size = SEARCH_ROOMS.unpack_from(body)
        attr_end = SEARCH_ROOMS.size + count * INTEGER_FILTER.size
        if (not start or not 1 <= limit <= MAX_ROOM_RESULTS or value & ~mask
                or count > len(SEARCH_ATTR_IDS) or bin_op != bool(bin_size)
                or bin_size > MAX_ROOM_ATTRIBUTE or attr_end + bin_size != len(body)):
            return HTTPStatus.BAD_REQUEST, b""
        filters = list(INTEGER_FILTER.iter_unpack(body[SEARCH_ROOMS.size:attr_end]))
        if any(key not in SEARCH_ATTR_IDS or op not in COMPARE or reserved
               for key, op, reserved, _ in filters):
            return HTTPStatus.BAD_REQUEST, b""
        # Every route is loopback, where the NAT restriction has no effect.
        mask &= ~NAT_RESTRICTION
        value &= mask
        tag = body[attr_end:]
        matching = [room for room in self.rooms.values()
                    if (room.current_flags & mask) == value and (not tag or room.search_binary == tag)
                    and all(key in room.search_integers and COMPARE[op](room.search_integers[key], target)
                            for key, op, _, target in filters)]
        rows = matching[start - 1:start - 1 + limit]
        return HTTPStatus.OK, ROOM_LIST.pack(start, len(matching), len(rows)) + b"".join(room.row(roster) for room in rows)

    def update(self, roster: dict[bytes, Member], token: bytes, body: bytes,
               *, internal: bool, extended: bool) -> tuple[HTTPStatus, bytes]:
        if len(body) < UPDATE_ROOM.size:
            return HTTPStatus.BAD_REQUEST, b""
        room_id, mask, value, size = UPDATE_ROOM.unpack_from(body)
        allowed = CREATE_FLAGS if internal else MUTABLE_FLAGS
        if mask & ~allowed or value & ~mask or size > MAX_ROOM_ATTRIBUTE or UPDATE_ROOM.size + size != len(body):
            return HTTPStatus.BAD_REQUEST, b""
        room = self.rooms.get(room_id)
        if room is None or token not in room.members:
            return HTTPStatus.NOT_FOUND, b""
        if token != room.owner:
            return HTTPStatus.FORBIDDEN, b""
        flags = (room.flags & ~mask) | value
        attribute = body[UPDATE_ROOM.size:]
        if flags != room.flags or attribute != (room.internal if internal else room.listing):
            room.flags = flags
            if internal:
                room.internal = attribute
            else:
                room.listing = attribute
            room.revision += 1
        return HTTPStatus.OK, room.view(roster, token, extended)

    def exchange(self, roster: dict[bytes, Member], token: bytes, operation: int,
                 body: bytes, extended: bool) -> tuple[HTTPStatus, bytes]:
        if operation == CREATE:
            return self.create(roster, token, body, extended)
        if operation == SEARCH:
            return self.search(roster, body)
        if operation == UPDATE or (extended and operation == UPDATE_INTERNAL):
            return self.update(roster, token, body, internal=operation == UPDATE_INTERNAL, extended=extended)
        if operation not in (JOIN, VIEW, LEAVE, EXTERNAL) or len(body) != ROOM_ID.size:
            return HTTPStatus.BAD_REQUEST, b""
        room_id, = ROOM_ID.unpack(body)
        room = self.rooms.get(room_id)
        if room is None:
            return HTTPStatus.NOT_FOUND, b""
        if operation == EXTERNAL:
            return HTTPStatus.OK, ROOM_LIST.pack(1, 1, 1) + room.row(roster)
        if operation == JOIN and token not in room.members:
            if roster[token].room_id or room.current_flags & (CLOSED | FULL):
                return HTTPStatus.CONFLICT, b""
            room.members[token] = None
            roster[token].room_id = room_id
            room.revision += 1
        if token not in room.members:
            return HTTPStatus.NOT_FOUND, b""
        if operation == LEAVE:
            self.leave(roster, token)
            return HTTPStatus.OK, b""
        return HTTPStatus.OK, room.view(roster, token, extended)
