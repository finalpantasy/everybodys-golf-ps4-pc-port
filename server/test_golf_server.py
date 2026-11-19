"""Replay the HTTP request shapes documented in analysis/online/protocol.md."""
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import http.client
import json
from pathlib import Path
from struct import pack, unpack_from
from tempfile import TemporaryDirectory
from threading import Barrier, Thread
import zlib
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from xml.etree import ElementTree

from golf_server import DISCOVERY_PATH, LOOPBACK, MAX_DISCOVERY_BYTES, GolfServer
from make_discovery_fixture import discovery_document

USER_AGENT = "PS4Application nolib/0.0 (U-UP9000-CUSA04687_00-EVERYBODYSGOLF07/2017022700/1170)"


SERVER_TIME_PATH = "/nmg-us/replay-probe/gameapi_getservertime"
LOCAL_LOBBY_PATH = "/nmg-us/local-lobby/v1"
LOCAL_PACKET_PATH = LOCAL_LOBBY_PATH + "/packets"
LOCAL_CHANNEL_PATH = LOCAL_LOBBY_PATH + "/channels"
LOCAL_TRANSPORT_PATH = LOCAL_LOBBY_PATH + "/transport"
LOCAL_ROOM_PATH = LOCAL_LOBBY_PATH + "/rooms"
LOCAL_LOBBY_HEADERS = {"Content-Type": "application/octet-stream"}
SERVER_TIME_HEADERS = {"Content-Type": "multipart/form-data; boundary=xYzZY", "User-Agent": USER_AGENT}
SERVER_TIME_REQUEST = (
    b'--xYzZY\r\nContent-Disposition: form-data; name="p"\r\n\r\n'
    b"\x00\x80\x01\x00\x10\x00\x05\x00CUSA04687_00\0\x03\x03\x03"
    b"\x50\x00\x02\x00\x02\0\0\0\x10\x80\x01\x00\r\n--xYzZY--\r\n"
)
SERVER_TIME = datetime(2026, 11, 17, 23, 18, 42)
EULA_PATH = "/nmg-us/replay-probe/gameapi_geteula"
EULA_TEXT = b"Local terms.\n"
EULA_REQUEST = SERVER_TIME_REQUEST.replace(b"\x10\x80\x01\x00", b"\x50\x10\x02\x00\x03\0\0\0\x10\x80\x01\x00")
EULA_ALTERNATE_REQUEST = EULA_REQUEST.replace(
    b"CUSA04687_00\0\x03\x03\x03", b"NPJA00086_PUB\0\x02\x02"
).replace(b"\x50\x10\x02\x00\x03\0\0\0", b"\x50\x10\x02\x00\0\0\0\0")


NOTICE_PATH = "/nmg-us/replay-probe/gameapi_getinfolist"
NOTICE_FIELDS = (
    b"\x80\x00\x41\x00" + b"\0" * 256
    + b"\x83\x00\x02\x00abc\0"
    + bytes.fromhex("5030020001000000 0040020001000000 104002000a000000")
)
NOTICE_REQUEST = SERVER_TIME_REQUEST.replace(b"\x10\x80\x01\x00", NOTICE_FIELDS + b"\x10\x80\x01\x00")


SCORE_PATH = "/nmg-us/replay-probe/gameapi_getscorelist"
SCORE_INNER = bytes(range(8))
SCORE_FIELDS = (
    b"\x20\x00\x03\x00Golfer\0\x01"
    + b"\x60\x00\x03\x00" + bytes(range(8))
    + b"\x40\x41\x07\x00Daily_20261118_00_score\0"
    + bytes.fromhex("0040020001000000 10400200e8030000")
)
SCORE_REQUEST = SERVER_TIME_REQUEST.replace(b"\x10\x80\x01\x00", SCORE_FIELDS + b"\x10\x80\x01\x00")
BOARD_PATH = "/nmg-us/replay-probe/gameapi_getboardlist"
BOARD_FIELDS = (
    b"\x20\x00\x03\x00Golfer\0\x01"
    + b"\x60\x00\x03\x00" + bytes(range(8))
    + bytes.fromhex("0040020001000000 1040020002000000")
)
BOARD_REQUEST = SERVER_TIME_REQUEST.replace(b"\x10\x80\x01\x00", BOARD_FIELDS + b"\x10\x80\x01\x00")


NATIONAL_BOARD_PATH = "/nmg-us/replay-probe/gameapi_getboardlistnational"
NATIONAL_BOARD_FIELDS = NOTICE_FIELDS[:268] + bytes.fromhex("404a020000000000")
NATIONAL_BOARD_REQUEST = SERVER_TIME_REQUEST.replace(
    b"\x10\x80\x01\x00", NATIONAL_BOARD_FIELDS + b"\x10\x80\x01\x00"
)
NATIONAL_GAME_DATA_PATH = "/nmg-us/replay-probe/gameapi_getnationalgamedata"
NATIONAL_OWN_SCORE_PATH = "/nmg-us/replay-probe/gameapi_getmyscorenational"
DOWNLOAD_BASE = "/nmg-us/replay-probe/gamedata-down"
NATIONAL_GAME_DATA_REQUEST = SERVER_TIME_REQUEST.replace(
    b"\x10\x80\x01\x00",
    NOTICE_FIELDS[:268] + bytes.fromhex("40410500") + b"LocalTournament\0"
    + bytes.fromhex("4741020001000000 f641020000000000 10800100")
)

OWN_SCORE_PATH = "/nmg-us/replay-probe/gameapi_getmyscore"
TOP_PLAYER_PATH = "/nmg-us/replay-probe/gameapi_gettopplayerlist"
SCORE_DISTRIBUTION_PATH = "/nmg-us/replay-probe/gameapi_getscoredistribution"
SCORE_BOARD_PREFIX = SCORE_PATH + "?account="
SCORE_BOARD_TARGET = SCORE_BOARD_PREFIX + "5932163534510096385&n=1&s=1"
USER_STATUS_PATH = "/nmg-us/replay-probe/gameapi_getuserstatus"
USER_STATUS_SESSION = bytes.fromhex("86002100") + bytes(128) + bytes.fromhex("8700020000000000 8800020000000000")
USER_STATUS_REQUEST = SERVER_TIME_REQUEST.replace(
    bytes.fromhex("10800100"), NOTICE_FIELDS[:268] + USER_STATUS_SESSION + bytes.fromhex("0025020000000000 10800100")
)


def string_record(kind: int, value: bytes) -> bytes:
    padding = (-(len(value) + 1)) % 4
    payload = value + b"\0" + bytes([padding]) * padding
    return pack("<2H", kind, 1 + len(payload) // 4) + payload


def own_score_request(selector: int, group: bytes, token: bytes = b"abc") -> bytes:
    fields = (bytes.fromhex("80004100") + bytes(256) + string_record(0x0083, token)
              + pack("<2HI", 0x4A00, 2, selector) + string_record(0x4140, group))
    return SERVER_TIME_REQUEST.replace(b"\x10\x80\x01\x00", fields + b"\x10\x80\x01\x00")


def score_board_request(selector: int, group: bytes, limit: int, token: bytes = b"abc") -> bytes:
    tail = pack("<2HI2HI", 0x4000, 2, 1, 0x4010, 2, limit) + bytes.fromhex("10800100")
    return own_score_request(selector, group, token).replace(bytes.fromhex("10800100"), tail)


def top_player_request(token: bytes) -> bytes:
    records = bytes.fromhex("004a020000000000 304a020020180914 104a020000000000 "
                            "204a020001000000 1040020009000000")
    end = bytes.fromhex("10800100")
    return SERVER_TIME_REQUEST.replace(end, NOTICE_FIELDS[:260] + string_record(0x0083, token) + records + end)


def schedule_request(selector: int, token: bytes = b"abc", *, course: int = 0, limit: int = 18) -> bytes:
    records = pack("<2HI2HI2HI", 0x4A00, 2, selector, 0x4A40, 2, 0, 0x4A50, 2, 2)
    if course:
        records += pack("<2HI2HI2HI", 0x4A10, 2, course, 0x4000, 2, 1, 0x4010, 2, limit)
    return SERVER_TIME_REQUEST.replace(bytes.fromhex("10800100"),
                                       NOTICE_FIELDS[:260] + string_record(0x0083, token)
                                       + records + bytes.fromhex("10800100"))


RIVAL_LIST_PATH = "/nmg-us/replay-probe/gameapi_getrivallist"


def rival_request(group: bytes, token: bytes = b"local", detail: bytes = b"") -> bytes:
    tail = bytes.fromhex("10800100") + b"\r\n--xYzZY--\r\n"
    fields = (bytes.fromhex("80004100") + bytes(256) + string_record(0x0083, token)
              + bytes.fromhex("004a020001000000") + string_record(0x4140, group)
              + bytes.fromhex("414103000102030405060708") + string_record(0x4142, detail)
              + bytes.fromhex("4341020002000000 4441020003000000"))
    return SERVER_TIME_REQUEST.removesuffix(tail) + fields + tail


REGISTER_OPERATIONS = (
    "gameapi_registscore", "gameapi_registscoredaily", "gameapi_registscorelongdrivecontest",
)
REGISTER_GROUPS = (b"OneHole_20261118_0_1", b"Daily_20261118_0_IN", b"LongDriveContest_20261118_0_1")
REGISTER_TARGETS = tuple(
    f"/nmg-us/replay-probe/{op}?account=5932163534510096385&n=1&s=1" for op in REGISTER_OPERATIONS
)


def registration_request(selector: int, score: int, *, group: bytes | None = None, token: bytes = b"abc",
                         name_stamp: bytes = b"Golfer@2026-11-18T10:00:00+09:00",
                         description: bytes = b"local fixture", detail: bytes = b"0") -> bytes:
    fields = (pack("<2HQ", 0x4141, 3, 0) + string_record(0x4142, description)
              + pack("<2HI2HI", 0x4143, 2, 0, 0x4144, 2, 0)
              + string_record(0x42B0, name_stamp)
              + pack("<2Hq", 0x4500, 3, score))
    if selector < 2:
        fields += pack("<2Hq", 0x4501, 3, 21)
    for index in range(11 if selector == 2 else 14):
        fields += string_record(0x4600 + index, detail)
    return own_score_request(selector, group or REGISTER_GROUPS[selector], token).replace(
        bytes.fromhex("10800100"), fields + bytes.fromhex("10800100")
    )


LOGIN_ACCOUNT = b"5932163534510096385"
LOGIN_TARGET = "/nmg-us/replay-probe/gameapi_login?account=5932163534510096385&n=1&s=1"
LOGIN_FIELDS = (
    b"\x20\x00\x03\x00Golfer\0\x01"
    + b"\x84\x00\x06\x00" + LOGIN_ACCOUNT + b"\0"
    + bytes.fromhex("700003000000000000000202 71000500") + b"\0" * 16
    + b"\x85\x00\x05\x00GolfLocalProbe\0\x01"
    + bytes.fromhex("3220020000000000")
)
LOGIN_REQUEST = SERVER_TIME_REQUEST.replace(b"\x10\x80\x01\x00", LOGIN_FIELDS+b"\x10\x80\x01\x00")
PROPERTY_PATH = "/nmg-us/replay-probe/gameapi_getgamepropertyinfo"
PROPERTY_FIELDS = bytes.fromhex("0476020001000000 0576020000000000")
PROPERTY_REQUEST = SERVER_TIME_REQUEST.replace(b"\x10\x80\x01\x00", PROPERTY_FIELDS + b"\x10\x80\x01\x00")
TELEMETRY_PATH = "/nmg-us/replay-probe/analytics/19d916d7-6a01-4371-9e6c-c91b2ff386bb/telemetry"
TELEMETRY_HEADERS = {"Content-Type": "application/json"}
TELEMETRY_REQUEST = b'{"count":    1,"events":[{"event":"local probe"}]}'


class GolfServerTests(unittest.TestCase):
    def start(self, fixture=None, **options):
        with patch("socket.getfqdn", side_effect=AssertionError("unexpected host lookup")):
            server = GolfServer(0, fixture, **options)
        worker = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 3)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.assertEqual(server.server_address[0], "127.0.0.1")
        client = http.client.HTTPConnection(LOOPBACK, server.server_port, timeout=3)
        self.addCleanup(client.close)
        return client

    def lobby_exchange(self, client, operation, world, token=bytes(16), name=b"", expected=200):
        request = pack("<BBH16s16s", operation, world, 0, token, name)
        client.request("POST", LOCAL_LOBBY_PATH, body=request, headers=LOCAL_LOBBY_HEADERS)
        response = client.getresponse()
        body = response.read()
        self.assertEqual(response.status, expected)
        if expected != 200:
            self.assertEqual(body, b"")
            return None
        if operation == 3:
            self.assertEqual(body, bytes(20))
            return None
        own_id, count, reserved, session = unpack_from("<HBB16s", body)
        self.assertEqual(reserved, 0)
        self.assertNotEqual(session, bytes(16))
        self.assertEqual(len(body), 20 + count * 18)
        roster = []
        for i in range(count):
            member_id, padded_name = unpack_from("<H16s", body, 20 + i * 18)
            roster.append((member_id, padded_name.rstrip(b"\0")))
        return own_id, session, roster

    def test_local_lobby_two_clients_converge_and_leave(self):
        first = self.start(local_lobbies=True)
        second = http.client.HTTPConnection(LOOPBACK, first.port, timeout=3)
        self.addCleanup(second.close)
        first_id, first_token, first_view = self.lobby_exchange(first, 1, 7, name=b"Golfer")
        second_id, second_token, second_view = self.lobby_exchange(second, 1, 7, name=b"Golfer")
        self.assertEqual(first_view, [(first_id, b"Golfer")])
        self.assertNotEqual(first_token, second_token)
        self.assertNotEqual(first_id, second_id)
        self.assertEqual(second_view, [(first_id, b"Golfer"), (second_id, b"Golfer")])
        self.assertEqual(self.lobby_exchange(first, 2, 7, first_token), (first_id, first_token, second_view))
        self.lobby_exchange(second, 2, 8, second_token, expected=404)
        third_id, _, third_view = self.lobby_exchange(second, 1, 8, name=b"Local")
        self.assertEqual(third_view, [(third_id, b"Local")])
        self.lobby_exchange(second, 3, 7, second_token)
        self.lobby_exchange(second, 2, 7, second_token, expected=404)
        self.assertEqual(self.lobby_exchange(first, 2, 7, first_token), (first_id, first_token, first_view))
        new_id, _, _ = self.lobby_exchange(second, 1, 7, name=b"NewGolfer")
        self.assertNotIn(new_id, (first_id, second_id))

    def test_local_lobby_lease_expiry_and_capacity(self):
        with patch("lobby_registry.monotonic", return_value=10) as now:
            client = self.start(local_lobbies=True)
            sessions = [self.lobby_exchange(client, 1, 5, name=b"Golfer") for _ in range(50)]
            self.assertEqual(len(sessions[-1][2]), 50)
            self.lobby_exchange(client, 1, 5, name=b"Overflow", expected=409)
            now.return_value = 20
            self.lobby_exchange(client, 2, 5, sessions[0][1])
            now.return_value = 26
            self.lobby_exchange(client, 2, 5, sessions[1][1], expected=404)
            own_id, _, roster = self.lobby_exchange(client, 1, 5, name=b"AfterExpiry")
            self.assertEqual(roster, [(sessions[0][0], b"Golfer"), (own_id, b"AfterExpiry")])

    def test_local_lobby_join_retry_reuses_only_its_own_live_lease(self):
        client = self.start(local_lobbies=True)
        retry = http.client.HTTPConnection(LOOPBACK, client.port, timeout=3)
        self.addCleanup(retry.close)
        nonce = b"join-attempt-one"
        other_nonce = b"join-attempt-two"
        self.assertEqual(len(nonce), 16)
        self.assertEqual(len(other_nonce), 16)

        with patch("lobby_registry.monotonic", return_value=10) as now:
            barrier = Barrier(2)

            def join(connection):
                barrier.wait(timeout=3)
                return self.lobby_exchange(connection, 1, 5, nonce, name=b"Golfer")

            with ThreadPoolExecutor(max_workers=2) as pool:
                first, repeated = tuple(pool.map(join, (client, retry)))
            member, session, roster = first
            self.assertEqual(repeated, first)
            self.assertEqual(roster, [(member, b"Golfer")])
            self.assertNotEqual(session, nonce)
            self.lobby_exchange(client, 1, 5, nonce, name=b"BadName", expected=409)
            self.lobby_exchange(client, 2, 5, nonce, expected=404)

            member2, session2, roster2 = self.lobby_exchange(retry, 1, 5, other_nonce, name=b"Golfer")
            self.assertNotEqual(member2, member)
            self.assertNotEqual(session2, session)
            self.assertEqual(roster2, [(member, b"Golfer"), (member2, b"Golfer")])
            for _ in range(48):
                self.lobby_exchange(client, 1, 5, name=b"Filler")
            self.lobby_exchange(client, 1, 5, name=b"Overflow", expected=409)

            now.return_value = 20
            repeated = self.lobby_exchange(client, 1, 5, nonce, name=b"Golfer")
            self.assertEqual(repeated[:2], (member, session))
            self.assertEqual(len(repeated[2]), 50)
            now.return_value = 26
            self.lobby_exchange(retry, 2, 5, session2, expected=404)
            self.lobby_exchange(client, 3, 5, session)
            new_member, new_session, new_roster = self.lobby_exchange(client, 1, 5, nonce, name=b"Golfer")
            self.assertNotEqual((new_member, new_session), (member, session))
            self.assertEqual(new_roster, [(new_member, b"Golfer")])

    def test_local_lobby_rejects_bad_frames_and_stays_opt_in(self):
        client = self.start(local_lobbies=True)
        valid = pack("<BBH16s16s", 1, 7, 0, bytes(16), b"Golfer")
        cases = [
            (valid[:-1], LOCAL_LOBBY_HEADERS, 400),
            (valid[:2] + b"\x01" + valid[3:], LOCAL_LOBBY_HEADERS, 400),
            (valid[:1] + b"\0" + valid[2:], LOCAL_LOBBY_HEADERS, 400),
            (valid[:20] + b"Bad\0name".ljust(16, b"\0"), LOCAL_LOBBY_HEADERS, 400),
            (valid, {"Content-Type": "application/json"}, 415),
        ]
        for body, headers, status in cases:
            client.request("POST", LOCAL_LOBBY_PATH, body=body, headers=headers)
            response = client.getresponse()
            self.assertEqual((response.status, response.read()), (status, b""))
        client.request("GET", LOCAL_LOBBY_PATH)
        response = client.getresponse()
        self.assertEqual((response.status, response.getheader("Allow"), response.read()), (405, "POST", b""))
        self.lobby_exchange(self.start(), 1, 7, name=b"Golfer", expected=404)

    def lobby_packets(self, client, world, token, sequence=0, ack=0, packets=(), expected=200, scoped=False):
        request = pack("<BBH16sQQ", world, scoped, len(packets), token, sequence, ack)
        if scoped:
            request += b"".join(pack("<QHHHH", generation, to, src, dst, len(data)) + data
                                for to, src, dst, data, generation in packets)
        else:
            request += b"".join(pack("<HHHH", to, src, dst, len(data)) + data for to, src, dst, data in packets)
        client.request("POST", LOCAL_PACKET_PATH, body=request, headers=LOCAL_LOBBY_HEADERS)
        response = client.getresponse()
        body = response.read()
        self.assertEqual(response.status, expected)
        if expected != 200:
            self.assertEqual(body, b"")
            return None
        outbound_ack, count, reserved = unpack_from("<QHH", body)
        self.assertEqual(reserved, 0)
        received, offset = [], 12
        for _ in range(count):
            if scoped:
                incoming_seq, generation, sender, src, dst, size = unpack_from("<QQHHHH", body, offset)
                offset += 24
                received.append((incoming_seq, sender, src, dst, body[offset:offset + size], generation))
            else:
                incoming_seq, sender, src, dst, size = unpack_from("<QHHHH", body, offset)
                offset += 16
                received.append((incoming_seq, sender, src, dst, body[offset:offset + size]))
            offset += size
        self.assertEqual(len(body), offset)
        return outbound_ack, received

    def test_local_peer_packets_preserve_order_and_survive_retries(self):
        first = self.start(local_lobbies=True)
        second = http.client.HTTPConnection(LOOPBACK, first.port, timeout=3)
        self.addCleanup(second.close)
        sender, tx, _ = self.lobby_exchange(first, 1, 7, name=b"Alpha")
        receiver, rx, _ = self.lobby_exchange(second, 1, 7, name=b"Beta")
        outbound = [(receiver, 25000, 25001, b"\xfd"), (receiver, 25002, 25003, b"\xfe\x00\x01")]
        # Repeat a request whose response was lost.
        self.assertEqual(self.lobby_packets(first, 7, tx, sequence=1, packets=outbound), (1, []))
        self.assertEqual(self.lobby_packets(first, 7, tx, sequence=1, packets=outbound), (1, []))
        incoming = [(i, sender, src, dst, data) for i, (_, src, dst, data) in enumerate(outbound, 1)]
        self.assertEqual(self.lobby_packets(second, 7, rx), (0, incoming))
        self.assertEqual(self.lobby_packets(second, 7, rx), (0, incoming))
        returning = [(sender, 25001, 25000, b"reply")]
        self.assertEqual(self.lobby_packets(second, 7, rx, sequence=1, ack=2, packets=returning), (1, []))
        self.assertEqual(self.lobby_packets(first, 7, tx), (1, [(1, receiver, 25001, 25000, b"reply")]))
        self.assertEqual(self.lobby_packets(first, 7, tx, ack=1), (1, []))
        self.assertEqual(self.lobby_packets(second, 7, rx, ack=2), (1, []))

    def test_local_peer_packets_validate_peers_ports_and_acknowledgements(self):
        client = self.start(local_lobbies=True)
        _, tx, _ = self.lobby_exchange(client, 1, 7, name=b"Sender")
        peer, rx, _ = self.lobby_exchange(client, 1, 7, name=b"Peer")
        self.lobby_exchange(client, 1, 8, name=b"OtherWorld")
        valid = (peer, 25000, 25001, b"valid")
        self.lobby_packets(client, 8, tx, expected=404)
        self.lobby_packets(client, 7, tx, sequence=1, packets=[(peer, 25000, 25003, b"bad")], expected=400)
        self.lobby_packets(client, 7, tx, ack=1, expected=409)
        self.lobby_packets(client, 7, tx, sequence=2, packets=[valid], expected=409)
        self.lobby_packets(client, 7, tx, sequence=1,
                           packets=[valid, (peer + 10, 25000, 25001, b"absent")], expected=404)
        self.assertEqual(self.lobby_packets(client, 7, rx), (0, []))
        self.assertEqual(self.lobby_packets(client, 7, tx, sequence=1, packets=[valid]), (1, []))
        self.lobby_packets(client, 7, tx, sequence=1, packets=[(peer, 25000, 25001, b"changed")], expected=409)

    def test_local_peer_packets_retry_after_queue_backpressure(self):
        client = self.start(local_lobbies=True)
        _, tx, _ = self.lobby_exchange(client, 1, 7, name=b"Sender")
        peer, rx, _ = self.lobby_exchange(client, 1, 7, name=b"Peer")
        batch = [(peer, 25000, 25001, bytes(4096))] * 16
        self.lobby_packets(client, 7, tx, sequence=1, packets=batch)
        self.lobby_packets(client, 7, tx, sequence=2, packets=[batch[0]], expected=429)
        _, received = self.lobby_packets(client, 7, rx)
        self.assertEqual(len(received), 16)
        self.assertEqual(received[-1][0], 16)
        self.assertEqual(self.lobby_packets(client, 7, rx, ack=16), (0, []))
        self.assertEqual(self.lobby_packets(client, 7, tx, sequence=2, packets=[batch[0]]), (2, []))
        _, received = self.lobby_packets(client, 7, rx, ack=16)
        self.assertEqual([row[0] for row in received], [17])

    def test_local_peer_packets_use_the_full_wire_payload_width(self):
        client = self.start(local_lobbies=True)
        sender, tx, _ = self.lobby_exchange(client, 1, 7, name=b"Sender")
        peer, rx, _ = self.lobby_exchange(client, 1, 7, name=b"Peer")
        data = bytes(range(256)) * 255 + bytes(range(255))
        self.assertEqual(len(data), 65535)
        over_budget = [(peer, 25000, 25001, data), (peer, 25002, 25003, b"XX")]
        self.lobby_packets(client, 7, tx, sequence=1, packets=over_budget, expected=400)
        packets = [(peer, 25000, 25001, data), (peer, 25002, 25003, b"X")]
        self.assertEqual(self.lobby_packets(client, 7, tx, sequence=1, packets=packets), (1, []))
        self.assertEqual(self.lobby_packets(client, 7, tx, sequence=1, packets=packets), (1, []))
        self.lobby_packets(client, 7, tx, sequence=2, packets=[packets[1]], expected=429)
        self.assertEqual(self.lobby_packets(client, 7, rx),
                         (0, [(1, sender, 25000, 25001, data), (2, sender, 25002, 25003, b"X")]))
        self.assertEqual(self.lobby_packets(client, 7, rx, ack=2), (0, []))
        self.assertEqual(self.lobby_packets(client, 7, tx, sequence=2, packets=[packets[1]]), (2, []))

    def lobby_channels(self, client, world, token, peer, revision, mask, expected=200, scoped=False):
        request = pack("<BBH16sQ", world, mask, peer, token, revision)
        client.request("POST", LOCAL_CHANNEL_PATH, body=request, headers=LOCAL_LOBBY_HEADERS)
        response = client.getresponse()
        body = response.read()
        self.assertEqual(response.status, expected)
        if expected != 200:
            self.assertEqual(body, b"")
            return None
        self.assertEqual(len(body), 20 if scoped else 12)
        echoed_revision, ready, reserved, recipient = unpack_from("<QBBH", body)
        self.assertEqual((echoed_revision, reserved, recipient), (revision, 0, peer))
        return (ready, unpack_from("<Q", body, 12)[0]) if scoped else ready

    def test_local_channels_require_reciprocal_ports_and_reject_stale_updates(self):
        first = self.start(local_lobbies=True)
        second = http.client.HTTPConnection(LOOPBACK, first.port, timeout=3)
        self.addCleanup(second.close)
        alpha, tx, _ = self.lobby_exchange(first, 1, 7, name=b"Alpha")
        beta, rx, _ = self.lobby_exchange(second, 1, 7, name=b"Beta")
        self.assertEqual(self.lobby_channels(first, 7, tx, beta, 1, 0b1111), 0)
        self.assertEqual(self.lobby_channels(second, 7, rx, alpha, 1, 0b1001), 0b1001)
        self.assertEqual(self.lobby_channels(first, 7, tx, beta, 1, 0b1111), 0b0110)
        self.lobby_channels(first, 7, tx, beta, 1, 1, expected=409)
        self.assertEqual(self.lobby_channels(second, 7, rx, alpha, 2, 0), 0)
        self.lobby_channels(second, 7, rx, alpha, 1, 0b1001, expected=409)
        self.assertEqual(self.lobby_channels(first, 7, tx, beta, 1, 0b1111), 0)

    def test_local_channels_expire_with_recipient_and_stay_opt_in(self):
        with patch("lobby_registry.monotonic", return_value=10) as now:
            client = self.start(local_lobbies=True)
            alpha, tx, _ = self.lobby_exchange(client, 1, 7, name=b"Alpha")
            beta, rx, _ = self.lobby_exchange(client, 1, 7, name=b"Beta")
            self.lobby_exchange(client, 1, 8, name=b"OtherWorld")
            self.lobby_channels(client, 8, tx, beta, 1, 15, expected=404)
            self.lobby_channels(client, 7, tx, alpha, 1, 15, expected=400)
            self.lobby_channels(client, 7, tx, beta, 0, 15, expected=400)
            self.lobby_channels(client, 7, tx, beta, 1, 16, expected=400)
            self.lobby_channels(client, 7, tx, beta, 1, 15)
            self.assertEqual(self.lobby_channels(client, 7, rx, alpha, 1, 15), 15)
            now.return_value = 20
            self.assertEqual(self.lobby_channels(client, 7, tx, beta, 1, 15), 15)
            now.return_value = 26
            self.lobby_channels(client, 7, tx, beta, 1, 15, expected=404)
            self.lobby_channels(client, 7, rx, alpha, 1, 15, expected=404)
            replacement, replacement_token, _ = self.lobby_exchange(client, 1, 7, name=b"Replacement")
            self.assertEqual(self.lobby_channels(client, 7, replacement_token, alpha, 1, 15), 0)
            self.assertEqual(self.lobby_channels(client, 7, tx, replacement, 1, 15), 15)
            self.lobby_channels(self.start(), 7, tx, beta, 1, 15, expected=404)

    def lobby_rooms(self, client, operation, world, token, payload=b"", expected=200, *, version=0):
        request = pack("<BBH16s", operation, world, version, token) + payload
        client.request("POST", LOCAL_ROOM_PATH, body=request, headers=LOCAL_LOBBY_HEADERS)
        response = client.getresponse()
        body = response.read()
        self.assertEqual(response.status, expected)
        if expected != 200:
            self.assertEqual(body, b"")
        return body

    def room_create_payload(self, nonce, capacity=2, flags=0x84000000, tag=b"Golf", listing=b"Course"):
        return (pack("<QHIBHH", nonce, capacity, flags, 1, len(tag), len(listing))
                + pack("<HI", 0x4c, 12) + tag + listing)

    def room_view(self, body):
        room_id, revision, flags, capacity, count, owner, own, size = unpack_from("<QQIHHHHH", body)
        members = []
        offset = 30
        for _ in range(count):
            member_id, name = unpack_from("<H16s", body, offset)
            members.append((member_id, name.rstrip(b"\0")))
            offset += 18
        self.assertEqual(len(body), offset + size)
        return room_id, revision, flags, capacity, owner, own, members, body[offset:]

    def room_search(self, client, world, token, start=1, limit=20, flags=0x74000000, value=0,
                    course=12, tag=b"Golf"):
        request = pack("<IIIIBBH", start, limit, flags, value, 1, int(bool(tag)), len(tag))
        request += pack("<HBBI", 0x4c, 1, 0, course) + tag
        body = self.lobby_rooms(client, 5, world, token, request)
        returned_start, total, count = unpack_from("<III", body)
        self.assertEqual(returned_start, start)
        rows = []
        offset = 12
        for _ in range(count):
            rid, revision, flags, capacity, members, owner, size, name = unpack_from("<QQIHHHH16s", body, offset)
            offset += 44
            rows.append((rid, revision, flags, capacity, members, owner, name.rstrip(b"\0"), body[offset:offset + size]))
            offset += size
        self.assertEqual(len(body), offset)
        return total, rows

    def test_local_room_create_search_join_and_owner_transfer(self):
        client = self.start(local_lobbies=True)
        a, alpha, _ = self.lobby_exchange(client, 1, 7, name=b"Alpha")
        b, beta, _ = self.lobby_exchange(client, 1, 7, name=b"Beta")
        _, gamma, _ = self.lobby_exchange(client, 1, 7, name=b"Gamma")
        created = self.lobby_rooms(client, 1, 7, alpha, self.room_create_payload(1))
        rid, revision, flags, capacity, owner, own, members, listing = self.room_view(created)
        self.assertEqual((revision, flags, capacity, owner, own, members, listing),
                         (1, 0x84000000, 2, a, a, [(a, b"Alpha")], b"Course"))
        self.assertEqual(self.lobby_rooms(client, 1, 7, alpha, self.room_create_payload(1)), created)
        self.lobby_rooms(client, 1, 7, alpha, self.room_create_payload(1, listing=b"Changed"), expected=409)
        self.assertEqual(self.room_search(client, 7, beta),
                         (1, [(rid, 1, flags, 2, 1, a, b"Alpha", b"Course")]))
        self.assertEqual(self.room_search(client, 7, beta, start=2), (1, []))
        self.assertEqual(self.room_search(client, 7, beta, course=11), (0, []))
        self.assertEqual(self.room_search(client, 7, beta, tag=b"Other"), (0, []))
        key = pack("<Q", rid)
        joined = self.lobby_rooms(client, 2, 7, beta, key)
        self.assertEqual(self.room_view(joined),
                         (rid, 2, flags | 0x20000000, 2, a, b, [(a, b"Alpha"), (b, b"Beta")], b"Course"))
        self.assertEqual(self.lobby_rooms(client, 2, 7, beta, key), joined)
        self.assertEqual(self.room_search(client, 7, gamma), (0, []))
        self.lobby_rooms(client, 2, 7, gamma, key, expected=409)
        self.lobby_rooms(client, 4, 7, alpha, key)
        self.lobby_rooms(client, 3, 7, alpha, key, expected=404)
        self.assertEqual(self.room_view(self.lobby_rooms(client, 3, 7, beta, key)),
                         (rid, 3, flags, 2, b, b, [(b, b"Beta")], b"Course"))
        self.lobby_rooms(client, 1, 7, alpha, self.room_create_payload(1), expected=409)
        self.lobby_rooms(client, 1, 7, alpha, self.room_create_payload(2, listing=b"x" * 257), expected=400)
        boundary = self.lobby_rooms(client, 1, 7, alpha, self.room_create_payload(2, listing=b"x" * 256))
        self.assertEqual(self.room_view(boundary)[-1], b"x" * 256)

    def test_local_room_world_expiry_and_owner_update(self):
        with patch("lobby_registry.monotonic", return_value=10) as now:
            client = self.start(local_lobbies=True)
            _, alpha, _ = self.lobby_exchange(client, 1, 7, name=b"Alpha")
            beta_id, beta, _ = self.lobby_exchange(client, 1, 7, name=b"Beta")
            _, elsewhere, _ = self.lobby_exchange(client, 1, 8, name=b"Elsewhere")
            room = self.room_view(self.lobby_rooms(client, 1, 7, alpha, self.room_create_payload(1, 3)))
            rid = room[0]
            key = pack("<Q", rid)
            self.assertEqual(self.room_search(client, 8, elsewhere), (0, []))
            self.lobby_rooms(client, 2, 8, elsewhere, key, expected=404)
            self.lobby_rooms(client, 2, 7, beta, key)
            change = pack("<QIIH", rid, 0x40000000, 0x40000000, 3) + b"New"
            self.lobby_rooms(client, 7, 7, beta, change, expected=403)
            self.assertEqual(self.room_view(self.lobby_rooms(client, 7, 7, alpha, change))[-1], b"New")
            self.assertEqual(self.room_search(client, 7, beta), (0, []))
            external = self.lobby_rooms(client, 6, 7, beta, key)
            self.assertEqual(unpack_from("<III", external), (1, 1, 1))
            self.assertTrue(external.endswith(b"New"))
            now.return_value = 20
            self.lobby_rooms(client, 3, 7, beta, key)
            now.return_value = 26
            remaining = self.room_view(self.lobby_rooms(client, 3, 7, beta, key))
            self.assertEqual((remaining[4], remaining[6]), (beta_id, [(beta_id, b"Beta")]))
            self.lobby_exchange(client, 3, 7, beta)
            _, observer, _ = self.lobby_exchange(client, 1, 7, name=b"Observer")
            self.lobby_rooms(client, 6, 7, observer, key, expected=404)
            self.lobby_rooms(self.start(), 6, 7, observer, key, expected=404)

    def test_room_updates_keep_the_search_listing_and_internal_attribute_separate(self):
        client = self.start(local_lobbies=True)
        _, owner, _ = self.lobby_exchange(client, 1, 7, name=b"Owner")
        _, member, _ = self.lobby_exchange(client, 1, 7, name=b"Member")
        _, late, _ = self.lobby_exchange(client, 1, 7, name=b"Late")

        def extended_view(body):
            count, size = unpack_from("<H4xH", body, 22)
            end = 30 + count * 18 + size
            signaling, reserved, hub, internal_size = unpack_from("<BBHH", body, end)
            self.assertEqual((signaling, reserved, hub), (1, 0, 0))
            self.assertEqual(len(body), end + 6 + internal_size)
            return self.room_view(body[:end]), body[end + 6:]

        created, internal = extended_view(self.lobby_rooms(
            client, 1, 7, owner, self.room_create_payload(1, capacity=3) + bytes.fromhex("01000000"),
            version=1,
        ))
        self.assertEqual(internal, b"Course")
        key = pack("<Q", created[0])
        self.lobby_rooms(client, 2, 7, member, key)
        listing = key + pack("<IIH", 0, 0, 6) + b"Public"
        public, internal = extended_view(self.lobby_rooms(client, 7, 7, owner, listing, version=1))
        self.assertEqual((public[-1], internal), (b"Public", b"Course"))
        update = key + pack("<IIH", 0xd4000000, 0xd4000000, 224) + b"x" * 224
        self.lobby_rooms(client, 8, 7, member, update, expected=403, version=1)
        private, internal = extended_view(self.lobby_rooms(client, 8, 7, owner, update, version=1))
        self.assertEqual((private[1], private[2], private[-1], internal),
                         (public[1] + 1, 0xd4000000, b"Public", b"x" * 224))
        self.assertEqual(extended_view(self.lobby_rooms(client, 8, 7, owner, update, version=1)),
                         (private, internal))
        self.assertEqual(extended_view(self.lobby_rooms(client, 3, 7, member, key, version=1))[1], internal)
        self.assertEqual(self.room_view(self.lobby_rooms(client, 3, 7, member, key)[:-4])[-1], b"Public")
        self.assertTrue(self.lobby_rooms(client, 6, 7, late, key).endswith(b"Public"))
        self.lobby_rooms(client, 2, 7, late, key, expected=409, version=1)
        reopen = key + pack("<IIH", 0x50000000, 0, 224) + b"x" * 224
        self.lobby_rooms(client, 8, 7, owner, reopen, version=1)
        joined, internal = extended_view(self.lobby_rooms(client, 2, 7, late, key, version=1))
        self.assertEqual((joined[-1], internal), (b"Public", b"x" * 224))
        self.lobby_rooms(client, 8, 7, owner, update, expected=400)
        self.lobby_rooms(client, 3, 7, owner, key, expected=400, version=2)

    def test_local_room_concurrent_join_never_overbooks_the_last_slot(self):
        client = self.start(local_lobbies=True)
        _, alpha, _ = self.lobby_exchange(client, 1, 7, name=b"Alpha")
        _, beta, _ = self.lobby_exchange(client, 1, 7, name=b"Beta")
        _, gamma, _ = self.lobby_exchange(client, 1, 7, name=b"Gamma")
        room = self.room_view(self.lobby_rooms(client, 1, 7, alpha, self.room_create_payload(1, flags=0)))
        key = pack("<Q", room[0])
        ready = Barrier(2, timeout=3)

        def try_join(token):
            with closing(http.client.HTTPConnection(LOOPBACK, client.port, timeout=3)) as peer:
                ready.wait()
                request = pack("<BBH16s", 2, 7, 0, token) + key
                peer.request("POST", LOCAL_ROOM_PATH, body=request, headers=LOCAL_LOBBY_HEADERS)
                reply = peer.getresponse()
                return reply.status, reply.read()

        with ThreadPoolExecutor(2) as workers:
            attempts = list(workers.map(try_join, (beta, gamma)))
        self.assertEqual(sorted(status for status, _ in attempts), [200, 409])
        winner = beta if attempts[0][0] == 200 else gamma
        self.assertEqual(len(self.room_view(self.lobby_rooms(client, 3, 7, alpha, key))[6]), 2)
        self.lobby_rooms(client, 4, 7, alpha, key)
        self.lobby_rooms(client, 3, 7, winner, key, expected=404)
        replacement = self.room_view(self.lobby_rooms(client, 1, 7, winner, self.room_create_payload(1)))
        self.assertNotEqual(replacement[0], room[0])

    def lobby_transport(self, client, world, token, room, expected=200):
        request = pack("<BBH16sQ", world, 0, 0, token, room)
        client.request("POST", LOCAL_TRANSPORT_PATH, body=request, headers=LOCAL_LOBBY_HEADERS)
        response = client.getresponse()
        body = response.read()
        self.assertEqual(response.status, expected)
        if expected != 200:
            self.assertEqual(body, b"")
            return None
        self.assertEqual(len(body), 24)
        scope, relay = unpack_from("<Q16s", body)
        self.assertEqual(scope, room)
        self.assertNotEqual(relay, bytes(16))
        return relay

    def room_message(self, client, operation, relay, room, cursor, payload=b"", expected=200):
        body = pack("<BBH16sQQ", 7, operation, 0, relay, room, cursor) + payload
        client.request("POST", "/nmg-us/local-lobby/v1/room-messages", body=body, headers=LOCAL_LOBBY_HEADERS)
        response = client.getresponse()
        body = response.read()
        self.assertEqual(response.status, expected)
        if operation == 1 or expected != 200:
            self.assertEqual(body, b"")
            return []
        count, = unpack_from("<H", body)
        offset = 2
        messages = []
        for _ in range(count):
            sequence, sender, cast, reserved, size = unpack_from("<QHBBH", body, offset)
            self.assertEqual(reserved, 0)
            offset += 14
            messages.append((sequence, sender, cast, body[offset:offset + size]))
            offset += size
        self.assertEqual(offset, len(body))
        return messages

    def room_send(self, client, relay, room, nonce, cast, targets, payload, expected=200):
        body = pack("<BBH", cast, len(targets), len(payload))
        body += b"".join(pack("<H", target) for target in targets) + payload
        self.room_message(client, 1, relay, room, nonce, body, expected)

    def test_room_messages_route_three_cast_types_and_retry_without_duplicates(self):
        client = self.start(local_lobbies=True)
        member_ids, leases, relays = [], [], []
        for name in (b"Owner", b"One", b"Two", b"Outsider"):
            member, lease, _ = self.lobby_exchange(client, 1, 7, name=name)
            member_ids.append(member)
            leases.append(lease)
        room = self.room_view(self.lobby_rooms(client, 1, 7, leases[0], self.room_create_payload(1, 4)))[0]
        for lease in leases[1:3]:
            self.lobby_rooms(client, 2, 7, lease, pack("<Q", room))
        for i, lease in enumerate(leases):
            relays.append(self.lobby_transport(client, 7, lease, room if i < 3 else 0))
        owner, first, second, outsider = member_ids
        sender, receiver1, receiver2, outsider_relay = relays
        self.room_message(client, 2, outsider_relay, room, 0, expected=404)
        self.room_send(client, sender, room, 4, 1, [], b"all")
        self.room_send(client, sender, room, 4, 1, [], b"all")
        self.room_send(client, sender, room, 4, 1, [], b"other", expected=409)
        self.room_send(client, sender, room, 5, 2, [first], b"one")
        self.room_send(client, sender, room, 6, 3, [first, outsider], b"outside", expected=404)
        self.room_send(client, sender, room, 6, 3, [first, first], b"dup", expected=400)
        self.room_send(client, sender, room, 6, 2, [owner], b"self", expected=400)
        self.room_send(client, sender, room, 6, 3, [first, second], b"both")
        self.room_send(client, sender, room, 7, 1, [], b"", expected=400)
        self.room_send(client, sender, room, 7, 1, [], bytes(1025), expected=400)
        self.room_message(client, 2, receiver1, room, 1, expected=409)
        first_inbox = [(1, owner, 1, b"all"), (2, owner, 2, b"one"), (3, owner, 3, b"both")]
        self.assertEqual(self.room_message(client, 2, receiver1, room, 0), first_inbox)
        self.assertEqual(self.room_message(client, 2, receiver1, room, 0), first_inbox)
        self.assertEqual(self.room_message(client, 2, receiver1, room, 3), [])
        self.assertEqual(self.room_message(client, 2, receiver2, room, 0),
                         [(1, owner, 1, b"all"), (2, owner, 3, b"both")])
        self.assertEqual(self.room_message(client, 2, sender, room, 0), [])
        for nonce in range(7, 39):
            self.room_send(client, sender, room, nonce, 2, [first], b"queued")
        self.room_send(client, sender, room, 39, 1, [], b"retry", expected=429)
        self.assertEqual(self.room_message(client, 2, receiver2, room, 2), [])
        batch = self.room_message(client, 2, receiver1, room, 3)
        self.assertEqual(batch, [(i, owner, 2, b"queued") for i in range(4, 12)])
        self.room_message(client, 2, receiver1, room, 11)
        self.room_send(client, sender, room, 39, 1, [], b"retry")
        self.assertEqual(self.room_message(client, 2, receiver2, room, 2), [(3, owner, 1, b"retry")])

    def test_room_messages_prune_both_sides_on_departure_and_rejoin(self):
        client = self.start(local_lobbies=True)
        _, alpha, _ = self.lobby_exchange(client, 1, 7, name=b"Alpha")
        beta, beta_token, _ = self.lobby_exchange(client, 1, 7, name=b"Beta")
        gamma, gamma_token, _ = self.lobby_exchange(client, 1, 7, name=b"Gamma")
        room = self.room_view(self.lobby_rooms(client, 1, 7, alpha, self.room_create_payload(1, 3)))[0]
        for token in (beta_token, gamma_token):
            self.lobby_rooms(client, 2, 7, token, pack("<Q", room))
        a, b, g = (self.lobby_transport(client, 7, token, room) for token in (alpha, beta_token, gamma_token))
        self.room_send(client, a, room, 1, 1, [], b"before")
        self.room_send(client, b, room, 2, 1, [], b"leaving")
        self.room_send(client, g, room, 3, 1, [], b"staying")
        self.lobby_rooms(client, 4, 7, beta_token, pack("<Q", room))
        self.assertEqual(self.room_message(client, 2, a, room, 0), [(2, gamma, 1, b"staying")])
        self.assertEqual(self.room_message(client, 2, a, room, 2), [])
        self.lobby_rooms(client, 2, 7, beta_token, pack("<Q", room))
        new_b = self.lobby_transport(client, 7, beta_token, room)
        self.room_send(client, b, room, 3, 1, [], b"old relay", expected=404)
        self.assertEqual(self.room_message(client, 2, new_b, room, 0), [])
        self.room_send(client, new_b, room, 1, 1, [], b"rejoined")
        self.assertEqual(self.room_message(client, 2, a, room, 2), [(3, beta, 1, b"rejoined")])

    def test_room_signaling_topology_controls_links_and_updates_the_star_hub(self):
        for topology in (1, 2):
            with self.subTest(topology=topology):
                client = self.start(local_lobbies=True)
                records = [self.lobby_exchange(client, 1, 7, name=name)[:2]
                           for name in (b"Alpha", b"Beta", b"Gamma", b"Delta")]
                (alpha, a), (beta, b), (gamma, g), (delta, d) = records
                create = self.room_create_payload(1, 4)
                self.lobby_rooms(client, 1, 7, a, create + pack("<BBH", topology, 1, 0), expected=400)
                reply = self.lobby_rooms(client, 1, 7, a, create + pack("<BBH", topology, 0, 0))
                room = self.room_view(reply[:-4])[0]
                self.assertEqual(reply[-4:], pack("<BBH", topology, 0, alpha if topology == 2 else 0))
                for lease in (b, g, d):
                    reply = self.lobby_rooms(client, 2, 7, lease, pack("<Q", room))
                    self.assertEqual(reply[-4:], pack("<BBH", topology, 0, alpha if topology == 2 else 0))
                a_relay, b_relay, g_relay, d_relay = (
                    self.lobby_transport(client, 7, lease, room) for lease in (a, b, g, d))
                self.lobby_channels(client, 7, a_relay, beta, 1, 15, scoped=True)
                _, alpha_gen = self.lobby_channels(client, 7, b_relay, alpha, 1, 15, scoped=True)
                self.lobby_packets(client, 7, b_relay, sequence=1,
                                   packets=[(alpha, 25000, 25001, b"hub", alpha_gen)], scoped=True)
                if topology == 1:
                    self.lobby_channels(client, 7, b_relay, gamma, 1, 15, scoped=True)
                else:
                    self.lobby_channels(client, 7, b_relay, gamma, 1, 15, expected=404, scoped=True)
                    _, gamma_gen = self.lobby_channels(client, 7, a_relay, gamma, 1, 15, scoped=True)
                    self.lobby_packets(client, 7, b_relay, sequence=2,
                                       packets=[(gamma, 25000, 25001, b"leaf", gamma_gen)], expected=404, scoped=True)
                    self.lobby_rooms(client, 4, 7, a, pack("<Q", room))
                    updated = self.lobby_rooms(client, 3, 7, b, pack("<Q", room))
                    self.assertEqual(updated[-4:], pack("<BBH", topology, 0, beta))
                    self.lobby_channels(client, 7, b_relay, gamma, 2, 15, scoped=True)
                    self.lobby_channels(client, 7, g_relay, beta, 1, 15, scoped=True)
                    self.lobby_channels(client, 7, d_relay, gamma, 1, 15, expected=404, scoped=True)

    def test_local_room_transport_revokes_old_tokens_and_scopes_channels(self):
        client = self.start(local_lobbies=True)
        alpha_id, alpha, _ = self.lobby_exchange(client, 1, 7, name=b"Alpha")
        beta_id, beta, _ = self.lobby_exchange(client, 1, 7, name=b"Beta")
        gamma_id, gamma, _ = self.lobby_exchange(client, 1, 7, name=b"Gamma")
        self.assertEqual(self.lobby_transport(client, 7, alpha, 0), alpha)
        world_only = (alpha_id, 25000, 25001, b"old lobby packet")
        self.assertEqual(self.lobby_packets(client, 7, beta, sequence=1, packets=[world_only]), (1, []))
        room_id = self.room_view(self.lobby_rooms(client, 1, 7, alpha, self.room_create_payload(1, 3)))[0]
        room = pack("<Q", room_id)
        alpha_room = self.lobby_transport(client, 7, alpha, room_id)
        self.assertNotEqual(alpha_room, alpha)
        self.assertEqual(self.lobby_transport(client, 7, alpha, room_id), alpha_room)
        self.lobby_transport(client, 7, alpha, 0, expected=404)
        self.lobby_packets(client, 7, alpha, expected=404)
        self.assertEqual(self.lobby_packets(client, 7, alpha_room, scoped=True), (0, []))
        self.lobby_packets(client, 7, alpha_room, expected=400)
        self.lobby_channels(client, 7, alpha_room, gamma_id, 1, 15, expected=404)
        self.lobby_packets(client, 7, gamma, sequence=1, packets=[world_only], expected=404)
        self.lobby_rooms(client, 2, 7, beta, room)
        beta_room = self.lobby_transport(client, 7, beta, room_id)
        ready, beta_generation = self.lobby_channels(client, 7, alpha_room, beta_id, 1, 15, scoped=True)
        self.assertEqual(ready, 0)
        self.assertEqual(self.lobby_channels(client, 7, beta_room, alpha_id, 1, 15, scoped=True)[0], 15)
        self.assertEqual(self.lobby_channels(client, 7, alpha_room, beta_id, 1, 15, scoped=True), (15, beta_generation))
        self.lobby_rooms(client, 4, 7, beta, room)
        self.lobby_channels(client, 7, alpha_room, beta_id, 1, 15, expected=404)
        self.lobby_packets(client, 7, beta_room, expected=404)
        self.assertNotIn(self.lobby_transport(client, 7, beta, 0), (beta, beta_room))
        self.lobby_rooms(client, 2, 7, beta, room)
        rejoined = self.lobby_transport(client, 7, beta, room_id)
        self.assertNotEqual(rejoined, beta_room)
        self.assertEqual(self.lobby_channels(client, 7, rejoined, alpha_id, 1, 15, scoped=True)[0], 0)
        ready, rejoined_generation = self.lobby_channels(client, 7, alpha_room, beta_id, 2, 15, scoped=True)
        self.assertEqual(ready, 15)
        self.assertNotEqual(rejoined_generation, beta_generation)
        stale = (beta_id, 25000, 25001, b"old destination", beta_generation)
        fresh = (beta_id, 25000, 25001, b"new destination", rejoined_generation)
        self.lobby_packets(client, 7, alpha_room, sequence=1, packets=[stale], expected=404, scoped=True)
        self.assertEqual(self.lobby_packets(client, 7, alpha_room, sequence=1, packets=[fresh], scoped=True), (1, []))

    def test_local_room_transport_drops_departed_frames_and_accepts_ack_gaps(self):
        client = self.start(local_lobbies=True)
        alpha_id, alpha, _ = self.lobby_exchange(client, 1, 7, name=b"Alpha")
        _, beta, _ = self.lobby_exchange(client, 1, 7, name=b"Beta")
        gamma_id, gamma, _ = self.lobby_exchange(client, 1, 7, name=b"Gamma")
        room_id = self.room_view(self.lobby_rooms(client, 1, 7, alpha, self.room_create_payload(1, 3)))[0]
        room = pack("<Q", room_id)
        self.lobby_rooms(client, 2, 7, beta, room)
        self.lobby_rooms(client, 2, 7, gamma, room)
        alpha_room = self.lobby_transport(client, 7, alpha, room_id)
        beta_room = self.lobby_transport(client, 7, beta, room_id)
        gamma_room = self.lobby_transport(client, 7, gamma, room_id)
        _, alpha_generation = self.lobby_channels(client, 7, beta_room, alpha_id, 1, 15, scoped=True)
        _, gamma_generation = self.lobby_channels(client, 7, alpha_room, gamma_id, 1, 15, scoped=True)
        packet = (alpha_id, 25000, 25001, b"from beta", alpha_generation)
        self.lobby_packets(client, 7, beta_room, sequence=1, packets=[packet], scoped=True)
        self.lobby_rooms(client, 4, 7, beta, room)
        self.lobby_packets(client, 7, gamma_room, sequence=1,
                           packets=[(alpha_id, 25002, 25003, b"from gamma", alpha_generation)], scoped=True)
        self.assertEqual(self.lobby_packets(client, 7, alpha_room, scoped=True),
                         (0, [(2, gamma_id, 25002, 25003, b"from gamma", gamma_generation)]))
        self.assertEqual(self.lobby_packets(client, 7, alpha_room, ack=2, scoped=True), (0, []))

    def test_get_without_fixture_is_unavailable(self):
        client = self.start()
        client.request("GET", DISCOVERY_PATH, headers={"User-Agent": USER_AGENT})
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (503, b""))

    def test_get_replays_fixture_bytes(self):
        fixture = bytes(range(16))
        client = self.start(fixture)
        client.request("GET", DISCOVERY_PATH, headers={"User-Agent": USER_AGENT, "Content-Length": "0"})
        response = client.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Length"), str(len(fixture)))
        self.assertEqual(response.read(), fixture)

    def test_combined_discovery_advertises_all_enabled_replay_routes(self):
        plain = discovery_document(eula=True, empty_notices=True, daily_scores=True,
                                   login_rejection=True, empty_boards=True,
                                   cached_property=True, discard_telemetry=True).rstrip(b"\0")
        document = ElementTree.fromstring(b"<fixture>" + plain + b"</fixture>")
        urls = {element.tag: element.text for element in document.findall("./gameurl1/*")}
        service_urls = [field.text for field in document if field.tag.endswith("_url1")]
        self.assertEqual(len(urls), 37)
        self.assertEqual(len(service_urls), 5)
        for url in [*urls.values(), *service_urls]:
            self.assertEqual(urlsplit(url).netloc, "127.0.0.1:8765")

        routes = (
            ("gameapi_getservertime", SERVER_TIME_PATH, SERVER_TIME_PATH, SERVER_TIME_REQUEST),
            ("gameapi_geteula", EULA_PATH, EULA_PATH, EULA_REQUEST),
            ("gameapi_getinfolist", NOTICE_PATH, NOTICE_PATH, NOTICE_REQUEST),
            ("gameapi_getscorelist", SCORE_PATH, SCORE_PATH, SCORE_REQUEST),
            ("gameapi_getboardlist", BOARD_PATH, BOARD_PATH, BOARD_REQUEST),
            ("gameapi_login", LOGIN_TARGET.split("=", 1)[0] + "=", LOGIN_TARGET, LOGIN_REQUEST),
            ("gameapi_getgamepropertyinfo", PROPERTY_PATH, PROPERTY_PATH, PROPERTY_REQUEST),
        )
        fixture = bytes(range(16))
        client = self.start(fixture, server_time=SERVER_TIME, eula_text=EULA_TEXT, empty_notices=True,
                            daily_score_block=SCORE_INNER, login_rejection=True,
                            empty_board_block=SCORE_INNER, cached_property=True, discard_telemetry=True)
        client.request("GET", DISCOVERY_PATH, headers={"User-Agent": USER_AGENT})
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (200, fixture))
        for name, advertised_path, request_path, request in routes:
            with self.subTest(route=name):
                self.assertEqual(urls[name], "https://127.0.0.1:8765" + advertised_path)
                client.request("POST", request_path, body=request, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual(response.status, 200)
                self.assertTrue(response.read().endswith(b"\x10\x80\x01\x00"))
        self.assertEqual(document.findtext("game_analytics_system_url1"),
                         "http://127.0.0.1:8765/nmg-us/replay-probe/analytics/")
        client.request("POST", TELEMETRY_PATH, body=TELEMETRY_REQUEST, headers=TELEMETRY_HEADERS)
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (200, b""))

    def test_cached_property_requires_opt_in(self):
        client = self.start()
        client.request("POST", PROPERTY_PATH, body=PROPERTY_REQUEST, headers=SERVER_TIME_HEADERS)
        self.assertEqual(client.getresponse().status, 404)

    def test_cached_property_checks_index_records_and_request_length(self):
        client = self.start(cached_property=True)
        self.assertEqual(len(PROPERTY_REQUEST), 118)
        second_version = PROPERTY_REQUEST.replace(bytes.fromhex("0576020000000000"),
                                                  bytes.fromhex("0576020078563412"))
        for request in (PROPERTY_REQUEST, second_version):
            client.request("POST", PROPERTY_PATH, body=request, headers=SERVER_TIME_HEADERS)
            response = client.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), bytes.fromhex("00800100 0000020001000000 0376020001000000 10800100"))
        invalid_index = PROPERTY_REQUEST.replace(bytes.fromhex("0476020001000000"),
                                                 bytes.fromhex("0476020002000000"))
        wrong_type = PROPERTY_REQUEST.replace(bytes.fromhex("05760200"), bytes.fromhex("06760200"))
        for request in (invalid_index, wrong_type, PROPERTY_REQUEST[:-1]):
            client.request("POST", PROPERTY_PATH, body=request, headers=SERVER_TIME_HEADERS)
            self.assertEqual(client.getresponse().status, 400)

    def test_telemetry_requires_opt_in_and_matching_path(self):
        disabled = self.start()
        client = self.start(discard_telemetry=True)
        for connection, target in ((disabled, TELEMETRY_PATH), (client, TELEMETRY_PATH + "?more=1"),
                                   (client, TELEMETRY_PATH.replace("analytics/", "analytics")),
                                   (client, TELEMETRY_PATH.replace("19d916d7", "19d916d8"))):
            connection.request("POST", target, body=b"{}", headers=TELEMETRY_HEADERS)
            self.assertEqual(connection.getresponse().status, 404)

    def test_telemetry_validates_json_type_and_size(self):
        client = self.start(discard_telemetry=True)
        cases = ((b"[]", TELEMETRY_HEADERS, 200), (b"{}", {}, 415),
                 (b"[", TELEMETRY_HEADERS, 400), (b"true", TELEMETRY_HEADERS, 400),
                 (b"{\xff}", TELEMETRY_HEADERS, 400), (b"[" * 2000, TELEMETRY_HEADERS, 400),
                 (b"{}".ljust(8192), TELEMETRY_HEADERS, 200), (b"{}".ljust(8193), TELEMETRY_HEADERS, 413))
        for body, headers, status in cases:
            client.request("POST", TELEMETRY_PATH, body=body, headers=headers)
            response = client.getresponse()
            self.assertEqual((response.status, response.read()), (status, b""))

    def test_discovery_rejects_post(self):
        client = self.start()
        client.request("POST", DISCOVERY_PATH)
        response = client.getresponse()
        self.assertEqual(response.status, 405)
        self.assertEqual(response.getheader("Allow"), "GET")

    def test_discovery_rejects_a_body(self):
        client = self.start()
        client.request("GET", DISCOVERY_PATH, body=b"x", headers={"User-Agent": USER_AGENT})
        self.assertEqual(client.getresponse().status, 400)

    def test_server_time_post_replays_binary_records(self):
        client = self.start(server_time=SERVER_TIME)
        client.request("POST", SERVER_TIME_PATH, body=SERVER_TIME_REQUEST, headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/octet-stream")
        self.assertEqual(response.getheader("Content-Length"), "28")
        self.assertEqual(response.read(), bytes.fromhex(
            "00800100 0000020001000000 005003002026111723184200 10800100"
        ))

    def test_server_time_route_requires_opt_in(self):
        client = self.start()
        client.request("POST", SERVER_TIME_PATH, body=SERVER_TIME_REQUEST, headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

    def test_server_time_rejects_other_body_and_content_type(self):
        client = self.start(server_time=SERVER_TIME)
        body = SERVER_TIME_REQUEST.replace(b"CUSA04687", b"CUSA00000")
        client.request("POST", SERVER_TIME_PATH, body=body, headers=SERVER_TIME_HEADERS)
        self.assertEqual(client.getresponse().status, 400)
        client.request("POST", SERVER_TIME_PATH, body=SERVER_TIME_REQUEST,
                       headers={"Content-Type": "application/json"})
        self.assertEqual(client.getresponse().status, 415)

    def test_server_time_rejects_unexpected_length(self):
        client = self.start(server_time=SERVER_TIME)
        client.request("POST", SERVER_TIME_PATH, body=b"", headers=SERVER_TIME_HEADERS)
        self.assertEqual(client.getresponse().status, 400)

    def test_eula_replays_local_text_for_both_request_variants(self):
        client = self.start(eula_text=EULA_TEXT)
        for body in (EULA_REQUEST, EULA_ALTERNATE_REQUEST):
            with self.subTest(title=body[58:71]):
                client.request("POST", EULA_PATH, body=body, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                expected = (
                    bytes.fromhex("00800100 0000020001000000 5010020001000000 00100100")
                    + bytes.fromhex("10100500 f0d9aace08f11862d810965f29f38ae3")
                    + bytes.fromhex("301002000d000000 20100500") + EULA_TEXT + b"\0" * 3
                    + bytes.fromhex("10800100")
                )
                self.assertEqual(response.getheader("Content-Type"), "application/octet-stream")
                self.assertEqual((response.status, response.read()), (200, expected))

    def test_eula_requires_an_explicit_fixture_and_valid_records(self):
        for options, body, status in (
            ({}, EULA_REQUEST, 404),
            ({"eula_text": EULA_TEXT}, EULA_REQUEST.replace(b"CUSA04687", b"CUSA00000"), 400),
            ({"eula_text": EULA_TEXT}, EULA_ALTERNATE_REQUEST.replace(
                b"\x50\x10\x02\x00\0\0\0\0", b"\x50\x10\x02\x00\x01\0\0\0"), 400),
        ):
            with self.subTest(status=status):
                client = self.start(**options)
                client.request("POST", EULA_PATH, body=body, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (status, b""))

    def test_eula_rejects_empty_oversize_and_invalid_text(self):
        for text in (b"", b"x" * 32768, b"terms\0more", b"\xff"):
            with self.subTest(length=len(text)), self.assertRaises(ValueError):
                GolfServer(0, eula_text=text)

    def test_notice_probe_is_disabled_by_default(self):
        client = self.start()
        client.request("POST", NOTICE_PATH, body=NOTICE_REQUEST, headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

    def test_notice_probe_replays_zero_count_for_all_login_selectors(self):
        client = self.start(empty_notices=True)
        selector_one = bytes.fromhex("5030020001000000")
        selector_zero = bytes.fromhex("5030020000000000")
        selector_two = bytes.fromhex("5030020002000000")
        request_two = NOTICE_REQUEST.replace(selector_one, selector_two)
        for request in (request_two, NOTICE_REQUEST, NOTICE_REQUEST.replace(selector_one, selector_zero).replace(
                b"\x83\x00\x02\x00abc\0", b"\x83\x00\x02\x00\0\x03\x03\x03")):
            client.request("POST", NOTICE_PATH, body=request, headers=SERVER_TIME_HEADERS)
            response = client.getresponse()
            self.assertEqual(response.getheader("Content-Type"), "application/octet-stream")
            self.assertEqual((response.status, response.read()), (200, bytes.fromhex(
                "00800100 0000020001000000 830003006c6f63616c000000 0030020000000000 10800100"
            )))

    def test_notice_probe_rejects_invalid_records_and_lengths(self):
        client = self.start(empty_notices=True)
        for request in (
            NOTICE_REQUEST[:-1],
            NOTICE_REQUEST.replace(b"\x83\x00\x02\x00abc\0", b"\x83\x00\x01\x00abc\0"),
            NOTICE_REQUEST.replace(b"\x83\x00\x02\x00abc\0", b"\x83\x00\x02\x00abcd"),
            NOTICE_REQUEST.replace(b"\x83\x00\x02\x00abc\0", b"\x83\x00\x02\x00a\0\x03\x00"),
            NOTICE_REQUEST.replace(bytes.fromhex("5030020001000000"), bytes.fromhex("5030020003000000")),
            NOTICE_REQUEST.replace(bytes.fromhex("104002000a000000"), bytes.fromhex("104002000b000000")),
            NOTICE_REQUEST + b"x" * 2048,
        ):
            with self.subTest(length=len(request)):
                client.request("POST", NOTICE_PATH, body=request, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (400, b""))

    def test_daily_score_probe_requires_an_explicit_fixture(self):
        client = self.start()
        client.request("POST", SCORE_PATH, body=SCORE_REQUEST, headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

    def test_empty_board_probe_requires_an_explicit_block(self):
        client = self.start()
        client.request("POST", BOARD_PATH, body=BOARD_REQUEST, headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

    def test_board_probe_replays_the_zero_count_branch(self):
        client = self.start(empty_board_block=SCORE_INNER)
        for limit in (2, 213):
            with self.subTest(limit=limit):
                request = BOARD_REQUEST.replace(b"\x10\x40\x02\x00\x02\0\0\0",
                                                b"\x10\x40\x02\x00" + bytes([limit]) + b"\0\0\0")
                client.request("POST", BOARD_PATH, body=request, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual(response.getheader("Content-Type"), "application/octet-stream")
                self.assertEqual((response.status, response.read()), (200,
                    bytes.fromhex("00800100 0000020001000000 60000300") + SCORE_INNER
                    + bytes.fromhex("00410100 1041020000000000 10800100")))

    def test_board_probe_rejects_bad_range_and_cipher_framing(self):
        client = self.start(empty_board_block=SCORE_INNER)
        requests = (
            BOARD_REQUEST.replace(b"\x00\x40\x02\x00\x01", b"\x00\x40\x02\x00\x00"),
            BOARD_REQUEST.replace(b"\x10\x40\x02\x00\x02", b"\x10\x40\x02\x00\xd6"),
            BOARD_REQUEST.replace(b"\x60\x00\x03\x00" + SCORE_INNER,
                                  b"\x60\x00\x04\x00" + SCORE_INNER + bytes(4)),
        )
        for request in requests:
            client.request("POST", BOARD_PATH, body=request, headers=SERVER_TIME_HEADERS)
            response = client.getresponse()
            self.assertEqual((response.status, response.read()), (400, b""))

    def test_national_board_probe_advertises_and_returns_the_no_download_reply(self):
        document = discovery_document(empty_national_boards=True).rstrip(b"\0")
        urls = ElementTree.fromstring(b"<fixture>" + document + b"</fixture>")
        self.assertEqual(urls.findtext("./gameurl1/gameapi_getboardlistnational"),
                         "https://127.0.0.1:8765" + NATIONAL_BOARD_PATH)
        client = self.start(empty_national_boards=True)
        for selector in (0, 1, 3):
            with self.subTest(selector=selector):
                request = NATIONAL_BOARD_REQUEST.replace(bytes.fromhex("404a020000000000"),
                                                         b"\x40\x4a\x02\x00" + bytes([selector, 0, 0, 0]))
                client.request("POST", NATIONAL_BOARD_PATH, body=request, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual(response.getheader("Content-Type"), "application/octet-stream")
                self.assertEqual((response.status, response.read()), (200,
                                 bytes.fromhex("00800100 0000020001000000 830003006c6f63616c000000 10800100")))

    def test_national_board_probe_requires_opt_in_and_a_supported_selector(self):
        client = self.start()
        client.request("POST", NATIONAL_BOARD_PATH, body=NATIONAL_BOARD_REQUEST, headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

        client = self.start(empty_national_boards=True)
        for request in (
            NATIONAL_BOARD_REQUEST.replace(b"abc\0", b"abcd"),
            NATIONAL_BOARD_REQUEST.replace(bytes.fromhex("404a020000000000"), bytes.fromhex("404a020002000000")),
            NATIONAL_BOARD_REQUEST.replace(bytes.fromhex("80004100"), bytes.fromhex("80004000")),
        ):
            with self.subTest(request=request):
                client.request("POST", NATIONAL_BOARD_PATH, body=request, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (400, b""))
        client.request("GET", NATIONAL_BOARD_PATH)
        response = client.getresponse()
        self.assertEqual((response.status, response.getheader("Allow"), response.read()), (405, "POST", b""))

    def test_national_tournament_replays_both_downloads(self):
        document = discovery_document(national_tournament=True).rstrip(b"\0")
        urls = ElementTree.fromstring(b"<fixture>" + document + b"</fixture>")
        self.assertEqual(urls.findtext("./gameurl1/gameapi_getnationalgamedata"),
                         "https://127.0.0.1:8765" + NATIONAL_GAME_DATA_PATH)
        self.assertEqual(urls.findtext("./cds_gamedata_down_url1"), "http://127.0.0.1:8765" + DOWNLOAD_BASE)
        client = self.start(national_tournament=True, server_time=datetime(2018, 9, 14, 12))
        success = bytes.fromhex("00800100 0000020001000000 830003006c6f63616c000000")
        end = bytes.fromhex("10800100")

        for selector in (0, 1, 3):
            with self.subTest(selector=selector):
                request = NATIONAL_BOARD_REQUEST.replace(bytes.fromhex("404a020000000000"),
                                                         pack("<2HI", 0x4A40, 2, selector))
                client.request("POST", NATIONAL_BOARD_PATH, body=request, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (200, success + bytes.fromhex("604a0800")
                                 + b"/local-national-board.bin\0\x02\x02" + end))
        client.request("GET", DOWNLOAD_BASE + "/local-national-board.bin")
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (200, bytes.fromhex(
            "0041020001000000 20410100 4541020001000000 4641020001000000 40410500")
            + b"LocalTournament\0" + bytes.fromhex("4741020001000000 4241020000030303"
            " 4341020000000000 4441020000000000 50410600") + b"Local Tournament\0\x03\x03\x03"
            + bytes.fromhex("774103002018091400000000 784103002018091423595900 30410100") + end))

        selector_two = NATIONAL_BOARD_REQUEST.replace(bytes.fromhex("404a020000000000"),
                                                      bytes.fromhex("404a020002000000"))
        client.request("POST", NATIONAL_BOARD_PATH, body=selector_two, headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (400, b""))
        for token in (b"\x83\x00\x02\x00abc\0", b"\x83\x00\xfc\x00" + b"x" * 1000 + b"\0\x03\x03\x03"):
            with self.subTest(token_bytes=len(token)):
                body = NATIONAL_GAME_DATA_REQUEST.replace(b"\x83\x00\x02\x00abc\0", token)
                client.request("POST", NATIONAL_GAME_DATA_PATH, body=body, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (200, success + bytes.fromhex("f5410700")
                                 + b"/local-tournament.xb\0\x03\x03\x03"
                                 + bytes.fromhex("f641020001000000 f741020000000000") + end))

        client.request("GET", DOWNLOAD_BASE + "/local-tournament.xb")
        response = client.getresponse()
        archive = response.read()
        self.assertEqual(response.status, 200)
        self.assertEqual(unpack_from("<4sIII", archive), (b"FB\0\0", 2, 4, 0))
        stream = 56
        files = {}
        for index in range(2):
            name, zero, ordinal, compressed, expanded = unpack_from("<5I", archive, 16 + index * 20)
            self.assertEqual((zero, ordinal), (0, index))
            files[name] = zlib.decompress(archive[stream:stream + compressed])
            self.assertEqual(len(files[name]), expanded)
            stream += (compressed + 3) & ~3
        self.assertEqual(stream, len(archive))
        self.assertEqual(set(files), {0xBD8494AE, 0x520E1D57})
        self.assertEqual(files[0xBD8494AE],
                         b"\xef\xbb\xbfresetThreshold\ttournamentId\tsponsored_US\tp1_course\tp1_hole\tp2_course\tp2_hole\r\n"
                         b"0\t1\t0\t1\t1\t1\t1\r\n")
        self.assertEqual(files[0x520E1D57], b"\xef\xbb\xbftournamentName_US_01_ENG\r\n\"Local Tournament\"\r\n")

    def test_national_tournament_rejects_wrong_id_and_disabled_downloads(self):
        for options, expected in (({}, 404), ({"national_tournament": True,
                                                "server_time": datetime(2018, 9, 14, 12)}, 400)):
            with self.subTest(status=expected):
                client = self.start(**options)
                body = NATIONAL_GAME_DATA_REQUEST.replace(bytes.fromhex("4741020001000000"),
                                                          bytes.fromhex("4741020002000000"))
                client.request("POST", NATIONAL_GAME_DATA_PATH, body=body, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (expected, b""))
                client.request("GET", DOWNLOAD_BASE + "/local-tournament.xb?unexpected")
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (404, b""))
                if not options:
                    client.request("GET", DOWNLOAD_BASE + "/local-tournament.xb")
                    response = client.getresponse()
                    self.assertEqual((response.status, response.read()), (404, b""))

    def test_bonus_list_replays_an_empty_page_for_a_valid_title_session(self):
        path = "/nmg-us/replay-probe/gameapi_getbonuslist"
        document = discovery_document(empty_bonus_list=True).rstrip(b"\0")
        urls = ElementTree.fromstring(b"<fixture>" + document + b"</fixture>")
        self.assertEqual(urls.findtext("./gameurl1/gameapi_getbonuslist"), "https://127.0.0.1:8765" + path)
        default = ElementTree.fromstring(b"<fixture>" + discovery_document().rstrip(b"\0") + b"</fixture>")
        self.assertEqual(default.findtext("./gameurl1/gameapi_getbonuslist"), "http://127.0.0.1:8765" + path)

        end = bytes.fromhex("10800100")
        page = bytes.fromhex("0040020000000000 1040020032000000")
        request = SERVER_TIME_REQUEST.replace(end, NOTICE_FIELDS[:260] + string_record(0x0083, b"") + page + end)
        large = request.replace(string_record(0x0083, b""), string_record(0x0083, b"x" * 1000))
        wrong_record = request.replace(bytes.fromhex("1040020032000000"), bytes.fromhex("1140020032000000"))
        expected = bytes.fromhex("00800100 0000020001000000 830003006c6f63616c000000 10800100")
        self.assertEqual((len(request), len(large), len(expected)), (386, 1386, 28))
        client = self.start(empty_bonus_list=True)
        for body, status, reply in ((request, 200, expected), (large, 200, expected), (wrong_record, 400, b"")):
            with self.subTest(request_length=len(body), status=status):
                client.request("POST", path, body=body, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (status, reply))
        client.request("GET", path)
        response = client.getresponse()
        self.assertEqual((response.status, response.getheader("Allow"), response.read()), (405, "POST", b""))
        disabled = self.start()
        disabled.request("POST", path, body=request, headers=SERVER_TIME_HEADERS)
        response = disabled.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

    def test_national_own_score_replies_with_no_local_score(self):
        document = discovery_document(national_tournament=True).rstrip(b"\0")
        urls = ElementTree.fromstring(b"<fixture>" + document + b"</fixture>")
        self.assertEqual(urls.findtext("./gameurl1/gameapi_getmyscorenational"),
                         "https://127.0.0.1:8765" + NATIONAL_OWN_SCORE_PATH)
        session = bytes.fromhex("86002100") + bytes(128) + bytes.fromhex("8700020000000000 8800020000000000")
        event = bytes.fromhex("40410500") + b"LocalTournament\0" + bytes.fromhex(
            "4741020001000000 4241020000030303 4341020000000000 4441020000000000")
        request = SERVER_TIME_REQUEST.replace(b"\x10\x80\x01\x00",
                                              NOTICE_FIELDS[:268] + session + event + b"\x10\x80\x01\x00")
        client = self.start(national_tournament=True, server_time=datetime(2018, 9, 14, 12))
        expected = bytes.fromhex("00800100 0000020001000000 830003006c6f63616c000000 0042020000000000 10800100")
        long_token = b"\x83\x00\xfc\x00" + b"x" * 1000 + b"\0\x03\x03\x03"
        maximum_request = request.replace(b"\x83\x00\x02\x00abc\0", long_token)
        wrong_event = request.replace(bytes.fromhex("4741020001000000"), bytes.fromhex("4741020002000000"))
        wrong_session = request.replace(bytes.fromhex("8800020000000000"), bytes.fromhex("8800020001000000"))
        for body, status, reply in ((request, 200, expected), (maximum_request, 200, expected),
                                    (wrong_event, 400, b""), (wrong_session, 400, b"")):
            with self.subTest(length=len(body), status=status):
                client.request("POST", NATIONAL_OWN_SCORE_PATH, body=body, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (status, reply))
        disabled = self.start()
        disabled.request("POST", NATIONAL_OWN_SCORE_PATH, body=request, headers=SERVER_TIME_HEADERS)
        response = disabled.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

    def test_national_join_replays_the_synthetic_first_entry(self):
        prefix = "/nmg-us/replay-probe/gameapi_noticejoinnational?account="
        path = prefix + "5932163534510096385&n=14&s=1"
        event = bytes.fromhex("40410500") + b"LocalTournament\0" + bytes.fromhex(
            "4741020001000000 4241020000030303 4341020000000000 4441020000000000")
        request = SERVER_TIME_REQUEST.replace(b"\x10\x80\x01\x00",
                                              NOTICE_FIELDS[:268] + event + b"\x10\x80\x01\x00")
        client = self.start(national_tournament=True, server_time=datetime(2018, 9, 14, 12))
        expected = bytes.fromhex("00800100 0000020001000000 83000300 6c6f63616c000000"
                                 "6249020000000000 10800100")
        client.request("POST", path, body=request, headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (200, expected))

        long_token = b"\x83\x00\xfc\x00" + b"x" * 1000 + b"\0\x03\x03\x03"
        maximum = request.replace(b"\x83\x00\x02\x00abc\0", long_token)
        wrong_id = request.replace(bytes.fromhex("4741020001000000"), bytes.fromhex("4741020002000000"))
        extra_login_record = request.replace(event, bytes.fromhex("8800020000000000") + event)
        for body, status, reply in ((maximum, 200, expected), (wrong_id, 400, b""),
                                    (extra_login_record, 400, b"")):
            with self.subTest(length=len(body), status=status):
                client.request("POST", path, body=body, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (status, reply))
        client.request("GET", path)
        response = client.getresponse()
        self.assertEqual((response.status, response.getheader("Allow"), response.read()), (405, "POST", b""))

        disabled = self.start()
        disabled.request("POST", path, body=request, headers=SERVER_TIME_HEADERS)
        response = disabled.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))
        for enabled, url in ((True, "https://127.0.0.1:8765" + prefix),
                             (False, "http://127.0.0.1:8765" + prefix.removesuffix("?account="))):
            document = discovery_document(national_tournament=enabled).rstrip(b"\0")
            urls = ElementTree.fromstring(b"<fixture>" + document + b"</fixture>")
            self.assertEqual(urls.findtext("./gameurl1/gameapi_noticejoinnational"), url)
        for target in (prefix, prefix + "5932163534510096385&n=14", prefix + "1&n=14&s=1"):
            with self.subTest(target=target):
                client.request("POST", target, body=request, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (400, b""))

    def test_national_distribution_returns_empty_download(self):
        path = "/nmg-us/replay-probe/gameapi_getscoredistributionnational"
        suffix = b"/local-national-distribution.json"
        download = DOWNLOAD_BASE + suffix.decode("ascii")
        document = discovery_document(national_tournament=True).rstrip(b"\0")
        urls = ElementTree.fromstring(b"<fixture>" + document + b"</fixture>")
        self.assertEqual(urls.findtext("./gameurl1/gameapi_getscoredistributionnational"),
                         "https://127.0.0.1:8765" + path)
        request = NATIONAL_GAME_DATA_REQUEST.replace(bytes.fromhex("f641020000000000"), b"")
        maximum = request.replace(b"\x83\x00\x02\x00abc\0", b"\x83\x00\xfc\x00" + b"x" * 1000 + b"\0\3\3\3")
        wrong_id = request.replace(bytes.fromhex("4741020001000000"), bytes.fromhex("4741020002000000"))
        reply = (bytes.fromhex("00800100 0000020001000000 83000300 6c6f63616c000000 92420a00")
                 + suffix + b"\0\x02\x02" + bytes.fromhex("10800100"))
        client = self.start(national_tournament=True, server_time=datetime(2018, 9, 14, 12))
        for body, status, expected in ((request, 200, reply), (maximum, 200, reply),
                                       (wrong_id, 400, b""), (NATIONAL_GAME_DATA_REQUEST, 400, b"")):
            with self.subTest(length=len(body), status=status):
                client.request("POST", path, body=body, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (status, expected))
        for target, status, expected in ((download, 200, b"[]"), (download + "?unexpected", 404, b"")):
            client.request("GET", target)
            response = client.getresponse()
            self.assertEqual((response.status, response.read()), (status, expected))

        disabled = self.start()
        disabled.request("POST", path, body=request, headers=SERVER_TIME_HEADERS)
        response = disabled.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))
        disabled.request("GET", download)
        response = disabled.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

    def test_national_score_list_returns_an_inline_empty_page(self):
        path = "/nmg-us/replay-probe/gameapi_getscorelistnational"
        document = discovery_document(national_tournament=True).rstrip(b"\0")
        urls = ElementTree.fromstring(b"<fixture>" + document + b"</fixture>")
        self.assertEqual(urls.findtext("./gameurl1/gameapi_getscorelistnational"),
                         "https://127.0.0.1:8765" + path)
        session = NOTICE_FIELDS[:268]
        event = bytes.fromhex("40410500") + b"LocalTournament\0" + bytes.fromhex(
            "4741020001000000 4241020000030303 4341020000000000 4441020000000000")
        page = bytes.fromhex("0040020001000000 1040020064000000 10800100")
        one = bytes.fromhex("0040020001000000 1040020001000000 10800100")
        account = bytes.fromhex("f3424100") + session[4:260]
        request = SERVER_TIME_REQUEST.replace(bytes.fromhex("10800100"), session + event + page)
        filtered = request.replace(page, account + one)
        max_token = b"\x83\x00\xfc\x00" + b"x" * 1000 + b"\0\3\3\3"
        maximum = filtered.replace(b"\x83\x00\x02\x00abc\0", max_token)
        invalid = filtered.replace(account, account[:4] + b"other\0" + bytes(250))
        expected = bytes.fromhex("00800100 0000020001000000 83000300 6c6f63616c000000"
                                 "0042020000000000 1042020001000000 10800100")
        client = self.start(national_tournament=True, server_time=datetime(2018, 9, 14, 12))
        for body, status, reply in ((request, 200, expected), (filtered, 200, expected),
                                    (maximum, 200, expected), (invalid, 400, b""),
                                    (request.replace(page, one), 400, b""),
                                    (filtered.replace(one, page), 400, b"")):
            with self.subTest(length=len(body), status=status):
                client.request("POST", path, body=body, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (status, reply))
        disabled = self.start()
        disabled.request("POST", path, body=request, headers=SERVER_TIME_HEADERS)
        response = disabled.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

    def test_national_score_registration_persists_both_scores_and_replays_all_views(self):
        route = "/nmg-us/replay-probe/gameapi_registscorenational?account="
        target = route + "5932163534510096385&n=1&s=1"
        score_list = "/nmg-us/replay-probe/gameapi_getscorelistnational"
        download = DOWNLOAD_BASE + "/local-national-distribution.json"
        term = bytes.fromhex("10800100")
        common = NOTICE_FIELDS[:268]
        event = bytes.fromhex("40410500") + b"LocalTournament\0" + bytes.fromhex(
            "4741020001000000 4241020000030303 4341020000000000 4441020000000000")
        login = bytes.fromhex("86002100") + bytes(128) + bytes.fromhex("8700020000000000 8800020000000000")
        page = bytes.fromhex("0040020001000000 1040020064000000")
        own_request = SERVER_TIME_REQUEST.replace(term, common + login + event + term)
        list_request = SERVER_TIME_REQUEST.replace(term, common + event + page + term)

        def registration(primary, secondary, *, player=b"Golfer", token=b"abc", detail=b"0"):
            session = common[:260] + string_record(0x0083, token)
            stats = pack("<2Hq2Hq", 0x4500, 3, primary, 0x4501, 3, secondary)
            details = b"".join(string_record(0x4600 + index, detail) for index in range(14))
            stamp = string_record(0x42B0, player + b"@2026-11-18T10:00:00+09:00")
            return SERVER_TIME_REQUEST.replace(term, session + event + stamp + stats + details + term)

        document = discovery_document(national_tournament=True, score_registration=True).rstrip(b"\0")
        urls = ElementTree.fromstring(b"<fixture>" + document + b"</fixture>")
        login_options = dict(national_tournament=True, server_time=datetime(2026, 11, 18, 12))
        prefix = bytes.fromhex("00800100 0000020001000000 830003006c6f63616c000000")
        rank = bytes.fromhex("7042020001000000")
        empty = prefix + bytes.fromhex("0042020000000000") + term
        ack = prefix + rank + bytes.fromhex("a0420100") + term
        best = pack("<2Hq2Hq", 0x4500, 3, -3, 0x4501, 3, 91)
        expected_own = (prefix + bytes.fromhex("0042020001000000 30420100 d142020002000000")
                        + rank + best + bytes.fromhex("40420100") + term)
        expected_list = (prefix + bytes.fromhex("0042020001000000 1042020001000000 50420100")
                         + rank + best + string_record(0x0020, b"Golfer") + string_record(0x0084, LOGIN_ACCOUNT)
                         + bytes.fromhex("60420100") + term)

        def request(client, method, path, expected_status, expected_reply, body=None):
            client.request(method, path, body=body, headers=SERVER_TIME_HEADERS if body is not None else {})
            response = client.getresponse()
            self.assertEqual((response.status, response.read()), (expected_status, expected_reply))

        with TemporaryDirectory() as directory:
            db = Path(directory) / "scores.sqlite"
            client = self.start(score_db=db, **login_options)
            request(client, "POST", NATIONAL_OWN_SCORE_PATH, 200, empty, own_request)
            min_size = registration(-2, 42, player=b"G")
            self.assertEqual(len(min_size), 590)
            request(client, "POST", target, 200, ack, min_size)
            request(client, "POST", target, 200, ack, registration(-3, 91))
            max_size = registration(8, 123, player=b"ABCDEFGHIJKLMNOP", token=b"x" * 1000, detail=b"a" * 255)
            self.assertEqual(len(max_size), 5134)
            request(client, "POST", target, 200, ack, max_size)
            request(client, "POST", target, 400, b"", registration(-9, 99).replace(
                bytes.fromhex("4741020001000000"), bytes.fromhex("4741020002000000")))
            request(client, "POST", target.replace("5932", "6932"), 400, b"", registration(-9, 99))
            request(client, "POST", target, 400, b"", registration(-9, 99).replace(
                bytes.fromhex("0d460200"), bytes.fromhex("0e460200")))
            request(client, "POST", target, 400, b"", registration(-(1 << 31) - 1, 99))
            restarted = self.start(score_db=db, **login_options)
            request(restarted, "POST", NATIONAL_OWN_SCORE_PATH, 200, expected_own, own_request)
            request(restarted, "POST", score_list, 200, expected_list, list_request)
            request(restarted, "GET", download, 200, b'[{"num":"1","score":"-3"}]')
            request(restarted, "POST", score_list, 200,
                    prefix + bytes.fromhex("0042020000000000 1042020001000000") + term,
                    list_request.replace(page, bytes.fromhex("0040020002000000 1040020064000000")))
            next_day = self.start(score_db=db, national_tournament=True, server_time=datetime(2026, 11, 19, 12))
            request(next_day, "POST", NATIONAL_OWN_SCORE_PATH, 200, empty, own_request)
            request(next_day, "GET", download, 200, b"[]")
            request(self.start(score_db=db), "POST", target, 404, b"", registration(-3, 91))
        request(self.start(**login_options), "POST", target, 404, b"", registration(-3, 91))
        self.assertEqual(urls.findtext("./gameurl1/gameapi_registscorenational"),
                         "https://127.0.0.1:8765" + route)

    def test_daily_score_probe_returns_empty_rows_and_preserves_inner_ciphertext(self):
        client = self.start(daily_score_block=SCORE_INNER)
        client.request("POST", SCORE_PATH, body=SCORE_REQUEST, headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        self.assertEqual(response.getheader("Content-Type"), "application/octet-stream")
        self.assertEqual((response.status, response.read()), (200, (
            bytes.fromhex("00800100 0000020001000000 60000300") + SCORE_INNER
            + bytes.fromhex("0042020000000000 1042020001000000 2042020000000000 10800100")
        )))

    def test_empty_regulation_probe_accepts_only_the_two_request_shapes(self):
        path = "/nmg-us/replay-probe/gameapi_getregulationdata"
        date = bytes.fromhex("10600200 20261118")
        tail = bytes.fromhex("10800100")
        fields = string_record(0x0020, b"Golfer") + bytes.fromhex("60000300") + SCORE_INNER
        undated = SERVER_TIME_REQUEST.replace(tail, fields + tail)
        dated = undated.replace(tail, date + tail)
        shortest = undated.replace(fields, string_record(0x0020, b"") + fields[-12:])
        longest = dated.replace(fields, string_record(0x0020, b"x" * 55) + pack("<2H", 0x0060, 13) + bytes(48))
        self.assertEqual((len(shortest), len(longest)), (122, 222))
        reply = (bytes.fromhex("00800100 0000020001000000 60000300") + SCORE_INNER
                 + bytes.fromhex("0060020000000000 10800100"))
        client = self.start(daily_score_block=SCORE_INNER, empty_regulations=True)
        for body, status, expected in (
            (undated, 200, reply), (dated, 200, reply), (shortest, 200, reply), (longest, 200, reply),
            (dated.replace(date, bytes.fromhex("10600200 20260230")), 400, b""),
            (dated.replace(date, bytes.fromhex("11600200 20261118")), 400, b""),
            (undated.replace(fields, fields[:-12] + bytes.fromhex("60000400") + bytes(12)), 400, b""),
            (undated.replace(fields, fields[:11] + b"\xff" + fields[12:]), 400, b""),
        ):
            with self.subTest(body=body.hex()):
                client.request("POST", path, body=body, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (status, expected))
        client.request("GET", path)
        response = client.getresponse()
        self.assertEqual((response.status, response.getheader("Allow"), response.read()), (405, "POST", b""))
        inactive = self.start(daily_score_block=SCORE_INNER)
        inactive.request("POST", path, body=undated, headers=SERVER_TIME_HEADERS)
        response = inactive.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))
        with self.assertRaisesRegex(ValueError, "requires --daily-score-block"):
            GolfServer(0, empty_regulations=True)

    def test_empty_regulation_discovery_advertises_the_exact_https_path(self):
        route = "./gameurl1/gameapi_getregulationdata"
        for enabled, scheme in ((False, "http"), (True, "https")):
            document = discovery_document(empty_regulations=enabled).rstrip(b"\0")
            urls = ElementTree.fromstring(b"<fixture>" + document + b"</fixture>")
            self.assertEqual(urls.findtext(route),
                             f"{scheme}://127.0.0.1:8765/nmg-us/replay-probe/gameapi_getregulationdata")

    def test_own_score_probe_advertises_the_exact_https_path(self):
        document = discovery_document(empty_own_score=True).rstrip(b"\0")
        urls = ElementTree.fromstring(b"<fixture>" + document + b"</fixture>")
        self.assertEqual(urls.findtext("./gameurl1/gameapi_getmyscore"),
                         "https://127.0.0.1:8765" + OWN_SCORE_PATH)
        self.assertEqual(urls.findtext("./gameurl1/gameapi_getuserstatus"),
                         "https://127.0.0.1:8765" + USER_STATUS_PATH)

    def test_top_player_and_distribution_advertise_plaintext_score_routes(self):
        for options, scheme in (({}, "http"), ({"empty_own_score": True}, "https"),
                                ({"score_registration": True}, "https")):
            document = discovery_document(**options).rstrip(b"\0")
            urls = ElementTree.fromstring(b"<fixture>" + document + b"</fixture>")
            for path in (TOP_PLAYER_PATH, SCORE_DISTRIBUTION_PATH):
                with self.subTest(options=options, path=path):
                    self.assertEqual(urls.findtext("./gameurl1/" + path.rsplit("/", 1)[1]),
                                     f"{scheme}://127.0.0.1:8765{path}")

    def test_top_player_and_distribution_check_request_fields_and_return_empty_results(self):
        top_small, top_large = top_player_request(b""), top_player_request(b"x" * 1000)
        distribution_small = own_score_request(1, b"Daily_20180914_0_IN", b"")
        distribution_large = own_score_request(1, b"Daily_20180914_-2147483648_OUT", b"x" * 1000)
        self.assertEqual(tuple(map(len, (top_small, top_large, distribution_small, distribution_large))),
                         (410, 1410, 402, 1414))
        client = self.start(empty_own_score=True)
        inactive = self.start()
        for path, bodies, invalid, record in (
            (TOP_PLAYER_PATH, (top_small, top_large),
             (top_small.replace(bytes.fromhex("20180914"), bytes.fromhex("20180931")),
              top_small.replace(bytes.fromhex("1040020009000000"), bytes.fromhex("104002000a000000")),
              top_small.replace(bytes.fromhex("004a020000000000"), bytes.fromhex("004a020001000000"))),
             "7049020000000000"),
            (SCORE_DISTRIBUTION_PATH, (distribution_small, distribution_large),
             (own_score_request(0, b"Daily_20180914_0_IN"),
              own_score_request(1, b"OneHole_20180914_0_1"),
              own_score_request(1, b"Daily_20180914_-2147483649_OUT")),
             "504902005b5d0000"),
        ):
            expected = bytes.fromhex("00800100 0000020001000000 830003006c6f63616c000000 " + record + " 10800100")
            for body, status in [(body, 200) for body in bodies] + [(body, 400) for body in invalid]:
                with self.subTest(path=path, length=len(body), status=status):
                    client.request("POST", path, body=body, headers=SERVER_TIME_HEADERS)
                    response = client.getresponse()
                    self.assertEqual((response.status, response.read()), (status, expected if status == 200 else b""))
            client.request("GET", path)
            response = client.getresponse()
            self.assertEqual((response.status, response.getheader("Allow"), response.read()), (405, "POST", b""))
            inactive.request("POST", path, body=bodies[0], headers=SERVER_TIME_HEADERS)
            response = inactive.getresponse()
            self.assertEqual((response.status, response.read()), (404, b""))

    def test_daily_distribution_replays_the_saved_score_for_the_queried_group(self):
        group = b"Daily_20180914_1_OUT"
        other_groups = (b"Daily_20180914_1_IN", b"Daily_20180914_2_OUT", b"Daily_20180915_1_OUT")
        empty = bytes.fromhex("00800100 0000020001000000 830003006c6f63616c000000 504902005b5d0000 10800100")
        prefix = bytes.fromhex("00800100 0000020001000000 830003006c6f63616c000000")
        term = bytes.fromhex("10800100")
        with TemporaryDirectory() as directory:
            db = Path(directory) / "scores.sqlite"
            writer = self.start(score_db=db)
            writer.request("POST", REGISTER_TARGETS[1], body=registration_request(1, -(1 << 31), group=group),
                           headers=SERVER_TIME_HEADERS)
            response = writer.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            reader = self.start(score_db=db)
            for requested in (group, *other_groups):
                payload = own_score_request(1, requested)
                expected = (prefix + string_record(0x4950, b'[{"num":"1","score":"-2147483648"}]') + term
                            if requested == group else empty)
                reader.request("POST", SCORE_DISTRIBUTION_PATH, body=payload, headers=SERVER_TIME_HEADERS)
                response = reader.getresponse()
                self.assertEqual((response.status, response.read()), (200, expected))

    def test_score_board_uses_the_session_account_query_prefix(self):
        for enabled, path in ((False, SCORE_PATH), (True, SCORE_BOARD_PREFIX)):
            with self.subTest(enabled=enabled):
                document = discovery_document(daily_scores=True, empty_own_score=enabled).rstrip(b"\0")
                urls = ElementTree.fromstring(b"<fixture>" + document + b"</fixture>")
                self.assertEqual(urls.findtext("./gameurl1/gameapi_getscorelist"),
                                 "https://127.0.0.1:8765" + path)

    def test_score_board_replays_no_scores_for_all_session_variants(self):
        client = self.start(empty_own_score=True, daily_score_block=SCORE_INNER)
        for counter, selector, group, count, token in (
            (0, 0, b"OneHole_20261118_0_1", 100, b"abc"),
            (-2147483648, 1, b"Daily_20261118_0_IN", 200, b""),
            (2147483647, 2, b"LongDriveContest_20261118_-2147483648_-2147483648", 5, b"x" * 1000),
        ):
            with self.subTest(selector=selector):
                target = SCORE_BOARD_TARGET.replace("n=1&", f"n={counter}&")
                client.request("POST", target, body=score_board_request(selector, group, count, token),
                               headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()),
                                 (200, bytes.fromhex("00800100 0000020010030090 10800100")))
        for unsigned_target in (SCORE_PATH, SCORE_BOARD_PREFIX):
            client.request("POST", unsigned_target, body=SCORE_REQUEST, headers=SERVER_TIME_HEADERS)
            response = client.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(len(response.read()), 52)

    def test_score_board_rejects_other_accounts_and_invalid_window_records(self):
        client = self.start(empty_own_score=True)
        request = score_board_request(0, b"OneHole_20261118_0_1", 100)
        for target, body in (
            (SCORE_BOARD_TARGET.replace("5932", "6932"), request),
            (SCORE_BOARD_TARGET.replace("n=1", "n=2147483648"), request),
            (SCORE_BOARD_TARGET + "&extra=1", request),
            (SCORE_BOARD_TARGET, score_board_request(0, b"OneHole_20261118_0_1", 0)),
            (SCORE_BOARD_TARGET, score_board_request(0, b"OneHole_20261118_0_1", 0xFFFFFFFF)),
            (SCORE_BOARD_TARGET, score_board_request(0, b"Daily_20261118_0_IN", 100)),
            (SCORE_BOARD_TARGET, request.replace(bytes.fromhex("0040020001000000"),
                                                 bytes.fromhex("0040020002000000"))),
        ):
            client.request("POST", target, body=body, headers=SERVER_TIME_HEADERS)
            response = client.getresponse()
            self.assertEqual((response.status, response.read()), (400, b""))
        client.request("GET", SCORE_BOARD_TARGET)
        response = client.getresponse()
        self.assertEqual((response.status, response.getheader("Allow"), response.read()), (405, "POST", b""))

    def test_empty_finish_and_sign_boards_require_the_board_fixture(self):
        finish_path = "/nmg-us/replay-probe/gameapi_getfinishboardlist"
        sign_path = "/nmg-us/replay-probe/gameapi_getsignboardlist"
        tail = bytes.fromhex("10800100")
        finish_request_tail = bytes.fromhex("00650100 2065020020251118")

        def finish_body(name, cipher):
            payload = (string_record(0x0020, name) + pack("<2H", 0x0060, 1 + len(cipher) // 4) + cipher
                       + finish_request_tail)
            return SERVER_TIME_REQUEST.replace(tail, payload + tail)

        def sign_body(token):
            return SERVER_TIME_REQUEST.replace(
                tail, bytes.fromhex("80004100") + bytes(256) + string_record(0x0083, token) + tail
            )

        disabled = self.start()
        for target, body in ((finish_path, finish_body(b"", SCORE_INNER)), (sign_path, sign_body(b""))):
            disabled.request("POST", target, body=body, headers=SERVER_TIME_HEADERS)
            response = disabled.getresponse()
            self.assertEqual((response.status, response.read()), (404, b""))

        client = self.start(empty_board_block=SCORE_INNER)
        finish_reply = (bytes.fromhex("00800100 0000020001000000 60000300") + SCORE_INNER
                        + bytes.fromhex("40650100 60650100 8065020000000000 "
                                        "50650100 70650100 9065020000000000 10800100"))
        sign_reply = bytes.fromhex("00800100 0000020001000000 830003006c6f63616c000000 0278020000000000 10800100")
        for target, body, size, expected in (
            (finish_path, finish_body(b"", SCORE_INNER), 134, finish_reply),
            (finish_path, finish_body(b"a" * 55, SCORE_INNER * 6), 226, finish_reply),
            (sign_path, sign_body(b""), 370, sign_reply),
            (sign_path, sign_body(b"x" * 1000), 1370, sign_reply),
        ):
            with self.subTest(path=target, size=size):
                self.assertEqual(len(body), size)
                client.request("POST", target, body=body, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (200, expected))

        invalid_date = finish_body(b"Golfer", SCORE_INNER).replace(bytes.fromhex("20251118"), bytes.fromhex("20250230"))
        for target, body in (
            (finish_path, invalid_date),
            (finish_path, finish_body(b"Golfer", SCORE_INNER + bytes(4))),
            (sign_path, sign_body(b"abc").replace(b"abc\0", b"abcd")),
        ):
            client.request("POST", target, body=body, headers=SERVER_TIME_HEADERS)
            response = client.getresponse()
            self.assertEqual((response.status, response.read()), (400, b""))

        for target in (finish_path, sign_path):
            client.request("GET", target)
            response = client.getresponse()
            self.assertEqual((response.status, response.getheader("Allow"), response.read()), (405, "POST", b""))

        for enabled in (False, True):
            plain = discovery_document(empty_boards=enabled).rstrip(b"\0")
            urls = ElementTree.fromstring(b"<fixture>" + plain + b"</fixture>")
            scheme = "https" if enabled else "http"
            for endpoint in (finish_path, sign_path):
                self.assertEqual(urls.findtext("./gameurl1/" + endpoint.rsplit("/", 1)[1]),
                                 f"{scheme}://127.0.0.1:8765{endpoint}")

    def test_score_board_requires_opt_in(self):
        client = self.start(daily_score_block=SCORE_INNER)
        client.request("POST", SCORE_BOARD_TARGET, body=score_board_request(0, b"OneHole_20261118_0_1", 100),
                       headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

    def test_character_assignment_matches_guest_post_contract(self):
        path = "/nmg-us/replay-probe/gameapi_assignmentcharactordownload"
        body = SERVER_TIME_REQUEST.replace(bytes.fromhex("10800100"),
                                           NOTICE_FIELDS[:268] + bytes.fromhex("10800100"))
        disabled = self.start()
        disabled.request("POST", path, body=body, headers=SERVER_TIME_HEADERS)
        response = disabled.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

        client = self.start(empty_own_score=True)
        expected = bytes.fromhex("00800100 0000020001000000 830003006c6f63616c000000 10800100")
        context = pack("<2H", 0x0080, 65) + bytes(256)
        for token in (b"", b"abc", b"x" * 1000):
            with self.subTest(token_length=len(token)):
                fields = context + string_record(0x0083, token) + bytes.fromhex("10800100")
                request = SERVER_TIME_REQUEST.replace(bytes.fromhex("10800100"), fields)
                client.request("POST", path, body=request, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.getheader("Content-Type"), response.read()),
                                 (200, "application/octet-stream", expected))
        for invalid in (
            body.replace(b"abc\0", b"abcd"),
            body.replace(string_record(0x0083, b"abc"), string_record(0x0083, b"x" * 1001)),
            body.replace(bytes.fromhex("80004100"), bytes.fromhex("80004000")),
            body.replace(bytes.fromhex("10800100"), pack("<2HI", 0x2500, 2, 0) + bytes.fromhex("10800100")),
        ):
            client.request("POST", path, body=invalid, headers=SERVER_TIME_HEADERS)
            response = client.getresponse()
            self.assertEqual((response.status, response.read()), (400, b""))
        client.request("GET", path)
        response = client.getresponse()
        self.assertEqual((response.status, response.getheader("Allow"), response.read()), (405, "POST", b""))

    def test_course_world_assignment_checks_the_local_session_target_and_reply(self):
        prefix = "/nmg-us/replay-probe/gameapi_assignmentcourseworld?account="
        path = prefix + "5932163534510096385&n=28&s=1"
        context = NOTICE_FIELDS[:260]
        end = bytes.fromhex("10800100")
        body = SERVER_TIME_REQUEST.replace(end, context + string_record(0x0083, b"abc") + end)
        guest_sized_body = body.replace(string_record(0x0083, b"abc"), string_record(0x0083, b"LocalSession12"))
        self.assertEqual(len(guest_sized_body), 382)
        client = self.start(empty_own_score=True)
        reply = bytes.fromhex("00800100 0000020001000000 10800100")
        for target, request, expected in (
            (path, body, 200),
            (path, guest_sized_body, 200),
            (path.replace("n=28", "n=-2147483648"), body, 200),
            (path.replace("n=28", "n=2147483648"), body, 400),
            (path.replace("5932163534510096385", "5932163534510096386"), body, 400),
            (path, body.replace(b"abc\0", b"abcd"), 400),
            (path, body.replace(bytes.fromhex("80004100"), bytes.fromhex("80004000")), 400),
        ):
            with self.subTest(target=target, expected=expected):
                client.request("POST", target, body=request, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (expected, reply if expected == 200 else b""))
        client.request("GET", path)
        response = client.getresponse()
        self.assertEqual((response.status, response.getheader("Allow"), response.read()), (405, "POST", b""))

        disabled = self.start()
        disabled.request("POST", path, body=body, headers=SERVER_TIME_HEADERS)
        response = disabled.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

        plain = discovery_document(score_registration=True).rstrip(b"\0")
        urls = ElementTree.fromstring(b"<fixture>" + plain + b"</fixture>")
        self.assertEqual(urls.findtext("./gameurl1/gameapi_assignmentcourseworld"), f"https://127.0.0.1:8765{prefix}")

    def test_character_download_count_checks_account_and_replays_two_empty_counts(self):
        bare = "/nmg-us/replay-probe/gameapi_getcountcharactordownload?account="
        path = bare + "5932163534510096385&n=-2147483648&s=1"
        tail = bytes.fromhex("10800100")
        context = bytes.fromhex("80004100") + bytes(256)
        counts = bytes.fromhex("0777020000000000 0877020000000000")
        expected = bytes.fromhex("00800100 0000020001000000 830003006c6f63616c000000") + counts + tail

        def body(token, account=LOGIN_ACCOUNT):
            records = context + string_record(0x0083, token) + string_record(0x7704, account) + tail
            return SERVER_TIME_REQUEST.replace(tail, records)

        disabled = self.start()
        disabled.request("POST", path, body=body(b""), headers=SERVER_TIME_HEADERS)
        response = disabled.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

        client = self.start(empty_own_score=True)
        for target, token, size in ((bare, b"", 394), (path, b"x" * 1000, 1394)):
            request = body(token)
            self.assertEqual(len(request), size)
            client.request("POST", target, body=request, headers=SERVER_TIME_HEADERS)
            response = client.getresponse()
            self.assertEqual((response.status, response.read()), (200, expected))

        for invalid_target in (path.replace("6385&", "6386&"), path.replace("-2147483648", "2147483648")):
            client.request("POST", invalid_target, body=body(b""), headers=SERVER_TIME_HEADERS)
            response = client.getresponse()
            self.assertEqual((response.status, response.read()), (400, b""))

        for invalid in (
            body(b"", b"5932163534510096386"),
            body(b"x" * 1001),
            body(b"abc").replace(bytes.fromhex("04770600"), bytes.fromhex("04770500")),
        ):
            client.request("POST", path, body=invalid, headers=SERVER_TIME_HEADERS)
            response = client.getresponse()
            self.assertEqual((response.status, response.read()), (400, b""))
        client.request("GET", path)
        response = client.getresponse()
        self.assertEqual((response.status, response.getheader("Allow"), response.read()), (405, "POST", b""))

        for options in ({}, {"empty_own_score": True}, {"score_registration": True}):
            xml = discovery_document(**options).rstrip(b"\0")
            root = ElementTree.fromstring(b"<fixture>" + xml + b"</fixture>")
            scheme = "https" if options else "http"
            self.assertEqual(root.findtext("./gameurl1/gameapi_getcountcharactordownload"),
                             f"{scheme}://127.0.0.1:8765{bare if options else bare.split('?')[0]}")

    def test_character_assignment_uses_the_plaintext_builder_in_score_discovery(self):
        key = "./gameurl1/gameapi_assignmentcharactordownload"
        for options in ({}, {"empty_own_score": True}, {"score_registration": True}):
            with self.subTest(options=options):
                xml = discovery_document(**options).rstrip(b"\0")
                root = ElementTree.fromstring(b"<fixture>" + xml + b"</fixture>")
                scheme = "https" if options else "http"
                self.assertEqual(root.findtext(key),
                                 scheme + "://127.0.0.1:8765/nmg-us/replay-probe/gameapi_assignmentcharactordownload")

    def test_score_registration_discovery_advertises_each_account_prefix(self):
        plain = discovery_document(score_registration=True).rstrip(b"\0")
        urls = ElementTree.fromstring(b"<fixture>" + plain + b"</fixture>")
        for operation, target in zip(REGISTER_OPERATIONS, REGISTER_TARGETS):
            self.assertEqual(urls.findtext(f"./gameurl1/{operation}"),
                             "https://127.0.0.1:8765" + target.split("?")[0] + "?account=")

    def test_score_registration_persists_and_replays_each_variant(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "scores.sqlite"
            first = self.start(score_db=database)
            first.request("POST", REGISTER_TARGETS[0], body=registration_request(0, 3),
                          headers=SERVER_TIME_HEADERS)
            response = first.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            for selector, score in enumerate((-2, 3, 32530)):
                first.request("POST", REGISTER_TARGETS[selector], body=registration_request(selector, score),
                              headers=SERVER_TIME_HEADERS)
                response = first.getresponse()
                expected = bytes.fromhex("00800100 0000020001000000 830003006c6f63616c000000")
                if selector < 2:
                    expected += bytes.fromhex("7042020001000000")
                self.assertEqual((response.status, response.read()), (200, expected + bytes.fromhex("a0420100 10800100")))
            first.close()
            # A second listener opens the same file and has no access to the first one's memory.
            second = self.start(score_db=database)
            for selector, score in enumerate((-2, 3, 32530)):
                group = REGISTER_GROUPS[selector]
                values = pack("<2Hq", 0x4500, 3, score)
                if selector < 2:
                    values += pack("<2Hq", 0x4501, 3, 21)
                own = (bytes.fromhex("00800100 0000020001000000 830003006c6f63616c000000"
                                     "0042020001000000 30420100 7042020001000000")
                       + values + bytes.fromhex("40420100 10800100"))
                board = (bytes.fromhex("00800100 0000020001000000 830003006c6f63616c000000"
                                       "0042020001000000 1042020001000000 50420100 7042020001000000")
                         + values + string_record(0x0020, b"Golfer") + string_record(0x0084, LOGIN_ACCOUNT)
                         + bytes.fromhex("60420100 10800100"))
                for path, body, expected in (
                    (OWN_SCORE_PATH, own_score_request(selector, group), own),
                    (SCORE_BOARD_TARGET, score_board_request(selector, group, 5), board),
                ):
                    second.request("POST", path, body=body, headers=SERVER_TIME_HEADERS)
                    response = second.getresponse()
                    self.assertEqual((response.status, response.read()), (200, expected))

    def test_one_hole_registration_keeps_the_lower_primary_score(self):
        with TemporaryDirectory() as directory:
            client = self.start(score_db=Path(directory) / "scores.sqlite")
            for score in (3, -2, 4):
                client.request("POST", REGISTER_TARGETS[0], body=registration_request(0, score),
                               headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual(response.status, 200)
                response.read()

            group = REGISTER_GROUPS[0]
            for target, body in ((OWN_SCORE_PATH, own_score_request(0, group)),
                                 (SCORE_BOARD_TARGET, score_board_request(0, group, 5))):
                with self.subTest(target=target):
                    client.request("POST", target, body=body, headers=SERVER_TIME_HEADERS)
                    response = client.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertIn(pack("<2Hq", 0x4500, 3, -2), response.read())

    def test_score_registration_rejects_shape_and_account_mismatches(self):
        with TemporaryDirectory() as directory:
            client = self.start(score_db=Path(directory) / "scores.sqlite")
            request = registration_request(0, -1)
            for path, body in (
                (REGISTER_TARGETS[0].replace("5932", "6932"), request),
                (REGISTER_TARGETS[1], request),
                (REGISTER_TARGETS[0], request.replace(b"\x06\x46\x02\x00", b"\x07\x46\x02\x00")),
                (REGISTER_TARGETS[0], request.replace(b"Golfer@", b"\nolfer@")),
            ):
                client.request("POST", path, body=body, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (400, b""))
            client.request("POST", OWN_SCORE_PATH, body=own_score_request(0, REGISTER_GROUPS[0]),
                           headers=SERVER_TIME_HEADERS)
            response = client.getresponse()
            self.assertEqual((response.status, response.read()),
                             (200, bytes.fromhex("00800100 0000020010030090 10800100")))

    def test_score_registration_requires_a_database(self):
        client = self.start(empty_own_score=True, login_completion=True)
        client.request("POST", REGISTER_TARGETS[0], body=registration_request(0, -1), headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

    def test_event_schedule_discovery_uses_the_board_url(self):
        plain = discovery_document(event_schedule=True).rstrip(b"\0")
        urls = ElementTree.fromstring(b"<fixture>" + plain + b"</fixture>")
        self.assertEqual(urls.findtext("./gameurl1/gameapi_getboardlist"), "https://127.0.0.1:8765" + BOARD_PATH)

    def test_daily_rivals_require_the_configured_event_and_replay_zero_rows(self):
        path = RIVAL_LIST_PATH
        group = b"Daily_20261118_1_OUT"
        day = datetime(2026, 11, 18, 13)
        expected = bytes.fromhex(
            "00800100 0000020001000000 830003006c6f63616c000000 3049020000000000 10800100"
        )
        def request(token=b"local", label=group, detail=b""):
            return rival_request(label, token, detail)

        client = self.start(server_time=day, event_group=group.decode("ascii"))
        for body, status in (
            (request(b""), 200),
            (request(b"x" * 1000, detail=b"y" * 127), 200),
            (request(token=b"x" * 1001), 400),
            (request(label=b"Daily_20261118_1_IN"), 400),
            (request().replace(bytes.fromhex("004a020001000000"), bytes.fromhex("004a020002000000")), 400),
            (request().replace(bytes.fromhex("41410300"), bytes.fromhex("41410400")), 400),
            (request()[:-1], 400),
        ):
            with self.subTest(length=len(body), status=status):
                client.request("POST", path, body=body, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (status, expected if status == 200 else b""))
        client.request("GET", path)
        response = client.getresponse()
        self.assertEqual((response.status, response.getheader("Allow"), response.read()), (405, "POST", b""))

        for group_option in (None, "OneHole_20261118_0_1"):
            inactive = self.start(server_time=day, event_group=group_option)
            inactive.request("POST", path, body=request(), headers=SERVER_TIME_HEADERS)
            response = inactive.getresponse()
            self.assertEqual((response.status, response.read()), (404, b""))

        for enabled, scheme in ((False, "http"), (True, "https")):
            plain = discovery_document(event_schedule=enabled).rstrip(b"\0")
            urls = ElementTree.fromstring(b"<fixture>" + plain + b"</fixture>")
            self.assertEqual(urls.findtext("./gameurl1/gameapi_getrivallist"),
                             f"{scheme}://127.0.0.1:8765{path}")

    def test_event_schedule_returns_only_the_configured_group(self):
        day = datetime(2026, 11, 18, 13)
        for selector, group in enumerate(REGISTER_GROUPS):
            with self.subTest(selector=selector):
                client = self.start(event_group=group.decode(), server_time=day, empty_board_block=SCORE_INNER)
                prefix = bytes.fromhex("00800100 0000020001000000 830003006c6f63616c000000")
                row = (bytes.fromhex("20410100") + string_record(0x4140, group)
                       + bytes.fromhex("50410100 774103002026111800000000 784103002026111823595900 30410100"))
                for requested in (selector, (selector + 1) % 3):
                    client.request("POST", BOARD_PATH, body=schedule_request(requested), headers=SERVER_TIME_HEADERS)
                    response = client.getresponse()
                    board = bytes.fromhex("0041020001000000 10410100") + row if requested == selector else (
                        bytes.fromhex("0041020000000000 10410100"))
                    self.assertEqual((response.status, response.read()),
                                     (200, prefix + board + bytes.fromhex("10800100")))
                client.request("POST", BOARD_PATH, body=BOARD_REQUEST, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (200, (
                    bytes.fromhex("00800100 0000020001000000 60000300") + SCORE_INNER
                    + bytes.fromhex("00410100 1041020000000000 10800100")
                )))

    def test_event_schedule_validates_the_window_and_requires_a_matching_server_date(self):
        day = datetime(2026, 11, 18, 13)
        with self.assertRaises(ValueError):
            GolfServer(0, event_group="OneHole_20261119_0_1", server_time=day)
        client = self.start(event_group="OneHole_20261118_0_1", server_time=day)
        for body, status in (
            (schedule_request(0, course=1), 200),
            (schedule_request(1, course=1, limit=6), 200),
            (schedule_request(0, course=1, limit=6), 400),
            (schedule_request(5), 400),
        ):
            client.request("POST", BOARD_PATH, body=body, headers=SERVER_TIME_HEADERS)
            response = client.getresponse()
            self.assertEqual(response.status, status)
            response.read()

    def test_event_schedule_can_advertise_a_round_and_its_daily_group(self):
        day = datetime(2026, 11, 18, 13)
        one_hole = tuple(f"OneHole_20261118_0_{hole}".encode("ascii") for hole in range(1, 10))
        daily = (b"Daily_20261118_0_OUT", b"Daily_20261118_0_IN")
        groups = (*one_hole, *daily, one_hole[0])
        client = self.start(event_group=tuple(group.decode("ascii") for group in groups), server_time=day)
        prefix = bytes.fromhex("00800100 0000020001000000 830003006c6f63616c000000")
        end = bytes.fromhex("10800100")
        for selector, rows in enumerate((one_hole, daily, ())):
            with self.subTest(selector=selector):
                client.request("POST", BOARD_PATH, body=schedule_request(selector), headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                expected = prefix + pack("<2HI2H", 0x4100, 2, len(rows), 0x4110, 1)
                for group in rows:
                    expected += (bytes.fromhex("20410100") + string_record(0x4140, group)
                                 + bytes.fromhex("50410100 774103002026111800000000 "
                                                 "784103002026111823595900 30410100"))
                self.assertEqual((response.status, response.read()), (200, expected + end))
        for group in (*daily, b"Daily_20261118_1_OUT"):
            expected_status = 200 if group in daily else 400
            client.request("POST", RIVAL_LIST_PATH, body=rival_request(group), headers=SERVER_TIME_HEADERS)
            response = client.getresponse()
            self.assertEqual(response.status, expected_status)
            response.read()

    def test_event_schedule_rejects_more_than_eighteen_rows_for_a_selector(self):
        groups = tuple(f"OneHole_20261118_0_{hole}" for hole in range(1, 20))
        with self.assertRaisesRegex(ValueError, "18 event groups"):
            GolfServer(0, event_group=groups, server_time=datetime(2026, 11, 18))

    def test_character_board_checks_its_selector_five_layout_and_returns_no_rows(self):
        path = "/nmg-us/replay-probe/gameapi_getboardlistcharactordownload"
        end = bytes.fromhex("10800100")
        board_fields = bytes.fromhex("404a020001000000 0040020001000000 1040020002000000")
        window = bytes.fromhex("104a020001000000") + board_fields[8:]
        short = SERVER_TIME_REQUEST.replace(
            end, NOTICE_FIELDS[:260] + string_record(0x0083, b"") + board_fields + end
        )
        longest = short.replace(string_record(0x0083, b""), string_record(0x0083, b"x" * 1000))
        longest = longest.replace(end, window + end)
        self.assertEqual(tuple(map(len, (short, longest))), (394, 1418))
        expected = bytes.fromhex(
            "00800100 0000020001000000 830003006c6f63616c000000 0041020000000000 10410100 10800100"
        )
        date = datetime(2026, 11, 18, 13)
        client = self.start(empty_board_block=SCORE_INNER, server_time=date, event_group="OneHole_20261118_0_1")
        for body, status in (
            (short, 200),
            (longest, 200),
            (short.replace(board_fields, board_fields[:12] + bytes(4) + board_fields[16:]), 400),
            (longest.replace(window, window[:-4] + bytes(4)), 400),
            (longest.replace(window, window[:4] + bytes(4) + window[8:]), 400),
            (schedule_request(5), 400),
        ):
            with self.subTest(length=len(body), status=status):
                client.request("POST", path, body=body, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (status, expected if status == 200 else b""))
        client.request("GET", path)
        response = client.getresponse()
        self.assertEqual((response.status, response.getheader("Allow"), response.read()), (405, "POST", b""))
        inactive = self.start()
        inactive.request("POST", path, body=short, headers=SERVER_TIME_HEADERS)
        response = inactive.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))
        for enabled, scheme in ((False, "http"), (True, "https")):
            plain = discovery_document(empty_boards=enabled).rstrip(b"\0")
            urls = ElementTree.fromstring(b"<fixture>" + plain + b"</fixture>")
            self.assertEqual(urls.findtext("./gameurl1/gameapi_getboardlistcharactordownload"),
                             f"{scheme}://127.0.0.1:8765{path}")

    def test_own_score_login_enables_session_gate_and_supplies_echo_records(self):
        client = self.start(empty_own_score=True, login_completion=True)
        client.request("POST", LOGIN_TARGET, body=LOGIN_REQUEST, headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        expected = bytes.fromhex("00800100 0000020001000000 2020020001000000 3220020001000000")
        self.assertEqual((response.status, response.read()),
                         (200, expected + USER_STATUS_SESSION + bytes.fromhex("10800100")))

    def test_own_score_user_status_replay_checks_echo_and_finishes(self):
        client = self.start(empty_own_score=True)
        client.request("POST", USER_STATUS_PATH, body=USER_STATUS_REQUEST, headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        self.assertEqual((response.status, response.read()),
                         (200, bytes.fromhex("00800100 0000020001000000 10800100")))
        for request in (
            USER_STATUS_REQUEST.replace(USER_STATUS_SESSION, USER_STATUS_SESSION[:-1] + b"\x01"),
            USER_STATUS_REQUEST.replace(bytes.fromhex("0025020000000000"), bytes.fromhex("0025020001000000")),
        ):
            client.request("POST", USER_STATUS_PATH, body=request, headers=SERVER_TIME_HEADERS)
            response = client.getresponse()
            self.assertEqual((response.status, response.read()), (400, b""))

    def test_user_status_probe_requires_opt_in(self):
        client = self.start()
        client.request("POST", USER_STATUS_PATH, body=USER_STATUS_REQUEST, headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

    def test_own_score_probe_replays_no_score_for_each_variant(self):
        client = self.start(empty_own_score=True)
        for selector, group, token in (
            (0, b"OneHole_20261118_0_1", b""),
            (1, b"Daily_20261118_0_IN", b"abc"),
            (1, b"Daily_20261118_0_OUT", b"abc"),
            (2, b"LongDriveContest_20261118_-2147483648_-2147483648", b"x" * 1000),
        ):
            with self.subTest(selector=selector, group=group):
                client.request("POST", OWN_SCORE_PATH, body=own_score_request(selector, group, token),
                               headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual(response.getheader("Content-Type"), "application/octet-stream")
                self.assertEqual((response.status, response.read()),
                                 (200, bytes.fromhex("00800100 0000020010030090 10800100")))

    def test_own_score_probe_rejects_mismatched_and_malformed_requests(self):
        client = self.start(empty_own_score=True)
        valid = own_score_request(0, b"OneHole_20261118_0_1")
        for request in (
            own_score_request(0, b"Daily_20261118_0_IN"),
            own_score_request(1, b"Daily_20261118_0_score"),
            own_score_request(1, b"Daily_20261118_2147483648_OUT"),
            own_score_request(3, b"OneHole_20261118_0_1"),
            valid.replace(b"abc\0", b"abcd"),
            valid[:-1],
        ):
            with self.subTest(size=len(request)):
                client.request("POST", OWN_SCORE_PATH, body=request, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (400, b""))
        client.request("GET", OWN_SCORE_PATH)
        response = client.getresponse()
        self.assertEqual((response.status, response.getheader("Allow"), response.read()), (405, "POST", b""))

    def test_own_score_probe_requires_opt_in(self):
        client = self.start()
        client.request("POST", OWN_SCORE_PATH, body=own_score_request(0, b"OneHole_20261118_0_1"),
                       headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

    def test_daily_score_probe_rejects_other_variants_and_bad_framing(self):
        client = self.start(daily_score_block=SCORE_INNER)
        for request in (
            SCORE_REQUEST.replace(b"_score\0", b"_holescore\0"),
            SCORE_REQUEST.replace(b"Daily_20261118_00_score\0", b"Daily_2026xx18_00_score\0"),
            SCORE_REQUEST.replace(bytes.fromhex("10400200e8030000"), bytes.fromhex("1040020012000000")),
            SCORE_REQUEST.replace(b"\x60\x00\x03\x00" + bytes(range(8)),
                                  b"\x60\x00\x04\x00" + bytes(range(12))),
            SCORE_REQUEST.replace(b"Golfer\0\x01", b"Golfer\0\x02"),
            SCORE_REQUEST[:-1],
        ):
            with self.subTest(length=len(request)):
                client.request("POST", SCORE_PATH, body=request, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (400, b""))
        with self.assertRaises(ValueError):
            GolfServer(0, daily_score_block=b"short")

    def test_login_rejection_requires_opt_in(self):
        client = self.start()
        client.request("POST", LOGIN_TARGET, body=LOGIN_REQUEST, headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

    def test_local_login_completion_uses_the_same_request_contract(self):
        client = self.start(login_completion=True)
        client.request("POST", LOGIN_TARGET, body=LOGIN_REQUEST, headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.read(), bytes.fromhex("008001000000020001000000202002000100000010800100"))
        client.request("POST", LOGIN_TARGET,
                       body=LOGIN_REQUEST.replace(b"GolfLocalProbe", b"NotALocalProbe"),
                       headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (400, b""))

    def test_login_reply_modes_are_mutually_exclusive(self):
        with self.assertRaisesRegex(ValueError, "one login reply"):
            GolfServer(0, login_rejection=True, login_completion=True)

    def test_login_rejection_replays_the_gate_value(self):
        client = self.start(login_rejection=True)
        client.request("POST", LOGIN_TARGET, body=LOGIN_REQUEST, headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        self.assertEqual(response.getheader("Content-Type"), "application/octet-stream")
        self.assertEqual((response.status, response.read()), (200, bytes.fromhex(
            "00800100 0000020001000000 2020020004000000 10800100"
        )))

    def test_login_rejection_requires_the_local_account_and_probe_code(self):
        client = self.start(login_rejection=True)
        for target, body in (
            (LOGIN_TARGET, LOGIN_REQUEST.replace(b"GolfLocalProbe", b"GolfOtherProbe")),
            (LOGIN_TARGET, LOGIN_REQUEST.replace(LOGIN_ACCOUNT, b"6932163534510096385")),
            (LOGIN_TARGET.replace("5932", "6932"), LOGIN_REQUEST),
            (LOGIN_TARGET+"&extra=1", LOGIN_REQUEST),
            (LOGIN_TARGET.replace("n=1", "n=2147483648"), LOGIN_REQUEST),
            (LOGIN_TARGET, LOGIN_REQUEST[:-1]),
        ):
            with self.subTest(target=target, size=len(body)):
                client.request("POST", target, body=body, headers=SERVER_TIME_HEADERS)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (400, b""))

    def test_empty_service_entitlements(self):
        client = self.start()
        client.request("GET", "/v1/users/me/entitlements?entitlement_type=service")
        response = client.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/json")
        self.assertEqual(json.load(response), {"size": 0, "entitlements": []})

    def test_synthetic_account_friend_list_is_empty(self):
        client = self.start()
        client.request("GET", "/v1/users/5932163534510096385/friendList"
                       "?friendStatus=friend&limit=2000&presenceType=incontext")
        response = client.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/json")
        self.assertEqual(json.load(response), {"friendList": []})

    def test_unknown_account_friend_list_returns_not_found(self):
        client = self.start()
        client.request("GET", "/v1/users/1/friendList"
                       "?friendStatus=friend&limit=2000&presenceType=incontext")
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

    def test_default_store_root_returns_empty_catalog(self):
        client = self.start()
        client.request("GET", "/v1/users/me/container/?size=128&serviceLabel=0")
        response = client.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/json")
        self.assertEqual(json.load(response), [])

    def test_store_label_batch_requires_catalog_data(self):
        client = self.start()
        client.request("GET", "/v1/users/me/container/sample-a:sample-b?size=128&serviceLabel=0")
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))
        client.request("GET", "/v1/users/me/container/EN00020000000000?size=128&serviceLabel=0")
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

    def test_store_catalog_returns_products_in_requested_order(self):
        client = self.start(catalog_fixture=True)
        labels = ("EN00020000000000", "EN00010000000000",
                  *(f"EN000000000000{i:02d}" for i in range(4, 16)))
        client.request("GET", f"/v1/users/me/container/{':'.join(labels)}?size=128&serviceLabel=0")
        response = client.getresponse()
        self.assertEqual((response.status, response.getheader("Content-Type")), (200, "application/json"))
        self.assertEqual(json.load(response), [
            {"container_type": "product", "label": label, "skus": [
                {"label": "LOCAL_" + label, "price": 0, "display_price": "",
                 "is_purchaseable": False, "use_count": 0}
            ]} for label in labels
        ])

    def test_store_catalog_rejects_unknown_labels_and_query_variants(self):
        client = self.start(catalog_fixture=True)
        prefix = "/v1/users/me/container/"
        query = "?size=128&serviceLabel=0"
        label = "EN00000000000001"
        for target in (prefix + label + ":EN00000000000030" + query,
                       prefix + label + ":" + query,
                       prefix + ":".join([label] * 33) + query,
                       prefix + label + query.replace("128", "129"),
                       prefix + label + query.replace("=0", "=1")):
            with self.subTest(target=target):
                client.request("GET", target)
                response = client.getresponse()
                self.assertEqual((response.status, response.read()), (404, b""))
        client.request("POST", prefix + label + query)
        response = client.getresponse()
        self.assertEqual((response.status, response.getheader("Allow"), response.read()), (405, "GET", b""))

    def test_entitlement_consumption_is_unimplemented(self):
        client = self.start()
        client.request("PUT", "/v1/users/me/entitlements/1234", body=b'{"use_count":1}',
                       headers={"Content-Type": "application/json; charset=utf-8"})
        response = client.getresponse()
        self.assertEqual((response.status, response.read()), (404, b""))

    def test_ticket_grant_replay_consumes_each_label_once(self):
        client = self.start(ticket_grants=True)
        path = "/v1/users/me/entitlements"
        query = "?entitlement_type=service"
        headers = {"Content-Type": "application/json; charset=utf-8"}

        client.request("GET", path + query)
        response = client.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(json.load(response), {"size": 2, "entitlements": [
            {"id": "EN0001", "use_count": 0, "use_limit": 1},
            {"id": "EN0002", "use_count": 0, "use_limit": 10},
        ]})

        client.request("PUT", path + "/EN0002", body=b'{"use_count":10}', headers=headers)
        reply = client.getresponse()
        self.assertEqual((reply.status, reply.read()), (200, b"{}"))
        client.request("PUT", path + "/EN0002", body=b'{"use_count":10}', headers=headers)
        reply = client.getresponse()
        self.assertEqual((reply.status, reply.read()), (409, b""))

        client.request("GET", path + query)
        reply = client.getresponse()
        self.assertEqual(reply.status, 200)
        self.assertEqual(json.load(reply)["entitlements"][1], {"id": "EN0002", "use_count": 10, "use_limit": 0})

    def test_ticket_grant_replay_rejects_other_labels_and_amounts(self):
        client = self.start(ticket_grants=True)
        path = "/v1/users/me/entitlements/"
        headers = {"Content-Type": "application/json; charset=utf-8"}
        for key, body, status in (
            ("EN00010000000000", b'{"use_count":1}', 404),
            ("EN0001", b'{"use_count":10}', 409),
            ("EN0001", b'{"use_count":true}', 400),
            ("EN0001", b'{"use_count":1}', 200),
        ):
            with self.subTest(key=key, body=body):
                client.request("PUT", path + key, body=body, headers=headers)
                self.assertEqual(client.getresponse().status, status)

    def test_unknown_path_is_not_forwarded(self):
        client = self.start()
        client.request("GET", "/gameapi_login")
        self.assertEqual(client.getresponse().status, 404)

    def test_rejects_empty_oversized_or_unaligned_fixture(self):
        for body in (b"", b"x", b"x" * (MAX_DISCOVERY_BYTES + 8)):
            with self.subTest(size=len(body)), self.assertRaises(ValueError):
                GolfServer(0, body)


if __name__ == "__main__":
    unittest.main()
