"""Loopback HTTP replay for Everybody's Golf 1.17."""
import argparse
from collections.abc import Sequence
from contextlib import closing
from datetime import datetime
from functools import partial
from hashlib import md5
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import AddressValueError, IPv4Address
import json
from pathlib import Path
import re
import sqlite3
from socketserver import TCPServer
from struct import pack, unpack_from
from threading import Lock

from lobby_registry import (
    CHANNEL_REQUEST,
    LOBBY_CONTENT_TYPE, LOBBY_PATH, LOBBY_REQUEST, LobbyRegistry,
    PEER_CHANNEL_PATH, PEER_PACKET_PATH, PEER_REQUEST, PEER_REQUEST_MAX,
    TRANSPORT_PATH, TRANSPORT_REQUEST,
)
from room_registry import (
    ROOM_HEADER, ROOM_MESSAGE_PATH, ROOM_MESSAGE_REQUEST, ROOM_MESSAGE_REQUEST_MAX, ROOM_PATH, ROOM_REQUEST_MAX,
)
from tournament_archive import tournament_archive

LOCAL_LOBBY_PATHS = (LOBBY_PATH, PEER_PACKET_PATH, PEER_CHANNEL_PATH, ROOM_PATH, TRANSPORT_PATH, ROOM_MESSAGE_PATH)

DISCOVERY_PATH = "/nmg-us/ss.info"
SERVER_TIME_PATH = "/nmg-us/replay-probe/gameapi_getservertime"
EULA_PATH = "/nmg-us/replay-probe/gameapi_geteula"
NOTICE_PATH = "/nmg-us/replay-probe/gameapi_getinfolist"
BONUS_LIST_PATH = "/nmg-us/replay-probe/gameapi_getbonuslist"
REGULATION_PATH = "/nmg-us/replay-probe/gameapi_getregulationdata"
DAILY_SCORE_PATH = "/nmg-us/replay-probe/gameapi_getscorelist"
SCORE_BOARD_PREFIX = DAILY_SCORE_PATH + "?account="
REGISTRATION_OPERATIONS = (
    "gameapi_registscore", "gameapi_registscoredaily", "gameapi_registscorelongdrivecontest",
)
REGISTRATION_PREFIXES = tuple(f"/nmg-us/replay-probe/{name}?account=" for name in REGISTRATION_OPERATIONS)
OWN_SCORE_PATH = "/nmg-us/replay-probe/gameapi_getmyscore"
TOP_PLAYER_PATH = "/nmg-us/replay-probe/gameapi_gettopplayerlist"
SCORE_DISTRIBUTION_PATH = "/nmg-us/replay-probe/gameapi_getscoredistribution"
USER_STATUS_PATH = "/nmg-us/replay-probe/gameapi_getuserstatus"
COURSE_ASSIGNMENT_PREFIX = "/nmg-us/replay-probe/gameapi_assignmentcourseworld?account="
CHARACTER_ASSIGNMENT_PATH = "/nmg-us/replay-probe/gameapi_assignmentcharactordownload"
CHARACTER_COUNT_PREFIX = "/nmg-us/replay-probe/gameapi_getcountcharactordownload?account="
FINISH_BOARD_PATH = "/nmg-us/replay-probe/gameapi_getfinishboardlist"
SIGN_BOARD_PATH = "/nmg-us/replay-probe/gameapi_getsignboardlist"
RIVAL_LIST_PATH = "/nmg-us/replay-probe/gameapi_getrivallist"
BOARD_LIST_PATH = "/nmg-us/replay-probe/gameapi_getboardlist"
CHARACTER_BOARD_PATH = "/nmg-us/replay-probe/gameapi_getboardlistcharactordownload"
NATIONAL_BOARD_PATH = "/nmg-us/replay-probe/gameapi_getboardlistnational"
NATIONAL_GAME_DATA_PATH = "/nmg-us/replay-probe/gameapi_getnationalgamedata"
NATIONAL_OWN_SCORE_PATH = "/nmg-us/replay-probe/gameapi_getmyscorenational"
NATIONAL_JOIN_PATH = "/nmg-us/replay-probe/gameapi_noticejoinnational"
# The game appends "%llu&n=%d&s=1" to the join URL (eboot 0xb5d300), so the fixture ends it in "?account=".
NATIONAL_JOIN_PREFIX = NATIONAL_JOIN_PATH + "?account="
NATIONAL_DISTRIBUTION_PATH = "/nmg-us/replay-probe/gameapi_getscoredistributionnational"
NATIONAL_SCORE_LIST_PATH = "/nmg-us/replay-probe/gameapi_getscorelistnational"
NATIONAL_REGISTRATION_PREFIX = "/nmg-us/replay-probe/gameapi_registscorenational?account="
GAME_DOWNLOAD_BASE = "/nmg-us/replay-probe/gamedata-down"
NATIONAL_BOARD_SUFFIX = "/local-national-board.bin"
NATIONAL_BOARD_DOWNLOAD_PATH = GAME_DOWNLOAD_BASE + NATIONAL_BOARD_SUFFIX
NATIONAL_GAME_DATA_SUFFIX = "/local-tournament.xb"
NATIONAL_GAME_DOWNLOAD_PATH = GAME_DOWNLOAD_BASE + NATIONAL_GAME_DATA_SUFFIX
NATIONAL_DISTRIBUTION_SUFFIX = "/local-national-distribution.json"
NATIONAL_DISTRIBUTION_DOWNLOAD_PATH = GAME_DOWNLOAD_BASE + NATIONAL_DISTRIBUTION_SUFFIX
LOCAL_TOURNAMENT_ID = 1
LOCAL_TOURNAMENT_VERSION = 1
# Board word 0x4146 becomes entry +0x271, the stage whose p<n>_ settings the entry screen uses.
# 0 fails the check at 0xc4e095-0xc4e0a3 and shows "Connection failed"; 1 selects the p1_ settings.
LOCAL_TOURNAMENT_STAGE = 1
LOCAL_TOURNAMENT_GROUP = b"LocalTournament"
LOGIN_PREFIX = "/nmg-us/replay-probe/gameapi_login?account="
PROPERTY_INFO_PATH = "/nmg-us/replay-probe/gameapi_getgamepropertyinfo"
ANALYTICS_PREFIX = "/nmg-us/replay-probe/analytics/"
TELEMETRY_PATH = ANALYTICS_PREFIX + "19d916d7-6a01-4371-9e6c-c91b2ff386bb/telemetry"
MAX_TELEMETRY_BYTES = 8192
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
NATIONAL_BOARD_FIELDS = ((0x0080, 65, 65), (0x0083, 2, 252), (0x4A40, 2, 2))
# Board selectors 0, 1 and 3 fill entry lists +0x11c0, the main entry and list +8; the join
# path reads the main entry ([0x2c81150]+0x28c), so selector 1 must carry the tournament too.
NATIONAL_BOARD_DOWNLOAD_SELECTORS = (0, 1, 3)
NATIONAL_BOARD_MIN_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(
    minimum for _, minimum, _ in NATIONAL_BOARD_FIELDS
)
NATIONAL_BOARD_MAX_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(
    maximum for _, _, maximum in NATIONAL_BOARD_FIELDS
)
NATIONAL_BOARD_REPLY = pack("<4HI2H", 0x8000, 1, 0x0000, 2, 1, 0x0083, 3) + b"local\0\0\0" + TERMINATOR
DAILY_SCORE_TAIL = pack("<2HI2HI", 0x4000, 2, 1, 0x4010, 2, 1000) + SERVER_TIME_SUFFIX
DAILY_SCORE_FIELDS = ((0x0020, 2, 15), (0x0060, 3, 13), (0x4140, 7, 7))
REGULATION_FIELDS = DAILY_SCORE_FIELDS[:2]
DATED_REGULATION_FIELDS = REGULATION_FIELDS + ((0x6010, 2, 2),)
REGULATION_MIN_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(low for _, low, _ in REGULATION_FIELDS)
REGULATION_MAX_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(high for _, _, high in DATED_REGULATION_FIELDS)
DAILY_SCORE_FIXED_BYTES = len(SERVER_TIME_PREFIX) + 4 + len(DAILY_SCORE_TAIL)
DAILY_SCORE_MIN_BYTES = DAILY_SCORE_FIXED_BYTES + 4 * sum(minimum for _, minimum, _ in DAILY_SCORE_FIELDS)
DAILY_SCORE_MAX_BYTES = DAILY_SCORE_FIXED_BYTES + 4 * sum(maximum for _, _, maximum in DAILY_SCORE_FIELDS)
OWN_SCORE_FIELDS = ((0x0080, 65, 65), (0x0083, 2, 252), (0x4A00, 2, 2), (0x4140, 6, 14))
OWN_SCORE_MIN_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(minimum for _, minimum, _ in OWN_SCORE_FIELDS)
OWN_SCORE_MAX_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(maximum for _, _, maximum in OWN_SCORE_FIELDS)
TITLE_SESSION_FIELDS = OWN_SCORE_FIELDS[:2]
TITLE_SESSION_MIN_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(
    minimum for _, minimum, _ in TITLE_SESSION_FIELDS
)
TITLE_SESSION_MAX_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(
    maximum for _, _, maximum in TITLE_SESSION_FIELDS
)
TOURNAMENT_GROUP_WORDS = 1 + (len(LOCAL_TOURNAMENT_GROUP) + 4) // 4
NATIONAL_DISTRIBUTION_FIELDS = TITLE_SESSION_FIELDS + (
    (0x4140, TOURNAMENT_GROUP_WORDS, TOURNAMENT_GROUP_WORDS), (0x4147, 2, 2),
)
NATIONAL_DISTRIBUTION_MIN_BYTES = TITLE_SESSION_MIN_BYTES + 4 * TOURNAMENT_GROUP_WORDS + 8
NATIONAL_DISTRIBUTION_MAX_BYTES = TITLE_SESSION_MAX_BYTES + 4 * TOURNAMENT_GROUP_WORDS + 8
NATIONAL_GAME_DATA_FIELDS = NATIONAL_DISTRIBUTION_FIELDS + ((0x41F6, 2, 2),)
NATIONAL_GAME_DATA_MIN_BYTES = NATIONAL_DISTRIBUTION_MIN_BYTES + 8
NATIONAL_GAME_DATA_MAX_BYTES = NATIONAL_DISTRIBUTION_MAX_BYTES + 8
TOP_PLAYER_FIELDS = TITLE_SESSION_FIELDS + tuple(
    (kind, 2, 2) for kind in (0x4A00, 0x4A30, 0x4A10, 0x4A20, 0x4010)
)
TOP_PLAYER_MIN_BYTES = TITLE_SESSION_MIN_BYTES + 40
TOP_PLAYER_MAX_BYTES = TITLE_SESSION_MAX_BYTES + 40
SCORE_DISTRIBUTION_FIELDS = TITLE_SESSION_FIELDS + ((0x4A00, 2, 2), (0x4140, 6, 9))
SCORE_DISTRIBUTION_MIN_BYTES = TITLE_SESSION_MIN_BYTES + 32
SCORE_DISTRIBUTION_MAX_BYTES = TITLE_SESSION_MAX_BYTES + 44
CHARACTER_COUNT_FIELDS = TITLE_SESSION_FIELDS + ((0x7704, 6, 6),)
CHARACTER_COUNT_MIN_BYTES = TITLE_SESSION_MIN_BYTES + 24
CHARACTER_COUNT_MAX_BYTES = TITLE_SESSION_MAX_BYTES + 24
SCORE_BOARD_FIELDS = OWN_SCORE_FIELDS + ((0x4000, 2, 2), (0x4010, 2, 2))
SCORE_BOARD_MIN_BYTES = OWN_SCORE_MIN_BYTES + 16
SCORE_BOARD_MAX_BYTES = OWN_SCORE_MAX_BYTES + 16
REGISTRATION_COMMON_FIELDS = OWN_SCORE_FIELDS[:3]
SCORE_STAMP_FIELDS = ((0x42B0, 8, 12), (0x4500, 3, 3))
REGISTRATION_METADATA_FIELDS = (
    (0x4141, 3, 3), (0x4142, 2, 33), (0x4143, 2, 2), (0x4144, 2, 2),
) + SCORE_STAMP_FIELDS
SCORE_DETAIL_FIELDS = tuple((0x4600 + index, 2, 65) for index in range(14))
RIVAL_LIST_FIELDS = (REGISTRATION_COMMON_FIELDS + ((0x4140, 6, 9),)
                     + REGISTRATION_METADATA_FIELDS[:4])
RIVAL_LIST_MIN_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(minimum for _, minimum, _ in RIVAL_LIST_FIELDS)
RIVAL_LIST_MAX_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(maximum for _, _, maximum in RIVAL_LIST_FIELDS)
REGISTRATION_FIELDS = tuple(
    REGISTRATION_COMMON_FIELDS + ((0x4140, low, high),) + REGISTRATION_METADATA_FIELDS
    + (() if selector == 2 else ((0x4501, 3, 3),))
    + (SCORE_DETAIL_FIELDS[:11] if selector == 2 else SCORE_DETAIL_FIELDS)
    for selector, (low, high) in enumerate(((7, 12), (6, 9), (9, 14)))
)
REGISTRATION_SIZES = tuple(
    (SERVER_TIME_REQUEST_BYTES + 4 * sum(minimum for _, minimum, _ in layout),
     SERVER_TIME_REQUEST_BYTES + 4 * sum(maximum for _, _, maximum in layout))
    for layout in REGISTRATION_FIELDS
)
SCORE_GROUP_NUMBER = rb"(0|-?[1-9][0-9]{0,9})"
OWN_SCORE_GROUPS = (
    re.compile(rb"OneHole_[0-9]{8}_" + SCORE_GROUP_NUMBER + b"_" + SCORE_GROUP_NUMBER),
    re.compile(rb"Daily_[0-9]{8}_" + SCORE_GROUP_NUMBER + rb"_(?:IN|OUT)"),
    re.compile(rb"LongDriveContest_[0-9]{8}_" + SCORE_GROUP_NUMBER + b"_" + SCORE_GROUP_NUMBER),
)
OWN_SCORE_EMPTY_REPLY = pack("<4HI", 0x8000, 1, 0x0000, 2, 0x90000310) + TERMINATOR
USER_STATUS_SESSION = ((0x0086, bytes(128)), (0x0087, bytes(4)), (0x0088, bytes(4)))
USER_STATUS_FIELDS = OWN_SCORE_FIELDS[:2] + tuple(
    (kind, 1 + len(payload) // 4, 1 + len(payload) // 4) for kind, payload in USER_STATUS_SESSION
) + ((0x2500, 2, 2),)
USER_STATUS_MIN_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(minimum for _, minimum, _ in USER_STATUS_FIELDS)
USER_STATUS_MAX_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(maximum for _, _, maximum in USER_STATUS_FIELDS)
NATIONAL_EVENT_FIELDS = (
    (0x4140, TOURNAMENT_GROUP_WORDS, TOURNAMENT_GROUP_WORDS),
    (0x4147, 2, 2), (0x4142, 2, 2), (0x4143, 2, 2), (0x4144, 2, 2),
)
NATIONAL_JOIN_FIELDS = TITLE_SESSION_FIELDS + NATIONAL_EVENT_FIELDS
NATIONAL_EVENT_BYTES = 4 * sum(words for _, words, _ in NATIONAL_EVENT_FIELDS)
NATIONAL_JOIN_MIN_BYTES = TITLE_SESSION_MIN_BYTES + NATIONAL_EVENT_BYTES
NATIONAL_JOIN_MAX_BYTES = TITLE_SESSION_MAX_BYTES + NATIONAL_EVENT_BYTES
NATIONAL_REGISTRATION_FIELDS = NATIONAL_JOIN_FIELDS + SCORE_STAMP_FIELDS + ((0x4501, 3, 3),) + SCORE_DETAIL_FIELDS
NATIONAL_REGISTRATION_MIN_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(
    minimum for _, minimum, _ in NATIONAL_REGISTRATION_FIELDS
)
NATIONAL_REGISTRATION_MAX_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(
    maximum for _, _, maximum in NATIONAL_REGISTRATION_FIELDS
)
NATIONAL_SCORE_LIST_PAGE_FIELDS = ((0x4000, 2, 2), (0x4010, 2, 2))
NATIONAL_SCORE_LIST_FIELDS = NATIONAL_JOIN_FIELDS + NATIONAL_SCORE_LIST_PAGE_FIELDS
NATIONAL_SCORE_LIST_SINGLE_FIELDS = NATIONAL_JOIN_FIELDS + ((0x42F3, 65, 65),) + NATIONAL_SCORE_LIST_PAGE_FIELDS
NATIONAL_SCORE_LIST_MIN_BYTES = NATIONAL_JOIN_MIN_BYTES + 16
NATIONAL_SCORE_LIST_MAX_BYTES = NATIONAL_JOIN_MAX_BYTES + 260 + 16
NATIONAL_OWN_SCORE_FIELDS = USER_STATUS_FIELDS[:-1] + NATIONAL_EVENT_FIELDS
NATIONAL_OWN_SCORE_MIN_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(
    minimum for _, minimum, _ in NATIONAL_OWN_SCORE_FIELDS
)
NATIONAL_OWN_SCORE_MAX_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(
    maximum for _, _, maximum in NATIONAL_OWN_SCORE_FIELDS
)
TITLE_SUCCESS_PREFIX = pack("<4HI", 0x8000, 1, 0x0000, 2, 1)
TITLE_SUCCESS_REPLY = TITLE_SUCCESS_PREFIX + TERMINATOR
BOARD_LIST_FIELDS = ((0x0020, 2, 15), (0x0060, 3, 13), (0x4000, 2, 2), (0x4010, 2, 2))
BOARD_LIST_MIN_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(minimum for _, minimum, _ in BOARD_LIST_FIELDS)
BOARD_LIST_MAX_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(maximum for _, _, maximum in BOARD_LIST_FIELDS)
FINISH_BOARD_FIELDS = BOARD_LIST_FIELDS[:2] + ((0x6500, 1, 1), (0x6520, 2, 2))
FINISH_BOARD_MIN_BYTES = BOARD_LIST_MIN_BYTES - 4
FINISH_BOARD_MAX_BYTES = BOARD_LIST_MAX_BYTES - 4
SCHEDULE_FIELDS = OWN_SCORE_FIELDS[:3] + ((0x4A40, 2, 2), (0x4A50, 2, 2))
SCHEDULE_PAGE = ((0x4000, 2, 2), (0x4010, 2, 2))
BONUS_LIST_FIELDS = TITLE_SESSION_FIELDS + SCHEDULE_PAGE
BONUS_LIST_MIN_BYTES = TITLE_SESSION_MIN_BYTES + 16
BONUS_LIST_MAX_BYTES = TITLE_SESSION_MAX_BYTES + 16
SCHEDULE_WINDOW = ((0x4A10, 2, 2),) + SCHEDULE_PAGE
CHARACTER_BOARD_FIELDS = TITLE_SESSION_FIELDS + ((0x4A40, 2, 2),) + SCHEDULE_PAGE
SCHEDULE_MIN_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(minimum for _, minimum, _ in SCHEDULE_FIELDS)
SCHEDULE_MAX_ROWS = 18
SCHEDULE_MAX_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(
    maximum for _, _, maximum in SCHEDULE_FIELDS + SCHEDULE_WINDOW
)
# Matches the primary synthetic account in the runtime's sceNpGetAccountIdA.
LOCAL_ACCOUNT_ID = 0x5253474E00000001
LOGIN_FIELDS = ((0x0020, 2, 15), (0x0084, 6, 6), (0x0070, 3, 3),
                (0x0071, 5, 5), (0x0085, 5, 5), (0x2032, 2, 2))
LOGIN_MIN_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(minimum for _, minimum, _ in LOGIN_FIELDS)
LOGIN_MAX_BYTES = SERVER_TIME_REQUEST_BYTES + 4 * sum(maximum for _, _, maximum in LOGIN_FIELDS)
LOGIN_PROBE_CODE = b"GolfLocalProbe"
# Any decimal account id: each runtime instance can have its own (GOLF_ACCOUNT_ID / GOLF_ONLINE_ID).
SESSION_QUERY = r"(?:[1-9][0-9]{0,19})&n=(0|-?[1-9][0-9]{0,9})&s=1"


def valid_account_field(field: bytes) -> bool:
    """A NUL-terminated decimal account id that fits in 64 bits."""
    digits = field[:-1] if field.endswith(b"\0") else b""
    return (1 <= len(digits) <= 20 and digits.isdigit() and digits[:1] != b"0" and
            int(digits) < (1 << 64))
LOGIN_TARGET = re.compile(re.escape(LOGIN_PREFIX) + SESSION_QUERY)
SCORE_BOARD_TARGET = re.compile(re.escape(SCORE_BOARD_PREFIX) + SESSION_QUERY)
COURSE_ASSIGNMENT_TARGET = re.compile(re.escape(COURSE_ASSIGNMENT_PREFIX) + SESSION_QUERY)
CHARACTER_COUNT_TARGET = re.compile(re.escape(CHARACTER_COUNT_PREFIX) + SESSION_QUERY)
REGISTRATION_TARGETS = tuple(re.compile(re.escape(prefix) + SESSION_QUERY) for prefix in REGISTRATION_PREFIXES)
NATIONAL_REGISTRATION_TARGET = re.compile(re.escape(NATIONAL_REGISTRATION_PREFIX) + SESSION_QUERY)
NATIONAL_JOIN_TARGET = re.compile(re.escape(NATIONAL_JOIN_PREFIX) + SESSION_QUERY)
LOCAL_SCORE_NAME = re.compile(rb"[A-Za-z0-9_-]{1,16}")
SCORE_TIMESTAMP = re.compile(rb"[0-9]{1,4}(?:-[0-9]{2}){2}T[0-9]{2}(?::[0-9]{2}){2}\+09:00")
SCORE_SUCCESS_PREFIX = pack("<4HI2H", 0x8000, 1, 0, 2, 1, 0x0083, 3) + b"local\0\0\0"
BONUS_LIST_REPLY = SCORE_SUCCESS_PREFIX + TERMINATOR
NATIONAL_OWN_SCORE_EMPTY_REPLY = SCORE_SUCCESS_PREFIX + pack("<2HI", 0x4200, 2, 0) + TERMINATOR
NATIONAL_JOIN_REPLY = SCORE_SUCCESS_PREFIX + pack("<2HI", 0x4962, 2, 0) + TERMINATOR
NATIONAL_SCORE_LIST_REPLY = SCORE_SUCCESS_PREFIX + pack("<2HI2HI", 0x4200, 2, 0, 0x4210, 2, 1) + TERMINATOR
TOP_PLAYER_REPLY = SCORE_SUCCESS_PREFIX + pack("<2HI", 0x4970, 2, 0) + TERMINATOR
SCORE_DISTRIBUTION_REPLY = SCORE_SUCCESS_PREFIX + pack("<2H", 0x4950, 2) + b"[]\0\0" + TERMINATOR
# The record length is a 16-bit word count, including its header and padded NUL.
MAX_DISTRIBUTION_JSON = 4 * (0xFFFF - 1) - 1
CHARACTER_ASSIGNMENT_REPLY = SCORE_SUCCESS_PREFIX + TERMINATOR
CHARACTER_COUNT_REPLY = SCORE_SUCCESS_PREFIX + pack("<2HI2HI", 0x7707, 2, 0, 0x7708, 2, 0) + TERMINATOR
SIGN_BOARD_REPLY = SCORE_SUCCESS_PREFIX + pack("<2HI", 0x7802, 2, 0) + TERMINATOR
RIVAL_LIST_REPLY = SCORE_SUCCESS_PREFIX + pack("<2HI", 0x4930, 2, 0) + TERMINATOR
SCORE_RANK_RECORD = pack("<2HI", 0x4270, 2, 1)
LOGIN_REJECT_REPLY = pack("<4HI2HI", 0x8000, 1, 0x0000, 2, 1, 0x2020, 2, 4) + TERMINATOR
LOGIN_COMPLETE_REPLY = pack("<4HI2HI", 0x8000, 1, 0x0000, 2, 1, 0x2020, 2, 1) + TERMINATOR
LOGIN_SCORE_SESSION_REPLY = (LOGIN_COMPLETE_REPLY[:-len(TERMINATOR)] + pack("<2HI", 0x2032, 2, 1)
                            + b"".join(pack("<2H", kind, 1 + len(payload) // 4) + payload
                                       for kind, payload in USER_STATUS_SESSION) + TERMINATOR)
PROPERTY_INDEX_HEADER = pack("<2HI", 0x7604, 2, 1)
PROPERTY_VERSION_HEADER = pack("<2H", 0x7605, 2)
PROPERTY_REQUEST_BYTES = SERVER_TIME_REQUEST_BYTES + len(PROPERTY_INDEX_HEADER) + len(PROPERTY_VERSION_HEADER) + 4
PROPERTY_CACHED_REPLY = pack("<4HI2HI", 0x8000, 1, 0x0000, 2, 1, 0x7603, 2, 1) + TERMINATOR
FRIEND_LIST_PATH = (f"/v1/users/{LOCAL_ACCOUNT_ID}/friendList"
                    "?friendStatus=friend&limit=2000&presenceType=incontext")
ENTITLEMENT_ITEM_PREFIX = "/v1/users/me/entitlements/"
ENTITLEMENT_LIST = "/v1/users/me/entitlements?entitlement_type=service"
TICKET_SIZES = {"EN0001": 1, "EN0002": 10}
COMMERCE_PREFIX = "/v1/users/me/container/"
COMMERCE_QUERY = "?size=128&serviceLabel=0"
# ProductLabel rows verified against the bundled 1.17 entitlement table.
COMMERCE_LABELS = {f"EN000000000000{i:02d}" for i in range(1, 30)} | {
    "EN00010000000000", "EN00020000000000",
}
JSON_TYPE = "application/json; charset=utf-8"
MAX_CONSUME_BYTES = len(b'{"use_count":4294967295}')
JSON_GET_RESPONSES = {
    FRIEND_LIST_PATH: b'{"friendList":[]}',
    ENTITLEMENT_LIST: b'{"size":0,"entitlements":[]}',
    COMMERCE_PREFIX + COMMERCE_QUERY: b"[]",
}
MAX_DISCOVERY_BYTES = 0xA2800
DISCOVERY_BLOCK = 8
LOOPBACK = "127.0.0.1"
# The room key a runtime sends (--server-key / GOLF_SERVER_KEY, from the invite code).
ROOM_KEY_HEADER = "X-Golf-Key"
DEFAULT_SCORE_LIST_ROWS = 20
MAX_SCORE_LIST_ROWS = 100


def commerce_batch_labels(path: str) -> list[str]:
    if not path.startswith(COMMERCE_PREFIX) or not path.endswith(COMMERCE_QUERY):
        return []
    labels = path[len(COMMERCE_PREFIX):-len(COMMERCE_QUERY)].split(":", 32)
    return labels if len(labels) <= 32 and COMMERCE_LABELS.issuperset(labels) else []


def commerce_batch_reply(labels: list[str]) -> bytes:
    return json.dumps([
        {"container_type": "product", "label": label, "skus": [
            {"label": "LOCAL_" + label, "price": 0, "display_price": "",
             "is_purchaseable": False, "use_count": 0}
        ]} for label in labels
    ]).encode("ascii")


def bcd_timestamp(at: datetime) -> bytes:
    return bytes.fromhex(f"{at.year:04d}{at:%m%d%H%M%S}") + b"\0"


def server_time_records(at: datetime) -> bytes:
    return (
        pack("<4HI", 0x8000, 1, 0x0000, 2, 1)
        + pack("<2H", 0x5000, 3) + bcd_timestamp(at)
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


def valid_property_request(body: bytes) -> bool:
    offset = len(SERVER_TIME_PREFIX) + 4
    fields = PROPERTY_INDEX_HEADER + PROPERTY_VERSION_HEADER
    return valid_server_time_request(body) and body[offset:offset + len(fields)] == fields


def valid_eula_request(body: bytes) -> bool:
    revision = len(SERVER_TIME_PREFIX) + 4
    if body[revision:revision + 4] != EULA_REVISION_HEADER or not body.endswith(SERVER_TIME_SUFFIX):
        return False
    if body.startswith(SERVER_TIME_PREFIX):
        return True
    return body.startswith(EULA_ALTERNATE_PREFIX) and body[revision + 4:revision + 8] == b"\0" * 4


def padded_string(field: bytes) -> bytes | None:
    value, terminator, padding = field.partition(b"\0")
    if not terminator or len(padding) > 3 or padding != bytes([len(padding)]) * len(padding):
        return None
    return value


def valid_notice_request(body: bytes) -> bool:
    if (not body.startswith(SERVER_TIME_PREFIX) or not body.endswith(NOTICE_TAIL) or
            body[NOTICE_CONTEXT_OFFSET:NOTICE_CONTEXT_OFFSET + 4] != NOTICE_CONTEXT_HEADER):
        return False

    record_type, words = unpack_from("<2H", body, NOTICE_TOKEN_OFFSET)
    selector_offset = NOTICE_TOKEN_OFFSET + words * 4
    if (record_type != 0x0083 or words < 2 or
            selector_offset + 8 + len(NOTICE_TAIL) != len(body)):
        return False
    token = padded_string(body[NOTICE_TOKEN_OFFSET + 4:selector_offset])
    if token is None or len(token) > 1000:
        return False
    kind, size, selector = unpack_from("<2HI", body, selector_offset)
    return (kind, size) == (0x3050, 2) and selector in (0, 1, 2)


def title_fields(body: bytes, tail: bytes, layout: tuple) -> list[bytes] | None:
    if not body.startswith(SERVER_TIME_PREFIX) or not body.endswith(tail):
        return None
    offset = len(SERVER_TIME_PREFIX) + 4
    end = len(body) - len(tail)
    fields = []
    for expected, minimum, maximum in layout:
        if offset + 4 > end:
            return None
        kind, words = unpack_from("<2H", body, offset)
        next_offset = offset + 4 * words
        if kind != expected or not minimum <= words <= maximum or next_offset > end:
            return None
        fields.append(body[offset + 4:next_offset])
        offset = next_offset
    return fields if offset == end else None


def valid_title_session_request(body: bytes, *, layout: tuple = TITLE_SESSION_FIELDS) -> bool:
    fields = title_fields(body, SERVER_TIME_SUFFIX, layout)
    token = padded_string(fields[1]) if fields is not None else None
    return token is not None and len(token) <= 1000


def valid_character_count_request(body: bytes) -> bool:
    fields = title_fields(body, SERVER_TIME_SUFFIX, CHARACTER_COUNT_FIELDS)
    if fields is None:
        return False
    token = padded_string(fields[1])
    return token is not None and len(token) <= 1000 and valid_account_field(fields[2])


def valid_top_player_request(body: bytes) -> bool:
    fields = title_fields(body, SERVER_TIME_SUFFIX, TOP_PLAYER_FIELDS)
    if fields is None:
        return False
    _context, token, selector, event_date, _course, _hole, limit = fields
    token = padded_string(token)
    if token is None or len(token) > 1000 or selector != bytes(4) or limit != pack("<I", 9):
        return False
    date_digits = event_date.hex()
    try:
        datetime(int(date_digits[:4]), int(date_digits[4:6]), int(date_digits[6:]))
    except ValueError:
        return False
    return True


def score_distribution_group(body: bytes) -> bytes | None:
    fields = title_fields(body, SERVER_TIME_SUFFIX, SCORE_DISTRIBUTION_FIELDS)
    return score_group(fields) if fields is not None and fields[2] == pack("<I", 1) else None


def valid_national_board_request(body: bytes) -> bool:
    fields = title_fields(body, SERVER_TIME_SUFFIX, NATIONAL_BOARD_FIELDS)
    if fields is None:
        return False
    _context, token, selector_record = fields
    selector = unpack_from("<I", selector_record)[0]
    return padded_string(token) is not None and selector in NATIONAL_BOARD_DOWNLOAD_SELECTORS


def valid_national_id_request(body: bytes, *, layout: tuple) -> bool:
    fields = title_fields(body, SERVER_TIME_SUFFIX, layout)
    if fields is None:
        return False
    _context, token, group, event_id = fields[:4]
    token = padded_string(token)
    return (token is not None and len(token) <= 1000 and padded_string(group) == LOCAL_TOURNAMENT_GROUP
            and event_id == pack("<I", LOCAL_TOURNAMENT_ID))


def score_group(fields: list[bytes]) -> bytes | None:
    _context, token, variant, group = fields[:4]
    token = padded_string(token)
    group = padded_string(group)
    selector = unpack_from("<I", variant)[0]
    if token is None or len(token) > 1000 or group is None or not valid_score_group(group, selector):
        return None
    return group


def valid_score_group(group: bytes, selector: int) -> bool:
    if selector >= len(OWN_SCORE_GROUPS):
        return False
    match = OWN_SCORE_GROUPS[selector].fullmatch(group)
    return match is not None and all(-(1 << 31) <= int(field) < (1 << 31) for field in match.groups())


def score_query_group(body: bytes, *, paged: bool) -> bytes | None:
    layout = SCORE_BOARD_FIELDS if paged else OWN_SCORE_FIELDS
    fields = title_fields(body, SERVER_TIME_SUFFIX, layout)
    if fields is None or (paged and (fields[4] != pack("<I", 1) or unpack_from("<i", fields[5])[0] <= 0)):
        return None
    return score_group(fields)


def valid_rival_request(body: bytes, groups: set[bytes]) -> bool:
    fields = title_fields(body, SERVER_TIME_SUFFIX, RIVAL_LIST_FIELDS)
    if fields is None:
        return False
    token = padded_string(fields[1])
    return (token is not None and len(token) <= 1000 and fields[2] == pack("<I", 1)
            and padded_string(fields[3]) in groups and padded_string(fields[5]) is not None)


def score_player(field: bytes) -> bytes | None:
    stamp = padded_string(field)
    if stamp is None:
        return None
    player, _, timestamp = stamp.partition(b"@")
    return player if LOCAL_SCORE_NAME.fullmatch(player) and SCORE_TIMESTAMP.fullmatch(timestamp) else None


def registered_national_score(body: bytes, group: bytes) -> tuple[bytes, bytes, int, int] | None:
    fields = title_fields(body, SERVER_TIME_SUFFIX, NATIONAL_REGISTRATION_FIELDS)
    if fields is None or not valid_national_event_fields(fields[2:7]):
        return None
    token = padded_string(fields[1])
    player = score_player(fields[7])
    if token is None or len(token) > 1000 or player is None or any(b"\0" not in field for field in fields[10:]):
        return None
    primary, secondary = (unpack_from("<q", field)[0] for field in fields[8:10])
    if any(not -(1 << 31) <= value < (1 << 31) for value in (primary, secondary)):
        return None
    return group, player, primary, secondary


def registered_score(body: bytes, selector: int) -> tuple[bytes, bytes, int, int | None] | None:
    long_drive = selector == 2
    fields = title_fields(body, SERVER_TIME_SUFFIX, REGISTRATION_FIELDS[selector])
    if fields is None or unpack_from("<I", fields[2])[0] != selector:
        return None
    group = score_group(fields)
    player = score_player(fields[8])
    if group is None or padded_string(fields[5]) is None or player is None:
        return None
    if any(b"\0" not in field for field in fields[10 if long_drive else 11:]):
        return None
    primary = unpack_from("<q", fields[9])[0]
    secondary = None if long_drive else unpack_from("<q", fields[10])[0]
    return group, player, primary, secondary


def score_registration_reply(selector: int) -> bytes:
    rank = b"" if selector == 2 else SCORE_RANK_RECORD
    return SCORE_SUCCESS_PREFIX + rank + pack("<2H", 0x42A0, 1) + TERMINATOR


def score_string(kind: int, value: bytes) -> bytes:
    padding = (-(len(value) + 1)) % 4
    payload = value + b"\0" + bytes([padding]) * padding
    return pack("<2H", kind, 1 + len(payload) // 4) + payload


def distribution_data(score: int) -> bytes:
    if not -(1 << 31) <= score < (1 << 31):
        return b"[]"
    return f'[{{"num":"1","score":"{score}"}}]'.encode("ascii")


def national_tournament_board(at: datetime) -> bytes:
    start = bcd_timestamp(at.replace(hour=0, minute=0, second=0, microsecond=0))
    end = bcd_timestamp(at.replace(hour=23, minute=59, second=59, microsecond=0))
    return (pack("<2HI2H2HI2HI", 0x4100, 2, 1, 0x4120, 1,
                 0x4145, 2, LOCAL_TOURNAMENT_VERSION, 0x4146, 2, LOCAL_TOURNAMENT_STAGE)
            + score_string(0x4140, LOCAL_TOURNAMENT_GROUP)
            + pack("<2HI", 0x4147, 2, LOCAL_TOURNAMENT_ID)
            + score_string(0x4142, b"") + pack("<2HI2HI", 0x4143, 2, 0, 0x4144, 2, 0)
            + score_string(0x4150, b"Local Tournament")
            + pack("<2H", 0x4177, 3) + start + pack("<2H", 0x4178, 3) + end
            + pack("<2H", 0x4130, 1) + TERMINATOR)


def national_game_data_reply() -> bytes:
    return (SCORE_SUCCESS_PREFIX + score_string(0x41F5, NATIONAL_GAME_DATA_SUFFIX.encode("ascii"))
            + pack("<2HI2HI", 0x41F6, 2, LOCAL_TOURNAMENT_VERSION, 0x41F7, 2, 0) + TERMINATOR)


def score_stats(row: tuple[bytes, int, int | None]) -> bytes:
    stats = pack("<2Hq", 0x4500, 3, row[1])
    if row[2] is not None:
        stats += pack("<2Hq", 0x4501, 3, row[2])
    return stats


def score_list_row(row: tuple[bytes, int, int | None], rank: int) -> bytes:
    player_records = score_string(0x0020, row[0]) + score_string(0x0084, str(LOCAL_ACCOUNT_ID).encode("ascii"))
    return (pack("<2H", 0x4250, 1) + pack("<2HI", 0x4270, 2, rank) + score_stats(row) + player_records
            + pack("<2H", 0x4260, 1))


def recorded_score_list_reply(rows: Sequence[tuple[tuple[bytes, int, int | None], int]], *,
                              start: int = 1) -> bytes:
    """A paged list: the row count, the window, then one 0x4250..0x4260 row per (row, rank)."""
    window = pack("<2HI2HI", 0x4200, 2, len(rows), 0x4210, 2, start)
    return SCORE_SUCCESS_PREFIX + window + b"".join(score_list_row(*entry) for entry in rows) + TERMINATOR


def recorded_score_reply(row: tuple[bytes, int, int | None], *, paged: bool, national: bool = False,
                         rank: int = 1) -> bytes:
    if paged:
        return recorded_score_list_reply([(row, rank)])
    entry = pack("<2HI", 0x42D1, 2, 2) if national else b""
    records = (pack("<2H", 0x4230, 1) + entry + pack("<2HI", 0x4270, 2, rank) + score_stats(row)
               + pack("<2H", 0x4240, 1))
    return SCORE_SUCCESS_PREFIX + pack("<2HI", 0x4200, 2, 1) + records + TERMINATOR


class ScoreStore:
    """One best score per (event group, player); the group key is shared by all players."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            columns = db.execute("PRAGMA table_info(local_scores)").fetchall()
            if not columns:
                db.execute(self.CREATE.format("local_scores"))
            elif {name for _, name, _, _, _, key in columns if key} != {"event_group", "player"}:
                # Older databases keep one row per event group; carry those rows over.
                db.execute(self.CREATE.format("local_scores_new"))
                db.execute("INSERT INTO local_scores_new SELECT event_group, player, primary_score, "
                           "secondary_score FROM local_scores")
                db.execute("DROP TABLE local_scores")
                db.execute("ALTER TABLE local_scores_new RENAME TO local_scores")

    CREATE = ("CREATE TABLE {} (event_group BLOB NOT NULL, player BLOB NOT NULL, "
              "primary_score INTEGER NOT NULL, secondary_score INTEGER, PRIMARY KEY (event_group, player))")

    def write(self, score: tuple[bytes, bytes, int, int | None]) -> None:
        better_or_equal = ">=" if self.order(score[0]) == "DESC" else "<="
        with closing(sqlite3.connect(self.path, timeout=2)) as db, db:
            db.execute("INSERT INTO local_scores VALUES (?, ?, ?, ?) "
                       "ON CONFLICT (event_group, player) DO UPDATE SET "
                       "primary_score = excluded.primary_score, secondary_score = excluded.secondary_score "
                       f"WHERE excluded.primary_score {better_or_equal} local_scores.primary_score",
                       score)

    @staticmethod
    def checked(row: tuple) -> tuple[bytes, int, int | None]:
        if (not isinstance(row[0], bytes) or not LOCAL_SCORE_NAME.fullmatch(row[0])
                or not isinstance(row[1], int) or (row[2] is not None and not isinstance(row[2], int))):
            raise sqlite3.DatabaseError("Invalid local score row")
        return row

    @staticmethod
    def order(group: bytes) -> str:
        # Long Drive ranks by distance; every other board ranks by strokes.
        return "DESC" if group.startswith(b"LongDriveContest_") else "ASC"

    def top(self, group: bytes, limit: int = 1) -> list[tuple[bytes, int, int | None]]:
        """Best rows first; ties keep the name order."""
        with closing(sqlite3.connect(self.path, timeout=2)) as db:
            rows = db.execute("SELECT player, primary_score, secondary_score FROM local_scores "
                              f"WHERE event_group = ? ORDER BY primary_score {self.order(group)}, player LIMIT ?",
                              (group, limit)).fetchall()
        return [self.checked(row) for row in rows]

    def ranked_page(self, group: bytes, start: int, limit: int) -> list[tuple[tuple[bytes, int, int | None], int]]:
        """Rank the full group before taking a one-based page."""
        order = self.order(group)
        with closing(sqlite3.connect(self.path, timeout=2)) as db:
            rows = db.execute("SELECT player, primary_score, secondary_score, "
                              f"RANK() OVER (ORDER BY primary_score {order}) "
                              "FROM local_scores WHERE event_group = ? "
                              f"ORDER BY primary_score {order}, player LIMIT ? OFFSET ?",
                              (group, limit, start - 1)).fetchall()
        return [(self.checked(row[:3]), row[3]) for row in rows]

    def distribution(self, group: bytes) -> bytes:
        """Count the retained best scores in this group by signed 32-bit score."""
        with closing(sqlite3.connect(self.path, timeout=2)) as db:
            rows = db.execute(
                "SELECT primary_score, COUNT(*) FROM local_scores WHERE event_group = ? "
                "AND typeof(primary_score) = 'integer' AND primary_score BETWEEN ? AND ? "
                "GROUP BY primary_score ORDER BY primary_score", (group, -(1 << 31), (1 << 31) - 1))
            data = [{"num": str(count), "score": str(score)} for score, count in rows]
        return json.dumps(data, separators=(",", ":")).encode("ascii")

    def read(self, group: bytes, player: bytes | None = None) -> tuple[bytes, int, int | None] | None:
        """The named player's row, or the best row when the player is unknown."""
        if player is None:
            rows = self.top(group)
            return rows[0] if rows else None
        with closing(sqlite3.connect(self.path, timeout=2)) as db:
            row = db.execute("SELECT player, primary_score, secondary_score FROM local_scores "
                             "WHERE event_group = ? AND player = ?", (group, player)).fetchone()
        return self.checked(row) if row is not None else None

    def read_ranked(self, group: bytes, player: bytes | None = None) -> tuple[tuple[bytes, int, int | None], int] | None:
        """Read the score and its competition rank from the same snapshot."""
        if player is None:
            best = self.read(group)
            return (best, 1) if best is not None else None
        better = "<" if self.order(group) == "ASC" else ">"
        with closing(sqlite3.connect(self.path, timeout=2)) as db:
            row = db.execute(
                "SELECT score.player, score.primary_score, score.secondary_score, "
                "(SELECT COUNT(*) + 1 FROM local_scores AS rival WHERE rival.event_group = score.event_group "
                f"AND rival.primary_score {better} score.primary_score) "
                "FROM local_scores AS score WHERE score.event_group = ? AND score.player = ?",
                (group, player)).fetchone()
        return (self.checked(row[:3]), row[3]) if row is not None else None


def valid_user_status_request(body: bytes) -> bool:
    fields = title_fields(body, SERVER_TIME_SUFFIX, USER_STATUS_FIELDS)
    if fields is None:
        return False
    token = padded_string(fields[1])
    return (token is not None and len(token) <= 1000 and fields[-1] == bytes(4) and
            all(actual == expected for actual, (_, expected) in zip(fields[2:-1], USER_STATUS_SESSION)))


def valid_national_event_fields(fields: list[bytes]) -> bool:
    group, tournament_id, description, first, second = fields
    return (padded_string(group) == LOCAL_TOURNAMENT_GROUP and tournament_id == pack("<I", LOCAL_TOURNAMENT_ID)
            and padded_string(description) == b"" and first == second == bytes(4))


def valid_national_join_request(body: bytes) -> bool:
    fields = title_fields(body, SERVER_TIME_SUFFIX, NATIONAL_JOIN_FIELDS)
    if fields is None:
        return False
    token = padded_string(fields[1])
    return token is not None and len(token) <= 1000 and valid_national_event_fields(fields[2:])


def valid_national_score_list_request(body: bytes) -> bool:
    tail_start = -len(SERVER_TIME_SUFFIX)
    single = body[tail_start - 4:tail_start] == pack("<I", 1)
    layout = NATIONAL_SCORE_LIST_SINGLE_FIELDS if single else NATIONAL_SCORE_LIST_FIELDS
    fields = title_fields(body, SERVER_TIME_SUFFIX, layout)
    if fields is None:
        return False
    token = padded_string(fields[1])
    if token is None or len(token) > 1000 or not valid_national_event_fields(fields[2:7]):
        return False
    if single:
        account, terminator, _padding = fields[7].partition(b"\0")
        return bool(terminator) and account == fields[0].partition(b"\0")[0]
    return True


def valid_national_own_score_request(body: bytes) -> bool:
    fields = title_fields(body, SERVER_TIME_SUFFIX, NATIONAL_OWN_SCORE_FIELDS)
    if fields is None:
        return False
    token = padded_string(fields[1])
    return (token is not None and len(token) <= 1000
            and fields[2:5] == [payload for _, payload in USER_STATUS_SESSION]
            and valid_national_event_fields(fields[5:]))


def valid_session_target(target: str, pattern: re.Pattern) -> bool:
    match = pattern.fullmatch(target)
    return match is not None and -(1 << 31) <= int(match[1]) < (1 << 31)


def valid_login_request(body: bytes) -> bool:
    fields = title_fields(body, SERVER_TIME_SUFFIX, LOGIN_FIELDS)
    if fields is None:
        return False
    name, account, metadata, reserved, code, _selector = fields
    return (padded_string(name) is not None and valid_account_field(account) and
            metadata[6:8] == b"\x02\x02" and reserved == bytes(16) and
            padded_string(code) == LOGIN_PROBE_CODE)


def valid_daily_score_request(body: bytes) -> bool:
    fields = title_fields(body, DAILY_SCORE_TAIL, DAILY_SCORE_FIELDS)
    if fields is None:
        return False
    account, cipher, event = fields
    event_name = padded_string(event)
    return (padded_string(account) is not None and len(cipher) % 8 == 0 and
            event_name is not None and re.fullmatch(rb"Daily_[0-9]{8}_[0-9]{2}_score", event_name) is not None)


def valid_regulation_request(body: bytes) -> bool:
    fields = title_fields(body, SERVER_TIME_SUFFIX, REGULATION_FIELDS)
    if fields is None:
        fields = title_fields(body, SERVER_TIME_SUFFIX, DATED_REGULATION_FIELDS)
        if fields is None:
            return False
        try:
            datetime.strptime(fields[2].hex(), "%Y%m%d")
        except ValueError:
            return False
    return padded_string(fields[0]) is not None and len(fields[1]) % 8 == 0


def daily_score_records(block: bytes) -> bytes:
    if len(block) != 8:
        raise ValueError("Daily score fixture must contain one encrypted 8-byte block")
    return (
        pack("<4HI2H", 0x8000, 1, 0x0000, 2, 1, 0x0060, 3) + block
        + pack("<2HI2HI2HI", 0x4200, 2, 0, 0x4210, 2, 1, 0x4220, 2, 0)
        + TERMINATOR
    )


def valid_board_list_request(body: bytes) -> bool:
    fields = title_fields(body, SERVER_TIME_SUFFIX, BOARD_LIST_FIELDS)
    if fields is None:
        return False
    account, cipher, start, limit = fields
    return (padded_string(account) is not None and len(cipher) % 8 == 0 and
            start == pack("<I", 1) and 2 <= unpack_from("<I", limit)[0] <= 213)


def empty_board_records(block: bytes) -> bytes:
    if len(block) != 8:
        raise ValueError("Empty board fixture must contain one encrypted 8-byte block")
    return (
        pack("<4HI2H", 0x8000, 1, 0x0000, 2, 1, 0x0060, 3) + block
        + pack("<4HI", 0x4100, 1, 0x4110, 2, 0) + TERMINATOR
    )


def valid_finish_board_request(body: bytes) -> bool:
    fields = title_fields(body, SERVER_TIME_SUFFIX, FINISH_BOARD_FIELDS)
    if fields is None:
        return False
    account, cipher, _marker, year_month_day = fields
    try:
        datetime.strptime(year_month_day.hex(), "%Y%m%d")
    except ValueError:
        return False
    return padded_string(account) is not None and len(cipher) % 8 == 0


def empty_finish_board_records(block: bytes) -> bytes:
    return (
        pack("<4HI2H", 0x8000, 1, 0x0000, 2, 1, 0x0060, 3) + block
        + pack("<6HI6HI", 0x6540, 1, 0x6560, 1, 0x6580, 2, 0,
               0x6550, 1, 0x6570, 1, 0x6590, 2, 0)
        + TERMINATOR
    )


def schedule_selector(body: bytes) -> int | None:
    fields = title_fields(body, SERVER_TIME_SUFFIX, SCHEDULE_FIELDS)
    if fields is None:
        fields = title_fields(body, SERVER_TIME_SUFFIX, SCHEDULE_FIELDS + SCHEDULE_WINDOW)
    if fields is None:
        return None
    token = padded_string(fields[1])
    selector = unpack_from("<I", fields[2])[0]
    if token is None or len(token) > 1000 or selector > 4:
        return None
    if len(fields) > len(SCHEDULE_FIELDS):
        size = unpack_from("<I", fields[4])[0]
        expected = (18, (2 * size + 2) & 0xFFFFFFFF, 18, 2, 2)[selector]
        if (unpack_from("<i", fields[5])[0] <= 0 or fields[6] != pack("<I", 1)
                or fields[7] != pack("<I", expected)):
            return None
    return selector


def valid_character_board_request(body: bytes) -> bool:
    fields = title_fields(body, SERVER_TIME_SUFFIX, CHARACTER_BOARD_FIELDS)
    if fields is None:
        fields = title_fields(body, SERVER_TIME_SUFFIX, CHARACTER_BOARD_FIELDS + SCHEDULE_WINDOW)
    if fields is None:
        return False
    token = padded_string(fields[1])
    page = [pack("<I", 1), pack("<I", 2)]
    if token is None or len(token) > 1000 or fields[3:5] != page:
        return False
    if len(fields) == len(CHARACTER_BOARD_FIELDS):
        return True
    return unpack_from("<i", fields[5])[0] > 0 and fields[6:] == page


def schedule_reply(rows: Sequence[bytes] = ()) -> bytes:
    header = pack("<2HI2H", 0x4100, 2, len(rows), 0x4110, 1)
    return SCORE_SUCCESS_PREFIX + header + b"".join(rows) + TERMINATOR


def schedule_records(group: str, at: datetime | None) -> tuple[int, bytes]:
    value = group.encode("ascii")
    selector = next((i for i in range(len(OWN_SCORE_GROUPS)) if valid_score_group(value, i)), None)
    if selector is None or at is None or value.split(b"_", 2)[1] != f"{at.year:04d}{at:%m%d}".encode("ascii"):
        raise ValueError("Event group must match a One Hole, Daily or Long Drive group on the configured server date")
    start = at.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(hour=23, minute=59, second=59)
    row = (pack("<2H", 0x4120, 1) + score_string(0x4140, value) + pack("<2H", 0x4150, 1)
           + pack("<2H", 0x4177, 3) + bcd_timestamp(start)
           + pack("<2H", 0x4178, 3) + bcd_timestamp(end) + pack("<2H", 0x4130, 1))
    return selector, row


def require_lobby_loopback(bind: str) -> None:
    try:
        if IPv4Address(bind).is_loopback:
            return
    except AddressValueError:
        pass
    raise ValueError("--local-lobbies requires an IPv4 loopback bind address")


class GolfServer(ThreadingHTTPServer):
    def __init__(self, port: int, discovery: bytes | None = None, *,
                 server_time: datetime | None = None, ticket_grants: bool = False,
                 eula_text: bytes | None = None, empty_notices: bool = False,
                 daily_score_block: bytes | None = None, login_rejection: bool = False,
                 empty_board_block: bytes | None = None, cached_property: bool = False,
                 discard_telemetry: bool = False, catalog_fixture: bool = False,
                 login_completion: bool = False, empty_national_boards: bool = False,
                 empty_own_score: bool = False, score_db: Path | None = None,
                 event_group: str | tuple[str, ...] | None = None, local_lobbies: bool = False,
                 national_tournament: bool = False, empty_bonus_list: bool = False,
                 empty_regulations: bool = False, bind: str = LOOPBACK,
                 handler: type[BaseHTTPRequestHandler] | None = None, room_key: str | None = None,
                 strict_key: bool = False):
        # With a room key, lobbies can face other machines: callers outside private and VPN
        # address ranges must send the key (see GolfHandler.parse_request).
        if local_lobbies and room_key is None:
            require_lobby_loopback(bind)
        if room_key is not None and not re.fullmatch(r"[0-9a-f]{7}", room_key):
            raise ValueError("The room key is 7 lowercase hex digits")
        self.room_key = room_key
        # strict_key: every caller but this PC needs the key, home network and VPN ones too.
        self.strict_key = strict_key and room_key is not None
        if discovery is not None and (not 0 < len(discovery) <= MAX_DISCOVERY_BYTES or
                                      len(discovery) % DISCOVERY_BLOCK):
            raise ValueError(f"Discovery fixture must contain complete 8-byte blocks, up to {MAX_DISCOVERY_BYTES} bytes")
        if score_db is not None:
            login_completion = empty_own_score = True
        if login_rejection and login_completion:
            raise ValueError("Select one login reply")
        if national_tournament and server_time is None:
            raise ValueError("National tournament replay requires --server-time")
        if empty_regulations and daily_score_block is None:
            raise ValueError("Empty regulation replay requires --daily-score-block")
        self.discovery = discovery
        self.server_time = server_time_records(server_time) if server_time is not None else None
        self.eula = eula_records(eula_text) if eula_text is not None else None
        self.ticket_grants = ticket_grants
        self.empty_notices = empty_notices
        self.empty_bonus_list = empty_bonus_list
        self.login_reply = None
        if login_rejection:
            self.login_reply = LOGIN_REJECT_REPLY
        elif login_completion:
            self.login_reply = LOGIN_SCORE_SESSION_REPLY if empty_own_score else LOGIN_COMPLETE_REPLY
        self.daily_score = daily_score_records(daily_score_block) if daily_score_block is not None else None
        self.regulations = (
            TITLE_SUCCESS_PREFIX + pack("<2H", 0x0060, 3) + daily_score_block
            + pack("<2HI", 0x6000, 2, 0) + TERMINATOR
        ) if empty_regulations else None
        self.empty_own_score = empty_own_score
        self.empty_national_boards = empty_national_boards
        self.national_board = national_tournament_board(server_time) if national_tournament else None
        self.national_archive = tournament_archive(LOCAL_TOURNAMENT_ID) if national_tournament else None
        self.national_score_group = (f"National_{server_time:%Y%m%d}_{LOCAL_TOURNAMENT_ID}".encode("ascii")
                                     if national_tournament and score_db is not None else None)
        self.empty_boards = empty_board_records(empty_board_block) if empty_board_block is not None else None
        self.finish_boards = empty_finish_board_records(empty_board_block) if empty_board_block is not None else None
        self.schedule: dict[int, list[bytes]] = {}
        self.rival_groups: set[bytes] = set()
        event_groups = (event_group,) if isinstance(event_group, str) else event_group or ()
        for group in dict.fromkeys(event_groups):
            selector, row = schedule_records(group, server_time)
            rows = self.schedule.setdefault(selector, [])
            if len(rows) == SCHEDULE_MAX_ROWS:
                raise ValueError(f"At most {SCHEDULE_MAX_ROWS} event groups are allowed per board selector")
            rows.append(row)
            if selector == 1:
                self.rival_groups.add(group.encode("ascii"))
        self.cached_property = cached_property
        self.discard_telemetry = discard_telemetry
        self.catalog_fixture = catalog_fixture
        self.consumed_tickets = set()
        self.ticket_lock = Lock()
        self.scores = ScoreStore(score_db) if score_db is not None else None
        self.local_lobbies = LobbyRegistry() if local_lobbies else None
        self.players: dict[str, bytes] = {}
        super().__init__((bind, port), handler or GolfHandler)

    def server_bind(self):
        TCPServer.server_bind(self)
        # HTTPServer.server_bind normally resolves its own host name.
        self.server_name, self.server_port = self.server_address

    def get_request(self):
        client, address = super().get_request()
        client.settimeout(3)
        return client, address


def needs_room_key(address: str) -> bool:
    """Callers from public addresses need the key; this PC, home networks and VPN ranges
    (private and shared 100.64.0.0/10 addresses, as Tailscale uses) do not."""
    try:
        return IPv4Address(address).is_global
    except AddressValueError:
        return True


class GolfHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: GolfServer

    def room_key_ok(self) -> bool:
        key = self.server.room_key
        address = self.client_address[0]
        if key is None or not (needs_room_key(address) or (self.server.strict_key and not address.startswith("127."))):
            return True
        sent = self.headers.get_all(ROOM_KEY_HEADER, [])
        return len(sent) == 1 and hmac.compare_digest(sent[0].strip().lower().encode("ascii", "replace"),
                                                      key.encode("ascii"))

    def parse_request(self) -> bool:
        if not super().parse_request():
            return False
        if self.room_key_ok():
            return True
        self.close_connection = True
        self.send_response(HTTPStatus.FORBIDDEN)
        self.send_header("Connection", "close")
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def reply(self, status: HTTPStatus, body: bytes = b"", *,
              content_type: str | None = None, allow: str | None = None, keep_alive: bool = False):
        # Lobby and packet exchanges reuse one connection per runtime thread: a new TCP
        # handshake per 20 ms tick would double the round trips over the internet.
        keep_alive = keep_alive and status == HTTPStatus.OK and not self.close_connection
        self.close_connection = not keep_alive
        self.send_response(status)
        self.send_header("Connection", "keep-alive" if keep_alive else "close")
        self.send_header("Content-Length", str(len(body)))
        if allow:
            self.send_header("Allow", allow)
        if content_type:
            self.send_header("Content-Type", content_type)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def reject_before_reading(self, status: HTTPStatus, *, allow: str | None = None):
        # Closing with unread request bytes can abort the response on Windows.
        lengths = self.headers.get_all("Content-Length", [])
        if (len(lengths) == 1 and re.fullmatch(r"[1-9][0-9]{0,3}", lengths[0])
                and "Transfer-Encoding" not in self.headers):
            self.rfile.read(int(lengths[0]))
        self.reply(status, allow=allow)

    def read_replay_online_id(self) -> bool:
        self.replay_online_id = None
        identities = self.headers.get_all("X-Golf-Online-Id", [])
        if identities:
            if (len(identities) != 1 or not self.client_address[0].startswith("127.")
                    or not identities[0].isascii()
                    or not LOCAL_SCORE_NAME.fullmatch(identities[0].encode("ascii"))):
                self.reject_before_reading(HTTPStatus.BAD_REQUEST)
                return False
            self.replay_online_id = identities[0].encode("ascii")
        return True

    def do_GET(self):
        if not self.read_replay_online_id():
            return
        labels = commerce_batch_labels(self.path) if self.server.catalog_fixture else []
        national_download = self.national_download()
        if self.path != DISCOVERY_PATH and self.path not in JSON_GET_RESPONSES and not labels and national_download is None:
            self.method_not_allowed()
            return
        lengths = self.headers.get_all("Content-Length", [])
        if lengths not in ([], ["0"]) or "Transfer-Encoding" in self.headers:
            self.reject_before_reading(HTTPStatus.BAD_REQUEST)
            return
        if national_download is not None:
            if self.path == NATIONAL_DISTRIBUTION_DOWNLOAD_PATH and self.server.national_score_group is not None:
                try:
                    saved = self.server.scores.read(self.server.national_score_group, self.player())
                except sqlite3.Error:
                    self.reply(HTTPStatus.SERVICE_UNAVAILABLE)
                    return
                if saved is not None:
                    national_download = distribution_data(saved[1])
            self.reply(HTTPStatus.OK, national_download, content_type="application/octet-stream")
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
            body = commerce_batch_reply(labels) if labels else JSON_GET_RESPONSES[self.path]
            self.reply(HTTPStatus.OK, body, content_type="application/json")
            return
        if self.server.discovery is None:
            self.reply(HTTPStatus.SERVICE_UNAVAILABLE)
            return
        self.reply(HTTPStatus.OK, self.server.discovery, content_type="application/octet-stream")

    def do_POST(self):
        if self.path in LOCAL_LOBBY_PATHS and self.server.local_lobbies is not None:
            self.local_lobby_post()
            return
        if self.server.discard_telemetry and self.path == TELEMETRY_PATH:
            self.discard_telemetry_post()
            return
        if not self.read_replay_online_id():
            return
        registration = self.registration_selector()
        score_query_paged = None
        if self.path == PROPERTY_INFO_PATH and self.server.cached_property:
            response = PROPERTY_CACHED_REPLY
            minimum = maximum = PROPERTY_REQUEST_BYTES
            validate = valid_property_request
        elif self.path == SERVER_TIME_PATH and self.server.server_time is not None:
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
        elif self.path == BONUS_LIST_PATH and self.server.empty_bonus_list:
            response = BONUS_LIST_REPLY
            minimum, maximum = BONUS_LIST_MIN_BYTES, BONUS_LIST_MAX_BYTES
            validate = partial(valid_title_session_request, layout=BONUS_LIST_FIELDS)
        elif self.path == REGULATION_PATH and self.server.regulations is not None:
            response = self.server.regulations
            minimum, maximum = REGULATION_MIN_BYTES, REGULATION_MAX_BYTES
            validate = valid_regulation_request
        elif self.is_daily_score():
            response = self.server.daily_score
            minimum, maximum = DAILY_SCORE_MIN_BYTES, DAILY_SCORE_MAX_BYTES
            validate = valid_daily_score_request
        elif self.path.startswith(SCORE_BOARD_PREFIX) and self.server.empty_own_score:
            if not valid_session_target(self.path, SCORE_BOARD_TARGET):
                self.reject_before_reading(HTTPStatus.BAD_REQUEST)
                return
            response = OWN_SCORE_EMPTY_REPLY
            minimum, maximum = SCORE_BOARD_MIN_BYTES, SCORE_BOARD_MAX_BYTES
            score_query_paged = True
            validate = None
        elif self.path == OWN_SCORE_PATH and self.server.empty_own_score:
            response = OWN_SCORE_EMPTY_REPLY
            minimum, maximum = OWN_SCORE_MIN_BYTES, OWN_SCORE_MAX_BYTES
            score_query_paged = False
            validate = None
        elif self.path == TOP_PLAYER_PATH and self.server.empty_own_score:
            response = TOP_PLAYER_REPLY
            minimum, maximum = TOP_PLAYER_MIN_BYTES, TOP_PLAYER_MAX_BYTES
            validate = valid_top_player_request
        elif self.path == SCORE_DISTRIBUTION_PATH and self.server.empty_own_score:
            response = SCORE_DISTRIBUTION_REPLY
            minimum, maximum = SCORE_DISTRIBUTION_MIN_BYTES, SCORE_DISTRIBUTION_MAX_BYTES
            validate = None
        elif registration is not None:
            if not valid_session_target(self.path, REGISTRATION_TARGETS[registration]):
                self.reject_before_reading(HTTPStatus.BAD_REQUEST)
                return
            response = score_registration_reply(registration)
            minimum, maximum = REGISTRATION_SIZES[registration]
            validate = None
        elif self.path == CHARACTER_ASSIGNMENT_PATH and self.server.empty_own_score:
            response = CHARACTER_ASSIGNMENT_REPLY
            minimum, maximum = TITLE_SESSION_MIN_BYTES, TITLE_SESSION_MAX_BYTES
            validate = valid_title_session_request
        elif self.path.startswith(COURSE_ASSIGNMENT_PREFIX) and self.server.empty_own_score:
            if not valid_session_target(self.path, COURSE_ASSIGNMENT_TARGET):
                self.reject_before_reading(HTTPStatus.BAD_REQUEST)
                return
            response = TITLE_SUCCESS_REPLY
            minimum, maximum = TITLE_SESSION_MIN_BYTES, TITLE_SESSION_MAX_BYTES
            validate = valid_title_session_request
        elif self.path.startswith(CHARACTER_COUNT_PREFIX) and self.server.empty_own_score:
            if self.path != CHARACTER_COUNT_PREFIX and not valid_session_target(self.path, CHARACTER_COUNT_TARGET):
                self.reject_before_reading(HTTPStatus.BAD_REQUEST)
                return
            response = CHARACTER_COUNT_REPLY
            minimum, maximum = CHARACTER_COUNT_MIN_BYTES, CHARACTER_COUNT_MAX_BYTES
            validate = valid_character_count_request
        elif self.path == FINISH_BOARD_PATH and self.server.finish_boards is not None:
            response = self.server.finish_boards
            minimum, maximum = FINISH_BOARD_MIN_BYTES, FINISH_BOARD_MAX_BYTES
            validate = valid_finish_board_request
        elif self.path == SIGN_BOARD_PATH and self.server.empty_boards is not None:
            response = SIGN_BOARD_REPLY
            minimum, maximum = TITLE_SESSION_MIN_BYTES, TITLE_SESSION_MAX_BYTES
            validate = valid_title_session_request
        elif self.path == CHARACTER_BOARD_PATH and self.server.empty_boards is not None:
            response = schedule_reply()
            minimum, maximum = SCHEDULE_MIN_BYTES, SCHEDULE_MAX_BYTES
            validate = valid_character_board_request
        elif self.path == RIVAL_LIST_PATH and self.server.rival_groups:
            response = RIVAL_LIST_REPLY
            minimum, maximum = RIVAL_LIST_MIN_BYTES, RIVAL_LIST_MAX_BYTES
            validate = partial(valid_rival_request, groups=self.server.rival_groups)
        elif self.path == USER_STATUS_PATH and self.server.empty_own_score:
            response = TITLE_SUCCESS_REPLY
            minimum, maximum = USER_STATUS_MIN_BYTES, USER_STATUS_MAX_BYTES
            validate = valid_user_status_request
        elif self.path == BOARD_LIST_PATH and (self.server.empty_boards is not None or self.server.schedule):
            response = None
            minimum = BOARD_LIST_MIN_BYTES if self.server.empty_boards is not None else SCHEDULE_MIN_BYTES
            maximum = SCHEDULE_MAX_BYTES if self.server.schedule else BOARD_LIST_MAX_BYTES
            validate = None
        elif self.path == NATIONAL_BOARD_PATH and (self.server.empty_national_boards or self.server.national_board):
            response = NATIONAL_BOARD_REPLY
            minimum, maximum = NATIONAL_BOARD_MIN_BYTES, NATIONAL_BOARD_MAX_BYTES
            validate = valid_national_board_request
        elif self.path == NATIONAL_GAME_DATA_PATH and self.server.national_archive is not None:
            response = national_game_data_reply()
            minimum, maximum = NATIONAL_GAME_DATA_MIN_BYTES, NATIONAL_GAME_DATA_MAX_BYTES
            validate = partial(valid_national_id_request, layout=NATIONAL_GAME_DATA_FIELDS)
        elif self.path == NATIONAL_DISTRIBUTION_PATH and self.server.national_archive is not None:
            response = (SCORE_SUCCESS_PREFIX + score_string(0x4292, NATIONAL_DISTRIBUTION_SUFFIX.encode("ascii"))
                        + TERMINATOR)
            minimum, maximum = NATIONAL_DISTRIBUTION_MIN_BYTES, NATIONAL_DISTRIBUTION_MAX_BYTES
            validate = partial(valid_national_id_request, layout=NATIONAL_DISTRIBUTION_FIELDS)
        elif self.path == NATIONAL_OWN_SCORE_PATH and self.server.national_archive is not None:
            response = NATIONAL_OWN_SCORE_EMPTY_REPLY
            minimum, maximum = NATIONAL_OWN_SCORE_MIN_BYTES, NATIONAL_OWN_SCORE_MAX_BYTES
            validate = valid_national_own_score_request
        elif self.path.startswith(NATIONAL_JOIN_PREFIX) and self.server.national_archive is not None:
            if not valid_session_target(self.path, NATIONAL_JOIN_TARGET):
                self.reject_before_reading(HTTPStatus.BAD_REQUEST)
                return
            response = NATIONAL_JOIN_REPLY
            minimum, maximum = NATIONAL_JOIN_MIN_BYTES, NATIONAL_JOIN_MAX_BYTES
            validate = valid_national_join_request
        elif self.path == NATIONAL_SCORE_LIST_PATH and self.server.national_archive is not None:
            response = NATIONAL_SCORE_LIST_REPLY
            minimum, maximum = NATIONAL_SCORE_LIST_MIN_BYTES, NATIONAL_SCORE_LIST_MAX_BYTES
            validate = valid_national_score_list_request
        elif self.path.startswith(NATIONAL_REGISTRATION_PREFIX) and self.server.national_score_group is not None:
            if not valid_session_target(self.path, NATIONAL_REGISTRATION_TARGET):
                self.reject_before_reading(HTTPStatus.BAD_REQUEST)
                return
            response = score_registration_reply(1)
            minimum, maximum = NATIONAL_REGISTRATION_MIN_BYTES, NATIONAL_REGISTRATION_MAX_BYTES
            validate = None
        elif self.path.startswith(LOGIN_PREFIX) and self.server.login_reply is not None:
            if not valid_session_target(self.path, LOGIN_TARGET):
                self.reject_before_reading(HTTPStatus.BAD_REQUEST)
                return
            response = self.server.login_reply
            minimum, maximum = LOGIN_MIN_BYTES, LOGIN_MAX_BYTES
            validate = valid_login_request
        else:
            self.method_not_allowed()
            return
        if self.headers.get_all("Content-Type", []) != [MULTIPART_TYPE]:
            self.reject_before_reading(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return
        lengths = self.headers.get_all("Content-Length", [])
        if (len(lengths) != 1 or not re.fullmatch(r"[1-9][0-9]{0,3}", lengths[0])
                or "Transfer-Encoding" in self.headers):
            self.reply(HTTPStatus.BAD_REQUEST)
            return
        length = int(lengths[0])
        if not minimum <= length <= maximum:
            self.reject_before_reading(HTTPStatus.BAD_REQUEST)
            return
        body = self.rfile.read(length)
        if len(body) != length or (validate is not None and not validate(body)):
            self.reply(HTTPStatus.BAD_REQUEST)
            return
        if self.path.startswith(LOGIN_PREFIX) and self.server.login_reply is not None:
            name = padded_string(title_fields(body, SERVER_TIME_SUFFIX, LOGIN_FIELDS)[0])
            if self.replay_online_id is not None and name != self.replay_online_id:
                self.reply(HTTPStatus.BAD_REQUEST)
                return
            if name is not None and LOCAL_SCORE_NAME.fullmatch(name):
                self.remember_player(name)
        if (self.path == NATIONAL_BOARD_PATH and self.server.national_board
                and unpack_from("<I", body, -len(SERVER_TIME_SUFFIX) - 4)[0] in NATIONAL_BOARD_DOWNLOAD_SELECTORS):
            response = SCORE_SUCCESS_PREFIX + score_string(0x4A60, NATIONAL_BOARD_SUFFIX.encode("ascii")) + TERMINATOR
        if response is None:
            response = self.board_reply(body)
            if response is None:
                self.reply(HTTPStatus.BAD_REQUEST)
                return
        if registration is not None:
            score = registered_score(body, registration)
            if score is None or not self.matches_player(score[1]):
                self.reply(HTTPStatus.BAD_REQUEST)
                return
            try:
                self.server.scores.write(score)
                self.remember_player(score[1])
            except sqlite3.Error:
                self.reply(HTTPStatus.SERVICE_UNAVAILABLE)
                return
        distribution_query = self.path == SCORE_DISTRIBUTION_PATH
        paged_list = bool(score_query_paged)
        if score_query_paged is not None or distribution_query:
            group = (score_distribution_group(body) if distribution_query
                     else score_query_group(body, paged=score_query_paged))
            if group is None:
                self.reply(HTTPStatus.BAD_REQUEST)
                return
            if self.server.scores is not None:
                try:
                    if paged_list:
                        ranked = self.server.scores.top(group, self.score_list_rows(body))
                        if ranked:
                            response = self.ranked_list_reply(ranked)
                    elif distribution_query:
                        data = self.server.scores.distribution(group)
                        if len(data) > MAX_DISTRIBUTION_JSON:
                            self.reply(HTTPStatus.SERVICE_UNAVAILABLE)
                            return
                        if data != b"[]":
                            response = SCORE_SUCCESS_PREFIX + score_string(0x4950, data) + TERMINATOR
                    else:
                        own = self.server.scores.read_ranked(group, self.player())
                        if own is not None:
                            row, rank = own
                            response = recorded_score_reply(row, paged=False, rank=rank)
                except sqlite3.Error:
                    self.reply(HTTPStatus.SERVICE_UNAVAILABLE)
                    return
        if self.server.national_score_group is not None:
            try:
                response = self.national_score_reply(body, response)
            except sqlite3.Error:
                self.reply(HTTPStatus.SERVICE_UNAVAILABLE)
                return
            if response is None:
                self.reply(HTTPStatus.BAD_REQUEST)
                return
        self.reply(HTTPStatus.OK, response, content_type="application/octet-stream")

    def national_score_reply(self, body: bytes, fallback: bytes) -> bytes | None:
        group = self.server.national_score_group
        if self.path.startswith(NATIONAL_REGISTRATION_PREFIX):
            score = registered_national_score(body, group)
            if score is None or not self.matches_player(score[1]):
                return None
            self.server.scores.write(score)
            self.remember_player(score[1])
        elif self.path in (NATIONAL_SCORE_LIST_PATH, NATIONAL_OWN_SCORE_PATH):
            paged = self.path == NATIONAL_SCORE_LIST_PATH
            if paged:
                start, _, size = unpack_from("<3I", body, -len(SERVER_TIME_SUFFIX) - 12)
                if not size or (size == 1 and start > 1):
                    return fallback
                start = max(1, start)
                ranked = self.server.scores.ranked_page(group, start, min(size, MAX_SCORE_LIST_ROWS))
                return recorded_score_list_reply(ranked, start=start)
            own = self.server.scores.read_ranked(group, self.player())
            if own is not None:
                row, rank = own
                return recorded_score_reply(row, paged=False, national=True, rank=rank)
        return fallback

    def matches_player(self, name: bytes) -> bool:
        return self.replay_online_id is None or name == self.replay_online_id

    def remember_player(self, name: bytes):
        if self.replay_online_id is None:
            self.server.players[self.client_address[0]] = name

    def player(self) -> bytes | None:
        """Resolve the explicit loopback identity or the legacy address mapping."""
        return self.replay_online_id or self.server.players.get(self.client_address[0])

    @staticmethod
    def score_list_rows(body: bytes) -> int:
        fields = title_fields(body, SERVER_TIME_SUFFIX, SCORE_BOARD_FIELDS)
        return min(unpack_from("<i", fields[5])[0], MAX_SCORE_LIST_ROWS) if fields else DEFAULT_SCORE_LIST_ROWS

    @staticmethod
    def ranked_list_reply(rows: list[tuple[bytes, int, int | None]]) -> bytes:
        """Rank the sorted first page from the same snapshot as its rows."""
        entries = []
        previous_score = None
        rank = 1
        for position, row in enumerate(rows, 1):
            if row[1] != previous_score:
                rank = position
                previous_score = row[1]
            entries.append((row, rank))
        return recorded_score_list_reply(entries)

    def board_reply(self, body: bytes) -> bytes | None:
        if BOARD_LIST_MIN_BYTES <= len(body) <= BOARD_LIST_MAX_BYTES and self.server.empty_boards is not None:
            return self.server.empty_boards if valid_board_list_request(body) else None
        if SCHEDULE_MIN_BYTES <= len(body) <= SCHEDULE_MAX_BYTES and self.server.schedule:
            selector = schedule_selector(body)
            if selector is not None:
                return schedule_reply(self.server.schedule.get(selector, ()))
        return None

    def local_lobby_post(self):
        if self.headers.get_all("Content-Type", []) != [LOBBY_CONTENT_TYPE]:
            self.reject_before_reading(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return
        lengths = self.headers.get_all("Content-Length", [])
        if (len(lengths) != 1 or not re.fullmatch(r"[1-9][0-9]{0,4}", lengths[0])
                or "Transfer-Encoding" in self.headers):
            self.reject_before_reading(HTTPStatus.BAD_REQUEST)
            return
        length = int(lengths[0])
        if self.path == PEER_PACKET_PATH:
            minimum, maximum = PEER_REQUEST.size, PEER_REQUEST_MAX
            exchange = self.server.local_lobbies.exchange_packets
        elif self.path == PEER_CHANNEL_PATH:
            minimum = maximum = CHANNEL_REQUEST.size
            exchange = self.server.local_lobbies.exchange_channels
        elif self.path == ROOM_PATH:
            minimum, maximum = ROOM_HEADER.size, ROOM_REQUEST_MAX
            exchange = self.server.local_lobbies.exchange_rooms
        elif self.path == ROOM_MESSAGE_PATH:
            minimum, maximum = ROOM_MESSAGE_REQUEST.size, ROOM_MESSAGE_REQUEST_MAX
            exchange = self.server.local_lobbies.exchange_room_messages
        elif self.path == TRANSPORT_PATH:
            minimum = maximum = TRANSPORT_REQUEST.size
            exchange = self.server.local_lobbies.exchange_transport
        else:
            minimum = maximum = LOBBY_REQUEST.size
            exchange = self.server.local_lobbies.exchange
        if not minimum <= length <= maximum:
            self.reject_before_reading(HTTPStatus.BAD_REQUEST)
            return
        request = self.rfile.read(length)
        if len(request) != length:
            self.reply(HTTPStatus.BAD_REQUEST)
            return
        status, body = exchange(request)
        self.reply(status, body, content_type=LOBBY_CONTENT_TYPE if body else None, keep_alive=True)

    def discard_telemetry_post(self):
        if self.headers.get_all("Content-Type", []) != ["application/json"]:
            self.reject_before_reading(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return
        lengths = self.headers.get_all("Content-Length", [])
        if (len(lengths) != 1 or not re.fullmatch(r"[1-9][0-9]{0,3}", lengths[0])
                or "Transfer-Encoding" in self.headers):
            self.reply(HTTPStatus.BAD_REQUEST)
            return
        length = int(lengths[0])
        if length > MAX_TELEMETRY_BYTES:
            self.reject_before_reading(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        body = self.rfile.read(length)
        try:
            value = json.loads(body.decode("utf-8")) if len(body) == length else None
        except (ValueError, RecursionError):
            value = None
        self.reply(HTTPStatus.OK if isinstance(value, (dict, list)) else HTTPStatus.BAD_REQUEST)

    def do_PUT(self):
        label = self.path.removeprefix(ENTITLEMENT_ITEM_PREFIX)
        if (not self.server.ticket_grants or label == self.path or label not in TICKET_SIZES):
            self.method_not_allowed()
            return
        if self.headers.get_all("Content-Type", []) != [JSON_TYPE]:
            self.reject_before_reading(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return
        lengths = self.headers.get_all("Content-Length", [])
        if (len(lengths) != 1 or not re.fullmatch(r"[1-9][0-9]?", lengths[0]) or
                int(lengths[0]) > MAX_CONSUME_BYTES or "Transfer-Encoding" in self.headers):
            self.reject_before_reading(HTTPStatus.BAD_REQUEST)
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

    def is_daily_score(self):
        return self.server.daily_score is not None and (
            self.path == DAILY_SCORE_PATH or (self.server.empty_own_score and self.path == SCORE_BOARD_PREFIX)
        )

    def registration_selector(self):
        if self.server.scores is None:
            return None
        return next((index for index, prefix in enumerate(REGISTRATION_PREFIXES)
                     if self.path.startswith(prefix)), None)

    def national_download(self):
        if self.path == NATIONAL_BOARD_DOWNLOAD_PATH:
            return self.server.national_board
        if self.path == NATIONAL_GAME_DOWNLOAD_PATH:
            return self.server.national_archive
        if self.path == NATIONAL_DISTRIBUTION_DOWNLOAD_PATH and self.server.national_archive is not None:
            return b"[]"
        return None

    def method_not_allowed(self):
        if (self.path == DISCOVERY_PATH or self.path in JSON_GET_RESPONSES
                or self.national_download() is not None
                or (self.server.catalog_fixture and commerce_batch_labels(self.path))):
            self.reject_before_reading(HTTPStatus.METHOD_NOT_ALLOWED, allow="GET")
        elif ((self.path in LOCAL_LOBBY_PATHS and self.server.local_lobbies is not None)
              or (self.path == SERVER_TIME_PATH and self.server.server_time is not None)
              or (self.path == EULA_PATH and self.server.eula is not None)
              or (self.path == NOTICE_PATH and self.server.empty_notices)
              or (self.path == BONUS_LIST_PATH and self.server.empty_bonus_list)
              or (self.path == REGULATION_PATH and self.server.regulations is not None)
              or self.is_daily_score()
              or (self.server.empty_own_score and valid_session_target(self.path, SCORE_BOARD_TARGET))
              or (self.server.scores is not None and
                  any(valid_session_target(self.path, route) for route in REGISTRATION_TARGETS))
              or (self.server.national_score_group is not None and
                  valid_session_target(self.path, NATIONAL_REGISTRATION_TARGET))
              or (self.server.empty_own_score and self.path in (
                  OWN_SCORE_PATH, TOP_PLAYER_PATH, SCORE_DISTRIBUTION_PATH, USER_STATUS_PATH,
                  CHARACTER_ASSIGNMENT_PATH, CHARACTER_COUNT_PREFIX))
              or (self.server.empty_own_score and valid_session_target(self.path, CHARACTER_COUNT_TARGET))
              or (self.server.empty_own_score and valid_session_target(self.path, COURSE_ASSIGNMENT_TARGET))
              or (self.path in (FINISH_BOARD_PATH, SIGN_BOARD_PATH, CHARACTER_BOARD_PATH)
                  and self.server.empty_boards is not None)
              or (self.path == RIVAL_LIST_PATH and self.server.rival_groups)
              or (self.path == NATIONAL_BOARD_PATH and (self.server.empty_national_boards or self.server.national_board))
              or (self.server.national_archive is not None and valid_session_target(self.path, NATIONAL_JOIN_TARGET))
              or (self.path in (NATIONAL_GAME_DATA_PATH, NATIONAL_OWN_SCORE_PATH,
                                NATIONAL_DISTRIBUTION_PATH, NATIONAL_SCORE_LIST_PATH)
                  and self.server.national_archive is not None)
              or (self.path == BOARD_LIST_PATH and (self.server.empty_boards is not None or self.server.schedule))
              or (self.path == PROPERTY_INFO_PATH and self.server.cached_property)
              or (self.path == TELEMETRY_PATH and self.server.discard_telemetry)
              or (self.server.login_reply is not None and valid_session_target(self.path, LOGIN_TARGET))):
            self.reject_before_reading(HTTPStatus.METHOD_NOT_ALLOWED, allow="POST")
        else:
            self.reject_before_reading(HTTPStatus.NOT_FOUND)

    do_HEAD = do_DELETE = do_PATCH = do_OPTIONS = method_not_allowed

    def log_message(self, format, *args):
        # Requests may contain account identifiers or credential headers.
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--bind", default=LOOPBACK, metavar="ADDRESS",
                        help="Address to listen on (default loopback; use 0.0.0.0 to host for other machines)")
    parser.add_argument("--ss-info-file", type=Path, help="Local encrypted discovery response fixture")
    parser.add_argument("--server-time", metavar="YYYY-MM-DDTHH:MM:SS",
                        help="Enable synthetic server-time replay at the specified time")
    parser.add_argument("--ticket-grants", action="store_true", help="Replay two synthetic ticket grants")
    parser.add_argument("--catalog-fixture", action="store_true",
                        help="Replay display-only entries for built-in product labels")
    parser.add_argument("--eula-file", type=Path, help="Local UTF-8 text for the EULA display probe")
    parser.add_argument("--empty-notices", action="store_true", help="Replay an empty local notice list")
    parser.add_argument("--empty-bonus-list", action="store_true", help="Replay an empty local bonus list")
    parser.add_argument("--daily-score-block", type=Path,
                        help="Encrypted block for the local daily score-list probe")
    parser.add_argument("--empty-regulations", action="store_true",
                        help="Replay no local event regulations (requires --daily-score-block)")
    parser.add_argument("--empty-own-score", action="store_true",
                        help="Enable local score queries and empty leaderboard replies")
    parser.add_argument("--score-db", type=Path,
                        help="Enable score registration and queries for the local account using this SQLite file")
    parser.add_argument("--event-group", action="append",
                        help="Advertise an event group on the --server-time date (repeat for additional groups)")
    parser.add_argument("--local-lobbies", action="store_true", help="Enable the native runtime's loopback lobby roster")
    parser.add_argument("--empty-board-block", type=Path,
                        help="Encrypted block for local empty board, finish-board, and sign-board fixtures")
    parser.add_argument("--empty-national-boards", action="store_true",
                        help="Return an empty national board for the login and entry selectors")
    parser.add_argument("--national-tournament", action="store_true",
                        help="Replay one local national tournament on the --server-time date")
    login = parser.add_mutually_exclusive_group()
    login.add_argument("--login-rejection", action="store_true",
                       help="Replay the local title login rejection")
    login.add_argument("--login-completion", action="store_true",
                       help="Probe the title's login completion branch with the synthetic account")
    parser.add_argument("--cached-property", action="store_true", help="Replay no update for property 1")
    parser.add_argument("--discard-telemetry", action="store_true", help="Discard local telemetry POST bodies")
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
        daily_score_block = None
        if args.daily_score_block:
            with args.daily_score_block.open("rb") as stream:
                daily_score_block = stream.read(9)
        empty_board_block = None
        if args.empty_board_block:
            with args.empty_board_block.open("rb") as stream:
                empty_board_block = stream.read(9)
        with GolfServer(args.port, discovery, server_time=server_time,
                        ticket_grants=args.ticket_grants, eula_text=eula_text,
                        empty_notices=args.empty_notices, daily_score_block=daily_score_block,
                        login_rejection=args.login_rejection, empty_board_block=empty_board_block,
                        cached_property=args.cached_property, discard_telemetry=args.discard_telemetry,
                        catalog_fixture=args.catalog_fixture, login_completion=args.login_completion,
                        empty_national_boards=args.empty_national_boards,
                        empty_own_score=args.empty_own_score, score_db=args.score_db,
                        event_group=tuple(args.event_group or ()),
                        local_lobbies=args.local_lobbies, national_tournament=args.national_tournament,
                        empty_bonus_list=args.empty_bonus_list, empty_regulations=args.empty_regulations,
                        bind=args.bind) as server:
            print(f"Listening on http://{args.bind}:{server.server_port}", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        return
    except (OSError, ValueError, OverflowError, sqlite3.Error) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
