from datetime import datetime
import http.client
from pathlib import Path
from struct import pack, unpack_from
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch
import zlib

from collab_cups import (AFTER_FINAL, FF30, FINAL, QUALIFIER, RESULTS_DAY, configured_cup, cup_clock, cup_phase,
                         notice_time, phase_stage, stage_window)
from golf_server import (LOOPBACK, GolfServer, cup_notice_item, national_tournament_board, notice_reply,
                         recorded_score_reply)
from test_golf_server import (LOGIN_REQUEST, LOGIN_TARGET, DOWNLOAD_BASE, NATIONAL_BOARD_PATH, NATIONAL_BOARD_REQUEST, NATIONAL_OWN_SCORE_PATH,
                              NOTICE_FIELDS, NOTICE_PATH, NOTICE_REQUEST, SERVER_TIME_HEADERS, SERVER_TIME_PATH,
                              SERVER_TIME_REQUEST, string_record)

DAY = datetime(2018, 9, 14, 12)
TERM = bytes.fromhex("10800100")
REGISTRATION = "/nmg-us/replay-probe/gameapi_registscorenational?account=5932163534510096385&n=4&s=1"


def event_fields(event_id: int, group: bytes = FF30.group) -> bytes:
    return (string_record(0x4140, group) + pack("<2HI", 0x4147, 2, event_id)
            + bytes.fromhex("4241020000030303 4341020000000000 4441020000000000"))


def registration(event_id: int, score: int, player: bytes = b"Golfer") -> bytes:
    session = NOTICE_FIELDS[:260] + string_record(0x0083, b"abc")
    stats = pack("<2Hq2Hq", 0x4500, 3, score, 0x4501, 3, 90)
    details = b"".join(string_record(0x4600 + index, b"0") for index in range(14))
    stamp = string_record(0x42B0, player + b"@2018-09-14T12:00:00+09:00")
    return SERVER_TIME_REQUEST.replace(TERM, session + event_fields(event_id) + stamp + stats + details + TERM)


def own_score_request(event_id: int) -> bytes:
    login = bytes.fromhex("86002100") + bytes(128) + bytes.fromhex("8700020000000000 8800020000000000")
    return SERVER_TIME_REQUEST.replace(TERM, NOTICE_FIELDS[:268] + login + event_fields(event_id) + TERM)


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
        hardcore = configured_cup("ff30", cut=-3, holes=3, course=1)
        self.assertEqual(hardcore.cut, -3)
        self.assertEqual([(stage.hole, stage.course) for stage in hardcore.stages], [(3, 1), (3, 1)])
        self.assertEqual([stage.entry_prizes for stage in hardcore.stages], [(8953, 8962), (8958,)])

    def test_schedule_keeps_each_clock_inside_its_stage_and_after_its_notice(self):
        self.assertEqual(stage_window(DAY, 1), (datetime(2018, 9, 12), datetime(2018, 9, 14, 23, 59, 59)))
        self.assertEqual(stage_window(DAY, 2), (datetime(2018, 9, 15), datetime(2018, 9, 17, 23, 59, 59)))
        phases = [cup_phase(passed=False, final_done=False, logins_after_cut=0),
                  cup_phase(passed=True, final_done=False, logins_after_cut=1),
                  cup_phase(passed=True, final_done=False, logins_after_cut=2),
                  cup_phase(passed=True, final_done=True, logins_after_cut=2)]
        self.assertEqual(phases, [QUALIFIER, RESULTS_DAY, FINAL, AFTER_FINAL])
        self.assertEqual([phase_stage(phase) for phase in phases], [1, 1, 2, 2])
        for phase in (QUALIFIER, FINAL):
            window = stage_window(DAY, phase_stage(phase))
            self.assertTrue(window[0] <= cup_clock(DAY, phase) <= window[1], phase)
        # Results logins come the day after the stage window (the game lists a result notice only
        # after the date its round recorded), with that stage kept open as the current entry.
        for phase in (RESULTS_DAY, AFTER_FINAL):
            stage = phase_stage(phase)
            self.assertLess(stage_window(DAY, stage)[1].date(), cup_clock(DAY, phase).date(), phase)
            window = stage_window(DAY, stage, through=cup_clock(DAY, phase))
            self.assertTrue(window[0] <= cup_clock(DAY, phase) <= window[1], phase)
        self.assertLess(cup_clock(DAY, RESULTS_DAY), cup_clock(DAY, FINAL))
        # The results day comes after a round played at the qualifier clock; the final's notice is
        # shown after the final round.
        self.assertGreater(cup_clock(DAY, RESULTS_DAY), cup_clock(DAY, QUALIFIER))
        self.assertTrue(notice_time(DAY, 1) <= cup_clock(DAY, QUALIFIER))
        self.assertTrue(notice_time(DAY, 2) <= cup_clock(DAY, AFTER_FINAL))
        # A missed cut keeps the qualifier (the player can try again).
        self.assertEqual(cup_phase(passed=False, final_done=True, logins_after_cut=0), QUALIFIER)


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

    def notices(self, client):
        status, reply = self.call(client, NOTICE_PATH, NOTICE_REQUEST.replace(
            bytes.fromhex("5030020001000000"), bytes.fromhex("5030020000000000")))
        self.assertEqual(status, 200)
        return reply

    def test_cup_needs_a_national_tournament(self):
        with self.assertRaises(ValueError):
            GolfServer(0, None, server_time=DAY, collab_cup=FF30)

    def test_qualifier_then_final_then_notices(self):
        with TemporaryDirectory() as directory:
            client = self.start(score_db=Path(directory) / "scores.sqlite", collab_cup=configured_cup("ff30", cut=3),
                                login_completion=True)
            self.assertEqual(self.board(client, 1), [(4, 1, 41)])
            self.assertEqual(self.board(client, 0), [(4, 1, 41), (4, 2, 42)])
            self.assertEqual(self.board(client, 3), [(4, 1, 41), (4, 2, 42)])
            self.assertEqual(self.clock(client), bytes.fromhex("20180914120000"))
            self.assertNotIn(b"<nid>", self.notices(client))

            # A missed cut: the prize notice comes, the final stays closed.
            self.assertEqual(self.call(client, REGISTRATION, registration(41, 5))[0], 200)
            status, own = self.call(client, NATIONAL_OWN_SCORE_PATH, own_score_request(41))
            self.assertEqual(status, 200)
            self.assertIn(pack("<2HI", 0x42D1, 2, 2), own)
            self.assertEqual(self.board(client, 1), [(4, 1, 41)])
            self.assertIn(b"<nid>4</nid>FINAL FANTASY 30th Anniversary Cup: Qualifier results", self.notices(client))

            # Making the cut: the session goes on with the qualifier current. The next login is the
            # results day (the qualifier stays current, so its prizes can be read); the one after
            # that opens the final.
            self.assertEqual(self.call(client, REGISTRATION, registration(41, 3))[0], 200)
            self.assertIn(pack("<2HI", 0x42D1, 2, 1), self.call(client, NATIONAL_OWN_SCORE_PATH,
                                                               own_score_request(41))[1])
            # The time request after the round already gives the results-day clock.
            self.assertEqual(self.clock(client), bytes.fromhex("20180915010000"))
            self.assertEqual(self.board(client, 1), [(4, 1, 41)])
            # Next boot (time, then login): still the results day; the boot after that opens the final.
            self.assertEqual(self.boot(client), bytes.fromhex("20180915010000"))
            self.assertEqual(self.board(client, 1), [(4, 1, 41)])
            self.assertEqual(self.boot(client), bytes.fromhex("20180916120000"))
            self.assertEqual(self.board(client, 1), [(4, 2, 42)])
            self.assertEqual(self.boot(client), bytes.fromhex("20180916120000"))
            # The final's own score never carries the passed flag.
            self.assertEqual(self.call(client, REGISTRATION, registration(42, 1))[0], 200)
            self.assertIn(pack("<2HI", 0x42D1, 2, 2), self.call(client, NATIONAL_OWN_SCORE_PATH,
                                                               own_score_request(42))[1])
            self.assertEqual(self.clock(client), bytes.fromhex("20180918120000"))
            self.assertEqual(self.board(client, 1), [(4, 2, 42)])
            notices = self.notices(client)
            self.assertIn(pack("<2HI", 0x3000, 2, 2), notices)
            self.assertLess(notices.index(b"Final results"), notices.index(b"Qualifier results"))

            # Another cup's group or event id is refused.
            self.assertEqual(self.call(client, REGISTRATION, registration(43, 0))[0], 400)
            self.assertEqual(self.call(client, REGISTRATION, registration(1, 0).replace(
                FF30.group, b"LocalTournament"))[0], 400)

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
