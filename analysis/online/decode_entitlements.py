"""Read the entitlement rows from Everybody's Golf 1.17's local XB table."""

import argparse
import csv
from dataclasses import dataclass
import json
from pathlib import Path
import re
import struct
import zlib

XB_HEADER_SIZE = 0x24
MAX_XB_BYTES = 1 << 20
COLUMNS = ["EntitlementLabel", "ProductLabel", "ItemSaveDataID"]


@dataclass(frozen=True)
class Entitlement:
    label: str
    product: str
    save_id: int


def decode(path: Path) -> list[Entitlement]:
    with path.open("rb") as stream:
        source = stream.read(MAX_XB_BYTES + 1)
    if not XB_HEADER_SIZE <= len(source) <= MAX_XB_BYTES or source[:4] != b"FB\0\0":
        raise ValueError("invalid entitlement XB header or file size")
    compressed, expanded = struct.unpack_from("<II", source, 0x1C)
    if not 0 < compressed <= len(source) - XB_HEADER_SIZE or not 0 < expanded <= MAX_XB_BYTES:
        raise ValueError("invalid entitlement XB stream size")
    inflater = zlib.decompressobj()
    decoded = inflater.decompress(source[XB_HEADER_SIZE:XB_HEADER_SIZE + compressed], expanded + 1)
    if not inflater.eof or inflater.unused_data or len(decoded) != expanded:
        raise ValueError("entitlement XB size does not match its header")
    rows = csv.reader(decoded.decode("ascii").splitlines(), delimiter="\t")
    if next(rows, None) != COLUMNS:
        raise ValueError("unexpected entitlement table columns")

    records = []
    for row in rows:
        if len(row) != 3:
            raise ValueError("entitlement row must have three fields")
        label, product, save_id = row
        if not re.fullmatch(r"EN[0-9]{1,14}", label) or not re.fullmatch(r"EN[0-9]{14}", product):
            raise ValueError("invalid entitlement or product label")
        if not re.fullmatch(r"[0-9]{1,9}", save_id):
            raise ValueError("invalid entitlement save-data ID")
        records.append(Entitlement(label, product, int(save_id)))
    if len({row.label for row in records}) != len(records) or len({row.product for row in records}) != len(records):
        raise ValueError("duplicate entitlement or product label")
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xb", type=Path)
    parser.add_argument("--inventory", type=Path, help="Compare product labels with the local DLC package inventory")
    options = parser.parse_args()
    try:
        rows = decode(options.xb)
        products = None
        if options.inventory:
            inventory = json.loads(options.inventory.read_text(encoding="utf-8"))
            products = {row["content_id"].rsplit("-", 1)[-1] for row in inventory["packages"]}
    except (OSError, ValueError, KeyError, TypeError, zlib.error) as exc:
        parser.error(str(exc))
    print("\t".join([*COLUMNS, "Package present"]) if products is not None else "\t".join(COLUMNS))
    for record in rows:
        line = f"{record.label}\t{record.product}\t{record.save_id}"
        print(f"{line}\t{record.product in products}" if products is not None else line)


if __name__ == "__main__":
    main()
