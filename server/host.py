"""Host the local Golf service for other players: builds the fixtures once, then serves.

    python -I host.py --eboot PATH --libcrypto PATH --state DIR --port N [--bind ADDR]
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime  # noqa: E402

from golf_server import GolfHandler, GolfServer, LOOPBACK, MAX_EULA_TEXT_BYTES  # noqa: E402
from make_daily_score_block import build_score_block  # noqa: E402
from make_discovery_fixture import build_fixture  # noqa: E402

# Bump when the fixture set below changes, so older caches are rebuilt.
FIXTURE_VERSION = 1
SERVER_TIME = datetime(2018, 9, 14, 12, 0, 0)
# The discovery options of the verified full online run (fixture ss-info-local-national-v7).
DISCOVERY_OPTIONS = dict(
    eula=True, empty_notices=True, daily_scores=True, empty_boards=True, login_rejection=True,
    empty_national_boards=True, cached_property=True, discard_telemetry=True, empty_own_score=True,
    score_registration=True, event_schedule=True, national_tournament=True,
)
EULA_TEXT = b"Local replay test.\n"
# Eagle City Golf Club is course 1; its Open Course round is holes 1 to 9.
EVENT_GROUPS = tuple(f"OneHole_{SERVER_TIME:%Y%m%d}_1_{hole}" for hole in range(1, 10))
FIXTURE_FILES = ("ss-info.bin", "score-block.bin", "eula.txt")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_fixtures(eboot: Path, libcrypto: str, state: Path) -> Path:
    """Return the fixture folder for this eboot, building it on the first call only."""
    key = file_sha256(eboot)
    final = state / f"fixtures-{key[:16]}-v{FIXTURE_VERSION}"
    marker = final / "fixtures.json"
    if marker.is_file():
        try:
            info = json.loads(marker.read_text(encoding="utf-8"))
            if (info.get("eboot_sha256") == key and info.get("version") == FIXTURE_VERSION
                    and all((final / name).is_file() for name in FIXTURE_FILES)):
                return final
        except (OSError, ValueError):
            pass
    building = state / f"{final.name}.building"
    shutil.rmtree(building, ignore_errors=True)
    shutil.rmtree(final, ignore_errors=True)
    building.mkdir(parents=True)
    (building / "ss-info.bin").write_bytes(build_fixture(eboot, libcrypto, **DISCOVERY_OPTIONS))
    (building / "score-block.bin").write_bytes(build_score_block(eboot, libcrypto))
    (building / "eula.txt").write_bytes(EULA_TEXT)
    (building / "fixtures.json").write_text(
        json.dumps({"eboot_sha256": key, "version": FIXTURE_VERSION}), encoding="utf-8")
    building.rename(final)
    return final


class LoggingHandler(GolfHandler):
    def log_request(self, code="-", size="-"):
        # The query string carries session ids, so only the path is logged.
        print(f"{self.client_address[0]} {self.command} {self.path.split('?')[0]} {code}", flush=True)


def make_server(fixtures: Path, state: Path, port: int, bind: str = LOOPBACK) -> GolfServer:
    score_block = (fixtures / "score-block.bin").read_bytes()
    return GolfServer(
        port, (fixtures / "ss-info.bin").read_bytes(), server_time=SERVER_TIME,
        eula_text=(fixtures / "eula.txt").read_bytes()[:MAX_EULA_TEXT_BYTES + 1], empty_notices=True,
        daily_score_block=score_block, empty_board_block=score_block, login_completion=True,
        empty_national_boards=True, cached_property=True, discard_telemetry=True,
        score_db=state / "scores.db", event_group=EVENT_GROUPS, national_tournament=True,
        bind=bind, handler=LoggingHandler)


def stop(*_):
    raise KeyboardInterrupt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eboot", type=Path, required=True, help="Prepared CUSA04687 1.17 eboot.elf")
    parser.add_argument("--libcrypto", required=True, help="OpenSSL libcrypto library with Blowfish support")
    parser.add_argument("--state", type=Path, required=True, help="Folder for fixtures and the score database")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--bind", default=LOOPBACK, metavar="ADDRESS",
                        help="Address to listen on (default loopback; 0.0.0.0 hosts for other machines)")
    args = parser.parse_args(argv)
    for name in ("SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop)
    try:
        args.state.mkdir(parents=True, exist_ok=True)
        fixtures = ensure_fixtures(args.eboot, args.libcrypto, args.state)
        server = make_server(fixtures, args.state, args.port, args.bind)
    except (OSError, AttributeError, ValueError, OverflowError) as error:
        print(f"error: {error}", file=sys.stderr, flush=True)
        return 1
    try:
        with server:
            print(f"ready {args.bind}:{server.server_port}", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
