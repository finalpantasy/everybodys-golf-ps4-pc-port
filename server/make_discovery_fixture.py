"""Build an Everybody's Golf 1.17 discovery fixture for IPv4 loopback."""
import argparse
import csv
import ctypes
from ctypes.util import find_library
import hashlib
from pathlib import Path

from golf_server import (
    ANALYTICS_PREFIX, BOARD_LIST_PATH, BONUS_LIST_PATH, CHARACTER_ASSIGNMENT_PATH, CHARACTER_BOARD_PATH,
    CHARACTER_COUNT_PREFIX,
    COURSE_ASSIGNMENT_PREFIX, DAILY_SCORE_PATH, EULA_PATH, FINISH_BOARD_PATH, GAME_DOWNLOAD_BASE, LOGIN_PREFIX,
    LOOPBACK, NATIONAL_BOARD_PATH, NATIONAL_DISTRIBUTION_PATH, NATIONAL_GAME_DATA_PATH, NATIONAL_JOIN_PATH,
    NATIONAL_OWN_SCORE_PATH, NATIONAL_REGISTRATION_PREFIX, NATIONAL_SCORE_LIST_PATH,
    NOTICE_PATH, OWN_SCORE_PATH,
    PROPERTY_INFO_PATH,
    REGISTRATION_OPERATIONS, REGISTRATION_PREFIXES, RIVAL_LIST_PATH, SCORE_BOARD_PREFIX,
    SCORE_DISTRIBUTION_PATH, SERVER_TIME_PATH, SIGN_BOARD_PATH, TOP_PLAYER_PATH, USER_STATUS_PATH,
)

PREPARED_EBOOT_HASH = "293156adf6462feedb574dd9cd5db45707469a6c407b1d89a2241a4bacde5dc2"
URL_MAP = Path(__file__).resolve().parents[1] / "analysis/online/title-url-map.tsv"
PROBE_ROOT = f"http://{LOOPBACK}:8765/nmg-us/replay-probe/"


def tag(name: str, value: str) -> str:
    return f"<{name}>{value}</{name}>"


def discovery_document(*, eula: bool = False, empty_notices: bool = False,
                       daily_scores: bool = False, login_rejection: bool = False,
                       empty_boards: bool = False, cached_property: bool = False,
                       discard_telemetry: bool = False, empty_national_boards: bool = False,
                       empty_own_score: bool = False, score_registration: bool = False,
                       event_schedule: bool = False, national_tournament: bool = False,
                       empty_bonus_list: bool = False) -> bytes:
    with URL_MAP.open(encoding="utf-8", newline="") as stream:
        entries = list(csv.DictReader(stream, delimiter="\t"))
    entries.sort(key=lambda row: (
        not row["validation_relocation_va"],
        int(row["validation_relocation_va"] or row["literal_va"], 16),
    ))
    urls = {row["key"]: PROBE_ROOT + row["key"] for row in entries}
    if len(urls) != 37:
        raise ValueError("Expected the 37-key discovery URL map")
    urls["gameapi_getservertime"] = f"https://{LOOPBACK}:8765{SERVER_TIME_PATH}"
    if eula:
        urls["gameapi_geteula"] = f"https://{LOOPBACK}:8765{EULA_PATH}"
    if empty_notices:
        urls["gameapi_getinfolist"] = f"https://{LOOPBACK}:8765{NOTICE_PATH}"
    if empty_bonus_list:
        urls["gameapi_getbonuslist"] = f"https://{LOOPBACK}:8765{BONUS_LIST_PATH}"
    if daily_scores:
        urls["gameapi_getscorelist"] = f"https://{LOOPBACK}:8765{DAILY_SCORE_PATH}"
    if empty_own_score or score_registration:
        urls["gameapi_getscorelist"] = f"https://{LOOPBACK}:8765{SCORE_BOARD_PREFIX}"
        urls["gameapi_getmyscore"] = f"https://{LOOPBACK}:8765{OWN_SCORE_PATH}"
        urls["gameapi_gettopplayerlist"] = f"https://{LOOPBACK}:8765{TOP_PLAYER_PATH}"
        urls["gameapi_getscoredistribution"] = f"https://{LOOPBACK}:8765{SCORE_DISTRIBUTION_PATH}"
        urls["gameapi_getuserstatus"] = f"https://{LOOPBACK}:8765{USER_STATUS_PATH}"
        urls["gameapi_assignmentcourseworld"] = f"https://{LOOPBACK}:8765{COURSE_ASSIGNMENT_PREFIX}"
        urls["gameapi_assignmentcharactordownload"] = f"https://{LOOPBACK}:8765{CHARACTER_ASSIGNMENT_PATH}"
        urls["gameapi_getcountcharactordownload"] = f"https://{LOOPBACK}:8765{CHARACTER_COUNT_PREFIX}"
    if score_registration:
        for operation, prefix in zip(REGISTRATION_OPERATIONS, REGISTRATION_PREFIXES):
            urls[operation] = f"https://{LOOPBACK}:8765{prefix}"
    if empty_boards or event_schedule:
        urls["gameapi_getboardlist"] = f"https://{LOOPBACK}:8765{BOARD_LIST_PATH}"
    if empty_boards:
        urls["gameapi_getfinishboardlist"] = f"https://{LOOPBACK}:8765{FINISH_BOARD_PATH}"
        urls["gameapi_getsignboardlist"] = f"https://{LOOPBACK}:8765{SIGN_BOARD_PATH}"
        urls["gameapi_getboardlistcharactordownload"] = f"https://{LOOPBACK}:8765{CHARACTER_BOARD_PATH}"
    if event_schedule:
        urls["gameapi_getrivallist"] = f"https://{LOOPBACK}:8765{RIVAL_LIST_PATH}"
    if empty_national_boards or national_tournament:
        urls["gameapi_getboardlistnational"] = f"https://{LOOPBACK}:8765{NATIONAL_BOARD_PATH}"
    if national_tournament:
        urls["gameapi_getnationalgamedata"] = f"https://{LOOPBACK}:8765{NATIONAL_GAME_DATA_PATH}"
        urls["gameapi_getmyscorenational"] = f"https://{LOOPBACK}:8765{NATIONAL_OWN_SCORE_PATH}"
        urls["gameapi_noticejoinnational"] = f"https://{LOOPBACK}:8765{NATIONAL_JOIN_PATH}"
        urls["gameapi_getscoredistributionnational"] = f"https://{LOOPBACK}:8765{NATIONAL_DISTRIBUTION_PATH}"
        urls["gameapi_getscorelistnational"] = f"https://{LOOPBACK}:8765{NATIONAL_SCORE_LIST_PATH}"
        if score_registration:
            urls["gameapi_registscorenational"] = f"https://{LOOPBACK}:8765{NATIONAL_REGISTRATION_PREFIX}"
    if login_rejection or score_registration:
        urls["gameapi_login"] = f"https://{LOOPBACK}:8765{LOGIN_PREFIX}"
    if cached_property:
        urls["gameapi_getgamepropertyinfo"] = f"https://{LOOPBACK}:8765{PROPERTY_INFO_PATH}"
    messages = "".join(tag(f"lang{language}", "Local discovery fixture")
                       for language in range(1, 21))
    fields = {
        "ss": "0",
        "msg1": messages,
        "client_ver_msg1": messages,
        "gameurl1": "".join(tag(name, url) for name, url in urls.items()),
        "interval1": tag("ssinfo", "3600") + tag("getservertime", "300"),
        "capone_url1": PROBE_ROOT + "capone",
        "game_analytics_system_url1": (
            f"http://{LOOPBACK}:8765{ANALYTICS_PREFIX}" if discard_telemetry else PROBE_ROOT + "analytics"
        ),
        "cds_gamedata_down_url1": f"http://{LOOPBACK}:8765{GAME_DOWNLOAD_BASE}",
        "cds_gamedata_up_url1": PROBE_ROOT + "gamedata-up",
        "cds_property_down_url1": PROBE_ROOT + "property-down",
        "client_ver1": "1270",
        "msg_busy1": messages,
    }
    document = "".join(tag(name, value) for name, value in fields.items()).encode("ascii")
    return document.ljust((len(document) + 8) & ~7, b"\0")


def read_prepared_eboot(eboot: Path) -> bytes:
    elf = eboot.read_bytes()
    if hashlib.sha256(elf).hexdigest() != PREPARED_EBOOT_HASH:
        raise ValueError("Expected the prepared CUSA04687 1.17 eboot.elf")
    return elf


def encrypt_blocks(plain: bytes, seed: bytes, iv: bytes, libcrypto: str) -> bytes:
    if not plain or len(plain) % 8 or len(iv) != 8:
        raise ValueError("Expected complete Blowfish blocks and an 8-byte IV")
    if any(byte >= 0x80 for byte in seed):
        raise ValueError("Unexpected cipher seed")

    crypto = ctypes.CDLL(libcrypto)
    # OpenSSL BF_KEY holds 18 round words and 4 tables of 256 words.
    schedule = (ctypes.c_uint32 * (18 + 4 * 256))()
    crypto.BF_set_key.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p)
    crypto.BF_set_key.restype = None
    crypto.BF_cbc_encrypt.argtypes = (ctypes.c_char_p, ctypes.c_void_p, ctypes.c_long,
                                     ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int)
    crypto.BF_cbc_encrypt.restype = None
    output = ctypes.create_string_buffer(len(plain))
    crypto.BF_set_key(ctypes.byref(schedule), len(seed), seed)
    crypto.BF_cbc_encrypt(plain, output, len(plain), ctypes.byref(schedule),
                          ctypes.create_string_buffer(iv, 8), 1)
    return output.raw


def build_fixture(eboot: Path, libcrypto: str, *, eula: bool = False, empty_notices: bool = False,
                  daily_scores: bool = False, login_rejection: bool = False,
                  empty_boards: bool = False, cached_property: bool = False,
                  discard_telemetry: bool = False, empty_national_boards: bool = False,
                  empty_own_score: bool = False, score_registration: bool = False,
                  event_schedule: bool = False, national_tournament: bool = False,
                  empty_bonus_list: bool = False) -> bytes:
    elf = read_prepared_eboot(eboot)
    # The prepared ELF maps these guest addresses at file offset VA + 0x4000.
    seed = elf[0x1361ED2 + 0x4000:0x1361EDA + 0x4000]
    iv = elf[0xF6D35 + 0x4000:0xF6D3D + 0x4000]
    plain = discovery_document(eula=eula, empty_notices=empty_notices, daily_scores=daily_scores,
                               login_rejection=login_rejection, empty_boards=empty_boards,
                               cached_property=cached_property, discard_telemetry=discard_telemetry,
                               empty_national_boards=empty_national_boards, empty_own_score=empty_own_score,
                               score_registration=score_registration, event_schedule=event_schedule,
                               national_tournament=national_tournament, empty_bonus_list=empty_bonus_list)
    return encrypt_blocks(plain, seed, iv, libcrypto)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eboot", type=Path, help="Prepared CUSA04687 1.17 eboot.elf")
    parser.add_argument("output", type=Path, help="New fixture file")
    parser.add_argument("--libcrypto", help="OpenSSL libcrypto library with Blowfish support")
    parser.add_argument("--eula", action="store_true", help="Use the plaintext EULA loopback route")
    parser.add_argument("--empty-notices", action="store_true",
                        help="Use the plaintext notice-list loopback route")
    parser.add_argument("--empty-bonus-list", action="store_true",
                        help="Use the plaintext bonus-list loopback route")
    parser.add_argument("--daily-scores", action="store_true",
                        help="Use the plaintext daily score-list loopback route")
    parser.add_argument("--empty-own-score", action="store_true",
                        help="Use the plaintext loopback routes for local score queries")
    parser.add_argument("--score-registration", action="store_true",
                        help="Use the local login, score registration and query routes")
    parser.add_argument("--event-schedule", action="store_true",
                        help="Advertise the local event schedule and daily rival-list routes")
    parser.add_argument("--empty-boards", action="store_true",
                        help="Use the plaintext empty board, finish, sign, and character board routes")
    parser.add_argument("--empty-national-boards", action="store_true",
                        help="Use the plaintext national board-list loopback route")
    parser.add_argument("--national-tournament", action="store_true",
                        help="Advertise local national board and game-data replay")
    parser.add_argument("--login-rejection", "--login-completion", action="store_true",
                        help="Use the plaintext title login probe route")
    parser.add_argument("--cached-property", action="store_true",
                        help="Use the plaintext cached-property route")
    parser.add_argument("--discard-telemetry", action="store_true",
                        help="Advertise the telemetry sink with a trailing slash")
    args = parser.parse_args()
    library = args.libcrypto or find_library("crypto")
    if not library:
        parser.error("Specify the OpenSSL library with --libcrypto")
    try:
        fixture = build_fixture(args.eboot, library, eula=args.eula,
                                empty_notices=args.empty_notices, daily_scores=args.daily_scores,
                                login_rejection=args.login_rejection, empty_boards=args.empty_boards,
                                cached_property=args.cached_property, discard_telemetry=args.discard_telemetry,
                                empty_national_boards=args.empty_national_boards,
                                empty_own_score=args.empty_own_score, score_registration=args.score_registration,
                                event_schedule=args.event_schedule, national_tournament=args.national_tournament,
                                empty_bonus_list=args.empty_bonus_list)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as stream:
            stream.write(fixture)
    except (OSError, AttributeError, ValueError) as error:
        parser.error(str(error))
    print(f"Wrote {len(fixture)} bytes to {args.output}")


if __name__ == "__main__":
    main()
