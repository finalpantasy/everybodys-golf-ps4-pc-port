"""Replay the HTTP request shapes documented in analysis/online/protocol.md."""
from datetime import datetime
import http.client
import json
from threading import Thread
import unittest
from unittest.mock import patch

from golf_server import DISCOVERY_PATH, LOOPBACK, MAX_DISCOVERY_BYTES, GolfServer

USER_AGENT = "PS4Application nolib/0.0 (U-UP9000-CUSA04687_00-EVERYBODYSGOLF07/2017022700/1170)"


SERVER_TIME_PATH = "/nmg-us/replay-probe/gameapi_getservertime"
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

    def test_notice_probe_replays_zero_count_for_both_selectors(self):
        client = self.start(empty_notices=True)
        selector_one = bytes.fromhex("5030020001000000")
        selector_zero = bytes.fromhex("5030020000000000")
        for request in (NOTICE_REQUEST, NOTICE_REQUEST.replace(selector_one, selector_zero).replace(
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
            NOTICE_REQUEST.replace(bytes.fromhex("5030020001000000"), bytes.fromhex("5030020002000000")),
            NOTICE_REQUEST.replace(bytes.fromhex("104002000a000000"), bytes.fromhex("104002000b000000")),
            NOTICE_REQUEST + b"x" * 2048,
        ):
            with self.subTest(length=len(request)):
                client.request("POST", NOTICE_PATH, body=request, headers=SERVER_TIME_HEADERS)
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
