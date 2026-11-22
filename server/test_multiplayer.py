"""Hosting for several players: --bind, per-player scores and the launcher's host.py."""
import contextlib
from concurrent.futures import ThreadPoolExecutor
import http.client
import io
from pathlib import Path
import sqlite3
from struct import pack
import sys
from tempfile import TemporaryDirectory
from threading import Barrier, Event, Thread
import unittest
from unittest.mock import patch

import golf_server
import host
from golf_server import GolfServer, ScoreStore
from test_golf_server import (
    BOARD_PATH, LOCAL_LOBBY_HEADERS, LOCAL_LOBBY_PATH, LOGIN_REQUEST, LOGIN_TARGET, OWN_SCORE_PATH,
    REGISTER_GROUPS, REGISTER_TARGETS, SCORE_BOARD_TARGET, SERVER_TIME_HEADERS, own_score_request,
    registration_request, schedule_request, score_board_request, string_record,
)

ROOT = Path(__file__).resolve().parents[1]
REAL_EBOOT = ROOT / "work/game-1.17-prepared/eboot.elf"
REAL_LIBCRYPTO = ROOT / "tools/msys2/msys64/clang64/bin/libcrypto-4-x64.dll"
GROUP = REGISTER_GROUPS[0]


def stamp(name: bytes) -> bytes:
    return name + b"@2026-11-18T10:00:00+09:00"


def stat(score: int) -> bytes:
    return pack("<2Hq", 0x4500, 3, score)


class BindTests(unittest.TestCase):
    def test_default_binds_loopback_only(self):
        with GolfServer(0) as server:
            self.assertEqual(server.server_address[0], "127.0.0.1")

    def test_bind_argument_reaches_the_listener(self):
        with GolfServer(0, bind="0.0.0.0") as server:
            self.assertEqual(server.server_address[0], "0.0.0.0")

    def test_replay_requires_loopback_before_opening_listener_or_database(self):
        with TemporaryDirectory() as directory:
            db = Path(directory) / "scores.sqlite"
            for bind in ("0.0.0.0", "192.0.2.1", "::1", "example.invalid"):
                with self.subTest(bind=bind), patch.object(GolfServer, "server_bind") as listen:
                    with self.assertRaisesRegex(ValueError, "requires an IPv4 loopback"):
                        GolfServer(0, bind=bind, local_lobbies=True, score_db=db)
                    listen.assert_not_called()
                    self.assertFalse(db.exists())

    def test_command_line_bind_option(self):
        for argv, expected in ((["golf_server.py"], "127.0.0.1"),
                               (["golf_server.py", "--bind", "0.0.0.0"], "0.0.0.0")):
            with self.subTest(argv=argv), patch.object(sys, "argv", argv), \
                    patch.object(golf_server, "GolfServer") as factory, contextlib.redirect_stdout(io.StringIO()):
                factory.return_value.__enter__.return_value.serve_forever.side_effect = KeyboardInterrupt
                golf_server.main()
                self.assertEqual(factory.call_args.kwargs["bind"], expected)


class ScoreStoreTests(unittest.TestCase):
    def test_two_players_rank_and_keep_their_own_rows(self):
        with TemporaryDirectory() as directory:
            store = ScoreStore(Path(directory) / "scores.sqlite")
            store.write((GROUP, b"Golfer", 3, 21))
            store.write((GROUP, b"Putter", 1, 20))
            store.write((GROUP, b"Golfer", 5, 22))  # worse: ignored
            self.assertEqual(store.top(GROUP, 5), [(b"Putter", 1, 20), (b"Golfer", 3, 21)])
            self.assertEqual(store.top(GROUP, 1), [(b"Putter", 1, 20)])
            self.assertEqual(store.read(GROUP, b"Golfer"), (b"Golfer", 3, 21))
            self.assertIsNone(store.read(GROUP, b"Nobody"))
            self.assertEqual(store.read(GROUP), (b"Putter", 1, 20))
            self.assertEqual(store.read_ranked(GROUP), ((b"Putter", 1, 20), 1))
            self.assertEqual(store.read_ranked(GROUP, b"Golfer"), ((b"Golfer", 3, 21), 2))
            self.assertIsNone(store.read_ranked(GROUP, b"Nobody"))
            store.write((GROUP, b"Golfer", 0, 19))
            self.assertEqual(store.top(GROUP, 5)[0], (b"Golfer", 0, 19))

    def test_long_drive_ranks_the_longest_first(self):
        drive = REGISTER_GROUPS[2]
        with TemporaryDirectory() as directory:
            store = ScoreStore(Path(directory) / "scores.sqlite")
            store.write((drive, b"Golfer", 200, None))
            store.write((drive, b"Putter", 250, None))
            self.assertEqual([row[0] for row in store.top(drive, 5)], [b"Putter", b"Golfer"])
            self.assertEqual(store.read_ranked(drive, b"Golfer"), ((b"Golfer", 200, None), 2))

    def test_old_single_row_database_is_migrated(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "scores.sqlite"
            with contextlib.closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE local_scores (event_group BLOB PRIMARY KEY, player BLOB NOT NULL, "
                           "primary_score INTEGER NOT NULL, secondary_score INTEGER)")
                db.execute("INSERT INTO local_scores VALUES (?, ?, ?, ?)", (GROUP, b"Golfer", 4, 20))
            for _ in range(2):  # a second open leaves the new table alone
                store = ScoreStore(path)
                self.assertEqual(store.read(GROUP, b"Golfer"), (b"Golfer", 4, 20))
            store.write((GROUP, b"Putter", 2, 19))
            self.assertEqual([row[0] for row in store.top(GROUP, 5)], [b"Putter", b"Golfer"])
            with contextlib.closing(sqlite3.connect(path)) as db:
                keys = [name for _, name, _, _, _, key in db.execute("PRAGMA table_info(local_scores)") if key]
            self.assertEqual(sorted(keys), ["event_group", "player"])


class TwoPlayerServerTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.server = GolfServer(0, score_db=Path(directory.name) / "scores.sqlite")
        worker = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 3)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def client(self, source: str):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3,
                                            source_address=(source, 0))
        self.addCleanup(client.close)
        return client

    def post(self, client, path, body):
        client.request("POST", path, body=body, headers=SERVER_TIME_HEADERS)
        response = client.getresponse()
        data = response.read()
        self.assertEqual(response.status, 200)
        return data

    def test_login_and_registration_bind_a_client_to_its_name(self):
        first, second = self.client("127.0.0.1"), self.client("127.0.0.2")
        self.post(first, LOGIN_TARGET, LOGIN_REQUEST.replace(b"Golfer", b"Putter"))
        self.assertEqual(self.server.players, {"127.0.0.1": b"Putter"})
        self.post(second, REGISTER_TARGETS[0], registration_request(0, 3, name_stamp=stamp(b"Golfer")))
        self.assertEqual(self.server.players["127.0.0.2"], b"Golfer")

    def test_own_score_and_list_replies_with_two_players(self):
        first, second = self.client("127.0.0.1"), self.client("127.0.0.2")
        self.post(first, REGISTER_TARGETS[0], registration_request(0, 3, name_stamp=stamp(b"Golfer")))
        self.post(second, REGISTER_TARGETS[0], registration_request(0, 1, name_stamp=stamp(b"Putter")))
        self.post(first, REGISTER_TARGETS[0], registration_request(0, 6, name_stamp=stamp(b"Golfer")))
        rank_two = pack("<2HI", 0x4270, 2, 2)
        rank_one = pack("<2HI", 0x4270, 2, 1)

        own_first = self.post(first, OWN_SCORE_PATH, own_score_request(0, GROUP))
        own_second = self.post(second, OWN_SCORE_PATH, own_score_request(0, GROUP))
        self.assertIn(rank_two + stat(3), own_first)
        self.assertIn(rank_one + stat(1), own_second)

        rows = self.post(first, SCORE_BOARD_TARGET, score_board_request(0, GROUP, 5))
        self.assertEqual(rows, self.post(second, SCORE_BOARD_TARGET, score_board_request(0, GROUP, 5)))
        self.assertIn(pack("<2HI", 0x4200, 2, 2), rows)
        names = [rows.index(string_record(0x0020, name)) for name in (b"Putter", b"Golfer")]
        self.assertEqual(names, sorted(names))
        self.assertIn(rank_one + stat(1), rows)
        self.assertIn(rank_two + stat(3), rows)
        self.assertEqual(rows.count(pack("<2H", 0x4260, 1)), 2)

        one = self.post(first, SCORE_BOARD_TARGET, score_board_request(0, GROUP, 1))
        self.assertIn(pack("<2HI", 0x4200, 2, 1), one)
        self.assertIn(string_record(0x0020, b"Putter"), one)
        self.assertNotIn(string_record(0x0020, b"Golfer"), one)

    def test_leaderboard_reads_tied_ranks_with_one_database_connection(self):
        client = self.client("127.0.0.1")
        for name, score in ((b"Zulu", 1), (b"Alpha", 1), (b"Charlie", 3), (b"Delta", 4)):
            self.post(client, REGISTER_TARGETS[0], registration_request(0, score, name_stamp=stamp(name)))

        with patch.object(sqlite3, "connect", wraps=sqlite3.connect) as connect:
            board = self.post(client, SCORE_BOARD_TARGET, score_board_request(0, GROUP, 3))
        self.assertEqual(connect.call_count, 1)
        tied = pack("<2HI", 0x4270, 2, 1) + stat(1)
        third = pack("<2HI", 0x4270, 2, 3) + stat(3)
        alpha, zulu, charlie = (board.index(name) for name in (b"Alpha", b"Zulu", b"Charlie"))
        self.assertLess(board.index(tied), alpha)
        self.assertLess(board.index(tied, alpha), zulu)
        self.assertLess(zulu, board.index(third))
        self.assertLess(board.index(third), charlie)
        self.assertNotIn(b"Delta", board)

    def test_own_score_and_rank_use_one_snapshot_during_a_score_update(self):
        client = self.client("127.0.0.1")
        self.post(client, REGISTER_TARGETS[0], registration_request(0, 3, name_stamp=stamp(b"Golfer")))
        self.server.scores.write((GROUP, b"Putter", 1, None))
        connect = sqlite3.connect
        opens = 0

        def update_between_reads(*args, **kwargs):
            nonlocal opens
            opens += 1
            if opens == 2:
                with contextlib.closing(connect(self.server.scores.path)) as writer, writer:
                    writer.execute("UPDATE local_scores SET primary_score = 0 WHERE event_group = ? AND player = ?",
                                   (GROUP, b"Golfer"))
            return connect(*args, **kwargs)

        query = own_score_request(0, GROUP)
        with patch.object(sqlite3, "connect", side_effect=update_between_reads):
            own = self.post(client, OWN_SCORE_PATH, query)
        self.assertIn(pack("<2HI", 0x4270, 2, 2) + stat(3), own)
        self.assertEqual(opens, 1)

    def test_two_clients_on_same_loopback_address_keep_their_own_scores(self):
        first, second = self.client("127.0.0.1"), self.client("127.0.0.1")

        def request_as(client, name, path, body=None, expected=200):
            headers = dict(SERVER_TIME_HEADERS, **{"X-Golf-Online-Id": name})
            client.request("POST" if body is not None else "GET", path, body=body, headers=headers)
            response = client.getresponse()
            data = response.read()
            self.assertEqual(response.status, expected)
            return data

        for client, name, score in ((first, "Golfer", 3), (second, "Putter", 1)):
            request_as(client, name, LOGIN_TARGET, LOGIN_REQUEST.replace(b"Golfer", name.encode()))
            request_as(client, name, REGISTER_TARGETS[0],
                    registration_request(0, score, name_stamp=stamp(name.encode())))

        query = own_score_request(0, GROUP)
        self.assertIn(stat(3), request_as(first, "Golfer", OWN_SCORE_PATH, query))
        self.assertIn(stat(1), request_as(second, "Putter", OWN_SCORE_PATH, query))
        self.assertNotIn(pack("<2H", 0x4500, 3), request_as(second, "Newbie", OWN_SCORE_PATH, query))
        request_as(first, "Golfer", REGISTER_TARGETS[0], registration_request(
            0, -1, name_stamp=stamp(b"Putter")), expected=400)
        request_as(first, "Putter", LOGIN_TARGET, LOGIN_REQUEST, expected=400)
        request_as(first, "bad id", OWN_SCORE_PATH, query, expected=400)

        self.server.national_archive = b"fixture"
        self.server.national_score_group = GROUP
        url = golf_server.NATIONAL_DISTRIBUTION_DOWNLOAD_PATH
        self.assertEqual(request_as(first, "Golfer", url), golf_server.distribution_data(3))
        self.assertEqual(request_as(second, "Putter", url), golf_server.distribution_data(1))

    def test_player_without_a_score_gets_no_own_row(self):
        first, second = self.client("127.0.0.1"), self.client("127.0.0.2")
        self.post(first, REGISTER_TARGETS[0], registration_request(0, 3, name_stamp=stamp(b"Golfer")))
        self.post(second, LOGIN_TARGET, LOGIN_REQUEST.replace(b"Golfer", b"Newbie"))
        own = self.post(second, OWN_SCORE_PATH, own_score_request(0, GROUP))
        self.assertNotIn(pack("<2H", 0x4500, 3), own)


class HostTests(unittest.TestCase):
    def fake_eboot(self, directory: str, content: bytes = b"eboot one") -> Path:
        path = Path(directory) / "eboot.elf"
        path.write_bytes(content)
        return path

    def test_fixtures_are_built_once_per_eboot_and_version(self):
        with TemporaryDirectory() as directory, \
                patch.object(host, "build_fixture", return_value=b"F" * 16) as fixture, \
                patch.object(host, "build_score_block", return_value=b"B" * 8) as block:
            eboot, state = self.fake_eboot(directory), Path(directory) / "state"
            first = host.ensure_fixtures(eboot, "crypto", state)
            self.assertEqual(sorted(p.name for p in first.iterdir()),
                             sorted((*host.FIXTURE_FILES, "fixtures.json")))
            self.assertEqual(host.ensure_fixtures(eboot, "crypto", state), first)
            self.assertEqual((fixture.call_count, block.call_count), (1, 1))
            self.assertEqual(fixture.call_args.kwargs, host.DISCOVERY_OPTIONS)

            other = self.fake_eboot(directory, b"eboot two")
            self.assertNotEqual(host.ensure_fixtures(other, "crypto", state), first)
            self.assertEqual(fixture.call_count, 2)

            self.fake_eboot(directory)
            with patch.object(host, "FIXTURE_VERSION", host.FIXTURE_VERSION + 1):
                host.ensure_fixtures(eboot, "crypto", state)
            self.assertEqual(fixture.call_count, 3)

    def test_concurrent_hosts_share_fixture_generation_and_score_schema(self):
        starting = Barrier(2)
        fixture_started = Event()
        release_fixture = Event()
        fixtures_ready = Barrier(2)

        def build_fixture(*args, **kwargs):
            fixture_started.set()
            self.assertTrue(release_fixture.wait(5))
            return b"F" * 16

        with TemporaryDirectory() as directory, \
                patch.object(host, "build_fixture", side_effect=build_fixture) as build, \
                patch.object(host, "build_score_block", return_value=b"B" * 8):
            eboot, state = self.fake_eboot(directory), Path(directory) / "state"

            def launch():
                starting.wait(5)
                fixtures = host.ensure_fixtures(eboot, "crypto", state)
                fixtures_ready.wait(5)
                with host.make_server(fixtures, state, 0):
                    return fixtures

            with ThreadPoolExecutor(max_workers=2) as workers:
                launches = [workers.submit(launch) for _ in range(2)]
                try:
                    self.assertTrue(fixture_started.wait(5))
                    self.assertFalse(fixtures_ready.broken)
                finally:
                    release_fixture.set()
                first, second = [launch.result(10) for launch in launches]
            self.assertEqual(first, second)
            self.assertEqual((first / "ss-info.bin").read_bytes(), b"F" * 16)
            self.assertEqual(build.call_count, 1)
            self.assertTrue((state / "scores.db").is_file())

    def test_damaged_cache_is_rebuilt(self):
        with TemporaryDirectory() as directory, \
                patch.object(host, "build_fixture", return_value=b"F" * 16) as fixture, \
                patch.object(host, "build_score_block", return_value=b"B" * 8):
            eboot, state = self.fake_eboot(directory), Path(directory) / "state"
            folder = host.ensure_fixtures(eboot, "crypto", state)
            (folder / "ss-info.bin").unlink()
            host.ensure_fixtures(eboot, "crypto", state)
            self.assertEqual(fixture.call_count, 2)
            self.assertTrue((folder / "ss-info.bin").is_file())

    def test_non_object_fixture_marker_rebuilds_the_cache(self):
        with (
            TemporaryDirectory() as directory,
            patch.object(host, "build_fixture", side_effect=[b"old fixture", b"new fixture"]),
            patch.object(host, "build_score_block", return_value=b"B" * 8),
        ):
            eboot, state = self.fake_eboot(directory), Path(directory) / "state"
            folder = host.ensure_fixtures(eboot, "crypto", state)
            marker = folder / "fixtures.json"
            marker.write_text("null", encoding="utf-8")

            self.assertEqual(host.ensure_fixtures(eboot, "crypto", state), folder)
            self.assertEqual((folder / "ss-info.bin").read_bytes(), b"new fixture")

    def test_main_prints_ready_creates_the_score_database_and_stops_cleanly(self):
        with TemporaryDirectory() as directory, \
                patch.object(host, "build_fixture", return_value=b"F" * 16), \
                patch.object(host, "build_score_block", return_value=b"B" * 8), \
                patch.object(GolfServer, "serve_forever", side_effect=KeyboardInterrupt), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            eboot, state = self.fake_eboot(directory), Path(directory) / "state"
            status = host.main(["--eboot", str(eboot), "--libcrypto", "crypto", "--state", str(state),
                                "--port", "0", "--bind", "127.0.0.1"])
            self.assertEqual(status, 0)
            self.assertRegex(out.getvalue(), r"^ready 127\.0\.0\.1:[0-9]+\n$")
            self.assertTrue((state / "scores.db").is_file())

    def test_main_reports_a_missing_eboot(self):
        with TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()):
            status = host.main(["--eboot", str(Path(directory) / "none.elf"), "--libcrypto", "crypto",
                                "--state", directory, "--port", "0"])
            self.assertEqual(status, 1)

    def test_main_reports_a_damaged_score_database_and_preserves_it(self):
        with TemporaryDirectory() as directory, \
                patch.object(host, "build_fixture", return_value=b"F" * 16), \
                patch.object(host, "build_score_block", return_value=b"B" * 8), \
                contextlib.redirect_stdout(io.StringIO()) as out, \
                contextlib.redirect_stderr(io.StringIO()) as err:
            eboot, state = self.fake_eboot(directory), Path(directory) / "state"
            state.mkdir()
            database = state / "scores.db"
            damaged = b"damaged score file"
            database.write_bytes(damaged)
            status = host.main(["--eboot", str(eboot), "--libcrypto", "crypto",
                                "--state", str(state), "--port", "0"])
            self.assertEqual(status, 1)
            self.assertIn("scores.db", err.getvalue())
            self.assertIn("file is not a database", err.getvalue())
            self.assertEqual(out.getvalue(), "")
            self.assertEqual(database.read_bytes(), damaged)

    def test_multiplayer_host_requires_loopback(self):
        with TemporaryDirectory() as directory:
            state = Path(directory)
            with self.assertRaisesRegex(ValueError, "requires an IPv4 loopback"):
                host.make_server(state, state, 0, "0.0.0.0", local_lobbies=True)

    @unittest.skipUnless(REAL_EBOOT.is_file() and REAL_LIBCRYPTO.is_file(), "prepared eboot or libcrypto missing")
    def test_real_fixtures_serve_discovery_lobbies_and_daily_scores(self):
        with TemporaryDirectory() as directory:
            state = Path(directory)
            folder = host.ensure_fixtures(REAL_EBOOT, str(REAL_LIBCRYPTO), state)
            built = (folder / "ss-info.bin").stat().st_mtime_ns
            self.assertEqual(host.ensure_fixtures(REAL_EBOOT, str(REAL_LIBCRYPTO), state), folder)
            self.assertEqual((folder / "ss-info.bin").stat().st_mtime_ns, built)
            with host.make_server(folder, state, 0, local_lobbies=True) as server:
                worker = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
                worker.start()
                try:
                    client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                    client.request("GET", golf_server.DISCOVERY_PATH)
                    response = client.getresponse()
                    self.assertEqual((response.status, response.read()),
                                     (200, (folder / "ss-info.bin").read_bytes()))
                    join = pack("<BBH16s16s", 1, 7, 0, bytes(16), b"Golfer")
                    client.request("POST", LOCAL_LOBBY_PATH, body=join, headers=LOCAL_LOBBY_HEADERS)
                    response = client.getresponse()
                    body = response.read()
                    self.assertEqual((response.status, len(body)), (200, 38))
                    self.assertIn(b"Golfer" + bytes(10), body)

                    daily = b"Daily_20180914_1_OUT"
                    client.request("POST", BOARD_PATH, body=schedule_request(1, course=1, limit=6),
                                   headers=SERVER_TIME_HEADERS)
                    response = client.getresponse()
                    board = response.read()
                    self.assertEqual(response.status, 200)
                    self.assertIn(string_record(0x4140, daily), board)
                    client.request("POST", REGISTER_TARGETS[1],
                                   body=registration_request(1, -9, group=daily),
                                   headers=SERVER_TIME_HEADERS)
                    response = client.getresponse()
                    response.read()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(server.scores.read(daily, b"Golfer"), (b"Golfer", -9, 21))
                    client.close()
                finally:
                    server.shutdown()
                    worker.join(3)


if __name__ == "__main__":
    unittest.main()
