"""Build the synthetic US tournament data archive served on loopback."""

from struct import pack
import zlib


PARAMETER_PATH = "data/sponsor/param/International_Tournament_"
SETTINGS_PATH = PARAMETER_PATH + "settings.txt"
MESSAGES_PATH = PARAMETER_PATH + "messages.txt"


def name_hash(path: str) -> int:
    result = 0
    for byte in path.lower().encode("ascii"):
        result = (31 * result + byte) & 0xFFFFFFFF
    return result


def tabular_row(columns: dict[str, int | str]) -> bytes:
    header = "\t".join(columns)
    row = "\t".join(map(str, columns.values()))
    return f"{header}\r\n{row}\r\n".encode("utf-8-sig")


def tournament_archive(tournament_id: int) -> bytes:
    settings = {"resetThreshold": 0, "tournamentId": tournament_id, "sponsored_US": 0}
    for stage in (1, 2):
        settings.update({f"p{stage}_course": 0, f"p{stage}_hole": 1})
    sources = {
        SETTINGS_PATH: tabular_row(settings),
        MESSAGES_PATH: tabular_row({"tournamentName_US_01_ENG": "Local Tournament"}),
    }
    records = []
    streams = []
    for index, (path, plain) in enumerate(sorted(sources.items(), key=lambda item: name_hash(item[0]))):
        compressed = zlib.compress(plain, 9)
        records.append(pack("<5I", name_hash(path), 0, index, len(compressed), len(plain)))
        streams.append(compressed.ljust((len(compressed) + 3) & ~3, b"\0"))
    return pack("<4sIII", b"FB\0\0", len(records), 4, 0) + b"".join(records + streams)
