"""Collab Cups: the 2018 tie-in national tournaments run by the local server.

A cup is one national tournament with two stages, a qualifier and a final. Each stage is its own
board row: both rows carry the same tournament number (word 0x4145, which the game copies to entry
+0x278) and their own event id (0x4147, entry +0x26c); word 0x4146 is the stage (1 or 2, entry
+0x271). One settings archive carries both stages (p1_ and p2_ keys), including the prize item ids.

The game decides nothing about results: the server ranks the score, makes the cut, and lists a
notice whose text starts with <nid>N</nid> (N = the tournament number). The game's Notices box then
pairs the notice with the stage-1 and stage-2 entries of tournament N, builds the prize list from
the settings (FUN_006c97a0) and grants it when the player opens the notice (0x6c89cf), once per save.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Stage:
    event_id: int          # board word 0x4147
    course: int            # p<n>_course: 1 Eagle City, 2 Alpina Forest, 3 Kanaloa Beach, 4 Vortex Valley, ...
    hole: int              # p<n>_hole: 0 = 18 holes, 1 = OUT 9, 2 = IN 9, 3 or more = that many holes
    regulation: int        # p<n>_regulation: a row of course_condition.xb (cup, tee, wind, mirror)
    entry_prizes: tuple[int, ...] = ()   # reg_reward_normal_1/_2 (and _sponcored_): given for finishing
    score_prize: tuple[int, int, int] | None = None   # (score at or under, item id, count)

    def settings(self, number: int) -> dict[str, int]:
        prefix = f"p{number}_"
        values = {"course": self.course, "hole": self.hole, "regulation": self.regulation}
        for slot in (1, 2):
            item = self.entry_prizes[slot - 1] if len(self.entry_prizes) >= slot else 0
            values[f"reg_reward_normal_{slot}"] = item
            values[f"reg_reward_sponcored_{slot}"] = item
        if self.score_prize is not None:
            score, item, count = self.score_prize
            values.update(score_reward_flag=1, score_reward_score=score, score_reward_itemId=item,
                          score_reward_itemCount=count)
        return {prefix + key: value for key, value in values.items()}


@dataclass(frozen=True)
class Cup:
    key: str
    number: int            # board word 0x4145 and the notice <nid>
    group: bytes           # board word 0x4140, sent back in every event request
    name: str
    qualifier: Stage
    final: Stage
    cut: int = 3           # qualifier score (strokes against par) at or under this makes the final

    @property
    def stages(self) -> tuple[Stage, Stage]:
        return (self.qualifier, self.final)

    def stage_of(self, event_id: int) -> int | None:
        for number, stage in enumerate(self.stages, 1):
            if stage.event_id == event_id:
                return number
        return None

    def settings(self) -> dict[str, int]:
        # resetThreshold 99: the join count never reaches it, so attempts are unlimited (Classic).
        values = {"resetThreshold": 99, "tournamentId": self.number, "sponsored_US": 0}
        for number, stage in enumerate(self.stages, 1):
            values.update(stage.settings(number))
        return values


# FF30 Collab Cup (2018-02-26..03-12, the 4th national tournament): Vortex Valley, 18 holes, big
# cup and a +3 pass line (player blog, 2018-03). The final used champion tees and strong wind
# (course_condition row 1034: cup 0, tee 2, wind 1). Finishing the qualifier gave the Cactuar outer
# 8953 and the twelve Cactuar caps (set 8962 = 8929-8940); finishing the final gave the Moogle 8958.
FF30 = Cup(
    key="ff30", number=4, group=b"FF30CollabCup", name="FINAL FANTASY 30th Anniversary Cup",
    qualifier=Stage(event_id=41, course=4, hole=0, regulation=1013, entry_prizes=(8953, 8962)),
    final=Stage(event_id=42, course=4, hole=0, regulation=1034, entry_prizes=(8958,)),
)

CUPS = {cup.key: cup for cup in (FF30,)}


def configured_cup(key: str, *, cut: int | None = None, holes: int | None = None,
                   course: int | None = None) -> Cup:
    """The catalog cup with the server's options: the cut (Hardcore uses -3) and, for tests, a
    shorter round (holes 3 or more = that many holes) or another course."""
    cup = CUPS[key]
    stages = []
    for stage in cup.stages:
        if holes is not None:
            stage = replace(stage, hole=holes)
        if course is not None:
            stage = replace(stage, course=course)
        stages.append(stage)
    return replace(cup, qualifier=stages[0], final=stages[1], cut=cup.cut if cut is None else cut)


# The qualifier and then the final, as the 2018 cups ran them. The game keeps one current national
# entry, filled from board selector 1 (the server sends only the current stage there, see
# national_tournament_board). Only the current entry has its settings archive loaded, and the prize
# code reads the prize ids from the entry whose event id matches the result record the game saved
# at the end of the round. So the qualifier stays current for one more login after the cut is made
# (the results day, when the player opens the qualifier notice), and the final is current after
# that. The game lists a stage's result notice only once that stage's window has closed, so the
# results-day clock is just after the qualifier window (the qualifier entry stays current). The game
# clock starts from the server time sent at login.
STAGE_DAYS = ((-2, 0), (1, 3))   # first and last day of each stage's window, relative to D
QUALIFIER, RESULTS_DAY, FINAL, AFTER_FINAL = range(4)
PHASE_CLOCK = ((0, 12), (1, 1), (2, 12), (4, 12))    # (day after D, hour) of the login clock
NOTICE_CLOCK = ((-1, 12), (1, 12))                    # each stage's <nid> notice date


def _at(day: datetime, offset: int, hour: int) -> datetime:
    return day.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=offset)


def stage_window(day: datetime, stage: int, through: datetime | None = None) -> tuple[datetime, datetime]:
    """A stage's window. `through` keeps it open to the end of that day: on a results login the
    stage that just closed stays the current entry, because the game builds no current entry from
    a closed selector-1 row, and the prize code reads the prize keys from that entry."""
    first, last = STAGE_DAYS[stage - 1]
    midnight = day.replace(hour=0, minute=0, second=0, microsecond=0)
    end = midnight + timedelta(days=last + 1) - timedelta(seconds=1)
    if through is not None:
        end = max(end, through.replace(hour=23, minute=59, second=59, microsecond=0))
    return midnight + timedelta(days=first), end


def cup_phase(*, passed: bool, final_done: bool, logins_after_cut: int) -> int:
    """The phase of a login. logins_after_cut counts this login (1 = the first after the cut)."""
    if not passed:
        return QUALIFIER
    if final_done:
        return AFTER_FINAL
    return RESULTS_DAY if logins_after_cut <= 1 else FINAL


def phase_stage(phase: int) -> int:
    """The stage that is current (board selector 1) in a phase."""
    return 1 if phase in (QUALIFIER, RESULTS_DAY) else 2


def cup_clock(day: datetime, phase: int) -> datetime:
    return _at(day, *PHASE_CLOCK[phase])


def notice_time(day: datetime, stage: int) -> datetime:
    """A stage's <nid> result notice date, before the clock of the phase that shows it (the game
    hides notices dated after its clock and remembers opened ones by date)."""
    return _at(day, *NOTICE_CLOCK[stage - 1])
