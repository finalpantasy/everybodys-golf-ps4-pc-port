"""Membership for the native runtime's opt-in loopback lobby service."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from hashlib import sha256
from http import HTTPStatus
from itertools import islice
import re
from secrets import token_bytes
from struct import Struct
from threading import Lock
from time import monotonic

from room_registry import (
    ROOM_HEADER, ROOM_MESSAGE_REQUEST, ROOM_MESSAGE_REQUEST_MAX, ROOM_REQUEST_MAX, RoomRegistry,
)


LOBBY_PATH = "/nmg-us/local-lobby/v1"
PEER_PACKET_PATH = LOBBY_PATH + "/packets"
PEER_CHANNEL_PATH = LOBBY_PATH + "/channels"
TRANSPORT_PATH = LOBBY_PATH + "/transport"
LOBBY_CONTENT_TYPE = "application/octet-stream"
LOBBY_REQUEST = Struct("<BBH16s16s")
ROSTER_HEADER = Struct("<HBB16s")
ROSTER_ROW = Struct("<H16s")
EMPTY_TOKEN = bytes(16)
LOCAL_NAME = re.compile(rb"[A-Za-z0-9_-]{1,16}")
WORLD_COUNT = 50
LOBBY_CAPACITY = 50
LEASE_SECONDS = 15
JOIN, POLL, LEAVE = 1, 2, 3
PEER_REQUEST = Struct("<BBH16sQQ")
PEER_OUTBOUND = Struct("<HHHH")
PEER_INBOUND = Struct("<QHHHH")
ROOM_OUTBOUND = Struct("<QHHHH")
ROOM_INBOUND = Struct("<QQHHHH")
PEER_RESPONSE = Struct("<QHH")
CHANNEL_REQUEST = Struct("<BBH16sQ")
CHANNEL_RESPONSE = Struct("<QBBH")
ROOM_CHANNEL_RESPONSE = Struct("<QBBHQ")
TRANSPORT_REQUEST = Struct("<BBH16sQ")
TRANSPORT_RESPONSE = Struct("<Q16s")
CHANNEL_MASK = 0x0f
# Up to 64 packets each way per exchange (the runtime's GOLF_RUDP_BATCH): with one exchange per
# round trip, 16 capped a 50 ms internet link below the hub's ~450 packets a second.
PACKETS_PER_EXCHANGE = 64
MAX_PACKET_BYTES = (1 << 16) - 1
# One exchange carries at most MAX_EXCHANGE_BYTES of payload each way; an inbox holds several
# exchanges' worth, so a full upload is not refused while the recipient still has unread packets
# (each refusal costs a round trip).
MAX_EXCHANGE_BYTES = 65536
MAX_INBOX_BYTES = 4 * MAX_EXCHANGE_BYTES
MAX_INBOX_PACKETS = 4 * PACKETS_PER_EXCHANGE
PEER_REQUEST_MAX = PEER_REQUEST.size + PACKETS_PER_EXCHANGE * ROOM_OUTBOUND.size + MAX_EXCHANGE_BYTES


@dataclass(frozen=True)
class Packet:
    sequence: int
    sender_id: int
    source_port: int
    destination_port: int
    data: bytes
    sender_generation: int

    def encode(self, scoped: bool) -> bytes:
        packet = (self.sender_id, self.source_port, self.destination_port, len(self.data))
        if scoped:
            return ROOM_INBOUND.pack(self.sequence, self.sender_generation, *packet) + self.data
        return PEER_INBOUND.pack(self.sequence, *packet) + self.data


@dataclass
class Member:
    member_id: int
    name: bytes
    expires: float
    join_nonce: bytes = EMPTY_TOKEN
    inbox: deque[Packet] = field(default_factory=deque)
    inbox_bytes: int = 0
    next_packet: int = 1
    read_ack: int = 0
    read_advertised: int = 0
    upload_seq: int = 0
    upload_digest: bytes = b""
    channels: dict[bytes, tuple[int, int]] = field(default_factory=dict)
    room_id: int = 0
    last_room_create: tuple[int, int, bytes] = (0, 0, b"")
    transport_room: int = 0
    relay_token: bytes = EMPTY_TOKEN
    relay_generation: int = 0

    def enqueue(self, sender: Member, src: int, dst: int, data: bytes):
        self.inbox.append(Packet(self.next_packet, sender.member_id, src, dst, data, sender.relay_generation))
        self.next_packet += 1
        self.inbox_bytes += len(data)

    def discard_sender(self, sender_id: int):
        if self.inbox:
            self.inbox = deque(packet for packet in self.inbox if packet.sender_id != sender_id)
            self.inbox_bytes = sum(len(packet.data) for packet in self.inbox)

    def rotate_transport(self, token: bytes, generation: int):
        self.relay_token = token
        self.relay_generation = generation
        self.transport_room = self.room_id
        self.channels.clear()
        self.inbox.clear()
        self.inbox_bytes = 0
        self.next_packet = 1
        self.read_ack = self.read_advertised = self.upload_seq = 0
        self.upload_digest = b""

    def acknowledge(self, sequence: int):
        while self.inbox and self.inbox[0].sequence <= sequence:
            self.inbox_bytes -= len(self.inbox.popleft().data)
        self.read_ack = sequence


def parse_upload(body: bytes, count: int, scoped: bool) -> list[tuple[int, int, int, bytes, int]] | None:
    offset = PEER_REQUEST.size
    packets = []
    payload_bytes = 0
    layout = ROOM_OUTBOUND if scoped else PEER_OUTBOUND
    for _ in range(count):
        if len(body) - offset < layout.size:
            return None
        values = layout.unpack_from(body, offset)
        destination, source_port, destination_port, size = values[-4:]
        generation = values[0] if scoped else 0
        offset += layout.size
        payload_bytes += size
        if (not destination or not 25000 <= source_port <= 25003 or destination_port != (source_port ^ 1)
                or not 0 < size <= MAX_PACKET_BYTES or payload_bytes > MAX_EXCHANGE_BYTES
                or len(body) - offset < size or (scoped and not generation)):
            return None
        packets.append((destination, source_port, destination_port, body[offset:offset + size], generation))
        offset += size
    return packets if offset == len(body) else None


class LobbyRegistry:
    def __init__(self):
        self.lock = Lock()
        self.rosters = [{} for _ in range(WORLD_COUNT)]
        self.next_ids = [1] * WORLD_COUNT
        self.rooms = [RoomRegistry(world) for world in range(1, WORLD_COUNT + 1)]
        self.relay_generation = 0

    def active_roster(self, index: int, now: float) -> dict[bytes, Member]:
        # Called with the registry lock held.
        roster = self.rosters[index]
        for expired in [key for key, member in roster.items() if member.expires <= now]:
            self.remove_member(index, roster, expired)
        return roster

    def remove_member(self, index: int, roster: dict[bytes, Member], token: bytes):
        self.rooms[index].leave(roster, token)
        member = roster.pop(token)
        self.discard_links(roster, token, member.member_id)
        self.sync_transport(roster)

    @staticmethod
    def discard_links(roster: dict[bytes, Member], token: bytes, member_id: int):
        for peer in roster.values():
            peer.channels.pop(token, None)
            peer.discard_sender(member_id)

    @staticmethod
    def new_token(roster: dict[bytes, Member], join_nonce: bytes = EMPTY_TOKEN) -> bytes:
        used = {member.relay_token for member in roster.values()}
        used.update(member.join_nonce for member in roster.values())
        token = token_bytes(16)
        while token in (EMPTY_TOKEN, join_nonce) or token in roster or token in used:
            token = token_bytes(16)
        return token

    def join(self, index: int, roster: dict[bytes, Member], nonce: bytes,
             name: bytes, now: float) -> bytes | None:
        if nonce != EMPTY_TOKEN:
            for token, member in roster.items():
                if member.join_nonce == nonce:
                    if member.name != name:
                        return None
                    member.expires = now + LEASE_SECONDS
                    return token
        if len(roster) == LOBBY_CAPACITY:
            return None
        token = self.new_token(roster, nonce)
        member_id = self.next_ids[index]
        used = {member.member_id for member in roster.values()}
        while member_id in used:
            member_id = member_id % 65535 + 1
        self.next_ids[index] = member_id % 65535 + 1
        self.relay_generation += 1
        roster[token] = Member(member_id, name, now + LEASE_SECONDS, join_nonce=nonce,
                               relay_token=token, relay_generation=self.relay_generation)
        return token

    def sync_transport(self, roster: dict[bytes, Member]):
        for token, member in roster.items():
            if member.transport_room == member.room_id:
                continue
            self.discard_links(roster, token, member.member_id)
            self.relay_generation += 1
            member.rotate_transport(self.new_token(roster), self.relay_generation)

    @staticmethod
    def relay_owner(roster: dict[bytes, Member], relay: bytes) -> tuple[bytes, Member] | None:
        direct = roster.get(relay)
        if direct is not None and direct.relay_token == relay:
            return relay, direct
        return next(((token, member) for token, member in roster.items() if member.relay_token == relay), None)

    def exchange(self, body: bytes) -> tuple[HTTPStatus, bytes]:
        if len(body) != LOBBY_REQUEST.size:
            return HTTPStatus.BAD_REQUEST, b""
        operation, world, reserved, token, name = LOBBY_REQUEST.unpack(body)
        if reserved or not 1 <= world <= WORLD_COUNT:
            return HTTPStatus.BAD_REQUEST, b""
        if operation == JOIN:
            if not LOCAL_NAME.fullmatch(name.rstrip(b"\0")):
                return HTTPStatus.BAD_REQUEST, b""
        elif operation not in (POLL, LEAVE) or token == EMPTY_TOKEN or name != EMPTY_TOKEN:
            return HTTPStatus.BAD_REQUEST, b""

        index = world - 1
        with self.lock:
            now = monotonic()
            roster = self.active_roster(index, now)

            if operation == JOIN:
                token = self.join(index, roster, token, name, now)
                if token is None:
                    return HTTPStatus.CONFLICT, b""
            else:
                member = roster.get(token)
                if member is None:
                    return HTTPStatus.NOT_FOUND, b""
                if operation == LEAVE:
                    self.remove_member(index, roster, token)
                    return HTTPStatus.OK, ROSTER_HEADER.pack(0, 0, 0, EMPTY_TOKEN)
                member.expires = now + LEASE_SECONDS

            header = ROSTER_HEADER.pack(roster[token].member_id, len(roster), 0, token)
            members = sorted(roster.values(), key=lambda member: member.member_id)
            body = b"".join(ROSTER_ROW.pack(member.member_id, member.name) for member in members)
            return HTTPStatus.OK, header + body

    def exchange_rooms(self, body: bytes) -> tuple[HTTPStatus, bytes]:
        if not ROOM_HEADER.size <= len(body) <= ROOM_REQUEST_MAX:
            return HTTPStatus.BAD_REQUEST, b""
        operation, world, version, token = ROOM_HEADER.unpack_from(body)
        if version not in (0, 1) or not 1 <= world <= WORLD_COUNT or token == EMPTY_TOKEN:
            return HTTPStatus.BAD_REQUEST, b""
        index = world - 1
        with self.lock:
            now = monotonic()
            roster = self.active_roster(index, now)
            if token not in roster:
                return HTTPStatus.NOT_FOUND, b""
            status, response = self.rooms[index].exchange(roster, token, operation, body[ROOM_HEADER.size:], version == 1)
            if status == HTTPStatus.OK:
                self.sync_transport(roster)
                roster[token].expires = now + LEASE_SECONDS
            return status, response

    def exchange_transport(self, body: bytes) -> tuple[HTTPStatus, bytes]:
        if len(body) != TRANSPORT_REQUEST.size:
            return HTTPStatus.BAD_REQUEST, b""
        world, reserved, flags, token, room = TRANSPORT_REQUEST.unpack(body)
        if reserved or flags or not 1 <= world <= WORLD_COUNT or token == EMPTY_TOKEN:
            return HTTPStatus.BAD_REQUEST, b""
        with self.lock:
            now = monotonic()
            roster = self.active_roster(world - 1, now)
            member = roster.get(token)
            if member is None or member.room_id != room:
                return HTTPStatus.NOT_FOUND, b""
            member.expires = now + LEASE_SECONDS
            return HTTPStatus.OK, TRANSPORT_RESPONSE.pack(room, member.relay_token)

    def exchange_room_messages(self, body: bytes) -> tuple[HTTPStatus, bytes]:
        if not ROOM_MESSAGE_REQUEST.size <= len(body) <= ROOM_MESSAGE_REQUEST_MAX:
            return HTTPStatus.BAD_REQUEST, b""
        world, operation, reserved, relay, room_id, cursor = ROOM_MESSAGE_REQUEST.unpack_from(body)
        if reserved or not 1 <= world <= WORLD_COUNT or relay == EMPTY_TOKEN or not room_id:
            return HTTPStatus.BAD_REQUEST, b""
        index = world - 1
        with self.lock:
            now = monotonic()
            roster = self.active_roster(index, now)
            owner = self.relay_owner(roster, relay)
            if owner is None or owner[1].room_id != room_id:
                return HTTPStatus.NOT_FOUND, b""
            token, member = owner
            room = self.rooms[index].rooms[room_id]
            status, reply = room.exchange_messages(roster, token, operation, cursor, body[ROOM_MESSAGE_REQUEST.size:])
            if status == HTTPStatus.OK:
                member.expires = now + LEASE_SECONDS
            return status, reply

    def exchange_channels(self, body: bytes) -> tuple[HTTPStatus, bytes]:
        if len(body) != CHANNEL_REQUEST.size:
            return HTTPStatus.BAD_REQUEST, b""
        world, mask, peer_id, token, revision = CHANNEL_REQUEST.unpack(body)
        if (not 1 <= world <= WORLD_COUNT or mask & ~CHANNEL_MASK or not peer_id
                or token == EMPTY_TOKEN or not revision):
            return HTTPStatus.BAD_REQUEST, b""
        with self.lock:
            now = monotonic()
            roster = self.active_roster(world - 1, now)
            owner = self.relay_owner(roster, token)
            if owner is None:
                return HTTPStatus.NOT_FOUND, b""
            own_token, own = owner
            if peer_id == own.member_id:
                return HTTPStatus.BAD_REQUEST, b""
            peer_token = next((key for key, member in roster.items() if member.member_id == peer_id), None)
            if peer_token is None or roster[peer_token].room_id != own.room_id:
                return HTTPStatus.NOT_FOUND, b""
            peer = roster[peer_token]
            hub = self.signaling_hub(world - 1, roster, own.room_id)
            if hub and hub not in (own.member_id, peer_id):
                return HTTPStatus.NOT_FOUND, b""
            last_revision, last_mask = own.channels.get(peer_token, (0, 0))
            if revision < last_revision or (revision == last_revision and mask != last_mask):
                return HTTPStatus.CONFLICT, b""
            own.channels[peer_token] = (revision, mask)
            own.expires = now + LEASE_SECONDS
            _, peer_mask = peer.channels.get(own_token, (0, 0))
            # Exchange bits 0/1 and 2/3 to match complementary virtual ports.
            paired_mask = ((peer_mask & 0b0101) << 1) | ((peer_mask & 0b1010) >> 1)
            ready = mask & paired_mask
            if own.room_id:
                return HTTPStatus.OK, ROOM_CHANNEL_RESPONSE.pack(revision, ready, 0, peer_id, peer.relay_generation)
            return HTTPStatus.OK, CHANNEL_RESPONSE.pack(revision, ready, 0, peer_id)

    def exchange_packets(self, body: bytes) -> tuple[HTTPStatus, bytes]:
        if not PEER_REQUEST.size <= len(body) <= PEER_REQUEST_MAX:
            return HTTPStatus.BAD_REQUEST, b""
        world, version, count, token, sequence, ack = PEER_REQUEST.unpack_from(body)
        if (version not in (0, 1) or not 1 <= world <= WORLD_COUNT or count > PACKETS_PER_EXCHANGE
                or token == EMPTY_TOKEN or bool(count) != bool(sequence)):
            return HTTPStatus.BAD_REQUEST, b""
        packets = parse_upload(body, count, version == 1)
        if packets is None:
            return HTTPStatus.BAD_REQUEST, b""
        digest = sha256(body[PEER_REQUEST.size:]).digest() if count else b""
        with self.lock:
            now = monotonic()
            roster = self.active_roster(world - 1, now)
            owner = self.relay_owner(roster, token)
            if owner is None:
                return HTTPStatus.NOT_FOUND, b""
            _, sender = owner
            if bool(sender.room_id) != bool(version):
                return HTTPStatus.BAD_REQUEST, b""
            if not sender.read_ack <= ack <= sender.read_advertised:
                return HTTPStatus.CONFLICT, b""

            if count and sequence == sender.upload_seq + 1:
                hub = self.signaling_hub(world - 1, roster, sender.room_id)
                status = self.deliver(roster, sender, packets, hub)
                if status != HTTPStatus.OK:
                    return status, b""
                sender.upload_seq = sequence
                sender.upload_digest = digest
            elif count and (sequence != sender.upload_seq or digest != sender.upload_digest):
                return HTTPStatus.CONFLICT, b""

            sender.acknowledge(ack)
            sender.expires = now + LEASE_SECONDS
            incoming = []
            payload = 0
            for packet in islice(sender.inbox, PACKETS_PER_EXCHANGE):
                payload += len(packet.data)
                if payload > MAX_EXCHANGE_BYTES:
                    break
                incoming.append(packet)
            if incoming:
                sender.read_advertised = max(sender.read_advertised, incoming[-1].sequence)
            return HTTPStatus.OK, (PEER_RESPONSE.pack(sender.upload_seq, len(incoming), 0)
                                   + b"".join(packet.encode(bool(version)) for packet in incoming))

    def signaling_hub(self, index: int, roster: dict[bytes, Member], room_id: int) -> int:
        return self.rooms[index].rooms[room_id].signaling_hub(roster) if room_id else 0

    def deliver(self, roster, sender, packets, hub: int) -> HTTPStatus:
        # Preflight the entire upload before modifying any recipient.
        recipients = {member.member_id: member for member in roster.values()}
        added = {}
        for destination, _, _, data, generation in packets:
            if destination == sender.member_id:
                return HTTPStatus.BAD_REQUEST
            recipient = recipients.get(destination)
            if recipient is None or recipient.room_id != sender.room_id:
                return HTTPStatus.NOT_FOUND
            if hub and hub not in (sender.member_id, destination):
                return HTTPStatus.NOT_FOUND
            if generation and generation != recipient.relay_generation:
                return HTTPStatus.NOT_FOUND
            count, size = added.get(destination, (0, 0))
            count += 1
            size += len(data)
            if (len(recipient.inbox) + count > MAX_INBOX_PACKETS
                    or recipient.inbox_bytes + size > MAX_INBOX_BYTES):
                return HTTPStatus.TOO_MANY_REQUESTS
            added[destination] = count, size
        for destination, src, dst, data, _ in packets:
            recipients[destination].enqueue(sender, src, dst, data)
        return HTTPStatus.OK
