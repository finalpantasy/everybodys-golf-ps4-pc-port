from datetime import datetime
import http.client
from pathlib import Path
from struct import pack, unpack_from
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch
import zlib

from collab_cups import (CUPS, FAMITSU, FF30, LEVEL5_1, LEVEL5_2, configured_cup, cup_clock, mode_cups,
                         notice_time, stage_windows)
from golf_server import (LOOPBACK, GolfServer, cup_notice_item, national_tournament_board, notice_reply,
                         recorded_score_reply)
from test_golf_server import (LOGIN_REQUEST, LOGIN_TARGET, DOWNLOAD_BASE, NATIONAL_BOARD_PATH, NATIONAL_BOARD_REQUEST, NATIONAL_OWN_SCORE_PATH,
                              NOTICE_FIELDS, NOTICE_PATH, NOTICE_REQUEST, SERVER_TIME_HEADERS, SERVER_TIME_PATH,
                              SERVER_TIME_REQUEST, string_record)

DAY = datetime(2018, 9, 14, 12)
TERM = bytes.fromhex("10800100")
REGISTRATION = "/nmg-us/replay-probe/gameapi_registscorenational?account=5932163534510096385&n=4&s=1"
JOIN = "/nmg-us/replay-probe/gameapi_noticejoinnational?account=5932163534510096385&n=14&s=1"
NATIONAL_SCORE_LIST_PATH = "/nmg-us/replay-probe/gameapi_getscorelistnational"
BONUS_LIST_PATH = "/nmg-us/replay-probe/gameapi_getbonuslist"
BONUS_LIST_REQUEST = SERVER_TIME_REQUEST.replace(TERM, NOTICE_FIELDS[:260] + string_record(0x0083, b"")
                                                 + bytes.fromhex("0040020000000000 1040020032000000") + TERM)


def event_fields(event_id: int, group: bytes = FF30.group) -> bytes:
    return (string_record(0x4140, group) + pack("<2HI", 0x4147, 2, event_id)
            + bytes.fromhex("4241020000030303 4341020000000000 4441020000000000"))


def registration(event_id: int, score: int, player: bytes = b"Golfer", group: bytes = FF30.group) -> bytes:
    session = NOTICE_FIELDS[:260] + string_record(0x0083, b"abc")
    stats = pack("<2Hq2Hq", 0x4500, 3, score, 0x4501, 3, 90)
    details = b"".join(string_record(0x4600 + index, b"0") for index in range(14))
    stamp = string_record(0x42B0, player + b"@2018-09-14T12:00:00+09:00")
    return SERVER_TIME_REQUEST.replace(TERM, session + event_fields(event_id, group) + stamp + stats + details + TERM)


def own_score_request(event_id: int, group: bytes = FF30.group) -> bytes:
    login = bytes.fromhex("86002100") + bytes(128) + bytes.fromhex("8700020000000000 8800020000000000")
    return SERVER_TIME_REQUEST.replace(TERM, NOTICE_FIELDS[:268] + login + event_fields(event_id, group) + TERM)


def score_list_request(event_id: int, group: bytes = FF30.group) -> bytes:
    page = bytes.fromhex("0040020001000000 1040020064000000")
    return SERVER_TIME_REQUEST.replace(TERM, NOTICE_FIELDS[:268] + event_fields(event_id, group) + page + TERM)


def join_request(event_id: int, group: bytes = FF30.group) -> bytes:
    return SERVER_TIME_REQUEST.replace(TERM, NOTICE_FIELDS[:268] + event_fields(event_id, group) + TERM)


def board_rows(board: bytes) -> list[tuple[int, int, int]]:
    """(number, stage, event id) of each row."""
    rows = []
    at = board.find(pack("<2H", 0x4120, 1))
    while at >= 0:
        number, stage = unpack_from("<4xI4xI", board, at + 4)
        event_id = unpack_from("<I", board, board.index(pack("<2H", 0x4147, 2), at) + 4)[0]
        rows.append((number, stage, event_id))
        at = board.find(pack("<2H", 0x4120, 1), at + 4)
    return rows


class CupCatalogTests(unittest.TestCase):
    def test_ff30_settings_carry_both_stages_and_prizes(self):
        settings = FF30.settings()
        self.assertEqual((settings["tournamentId"], settings["resetThreshold"]), (4, 99))
        self.assertEqual((settings["p1_course"], settings["p1_hole"], settings["p1_regulation"]), (4, 0, 1013))
        self.assertEqual((settings["p2_course"], settings["p2_hole"], settings["p2_regulation"]), (4, 0, 1034))
        self.assertEqual((settings["p1_reg_reward_normal_1"], settings["p1_reg_reward_normal_2"]), (8953, 8962))
        self.assertEqual((settings["p1_reg_reward_sponcored_1"], settings["p1_reg_reward_sponcored_2"]),
                         (8953, 8962))
        self.assertEqual((settings["p2_reg_reward_normal_1"], settings["p2_reg_reward_normal_2"]), (8958, 0))

    def test_configured_cup_overrides_cut_holes_and_course(self):
        self.assertEqual(configured_cup("ff30"), FF30)
        short = configured_cup("ff30", cut=-3, holes=3, course=1)
        self.assertEqual(short.cut, -3)
        self.assertEqual([(stage.hole, stage.course) for stage in short.stages], [(3, 1), (3, 1)])
        self.assertEqual([stage.entry_prizes for stage in short.stages], [(8953, 8962), (8958,)])

    def test_catalog_cups_have_their_own_numbers_events_and_prizes(self):
        self.assertEqual(list(CUPS), ["ff30", "level5-1", "level5-2", "famitsu"])
        self.assertEqual(len({cup.number for cup in CUPS.values()}), 4)
        events = [stage.event_id for cup in CUPS.values() for stage in cup.stages]
        self.assertEqual(len(set(events)), 8)
        # Request validation takes a 12 to 15 character group (a 5-word record, as LocalTournament).
        self.assertTrue(all(12 <= len(cup.group) <= 15 and cup.name.isascii() for cup in CUPS.values()))
        prizes = {key: [stage.entry_prizes for stage in cup.stages] for key, cup in CUPS.items()}
        self.assertEqual(prizes["level5-1"], [(9000,), (9001,)])
        self.assertEqual(prizes["level5-2"], [(9002,), (8984, 8985)])
        self.assertEqual(prizes["famitsu"], [(9128,), ()])
        # The Famitsu final's ranger suits have no textures: it pays 3,000 coins for finishing.
        settings = FAMITSU.settings()
        self.assertEqual((settings["p2_course"], settings["p2_reg_reward_normal_1"]), (10, 0))
        self.assertEqual((settings["p2_score_reward_flag"], settings["p2_score_reward_score"],
                          settings["p2_score_reward_itemId"], settings["p2_score_reward_itemCount"]),
                         (1, 99, 5716, 3000))
        self.assertNotIn("p1_score_reward_flag", settings)
        self.assertEqual(LEVEL5_2.settings()["p2_reg_reward_normal_2"], 8985)
        self.assertEqual(LEVEL5_1.settings()["p1_course"], 2)

    def test_modes_set_cut_final_conditions_and_attempts(self):
        classic, hardcore = mode_cups("classic"), mode_cups("hardcore")
        self.assertEqual(classic, tuple(CUPS.values()))
        self.assertTrue(all(cup.cut == -3 and cup.final.regulation == 1034 and cup.attempts == 3
                            and cup.settings()["resetThreshold"] == 3 for cup in hardcore))
        # Qualifier conditions and prizes do not change.
        self.assertEqual([cup.qualifier for cup in hardcore], [cup.qualifier for cup in classic])
        self.assertEqual([cup.final.entry_prizes for cup in hardcore], [cup.final.entry_prizes for cup in classic])
        self.assertTrue(all(cup.settings()["resetThreshold"] == 99 for cup in classic))
        self.assertEqual(mode_cups("hardcore", holes=3)[1].qualifier.hole, 3)
        with self.assertRaises(ValueError):
            mode_cups("earn")

    def test_schedule_keeps_the_clock_inside_the_current_stage(self):
        self.assertEqual(cup_clock(DAY, 0), datetime(2018, 9, 14, 12))
        self.assertEqual(cup_clock(DAY, 3), datetime(2018, 9, 17, 12))
        self.assertEqual(stage_windows(DAY, 0, 1), ((datetime(2018, 9, 12), datetime(2018, 9, 14, 23, 59, 59)),
                                                    (datetime(2018, 9, 15), datetime(2018, 9, 17, 23, 59, 59))))
        self.assertEqual(stage_windows(DAY, 5, 2), ((datetime(2018, 9, 14), datetime(2018, 9, 16, 23, 59, 59)),
                                                    (datetime(2018, 9, 17), datetime(2018, 9, 19, 23, 59, 59))))
        for day in range(6):
            for stage in (1, 2):
                window = stage_windows(DAY, day, stage)[stage - 1]
                self.assertTrue(window[0] <= cup_clock(DAY, day) <= window[1])
                # A round's record carries its window's last day; the clock after the round (one
                # day on) is past it, so the game lists the result notice.
                self.assertLess(window[1], cup_clock(DAY, day + 1))
                self.assertLessEqual(notice_time(DAY, day + 1, FF30), cup_clock(DAY, day + 1))
                self.assertGreater(notice_time(DAY, day + 1, FF30), window[1])
        self.assertNotEqual(notice_time(DAY, 1, FF30), notice_time(DAY, 1, LEVEL5_1))


class CupRecordTests(unittest.TestCase):
    def test_board_sends_both_stages_or_only_the_current_one(self):
        self.assertEqual(board_rows(national_tournament_board(DAY, FF30)), [(4, 1, 41), (4, 2, 42)])
        self.assertEqual(board_rows(national_tournament_board(DAY, FF30, current=1)), [(4, 1, 41)])
        self.assertEqual(board_rows(national_tournament_board(DAY, FF30, current=2)), [(4, 2, 42)])
        board = national_tournament_board(DAY, FF30)
        self.assertEqual(unpack_from("<2HI", board), (0x4100, 2, 2))
        self.assertIn(b"FINAL FANTASY 30th Anniversary Cup\0", board)
        self.assertIn(pack("<2H", 0x4177, 3) + bytes.fromhex("2018091200000000"), board)
        self.assertIn(pack("<2H", 0x4178, 3) + bytes.fromhex("2018091723595900"), board)

    def test_notice_item_pairs_by_tournament_number(self):
        item = cup_notice_item(FF30, 1, datetime(2018, 9, 13, 12))
        self.assertIn(b"<nid>4</nid>FINAL FANTASY 30th Anniversary Cup: Qualifier results\0", item)
        self.assertIn(pack("<2H", 0x3064, 3) + bytes.fromhex("2018091312000000"), item)
        self.assertTrue(item.startswith(pack("<2H", 0x3010, 1)) and item.endswith(pack("<2H", 0x3020, 1)))
        reply = notice_reply([item, item])
        self.assertIn(pack("<2HI", 0x3000, 2, 2) + item + item + TERM, reply)

    def test_own_score_flags_a_passed_qualifier(self):
        row = (b"Golfer", 2, 90)
        self.assertIn(pack("<2HI", 0x42D1, 2, 1),
                      recorded_score_reply(row, paged=False, national=True, passed=True))
        self.assertIn(pack("<2HI", 0x42D1, 2, 2), recorded_score_reply(row, paged=False, national=True))


class CupServerTests(unittest.TestCase):
    def start(self, **options):
        with patch("socket.getfqdn", side_effect=AssertionError("unexpected host lookup")):
            server = GolfServer(0, None, national_tournament=True, server_time=DAY, **options)
        worker = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 3)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        client = http.client.HTTPConnection(LOOPBACK, server.server_port, timeout=3)
        self.addCleanup(client.close)
        return client

    def call(self, client, path, body=None):
        client.request("POST" if body is not None else "GET", path, body=body,
                       headers=SERVER_TIME_HEADERS if body is not None else {})
        response = client.getresponse()
        return response.status, response.read()

    def board(self, client, selector):
        request = NATIONAL_BOARD_REQUEST.replace(bytes.fromhex("404a020000000000"), pack("<2HI", 0x4A40, 2, selector))
        self.assertEqual(self.call(client, NATIONAL_BOARD_PATH, request)[0], 200)
        status, board = self.call(client, DOWNLOAD_BASE + "/local-national-board.bin")
        self.assertEqual(status, 200)
        return board_rows(board)

    def clock(self, client):
        status, reply = self.call(client, SERVER_TIME_PATH, SERVER_TIME_REQUEST)
        self.assertEqual(status, 200)
        return reply[reply.index(pack("<2H", 0x5000, 3)) + 4:][:7]

    def boot(self, client):
        clock = self.clock(client)
        self.assertEqual(self.call(client, LOGIN_TARGET, LOGIN_REQUEST)[0], 200)
        return clock

    def open_notice(self, client, event_id, group=FF30.group):
        """The Notices box (bonus list), then a result notice: own score and score list of both stages."""
        self.assertEqual(self.call(client, NATIONAL_BOARD_PATH, NATIONAL_BOARD_REQUEST)[0], 200)
        self.assertEqual(self.call(client, BONUS_LIST_PATH, BONUS_LIST_REQUEST)[0], 200)
        for event in (event_id - (event_id % 10 == 2), event_id + (event_id % 10 == 1)):
            self.own(client, event, group)
            self.assertEqual(self.call(client, NATIONAL_SCORE_LIST_PATH, score_list_request(event, group))[0], 200)

    def own(self, client, event_id, group=FF30.group):
        status, reply = self.call(client, NATIONAL_OWN_SCORE_PATH, own_score_request(event_id, group))
        self.assertEqual(status, 200)
        return reply

    @staticmethod
    def archive_settings(archive):
        files, stream = [], 56
        for index in range(2):
            compressed, expanded = unpack_from("<2I", archive, 16 + index * 20 + 12)
            files.append(zlib.decompress(archive[stream:stream + compressed]))
            stream += (compressed + 3) & ~3
        settings = next(data for data in files if b"resetThreshold" in data)
        header, values = settings.decode("utf-8-sig").split("\r\n")[:2]
        return dict(zip(header.split("\t"), map(int, values.split("\t"))))

    def notices(self, client):
        status, reply = self.call(client, NOTICE_PATH, NOTICE_REQUEST.replace(
            bytes.fromhex("5030020001000000"), bytes.fromhex("5030020000000000")))
        self.assertEqual(status, 200)
        return reply

    def test_cup_needs_a_national_tournament(self):
        with self.assertRaises(ValueError):
            GolfServer(0, None, server_time=DAY, collab_cup=FF30)

    def test_qualifier_then_final_then_next_cup_in_one_sitting(self):
        with TemporaryDirectory() as directory:
            cups = (configured_cup("ff30", cut=3), LEVEL5_1)
            client = self.start(score_db=Path(directory) / "scores.sqlite", collab_cups=cups, login_completion=True,
                                empty_bonus_list=True)
            self.assertEqual(self.boot(client), bytes.fromhex("20180914120000"))
            self.assertEqual(self.board(client, 1), [(4, 1, 41)])
            self.assertEqual(self.board(client, 0), [(4, 1, 41), (4, 2, 42)])
            self.assertEqual(self.board(client, 3), [(4, 1, 41), (4, 2, 42)])
            self.assertNotIn(b"<nid>", self.notices(client))

            # A missed cut: the day moves on, the qualifier notice comes, the final stays closed.
            self.assertEqual(self.call(client, REGISTRATION, registration(41, 5))[0], 200)
            self.assertEqual(self.clock(client), bytes.fromhex("20180915120000"))
            self.assertIn(pack("<2HI", 0x42D1, 2, 2), self.own(client, 41))
            notices = self.notices(client)
            self.assertIn(b"<nid>4</nid>FINAL FANTASY 30th Anniversary Cup: Qualifier results", notices)
            self.assertIn(pack("<2H", 0x3064, 3) + bytes.fromhex("2018091500040000"), notices)
            self.assertEqual(self.board(client, 1), [(4, 1, 41)])

            # Making the cut: the next round's notice is dated that day.
            self.assertEqual(self.call(client, REGISTRATION, registration(41, 3))[0], 200)
            self.assertEqual(self.clock(client), bytes.fromhex("20180916120000"))
            self.assertIn(bytes.fromhex("2018091600040000"), self.notices(client))
            # The tournament screen (a board request, own score, score list) is not an opened notice.
            self.assertEqual(self.board(client, 1), [(4, 1, 41)])
            self.assertIn(pack("<2HI", 0x42D1, 2, 1), self.own(client, 41))
            self.assertEqual(self.call(client, NATIONAL_SCORE_LIST_PATH, score_list_request(41))[0], 200)
            self.assertEqual(self.board(client, 1), [(4, 1, 41)])
            # Neither is the entry screen (own score, then the join).
            self.own(client, 41)
            self.assertEqual(self.call(client, JOIN, join_request(41))[0], 200)
            self.assertEqual(self.board(client, 1), [(4, 1, 41)])
            # Opening the notice in the Notices box opens the final at the next board request.
            self.open_notice(client, 41)
            self.assertEqual(self.board(client, 1), [(4, 2, 42)])
            self.assertEqual(self.clock(client), bytes.fromhex("20180916120000"))
            self.assertEqual(self.boot(client), bytes.fromhex("20180916120000"))
            self.assertEqual(self.board(client, 1), [(4, 2, 42)])

            # The final: its notice, and the final's own score never carries the passed flag.
            self.assertEqual(self.call(client, REGISTRATION, registration(42, 1))[0], 200)
            self.assertIn(pack("<2HI", 0x42D1, 2, 2), self.own(client, 42))
            self.assertEqual(self.call(client, NATIONAL_SCORE_LIST_PATH, score_list_request(42))[0], 200)
            self.assertEqual(self.clock(client), bytes.fromhex("20180917120000"))
            self.assertEqual(self.board(client, 1), [(4, 2, 42)])
            notices = self.notices(client)
            self.assertIn(pack("<2HI", 0x3000, 2, 2), notices)
            self.assertLess(notices.index(b"Final results"), notices.index(b"Qualifier results"))

            # Opening the final's notice moves on to the next cup, on the same clock.
            self.open_notice(client, 42)
            self.assertEqual(self.board(client, 1), [(5, 1, 51)])
            self.assertEqual(self.clock(client), bytes.fromhex("20180917120000"))
            self.assertNotIn(b"<nid>", self.notices(client))
            status, archive = self.call(client, DOWNLOAD_BASE + "/local-tournament.xb")
            self.assertEqual(status, 200)
            self.assertEqual(self.archive_settings(archive)["tournamentId"], 5)
            group = LEVEL5_1.group
            self.assertEqual(self.call(client, REGISTRATION, registration(51, 0, group=group))[0], 200)
            self.open_notice(client, 51, group)
            self.assertEqual(self.board(client, 1), [(5, 2, 52)])
            self.assertEqual(self.call(client, REGISTRATION, registration(52, 0, group=group))[0], 200)
            self.open_notice(client, 52, group)
            # Round and round: FF30 again, with fresh scores.
            self.assertEqual(self.board(client, 1), [(4, 1, 41)])
            self.assertNotIn(b"<nid>", self.notices(client))
            self.assertEqual(self.call(client, NATIONAL_OWN_SCORE_PATH, own_score_request(41))[0], 200)

            # Another cup's group or an unknown event id is refused.
            self.assertEqual(self.call(client, REGISTRATION, registration(43, 0))[0], 400)
            self.assertEqual(self.call(client, REGISTRATION, registration(51, 0))[0], 400)
            self.assertEqual(self.call(client, REGISTRATION, registration(1, 0).replace(
                FF30.group, b"LocalTournament"))[0], 400)

    def test_hardcore_join_counts_rounds_per_stage_per_day(self):
        with TemporaryDirectory() as directory:
            client = self.start(score_db=Path(directory) / "scores.sqlite", collab_cups=mode_cups("hardcore"),
                                login_completion=True)
            counts = []
            for event_id in (41, 41, 41, 41, 42):
                status, reply = self.call(client, JOIN, join_request(event_id))
                self.assertEqual(status, 200)
                counts.append(unpack_from("<I", reply, reply.index(pack("<2H", 0x4962, 2)) + 4)[0])
            self.assertEqual(counts, [1, 2, 3, 4, 1])
            # -3 makes the cut, -2 does not.
            self.assertEqual(self.call(client, REGISTRATION, registration(41, -2))[0], 200)
            self.assertIn(pack("<2HI", 0x42D1, 2, 2), self.own(client, 41))
            self.assertEqual(self.call(client, REGISTRATION, registration(41, -3))[0], 200)
            self.assertIn(pack("<2HI", 0x42D1, 2, 1), self.own(client, 41))

    def test_classic_join_count_stays_zero(self):
        with TemporaryDirectory() as directory:
            client = self.start(score_db=Path(directory) / "scores.sqlite", collab_cups=mode_cups("classic"),
                                login_completion=True)
            for _ in range(5):
                reply = self.call(client, JOIN, join_request(41))[1]
                self.assertIn(pack("<2HI", 0x4962, 2, 0), reply)

    def test_cups_need_their_own_numbers(self):
        with self.assertRaises(ValueError):
            GolfServer(0, None, national_tournament=True, server_time=DAY, collab_cups=(FF30, FF30))

    def test_cup_archive_names_the_cup(self):
        client = self.start(collab_cup=FF30)
        status, archive = self.call(client, DOWNLOAD_BASE + "/local-tournament.xb")
        self.assertEqual(status, 200)
        files, stream = [], 56
        for index in range(2):
            compressed, expanded = unpack_from("<2I", archive, 16 + index * 20 + 12)
            files.append(zlib.decompress(archive[stream:stream + compressed]))
            stream += (compressed + 3) & ~3
        messages, settings = sorted(files, key=lambda data: b"resetThreshold" in data)
        header, values = settings.decode("utf-8-sig").split("\r\n")[:2]
        table = dict(zip(header.split("\t"), map(int, values.split("\t"))))
        self.assertEqual({key: table[key] for key in FF30.settings()}, FF30.settings())
        self.assertEqual((table["p1_reg_reward_normal_1"], table["p2_reg_reward_normal_1"]), (8953, 8958))
        self.assertIn(b'"FINAL FANTASY 30th Anniversary Cup"', messages)


if __name__ == "__main__":
    unittest.main()
