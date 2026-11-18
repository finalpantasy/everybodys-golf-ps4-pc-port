"""Build an Everybody's Golf 1.17 discovery fixture for IPv4 loopback."""
import argparse
import csv
import ctypes
from ctypes.util import find_library
import hashlib
from pathlib import Path

from golf_server import EULA_PATH, LOOPBACK, NOTICE_PATH, SERVER_TIME_PATH

PREPARED_EBOOT_HASH = "293156adf6462feedb574dd9cd5db45707469a6c407b1d89a2241a4bacde5dc2"
URL_MAP = Path(__file__).resolve().parents[1] / "analysis/online/title-url-map.tsv"
PROBE_ROOT = f"http://{LOOPBACK}:8765/nmg-us/replay-probe/"


def tag(name: str, value: str) -> str:
    return f"<{name}>{value}</{name}>"


def discovery_document(*, eula: bool = False, empty_notices: bool = False) -> bytes:
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
    messages = "".join(tag(f"lang{language}", "Local discovery fixture")
                       for language in range(1, 21))
    fields = {
        "ss": "0",
        "msg1": messages,
        "client_ver_msg1": messages,
        "gameurl1": "".join(tag(name, url) for name, url in urls.items()),
        "interval1": tag("ssinfo", "3600") + tag("getservertime", "300"),
        "capone_url1": PROBE_ROOT + "capone",
        "game_analytics_system_url1": PROBE_ROOT + "analytics",
        "cds_gamedata_down_url1": PROBE_ROOT + "gamedata-down",
        "cds_gamedata_up_url1": PROBE_ROOT + "gamedata-up",
        "cds_property_down_url1": PROBE_ROOT + "property-down",
        "client_ver1": "1270",
        "msg_busy1": messages,
    }
    document = "".join(tag(name, value) for name, value in fields.items()).encode("ascii")
    return document.ljust((len(document) + 8) & ~7, b"\0")


def build_fixture(eboot: Path, libcrypto: str, *,
                  eula: bool = False, empty_notices: bool = False) -> bytes:
    elf = eboot.read_bytes()
    if hashlib.sha256(elf).hexdigest() != PREPARED_EBOOT_HASH:
        raise ValueError("Expected the prepared CUSA04687 1.17 eboot.elf")
    # The prepared ELF maps these guest addresses at file offset VA + 0x4000.
    seed = elf[0x1361ED2 + 0x4000:0x1361EDA + 0x4000]
    iv = ctypes.create_string_buffer(elf[0xF6D35 + 0x4000:0xF6D3D + 0x4000], 8)
    if any(byte >= 0x80 for byte in seed):
        raise ValueError("Unexpected discovery cipher seed")

    crypto = ctypes.CDLL(libcrypto)
    # OpenSSL BF_KEY holds 18 round words and 4 tables of 256 words.
    schedule = (ctypes.c_uint32 * (18 + 4 * 256))()
    crypto.BF_set_key.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p)
    crypto.BF_set_key.restype = None
    crypto.BF_cbc_encrypt.argtypes = (ctypes.c_char_p, ctypes.c_void_p, ctypes.c_long,
                                     ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int)
    crypto.BF_cbc_encrypt.restype = None
    plain = discovery_document(eula=eula, empty_notices=empty_notices)
    output = ctypes.create_string_buffer(len(plain))
    crypto.BF_set_key(ctypes.byref(schedule), len(seed), seed)
    crypto.BF_cbc_encrypt(plain, output, len(plain), ctypes.byref(schedule), iv, 1)
    return output.raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eboot", type=Path, help="Prepared CUSA04687 1.17 eboot.elf")
    parser.add_argument("output", type=Path, help="New fixture file")
    parser.add_argument("--libcrypto", help="OpenSSL libcrypto library with Blowfish support")
    parser.add_argument("--eula", action="store_true", help="Use the plaintext EULA loopback route")
    parser.add_argument("--empty-notices", action="store_true",
                        help="Use the plaintext notice-list loopback route")
    args = parser.parse_args()
    library = args.libcrypto or find_library("crypto")
    if not library:
        parser.error("Specify the OpenSSL library with --libcrypto")
    try:
        fixture = build_fixture(args.eboot, library, eula=args.eula,
                                empty_notices=args.empty_notices)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as stream:
            stream.write(fixture)
    except (OSError, AttributeError, ValueError) as error:
        parser.error(str(error))
    print(f"Wrote {len(fixture)} bytes to {args.output}")


if __name__ == "__main__":
    main()
