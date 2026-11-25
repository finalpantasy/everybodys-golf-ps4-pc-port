"""Host the local Golf service for other players: builds the fixtures once, then serves.

    python -I host.py --eboot PATH --libcrypto PATH --state DIR --port N [--bind ADDR] [--local-lobbies]
    python -I host.py --online [--auto] [--port N] [--name NAME] [--no-port-mapping]

--online hosts multiplayer for friends: it listens on every adapter, turns on lobbies, keeps a
room key in <state>/room-key.txt, writes the invite codes to <state>/online.txt, answers LAN
discovery and asks the router to open the port. --auto finds the game, libcrypto and state
folder of an installed release (this file in tools/server), so a PC can host without playing.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import sys
import threading
import time

if os.name == "nt":
    import msvcrt
else:
    import fcntl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime  # noqa: E402

from collab_cups import CUPS, MODES, Cup, configured_cup, mode_cups  # noqa: E402
from golf_server import GolfHandler, GolfServer, LOOPBACK, MAX_EULA_TEXT_BYTES, require_lobby_loopback  # noqa: E402
from make_daily_score_block import build_score_block  # noqa: E402
from make_discovery_fixture import build_fixture  # noqa: E402
from online import OnlineHost, load_room_key  # noqa: E402

# Bump when the fixture set below changes, so older caches are rebuilt.
FIXTURE_VERSION = 2
SERVER_TIME = datetime(2018, 9, 14, 12, 0, 0)
# The discovery options of the verified full online run (fixture ss-info-local-national-v7).
DISCOVERY_OPTIONS = dict(
    eula=True, empty_notices=True, daily_scores=True, empty_boards=True, login_rejection=True,
    empty_national_boards=True, cached_property=True, discard_telemetry=True, empty_own_score=True,
    score_registration=True, event_schedule=True, national_tournament=True, empty_bonus_list=True,
)
EULA_TEXT = b"Local replay test.\n"
# Eagle City Golf Club is course 1; its Open Course round is holes 1 to 9.
EVENT_GROUPS = (
    *(f"OneHole_{SERVER_TIME:%Y%m%d}_1_{hole}" for hole in range(1, 10)),
    f"Daily_{SERVER_TIME:%Y%m%d}_1_OUT",
)
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
    state.mkdir(parents=True, exist_ok=True)
    lock_path = state / f"{final.name}.lock"
    with lock_path.open("a+b") as lock:
        # The OS releases the lock when the launcher closes or crashes.
        if os.name == "nt":
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        marker = final / "fixtures.json"
        if marker.is_file():
            try:
                info = json.loads(marker.read_text(encoding="utf-8"))
                if (isinstance(info, dict) and info.get("eboot_sha256") == key
                        and info.get("version") == FIXTURE_VERSION
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


def make_server(fixtures: Path, state: Path, port: int, bind: str = LOOPBACK, *,
                local_lobbies: bool = False, room_key: str | None = None, strict_key: bool = False,
                collab_cups: tuple[Cup, ...] = ()) -> GolfServer:
    if local_lobbies and room_key is None:
        require_lobby_loopback(bind)
    score_block = (fixtures / "score-block.bin").read_bytes()
    return GolfServer(
        port, (fixtures / "ss-info.bin").read_bytes(), server_time=SERVER_TIME,
        eula_text=(fixtures / "eula.txt").read_bytes()[:MAX_EULA_TEXT_BYTES + 1], empty_notices=True,
        daily_score_block=score_block, empty_board_block=score_block, login_completion=True,
        empty_national_boards=True, cached_property=True, discard_telemetry=True, empty_bonus_list=True,
        score_db=state / "scores.db", event_group=EVENT_GROUPS, national_tournament=True,
        local_lobbies=local_lobbies, bind=bind, handler=LoggingHandler, room_key=room_key,
        strict_key=strict_key, collab_cups=collab_cups)


def stop(*_):
    raise KeyboardInterrupt


def installed_paths(args):
    """--auto: the paths of an installed release, where this file is tools/server/host.py."""
    here = Path(__file__).resolve().parent
    root = here.parent.parent
    games = sorted((root / "data" / "game").glob("*/eboot.elf"), key=lambda p: p.stat().st_mtime, reverse=True)
    if args.eboot is None:
        if not games:
            raise ValueError("No prepared game: open the launcher once, set up the game files and press Play")
        args.eboot = games[0]
    if args.libcrypto is None:
        args.libcrypto = str(here / "libcrypto-4-x64.dll")
    if args.state is None:
        args.state = root / "data" / "server"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--eboot", type=Path, help="Prepared CUSA04687 1.17 eboot.elf")
    parser.add_argument("--libcrypto", help="OpenSSL libcrypto library with Blowfish support")
    parser.add_argument("--state", type=Path, help="Folder for fixtures and the score database")
    parser.add_argument("--port", type=int, help="TCP port (48765 with --online)")
    parser.add_argument("--bind", metavar="ADDRESS",
                        help="Address to listen on (default loopback, or every adapter with --online)")
    parser.add_argument("--local-lobbies", action="store_true", help="Enable multiplayer replay on loopback")
    parser.add_argument("--online", action="store_true", help="Host multiplayer for friends (see above)")
    parser.add_argument("--auto", action="store_true", help="Use the installed release's game and folders")
    parser.add_argument("--name", default="Golf server", help="Name other players see in LAN discovery")
    parser.add_argument("--no-port-mapping", action="store_true", help="Do not ask the router to open the port")
    parser.add_argument("--strict-key", action="store_true",
                        help="Ask every other PC for the room key, home network and VPN ones too")
    parser.add_argument("--stop-file", type=Path,
                        help="Stop cleanly (and close the router port) when this file appears")
    parser.add_argument("--no-web-lookup", action="store_true",
                        help="Do not ask a web service for the public address when the router does not say")
    parser.add_argument("--collab-cup", choices=sorted(CUPS),
                        help="Run this collab cup as the International Tournament (qualifier, final, prizes)")
    parser.add_argument("--collab-cups", choices=MODES,
                        help="Run every collab cup in turn (settings.ini collab_items=classic or hardcore)")
    parser.add_argument("--cup-cut", type=int, metavar="STROKES",
                        help="Qualifier pass line against par (default +3; Hardcore: -3)")
    parser.add_argument("--cup-holes", type=int, metavar="N", help="Test cup rounds of N holes (3 or more)")
    parser.add_argument("--cup-course", type=int, metavar="N", help="Play the cups on course N (1 Eagle City ...)")
    args = parser.parse_args(argv)
    try:
        if args.auto:
            installed_paths(args)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr, flush=True)
        return 1
    missing = [name for name in ("eboot", "libcrypto", "state") if getattr(args, name) is None]
    if missing:
        parser.error("missing " + ", ".join("--" + name for name in missing) + " (or use --auto)")
    if args.port is None:
        if not args.online:
            parser.error("--port is required")
        args.port = 48765
    bind = args.bind or ("0.0.0.0" if args.online else LOOPBACK)
    for name in ("SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop)
    host = None
    try:
        args.state.mkdir(parents=True, exist_ok=True)
        fixtures = ensure_fixtures(args.eboot, args.libcrypto, args.state)
        room_key = load_room_key(args.state) if args.online else None
        hardcore = args.collab_cups == "hardcore"
        options = {"cut": args.cup_cut, "holes": args.cup_holes, "course": args.cup_course}
        cups = ((configured_cup(args.collab_cup, hardcore=hardcore, **options),) if args.collab_cup
                else mode_cups(args.collab_cups, **options) if args.collab_cups else ())
        server = make_server(fixtures, args.state, args.port, bind,
                             local_lobbies=args.local_lobbies or args.online, room_key=room_key,
                             strict_key=args.strict_key,
                             collab_cups=cups)
        if args.online:
            name = "".join(c for c in args.name if c.isascii() and c.isprintable())[:32] or "Golf server"
            host = OnlineHost(args.state, server.server_port, room_key, name,
                              open_port=not args.no_port_mapping, web_lookup=not args.no_web_lookup)
    except sqlite3.Error as error:
        print(f"error: {args.state / 'scores.db'}: {error}", file=sys.stderr, flush=True)
        return 1
    except (OSError, AttributeError, ValueError, OverflowError) as error:
        print(f"error: {error}", file=sys.stderr, flush=True)
        return 1
    try:
        with server:
            print(f"ready {bind}:{server.server_port}", flush=True)
            if host is not None:
                host.start()
            if args.stop_file is not None:
                args.stop_file.unlink(missing_ok=True)

                def watch():
                    while not args.stop_file.exists():
                        time.sleep(0.25)
                    server.shutdown()
                threading.Thread(target=watch, name="stop-file", daemon=True).start()
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if host is not None:
            host.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
