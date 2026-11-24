"""Hosting for friends: invite codes, the room key, kept-alive lobby connections, router port
mapping (against fake routers on this PC) and LAN discovery."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import struct
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

import golf_server
from golf_server import GolfHandler, GolfServer
from lobby_registry import LOBBY_PATH, LOBBY_REQUEST
import invite
import online
import time
import portmap


class InviteCodeTests(unittest.TestCase):
    def test_round_trip_and_forgiving_input(self):
        code = invite.encode("192.168.1.20", 48765, 0x5a3f2c1)
        self.assertRegex(code, r"^[0-9A-HJKMNP-TV-Z]{4}(-[0-9A-HJKMNP-TV-Z]{4}){3}$")
        expected = ("192.168.1.20", 48765, 0x5a3f2c1)
        self.assertEqual(invite.decode(code), expected)
        self.assertEqual(invite.decode(" " + code.lower().replace("-", " ") + "\n"), expected)
        self.assertEqual(invite.decode(code.replace("-", "")), expected)
        confusable = code.replace("1", "I").replace("0", "O")
        self.assertEqual(invite.decode(confusable), expected)

    def test_every_single_symbol_typo_is_caught(self):
        code = invite.encode("203.0.113.7", 1, 1).replace("-", "")
        for position in range(16):
            for symbol in invite.ALPHABET:
                if symbol != code[position]:
                    typo = code[:position] + symbol + code[position + 1:]
                    self.assertIsNone(invite.decode(typo), typo)

    def test_rejects_wrong_lengths_letters_and_empty_fields(self):
        for text in ("", "ABCD", "R2M0-255Y-FPT7-WP1", "R2M0-255Y-FPT7-WP1XX", "R2M0-255Y-FPT7-WPU1"):
            self.assertIsNone(invite.decode(text), text)
        with self.assertRaises(ValueError):
            invite.encode("10.0.0.1", 0, 1)
        with self.assertRaises(ValueError):
            invite.encode("10.0.0.1", 1, 1 << invite.KEY_BITS)

    def test_key_text(self):
        key = invite.new_key()
        self.assertEqual(invite.parse_key(invite.key_text(key)), key)
        self.assertRegex(invite.key_text(key), r"^[0-9a-f]{7}$")
        for bad in ("", "0", "fffffff0", "xyz", "8000000"):
            self.assertIsNone(invite.parse_key(bad), bad)

    def test_room_key_is_kept_between_runs(self):
        with TemporaryDirectory() as directory:
            first = online.load_room_key(Path(directory))
            self.assertEqual(online.load_room_key(Path(directory)), first)
            (Path(directory) / "room-key.txt").write_text("junk", encoding="ascii")
            self.assertNotEqual(online.load_room_key(Path(directory)), "junk")


class RoomKeyServerTests(unittest.TestCase):
    def start(self, **options):
        server = GolfServer(0, **options)
        worker = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 3)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def join(self, client, headers=()):
        body = LOBBY_REQUEST.pack(1, 1, 0, bytes(16), b"Golfer".ljust(16, b"\0"))
        client.request("POST", LOBBY_PATH, body=body,
                       headers={"Content-Type": "application/octet-stream", **dict(headers)})
        response = client.getresponse()
        return response.status, response.getheader("Connection"), response.read()

    def test_lobbies_may_face_the_network_only_with_a_key(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            GolfServer(0, bind="0.0.0.0", local_lobbies=True)
        with self.assertRaisesRegex(ValueError, "7 lowercase hex"):
            GolfServer(0, bind="0.0.0.0", local_lobbies=True, room_key="xyz")
        with GolfServer(0, bind="0.0.0.0", local_lobbies=True, room_key="1234abc") as server:
            self.assertEqual(server.server_address[0], "0.0.0.0")

    def test_public_callers_need_the_key_and_home_callers_do_not(self):
        self.assertTrue(golf_server.needs_room_key("8.8.8.8"))
        for address in ("127.0.0.1", "192.168.1.5", "10.1.2.3", "172.16.0.9", "100.101.102.103"):
            self.assertFalse(golf_server.needs_room_key(address), address)

        server = self.start(local_lobbies=True, room_key="1234abc")
        with patch.object(golf_server, "needs_room_key", return_value=True):
            for headers in ((), (("X-Golf-Key", "7654321"),), (("X-Golf-Key", "1234abd"),)):
                client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                self.assertEqual(self.join(client, headers)[0], 403, headers)
                client.close()
            client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            self.assertEqual(self.join(client, (("X-Golf-Key", "1234ABC"),))[0], 200)
            client.close()
            client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            client.request("GET", "/nmg-us/ss.info")
            self.assertEqual(client.getresponse().status, 403)
            client.close()
        client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        self.assertEqual(self.join(client)[0], 200)
        client.close()

    def test_strict_key_asks_home_network_callers_too(self):
        server = self.start(local_lobbies=True, room_key="1234abc", strict_key=True)
        self.assertTrue(server.strict_key)
        client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        self.assertEqual(self.join(client)[0], 200)  # this PC never needs it
        client.close()
        handler = GolfHandler.__new__(GolfHandler)
        for address, key, expected in (("192.168.1.5", None, False), ("192.168.1.5", "1234abc", True),
                                       ("127.0.0.1", None, True)):
            handler.server, handler.client_address = server, (address, 1)
            handler.headers = http.client.HTTPMessage()
            if key is not None:
                handler.headers["X-Golf-Key"] = key
            self.assertEqual(handler.room_key_ok(), expected, (address, key))

    def test_lobby_exchanges_keep_the_connection_open(self):
        server = self.start(local_lobbies=True)
        client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        self.addCleanup(client.close)
        first = self.join(client)
        sock = client.sock
        second = self.join(client)
        self.assertEqual((first[0], first[1], second[0]), (200, "keep-alive", 200))
        self.assertIs(client.sock, sock)
        # Errors still close.
        client.request("POST", LOBBY_PATH, body=b"x", headers={"Content-Type": "application/octet-stream"})
        response = client.getresponse()
        self.assertEqual((response.status, response.getheader("Connection")), (400, "close"))


class FakeRouter(BaseHTTPRequestHandler):
    """A UPnP IGD description and WANIPConnection control point."""
    mappings: dict = {}
    leases: list = []
    permanent_only = True

    def log_message(self, *args):
        pass

    def do_GET(self):
        body = (b'<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0"><device>'
                b"<deviceType>urn:schemas-upnp-org:device:InternetGatewayDevice:1</deviceType><deviceList>"
                b"<device><serviceList><service>"
                b"<serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType>"
                b"<controlURL>/ctl/IPConn</controlURL></service></serviceList></device>"
                b"</deviceList></device></root>")
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        text = self.rfile.read(int(self.headers["Content-Length"])).decode()
        action = self.headers["SOAPAction"].strip('"').split("#")[1]
        fields = dict(__import__("re").findall(r"<(New\w+)>([^<]*)</New\w+>", text))
        status, reply = 200, ""
        if action == "AddPortMapping":
            FakeRouter.leases.append(fields["NewLeaseDuration"])
            if fields["NewLeaseDuration"] != "0" and FakeRouter.permanent_only:
                status = 500  # permanent leases only (error 725)
            else:
                FakeRouter.mappings[fields["NewExternalPort"]] = fields["NewInternalClient"]
        elif action == "GetExternalIPAddress":
            reply = "<NewExternalIPAddress>203.0.113.50</NewExternalIPAddress>"
        elif action == "DeletePortMapping":
            FakeRouter.mappings.pop(fields["NewExternalPort"], None)
        body = (f'<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
                + (f'<u:{action}Response xmlns:u="x">{reply}</u:{action}Response>' if status == 200 else
                   "<s:Fault><detail><UPnPError><errorCode>725</errorCode></UPnPError></detail></s:Fault>")
                + "</s:Body></s:Envelope>").encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class PortMappingTests(unittest.TestCase):
    def router(self, permanent_only):
        router = ThreadingHTTPServer(("127.0.0.1", 0), FakeRouter)
        Thread(target=router.serve_forever, daemon=True).start()
        self.addCleanup(router.server_close)
        self.addCleanup(router.shutdown)
        FakeRouter.mappings, FakeRouter.leases, FakeRouter.permanent_only = {}, [], permanent_only
        return f"http://127.0.0.1:{router.server_port}/desc.xml"

    def test_upnp_requests_a_finite_lease(self):
        mapping = portmap.upnp_map(48765, "192.168.1.20", [self.router(False)])
        self.assertEqual((FakeRouter.leases, mapping.lifetime), (["3600"], 3600))

    def test_upnp_725_falls_back_once_with_one_log_sentence(self):
        location = self.router(True)
        portmap.permanent_logged.clear()
        with patch("sys.stderr") as err:
            mapping = portmap.upnp_map(48765, "192.168.1.20", [location])
            portmap.upnp_map(48765, "192.168.1.20", [location])
        self.assertEqual((FakeRouter.leases, mapping.lifetime), (["3600", "0", "3600", "0"], 0))
        self.assertEqual(sum(c.args[0].count("permanent") for c in err.write.call_args_list if c.args), 1)

    def test_opener_renews_at_a_third_of_the_lease_and_unmaps_on_close(self):
        location = self.router(False)
        opener = portmap.PortOpener(48765, web_lookup=False, gateway="127.0.0.1")
        with patch.object(portmap, "LEASE_SECONDS", 3), patch.object(portmap, "RENEW_DIVISOR", 30),                 patch.object(portmap, "ssdp_locations", return_value=[location]),                 patch.object(portmap, "local_address", return_value="192.168.1.20"):
            opener.start()
            self.assertTrue(opener.done.wait(5))
            deadline = time.time() + 5
            while len(FakeRouter.leases) < 3 and time.time() < deadline:
                time.sleep(0.02)
            self.assertGreaterEqual(len(FakeRouter.leases), 3)
            self.assertEqual(set(FakeRouter.leases), {"3"})
            self.assertEqual(FakeRouter.mappings, {"48765": "192.168.1.20"})
            opener.close()
        self.assertEqual(FakeRouter.mappings, {})

    def test_upnp_maps_falls_back_to_a_permanent_lease_and_unmaps(self):
        FakeRouter.permanent_only = True
        router = ThreadingHTTPServer(("127.0.0.1", 0), FakeRouter)
        Thread(target=router.serve_forever, daemon=True).start()
        self.addCleanup(router.server_close)
        self.addCleanup(router.shutdown)
        location = f"http://127.0.0.1:{router.server_port}/desc.xml"
        mapping = portmap.upnp_map(48765, "192.168.1.20", [location])
        self.assertEqual((mapping.method, mapping.external_ip, mapping.lifetime), ("upnp", "203.0.113.50", 0))
        self.assertEqual(FakeRouter.mappings, {"48765": "192.168.1.20"})
        portmap.upnp_unmap(mapping, 48765)
        self.assertEqual(FakeRouter.mappings, {})

    def fake_gateway(self, answer):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        sock.settimeout(3)
        self.addCleanup(sock.close)
        seen = []

        def serve():
            try:
                while True:
                    data, sender = sock.recvfrom(1100)
                    seen.append(data)
                    reply = answer(data)
                    if reply:
                        sock.sendto(reply, sender)
            except OSError:
                pass
        Thread(target=serve, daemon=True).start()
        return sock.getsockname()[1], seen

    def test_nat_pmp_maps_and_reads_the_outside_address(self):
        def answer(data):
            if data == b"\x00\x00":
                return struct.pack(">BBHI", 0, 128, 0, 5) + socket.inet_aton("198.51.100.4")
            _, op, _, internal, external, lifetime = struct.unpack(">BBHHHI", data)
            return struct.pack(">BBHIHHI", 0, 130, 0, 5, internal, external, lifetime)
        port, seen = self.fake_gateway(answer)
        with patch.object(portmap, "NATPMP_PORT", port):
            mapping = portmap.natpmp_map("127.0.0.1", 48765)
        self.assertEqual((mapping.method, mapping.external_ip, mapping.lifetime), ("nat-pmp", "198.51.100.4", 3600))
        self.assertEqual(struct.unpack(">BBHHHI", seen[0]), (0, 2, 0, 48765, 48765, 3600))

    def test_pcp_maps_with_its_nonce(self):
        def answer(data):
            nonce = data[24:36]
            return (struct.pack(">BBBBII", 2, 0x81, 0, 0, 3600, 9) + bytes(12) + nonce
                    + struct.pack(">B3xHH", 6, 48765, 48765) + bytes(10) + b"\xff\xff" + socket.inet_aton("198.51.100.9"))
        port, seen = self.fake_gateway(answer)
        with patch.object(portmap, "NATPMP_PORT", port):
            mapping = portmap.pcp_map("127.0.0.1", "192.168.1.20", 48765)
        self.assertEqual((mapping.method, mapping.external_ip, mapping.lifetime), ("pcp", "198.51.100.9", 3600))
        self.assertEqual(len(seen[0]), 60)
        self.assertEqual(seen[0][20:24], socket.inet_aton("192.168.1.20"))

    def test_refused_mapping_is_reported(self):
        port, _ = self.fake_gateway(lambda data: struct.pack(">BBHIHHI", 0, 130, 2, 5, 48765, 0, 0)
                                    if len(data) == 12 else None)
        with patch.object(portmap, "NATPMP_PORT", port):
            self.assertIsNone(portmap.natpmp_map("127.0.0.1", 48765))

    def test_opener_explains_a_router_without_mapping(self):
        opener = portmap.PortOpener(48765, web_lookup=False, gateway="127.0.0.1")
        with patch.object(portmap, "ssdp_locations", return_value=[]), \
                patch.object(portmap, "natpmp_map", return_value=None), \
                patch.object(portmap, "pcp_map", return_value=None):
            opener.start()
            self.assertTrue(opener.done.wait(5))
        self.assertEqual(opener.mapping.method, "")
        self.assertIn("forward TCP port 48765", opener.mapping.note)

    def test_opener_flags_a_router_behind_another_router(self):
        opener = portmap.PortOpener(48765, web_lookup=False, gateway="127.0.0.1")
        with patch.object(portmap, "ssdp_locations", return_value=[]), \
                patch.object(portmap, "natpmp_map", return_value=portmap.Mapping("nat-pmp", "100.64.3.4")):
            opener.start()
            self.assertTrue(opener.done.wait(5))
        self.assertIn("not public", opener.mapping.note)
        self.assertEqual(opener.public_ip, "")


class LanDiscoveryTests(unittest.TestCase):
    def test_host_answers_a_find_broadcast_with_its_code(self):
        with TemporaryDirectory() as directory:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
            probe.close()
            host = online.OnlineHost(Path(directory), 48765, "1234abc", "Tester", open_port=False,
                                     discovery_port=port)
            host.start()
            self.addCleanup(host.close)
            found = online.find_hosts(wait=0.8, port=port)
            self.assertIn("Tester", [name for _, name in found])
            address, tcp_port, key = invite.decode(found[0][0])
            self.assertEqual((tcp_port, key), (48765, 0x1234abc))
            status = (Path(directory) / "online.txt").read_text(encoding="utf-8")
            self.assertIn("port=48765\nkey=1234abc\n", status)
            self.assertIn("portmap=off", status)


if __name__ == "__main__":
    unittest.main()
