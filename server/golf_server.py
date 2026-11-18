"""Loopback HTTP replay for Everybody's Golf 1.17."""
import argparse
from datetime import datetime
from hashlib import md5
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from socketserver import TCPServer
from struct import pack, unpack_from
from threading import Lock

DISCOVERY_PATH = "/nmg-us/ss.info"
SERVER_TIME_PATH = "/nmg-us/replay-probe/gameapi_getservertime"
EULA_PATH = "/nmg-us/replay-probe/gameapi_geteula"
NOTICE_PATH = "/nmg-us/replay-probe/gameapi_getinfolist"
MULTIPART_TYPE = "multipart/form-data; boundary=xYzZY"
TITLE_RECORD_PREFIX = (
    b'--xYzZY\r\nContent-Disposition: form-data; name="p"\r\n\r\n'
    + pack("<4H", 0x8000, 1, 0x0010, 5)
)
LANGUAGE_RECORD = pack("<2H", 0x0050, 2)
SERVER_TIME_PREFIX = TITLE_RECORD_PREFIX + b"CUSA04687_00\0\x03\x03\x03" + LANGUAGE_RECORD
TERMINATOR = pack("<2H", 0x8010, 1)
SERVER_TIME_SUFFIX = TERMINATOR + b"\r\n--xYzZY--\r\n"
SERVER_TIME_REQUEST_BYTES = len(SERVER_TIME_PREFIX) + 4 + len(SERVER_TIME_SUFFIX)
EULA_ALTERNATE_PREFIX = TITLE_RECORD_PREFIX + b"NPJA00086_PUB\0\x02\x02" + LANGUAGE_RECORD
EULA_REVISION_HEADER = pack("<2H", 0x1050, 2)
EULA_REQUEST_BYTES = SERVER_TIME_REQUEST_BYTES + len(EULA_REVISION_HEADER) + 4
MAX_EULA_TEXT_BYTES = 0x7FFF
NOTICE_CONTEXT_HEADER = pack("<2H", 0x0080, 65)
NOTICE_CONTEXT_OFFSET = len(SERVER_TIME_PREFIX) + 4
NOTICE_TOKEN_OFFSET = NOTICE_CONTEXT_OFFSET + len(NOTICE_CONTEXT_HEADER) + 256
NOTICE_TAIL = pack("<2HI2HI", 0x4000, 2, 1, 0x4010, 2, 10) + SERVER_TIME_SUFFIX
NOTICE_FIXED_REQUEST_BYTES = NOTICE_TOKEN_OFFSET + 8 + len(NOTICE_TAIL)
NOTICE_REPLY = (
    pack("<4HI", 0x8000, 1, 0x0000, 2, 1)
    + pack("<2H", 0x0083, 3) + b"local\0\0\0"
    + pack("<2HI", 0x3000, 2, 0) + TERMINATOR
)
# Matches the primary synthetic account in the runtime's sceNpGetAccountIdA.
LOCAL_ACCOUNT_ID = 0x5253474E00000001
FRIEND_LIST_PATH = (f"/v1/users/{LOCAL_ACCOUNT_ID}/friendList"
                    "?friendStatus=friend&limit=2000&presenceType=incontext")
ENTITLEMENT_ITEM_PREFIX = "/v1/users/me/entitlements/"
ENTITLEMENT_LIST = "/v1/users/me/entitlements?entitlement_type=service"
TICKET_SIZES = {"EN0001": 1, "EN0002": 10}
JSON_TYPE = "application/json; charset=utf-8"
MAX_CONSUME_BYTES = len(b'{"use_count":4294967295}')
JSON_GET_RESPONSES = {
    FRIEND_LIST_PATH: b'{"friendList":[]}',
    ENTITLEMENT_LIST: b'{"size":0,"entitlements":[]}',
    "/v1/users/me/container/?size=128&serviceLabel=0": b"[]",
}
MAX_DISCOVERY_BYTES = 0xA2800
DISCOVERY_BLOCK = 8
LOOPBACK = "127.0.0.1"


def server_time_records(at: datetime) -> bytes:
    # Synthetic response for the plaintext title API branch.
    packed_time = bytes.fromhex(f"{at.year:04d}{at:%m%d%H%M%S}")
    return (
        pack("<4HI", 0x8000, 1, 0x0000, 2, 1)
        + pack("<2H", 0x5000, 3) + packed_time + b"\0"
        + pack("<2H", 0x8010, 1)
    )


def eula_records(text: bytes) -> bytes:
    if not 0 < len(text) <= MAX_EULA_TEXT_BYTES or b"\0" in text:
        raise ValueError("EULA fixture must contain 1 to 32767 UTF-8 bytes with no NUL")
    text.decode("utf-8")
    text_words = (len(text) + 4) // 4
    return (
        pack("<4HI", 0x8000, 1, 0x0000, 2, 1)
        + EULA_REVISION_HEADER + pack("<I", 1)
        + pack("<4H", 0x1000, 1, 0x1010, 5)
        + md5(text, usedforsecurity=False).digest()
        + pack("<2HI2H", 0x1030, 2, len(text), 0x1020, text_words + 1)
        + text.ljust(text_words * 4, b"\0") + TERMINATOR
    )


def valid_server_time_request(body: bytes) -> bool:
    return body.startswith(SERVER_TIME_PREFIX) and body.endswith(SERVER_TIME_SUFFIX)


def valid_eula_request(body: bytes) -> bool:
    revision = len(SERVER_TIME_PREFIX) + 4
    if body[revision:revision + 4] != EULA_REVISION_HEADER or not body.endswith(SERVER_TIME_SUFFIX):
        return False
    if body.startswith(SERVER_TIME_PREFIX):
        return True
    return body.startswith(EULA_ALTERNATE_PREFIX) and body[revision + 4:revision + 8] == b"\0" * 4


def valid_notice_request(body: bytes) -> bool:
    if (not body.startswith(SERVER_TIME_PREFIX) or not body.endswith(NOTICE_TAIL) or
            body[NOTICE_CONTEXT_OFFSET:NOTICE_CONTEXT_OFFSET + 4] != NOTICE_CONTEXT_HEADER):
        return False

    record_type, words = unpack_from("<2H", body, NOTICE_TOKEN_OFFSET)
    selector_offset = NOTICE_TOKEN_OFFSET + words * 4
    if (record_type != 0x0083 or words < 2 or
            selector_offset + 8 + len(NOTICE_TAIL) != len(body)):
        return False
    token = body[NOTICE_TOKEN_OFFSET + 4:selector_offset]
    value, separator, padding = token.partition(b"\0")
    if (not separator or len(value) > 1000 or len(padding) > 3 or
            padding != bytes([len(padding)]) * len(padding)):
        return False
    kind, size, selector = unpack_from("<2HI", body, selector_offset)
    return (kind, size) == (0x3050, 2) and selector in (0, 1)


class GolfServer(ThreadingHTTPServer):
    def __init__(self, port: int, discovery: bytes | None = None, *,
                 server_time: datetime | None = None, ticket_grants: bool = False,
                 eula_text: bytes | None = None, empty_notices: bool = False):
        if discovery is not None and (not 0 < len(discovery) <= MAX_DISCOVERY_BYTES or
                                      len(discovery) % DISCOVERY_BLOCK):
            raise ValueError(f"Discovery fixture must contain complete 8-byte blocks, up to {MAX_DISCOVERY_BYTES} bytes")
        self.discovery = discovery
        self.server_time = server_time_records(server_time) if server_time is not None else None
        self.eula = eula_records(eula_text) if eula_text is not None else None
        self.ticket_grants = ticket_grants
        self.empty_notices = empty_notices
        self.consumed_tickets = set()
        self.ticket_lock = Lock()
        super().__init__((LOOPBACK, port), GolfHandler)

    def server_bind(self):
        TCPServer.server_bind(self)
        # HTTPServer.server_bind normally resolves its own host name.
        self.server_name, self.server_port = self.server_address

    def get_request(self):
        client, address = super().get_request()
        client.settimeout(3)
        return client, address


class GolfHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: GolfServer

    def reply(self, status: HTTPStatus, body: bytes = b"", *,
              content_type: str | None = None, allow: str | None = None):
        self.close_connection = True
        self.send_response(status)
        self.send_header("Connection", "close")
        self.send_header("Content-Length", str(len(body)))
        if allow:
            self.send_header("Allow", allow)
        if content_type:
            self.send_header("Content-Type", content_type)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        if self.path != DISCOVERY_PATH and self.path not in JSON_GET_RESPONSES:
            self.method_not_allowed()
            return
        lengths = self.headers.get_all("Content-Length", [])
        if lengths not in ([], ["0"]) or "Transfer-Encoding" in self.headers:
            self.reply(HTTPStatus.BAD_REQUEST)
            return
        if self.path == ENTITLEMENT_LIST and self.server.ticket_grants:
            with self.server.ticket_lock:
                grants = [
                    {"id": label, "use_count": size if label in self.server.consumed_tickets else 0,
                     "use_limit": 0 if label in self.server.consumed_tickets else size}
                    for label, size in TICKET_SIZES.items()
                ]
            body = json.dumps({"entitlements": grants, "size": len(grants)}).encode("ascii")
            self.reply(HTTPStatus.OK, body, content_type="application/json")
            return
        if self.path != DISCOVERY_PATH:
            self.reply(HTTPStatus.OK, JSON_GET_RESPONSES[self.path], content_type="application/json")
            return
        if self.server.discovery is None:
            self.reply(HTTPStatus.SERVICE_UNAVAILABLE)
            return
        self.reply(HTTPStatus.OK, self.server.discovery, content_type="application/octet-stream")

    def do_POST(self):
        if self.path == SERVER_TIME_PATH and self.server.server_time is not None:
            response = self.server.server_time
            minimum = maximum = SERVER_TIME_REQUEST_BYTES
            validate = valid_server_time_request
        elif self.path == EULA_PATH and self.server.eula is not None:
            response = self.server.eula
            minimum = maximum = EULA_REQUEST_BYTES
            validate = valid_eula_request
        elif self.path == NOTICE_PATH and self.server.empty_notices:
            response = NOTICE_REPLY
            minimum = NOTICE_FIXED_REQUEST_BYTES + 8
            maximum = NOTICE_FIXED_REQUEST_BYTES + 1008
            validate = valid_notice_request
        else:
            self.method_not_allowed()
            return
        if self.headers.get_all("Content-Type", []) != [MULTIPART_TYPE]:
            self.reply(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return
        lengths = self.headers.get_all("Content-Length", [])
        if (len(lengths) != 1 or not re.fullmatch(r"[1-9][0-9]{0,3}", lengths[0])
                or "Transfer-Encoding" in self.headers):
            self.reply(HTTPStatus.BAD_REQUEST)
            return
        length = int(lengths[0])
        if not minimum <= length <= maximum:
            self.reply(HTTPStatus.BAD_REQUEST)
            return
        body = self.rfile.read(length)
        if len(body) != length or not validate(body):
            self.reply(HTTPStatus.BAD_REQUEST)
            return
        self.reply(HTTPStatus.OK, response, content_type="application/octet-stream")

    def do_PUT(self):
        label = self.path.removeprefix(ENTITLEMENT_ITEM_PREFIX)
        if (not self.server.ticket_grants or label == self.path or label not in TICKET_SIZES):
            self.method_not_allowed()
            return
        if self.headers.get_all("Content-Type", []) != [JSON_TYPE]:
            self.reply(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return
        lengths = self.headers.get_all("Content-Length", [])
        if (len(lengths) != 1 or not re.fullmatch(r"[1-9][0-9]?", lengths[0]) or
                int(lengths[0]) > MAX_CONSUME_BYTES or "Transfer-Encoding" in self.headers):
            self.reply(HTTPStatus.BAD_REQUEST)
            return
        body = self.rfile.read(int(lengths[0]))
        match = re.fullmatch(rb'{"use_count":(0|[1-9][0-9]{0,9})}', body)
        if len(body) != int(lengths[0]) or not match:
            self.reply(HTTPStatus.BAD_REQUEST)
            return
        count = int(match[1])
        with self.server.ticket_lock:
            consumed = count == TICKET_SIZES[label] and label not in self.server.consumed_tickets
            if consumed:
                self.server.consumed_tickets.add(label)
        if consumed:
            self.reply(HTTPStatus.OK, b"{}", content_type="application/json")
        else:
            self.reply(HTTPStatus.CONFLICT)

    def method_not_allowed(self):
        if self.path == DISCOVERY_PATH or self.path in JSON_GET_RESPONSES:
            self.reply(HTTPStatus.METHOD_NOT_ALLOWED, allow="GET")
        elif ((self.path == SERVER_TIME_PATH and self.server.server_time is not None)
              or (self.path == EULA_PATH and self.server.eula is not None)
              or (self.path == NOTICE_PATH and self.server.empty_notices)):
            self.reply(HTTPStatus.METHOD_NOT_ALLOWED, allow="POST")
        else:
            self.reply(HTTPStatus.NOT_FOUND)

    do_HEAD = do_DELETE = do_PATCH = do_OPTIONS = method_not_allowed

    def log_message(self, format, *args):
        # Requests may contain account identifiers or credential headers.
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--ss-info-file", type=Path, help="Local encrypted discovery response fixture")
    parser.add_argument("--server-time", metavar="YYYY-MM-DDTHH:MM:SS",
                        help="Enable synthetic server-time replay at the specified time")
    parser.add_argument("--ticket-grants", action="store_true", help="Replay two synthetic ticket grants")
    parser.add_argument("--eula-file", type=Path, help="Local UTF-8 text for the EULA display probe")
    parser.add_argument("--empty-notices", action="store_true", help="Replay an empty local notice list")
    args = parser.parse_args()
    discovery = None
    try:
        if args.ss_info_file:
            with args.ss_info_file.open("rb") as stream:
                discovery = stream.read(MAX_DISCOVERY_BYTES + 1)
        server_time = None
        if args.server_time:
            server_time = datetime.strptime(args.server_time, "%Y-%m-%dT%H:%M:%S")
        eula_text = None
        if args.eula_file:
            with args.eula_file.open("rb") as stream:
                eula_text = stream.read(MAX_EULA_TEXT_BYTES + 1)
        with GolfServer(args.port, discovery, server_time=server_time,
                        ticket_grants=args.ticket_grants, eula_text=eula_text,
                        empty_notices=args.empty_notices) as server:
            print(f"Listening on http://{LOOPBACK}:{server.server_port}", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        return
    except (OSError, ValueError, OverflowError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
