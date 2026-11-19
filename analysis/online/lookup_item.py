"""Look up a save-data ID in the local Everybody's Golf 1.17 item index."""

import argparse
import csv
from pathlib import Path
from struct import unpack_from
import sys
import zlib


STREAM_OFFSET = 0x38
MAX_ARCHIVE_BYTES = 1 << 20
MAX_TEXT_BYTES = 8 << 20
ITEM_FIELDS = ("savedataID", "category", "labelFile", "tempName")


def lookup(path: Path, item_id: int) -> list[dict[str, str]]:
    with path.open("rb") as stream:
        archive = stream.read(MAX_ARCHIVE_BYTES + 1)
    if not STREAM_OFFSET <= len(archive) <= MAX_ARCHIVE_BYTES or archive[:4] != b"FB\0\0":
        raise ValueError("invalid item index XB header or file size")
    compressed, expanded = unpack_from("<II", archive, 0x1C)
    if not 0 < compressed <= len(archive) - STREAM_OFFSET or not 0 < expanded <= MAX_TEXT_BYTES:
        raise ValueError("invalid item index stream size")
    inflater = zlib.decompressobj()
    text = inflater.decompress(archive[STREAM_OFFSET:STREAM_OFFSET + compressed], expanded + 1)
    if not inflater.eof or inflater.unused_data or len(text) != expanded:
        raise ValueError("item index stream size does not match its header")
    rows = csv.DictReader(text.decode("utf-8-sig").rstrip("\0").splitlines(), delimiter="\t")
    if not set(ITEM_FIELDS).issubset(rows.fieldnames or ()):
        raise ValueError("unexpected item index columns")
    return [row for row in rows if row["savedataID"] == str(item_id)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="Path to Item_index_list.US_01.xb")
    parser.add_argument("id", help="Save-data ID in decimal or with a 0x hexadecimal prefix")
    args = parser.parse_args()
    try:
        item_id = int(args.id, 16 if args.id.lower().startswith("0x") else 10)
        if not 0 <= item_id <= 0xFFFFFFFF:
            raise ValueError("save-data ID must be an unsigned 32-bit value")
        matches = lookup(args.index, item_id)
    except (OSError, ValueError, zlib.error) as exc:
        parser.error(str(exc))
    if not matches:
        parser.exit(1, f"No item with save-data ID {item_id}\n")
    sys.stdout.reconfigure(encoding="utf-8")
    output = csv.DictWriter(sys.stdout, ITEM_FIELDS, delimiter="\t", extrasaction="ignore", lineterminator="\n")
    output.writeheader()
    output.writerows(matches)


if __name__ == "__main__":
    main()
