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
    attempts: int = 0      # rounds per stage per day (resetThreshold); 0 = unlimited

    @property
    def stages(self) -> tuple[Stage, Stage]:
        return (self.qualifier, self.final)

    def stage_of(self, event_id: int) -> int | None:
        for number, stage in enumerate(self.stages, 1):
            if stage.event_id == event_id:
                return number
        return None

    def settings(self) -> dict[str, int]:
        # resetThreshold: the entry screen refuses a new round once the join count the server sends
        # (gameapi_noticejoinnational, 0x4962) is above it (0xc4b8f3). 99 is never reached (Classic).
        values = {"resetThreshold": self.attempts or 99, "tournamentId": self.number, "sponsored_US": 0}
        for number, stage in enumerate(self.stages, 1):
            values.update(stage.settings(number))
        return values


# Rows of course_condition.xb (Cup_Use, Tee_Use, Wind_Use, Mirror_Use).
STANDARD = 1014        # (0, 0, 0, 0): regular tee; the entry screen shows Mega Cup and no mirror
BIG_CUP = 1013         # the FF30 qualifier (big cup, low growth per the 2018 player blog)
CHAMPION_WIND = 1034   # (0, 2, 1, 0): champion tees and strong wind (the FF30 final; Hardcore finals)
COIN_ITEM = 5716       # material_coin_00: coins, given with a count by score_reward

# FF30 Collab Cup (2018-02-26..03-12, the 4th national tournament): Vortex Valley, 18 holes, big
# cup and a +3 pass line (player blog, 2018-03). The final used champion tees and strong wind.
# Finishing the qualifier gave the Cactuar outer 8953 and the twelve Cactuar caps (set 8962 =
# 8929-8940); finishing the final gave the Moogle 8958.
FF30 = Cup(
    key="ff30", number=4, group=b"FF30CollabCup", name="FINAL FANTASY 30th Anniversary Cup",
    qualifier=Stage(event_id=41, course=4, hole=0, regulation=BIG_CUP, entry_prizes=(8953, 8962)),
    final=Stage(event_id=42, course=4, hole=0, regulation=CHAMPION_WIND, entry_prizes=(8958,)),
)

# LEVEL-5 20th anniversary cups (2018-06). Prizes from the item sets; courses and rules were not
# archived, so these are picks (Alpina Forest, then Kanaloa Beach, regular conditions). The
# tournament numbers and event ids of these and the Famitsu cup are this server's own.
LEVEL5_1 = Cup(
    key="level5-1", number=5, group=b"Level5Collab1", name="LEVEL-5 20th Anniversary Cup 1",
    # Set 9000: Toan and Xiao (8977-8978, 8982-8983, 8989-8990, 8994-8995). Set 9001: White Knight.
    qualifier=Stage(event_id=51, course=2, hole=0, regulation=STANDARD, entry_prizes=(9000,)),
    final=Stage(event_id=52, course=2, hole=0, regulation=STANDARD, entry_prizes=(9001,)),
)
LEVEL5_2 = Cup(
    key="level5-2", number=6, group=b"Level5Collab2", name="LEVEL-5 20th Anniversary Cup 2",
    # Set 9002: Evan, Shaati and Layton (8976, 8980-8981, 8986-8988, 8992-8993; Evan's pants 8980
    # has no model). Final: the Jibanyan and Komasan suits 8984 and 8985 (set 9003).
    qualifier=Stage(event_id=61, course=3, hole=0, regulation=STANDARD, entry_prizes=(9002,)),
    final=Stage(event_id=62, course=3, hole=0, regulation=STANDARD, entry_prizes=(8984, 8985)),
)
# Famitsu Collab Cup (2018-08-31..09-14): the final was on Akigase Keikoku (course 10, as in the
# course_10 use-right item). The qualifier course was not archived (Eagle City here). Qualifier:
# the T-shirt and cap set 9128 (three of its shirts, 9125-9127, have no texture). The final's
# ranger suits (set 9129) have no textures at all, so the final gives coins instead: score_reward
# with a score no round misses pays them for finishing.
FAMITSU = Cup(
    key="famitsu", number=7, group=b"FamitsuCollab", name="Famitsu Collab Cup",
    qualifier=Stage(event_id=71, course=1, hole=0, regulation=STANDARD, entry_prizes=(9128,)),
    final=Stage(event_id=72, course=10, hole=0, regulation=STANDARD, score_prize=(99, COIN_ITEM, 3000)),
)

# Served in this order, one at a time: the game keeps a single current national entry.
CUPS = {cup.key: cup for cup in (FF30, LEVEL5_1, LEVEL5_2, FAMITSU)}
MODES = ("classic", "hardcore")
HARDCORE_CUT = -3
HARDCORE_ATTEMPTS = 3


def configured_cup(key: str, *, cut: int | None = None, holes: int | None = None,
                   course: int | None = None, hardcore: bool = False) -> Cup:
    """The catalog cup with the server's options. Hardcore: cut -3, the final on champion tees in
    strong wind, three rounds per stage per day. Test only: a shorter round (holes 3 or more = that
    many holes) or another course."""
    cup = CUPS[key]
    stages = []
    for number, stage in enumerate(cup.stages, 1):
        if hardcore and number == 2:
            stage = replace(stage, regulation=CHAMPION_WIND)
        if holes is not None:
            stage = replace(stage, hole=holes)
        if course is not None:
            stage = replace(stage, course=course)
        stages.append(stage)
    if cut is None:
        cut = HARDCORE_CUT if hardcore else cup.cut
    return replace(cup, qualifier=stages[0], final=stages[1], cut=cut,
                   attempts=HARDCORE_ATTEMPTS if hardcore else cup.attempts)


def mode_cups(mode: str, **options) -> tuple[Cup, ...]:
    """Every catalog cup, in order, for a collab_items mode (classic or hardcore)."""
    if mode not in MODES:
        raise ValueError(f"cup mode is one of {', '.join(MODES)}")
    return tuple(configured_cup(key, hardcore=mode == "hardcore", **options) for key in CUPS)


# The schedule follows the player, not the calendar. The game clock (the server time sent at login
# and after each round) is a cup day counter: every finished cup round moves it one day on. The
# current stage's window always ends on the clock day, so it is open, and the round's result record
# (whose day is the window's last day, ring record +8) is listed in Notices from the next day,
# which is the clock the game gets right after the round. The game builds the prize list from the
# current entry, so a stage stays current until its notice is opened (gameapi_getmyscorenational
# from the Notices box): the qualifier until it is opened with the cut made, then the final until
# its notice is opened, then the next cup. Everything happens in one sitting.
CLOCK_HOUR = 12


def cup_clock(start: datetime, day: int) -> datetime:
    return start.replace(hour=CLOCK_HOUR, minute=0, second=0, microsecond=0) + timedelta(days=day)


def stage_windows(start: datetime, day: int, current: int) -> tuple[tuple[datetime, datetime], ...]:
    """Both stages' windows on cup day `day`. The current stage's window is the three days ending
    on the clock day; the other stage's is the three days before it (final current) or after it."""
    midnight = start.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=day)
    ends = {current: 0, 3 - current: -3 if current == 2 else 3}
    return tuple((midnight + timedelta(days=ends[stage] - 2),
                  midnight + timedelta(days=ends[stage] + 1, seconds=-1)) for stage in (1, 2))


def notice_time(start: datetime, day: int, cup: Cup) -> datetime:
    """The date of a result notice for a round that moved the cup day to `day`: that day's 00:00
    plus the cup number in minutes. The game shows a notice only when it is not dated after its
    clock and remembers opened notices by date, so each round's notice needs a new one."""
    return start.replace(hour=0, minute=cup.number, second=0, microsecond=0) + timedelta(days=day)
