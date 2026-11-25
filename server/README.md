# Local Golf service

Run these commands from the project root.

```sh
python -B server/golf_server.py --port 8765
python -B -m unittest discover -s server -v
```

The listener binds to `127.0.0.1` unless `--bind ADDRESS` is given
(`0.0.0.0` accepts other machines; open the port in the firewall).

## Hosting for friends

`host.py` is the launcher's one-command entry. It builds the discovery
fixture, daily score block and EULA text into `--state` once (cached by
the eboot's SHA-256 and `FIXTURE_VERSION`), keeps `scores.db` there, and
serves the verified full online flag set. It prints `ready <bind>:<port>`
when listening and one line per request.

```sh
python -I server/host.py --eboot work/game-1.17-prepared/eboot.elf     --libcrypto tools/msys2/msys64/clang64/bin/libcrypto-4-x64.dll     --state work/online/host --port 48765 --bind 0.0.0.0
```

### Multiplayer (`--online`)

`--online` is what the launcher's Host a game button runs. It listens on
every adapter (port 48765 unless `--port`), turns on the lobby routes,
and keeps a random 27-bit room key in `<state>/room-key.txt`. Callers
from public addresses must send the key in `X-Golf-Key`; this PC, home
networks and VPN ranges (private and 100.64.0.0/10 addresses) need not,
unless `--strict-key`. Lobby, channel and packet exchanges keep their
connection alive, and each exchange carries up to 64 packets each way.

Every packet between players goes through this server (the runtime's
RUDP and signaling HLE never send to a peer directly), so guests talk to
one address and only the host may need an open port. In the background
the host asks the router for TCP port mapping (`portmap.py`: UPnP IGD,
then NAT-PMP, then PCP; `--no-port-mapping` skips it). It takes the
public address from the router, or else from one HTTPS what-is-my-IP
request (`--no-web-lookup` skips it). It writes `<state>/online.txt`:

```text
port=48765
key=24503d5
lan=192.168.1.20 R2M0-255Y-FN4A-0YN1
vpn=100.95.1.2 CHFG-20NY-FN4A-0YNJ
internet=203.0.113.50 SC07-2CNY-FN4A-0YNA
portmap=upnp
note=The router forwards TCP port 48765 to this PC (UPNP).
```

An invite code (`invite.py`, decoded by the runtime's
`src/invite_code.h`) is 16 Crockford base32 symbols: IPv4 address (32
bits), port (16), room key (27) and a check symbol (5). Case, spaces and
dashes do not matter, and I, L and O read as 1, 1 and 0. The runtime
takes `--join CODE` (or `--join HOST[:PORT]` on a home network or VPN).
The host also answers `EGOLF-FIND 1` broadcasts on UDP 48765 with
`EGOLF-HOST 1 <code> <name>`, for the launcher's Find games on my
network. `--stop-file PATH` stops it cleanly (closing the router port)
when the file appears; `--auto` finds the game, libcrypto and `data\server`
of an installed release, as `tools\server\host-online.cmd` uses.

Scores are stored per online name. Loopback clients that send
`X-Golf-Online-Id` can use separate names on the same address. The header
must match the name in login and score registration requests. Clients
without the header use the last name seen for their IP address. Own-score
queries without a known name use the best row.

## Combined replay

Use a runtime with title replay, scoped local NpAuth, and the national
board bridge from `docs/MAILBOX.md`. Omit both `--libcrypto` arguments
on Linux if Python can find libcrypto with Blowfish support.

```bash
replay=$(mktemp -d work/golf-replay-XXXXXX)
eboot=work/game-1.17-prepared/eboot.elf
crypto=tools/msys2/msys64/clang64/bin/libcrypto-4-x64.dll
printf 'Local replay test.\n' > "$replay/eula.txt"
python -B server/make_discovery_fixture.py "$eboot" "$replay/ss-info.bin" \
    --libcrypto "$crypto" --eula --empty-notices --daily-scores --empty-boards \
    --login-completion --empty-national-boards --cached-property --discard-telemetry
python -B server/make_daily_score_block.py "$eboot" "$replay/score-block.bin" \
    --libcrypto "$crypto"
python -B server/golf_server.py --port 48765 --ss-info-file "$replay/ss-info.bin" \
    --eula-file "$replay/eula.txt" --empty-notices --daily-score-block "$replay/score-block.bin" \
    --empty-board-block "$replay/score-block.bin" --login-completion --empty-national-boards --cached-property \
    --discard-telemetry --server-time 2018-09-14T12:00:00
```

Start the guest with `--discovery-port 48765 --local-auth 1`, or set
`GOLF_DISCOVERY_PORT=48765` and `GOLF_LOCAL_AUTH=1` in its environment.
The runtime maps the advertised HTTPS replay URLs to this loopback
HTTP listener so the guest sends plaintext title records.

The runtime owner verified discovery, server time, cached property,
telemetry, and login completion in the guest. Both national board-list
replies passed host replay tests. The runtime owner also verified in
the guest that a 378-byte national board request received HTTP 200
and the title login queue completed on `0198f25`.

## Individual routes

| GET request | Local response |
|---|---|
| `/nmg-us/ss.info` | `503`, or exact ciphertext bytes from a fixture given with `--ss-info-file PATH`. The fixture must contain complete eight-byte blocks. |
| `/v1/users/me/entitlements?entitlement_type=service` | Empty by default. With `--ticket-grants`, two synthetic ticket rows. |
| `/v1/users/me/container/?size=128&serviceLabel=0` | Empty storefront catalog. |
| `/v1/users/5932163534510096385/friendList?friendStatus=friend&limit=2000&presenceType=incontext` | Empty friend list for the runtime's primary synthetic account. |

Use `--catalog-fixture` to serve synthetic display-only SKUs for the
bundled product labels. The route accepts one to 32 colon-delimited
labels and the exact query `?size=128&serviceLabel=0`. Each SKU has
zero price and use count, an empty display price, and a false
`is_purchaseable` flag. The guest uses the in-process commerce hook,
so checking the storefront requires runtime integration.

The server-time probe accepts `POST /nmg-us/replay-probe/gameapi_getservertime`
with the plaintext multipart request described in the protocol notes.
Enable it with a fixed date and time.

```sh
python -B server/golf_server.py --ss-info-file work/online/ss-info-local-v4.bin --server-time 2026-11-17T23:18:42
```

The fixture supplies an HTTPS URL to the guest so it uses plaintext
title records inside the HTTP body. The runtime must map that exact URL
to this HTTP listener. The runtime owner verified that the guest accepted
the 28-byte server-time reply on `e549b2c`.

To generate the v4 fixture, use the prepared 1.17 EBOOT and an OpenSSL
libcrypto library with Blowfish support. Supply `--libcrypto PATH` if
Python cannot find the library.

```sh
python -B server/make_discovery_fixture.py work/game-1.17-prepared/eboot.elf work/online/ss-info-local-v4.bin
```

For the EULA display probe, supply a local UTF-8 text file of up to
32,767 bytes. Generate a separate discovery fixture with `--eula`.

```sh
python -B server/make_discovery_fixture.py work/game-1.17-prepared/eboot.elf work/online/ss-info-local-eula.bin --eula
python -B server/golf_server.py --ss-info-file work/online/ss-info-local-eula.bin --eula-file work/online/eula-local.txt
```

The service answers only the documented EULA fetch with that file's
text. The guest's agreement flow is unverified.

For the empty notice list probe, pass `--empty-notices` to both commands.

```sh
python -B server/make_discovery_fixture.py work/game-1.17-prepared/eboot.elf work/online/ss-info-local-notices.bin --empty-notices
python -B server/golf_server.py --ss-info-file work/online/ss-info-local-notices.bin --empty-notices
```

The probe replies with a synthetic `0x0083` string and a zero-count notice
list for selectors 0, 1, and 2 from the default login sequence.
Guest acceptance is unverified.

For the daily event score probe, generate the discovery file and one
encrypted reply block from the same prepared 1.17 EBOOT.

```sh
python -B server/make_discovery_fixture.py work/game-1.17-prepared/eboot.elf work/online/ss-info-local-scores.bin --daily-scores
python -B server/make_daily_score_block.py work/game-1.17-prepared/eboot.elf work/online/daily-score-block.bin
python -B server/golf_server.py --ss-info-file work/online/ss-info-local-scores.bin --daily-score-block work/online/daily-score-block.bin
```

The service replies to the daily `_score` query with zero rows.
The encrypted reply block contains a synthetic string. Keep generated
fixtures local. Guest acceptance is unverified.

To replay empty personal scores and leaderboards, add `--empty-own-score` to the
discovery generator and server and keep `--login-completion` in both.
Apply the score-list bridge from the mailbox. The login reply enables
the guest's personal-score queries. The service answers user status,
personal scores and account-scoped score lists. Score queries return
the title's no-record status. The existing daily `_score` probe still
works when its reply block is configured.
The runtime owner reported HTTP replies for login, user status,
the score list and own score during an Open Course hole-1 run on
`4f1b424`. The guest stopped retrying those requests.

The score session also serves an empty top-player list and daily score
distribution. Regenerate discovery and apply the two leaderboard routes
from the mailbox. [Wire formats](../analysis/online/protocol.md#top-players-and-daily-score-distribution)

The same options enable the character-assignment POST
used after login. Regenerate the discovery fixture and apply the
character-assignment runtime route from the mailbox to use it. The
listener checks the title records and replies with the local session
token. See the [wire format](../analysis/online/protocol.md#character-download-assignment).

The score session also acknowledges course-world assignment for the
primary local account. Regenerate discovery and apply the course-world
route from the mailbox. [Wire format](../analysis/online/protocol.md#course-world-assignment)

With the count route from the mailbox, the fixture also answers
character download queries for the primary local account with two zero
counts. [Wire format](../analysis/online/protocol.md#character-download-counts)

To record scores locally, use `--score-registration` in the discovery
generator and `--score-db work/online/scores.sqlite` on the listener.
These switches enable the score session and query routes. Keep the
other discovery and listener options from the combined replay and
apply the score-registration bridge from the mailbox. Both score queries
read the same SQLite row for the single synthetic account after a
listener restart. One Hole keeps the lower primary score when
submissions arrive out of order. Guest submission and readback passed
for holes 1 and 2. [Trace evidence](../analysis/online/protocol.md#score-registration-and-follow-up-queries)

For a scheduled score test, also pass `--event-schedule` to the
discovery generator and apply the event schedule bridge from the
mailbox. On the listener, add `--event-group OneHole_20180914_0_1`
when using the combined replay's September 14, 2018 server date, or
supply another group that matches the date and mode being tested.
Repeat `--event-group` to include per-hole groups and the Daily group
in the same replay. The listener serves up to 18 distinct groups per
board selector. Apply the latest schedule bridge in the mailbox for
replies with multiple rows.
The legacy board probe still works with its reply block configured.
Guest entry and completion are unverified.

With `--empty-boards` on discovery and `--empty-board-block` on the
listener, the character download board returns an empty list. Apply the
character board route from the mailbox. [Wire format](../analysis/online/protocol.md#character-download-board)

For each scheduled `Daily_YYYYMMDD_N_OUT` or `Daily_YYYYMMDD_N_IN`
group, the listener also serves an empty rival list.
The `--event-schedule` discovery option advertises the rival-list URL.
Apply the rival-list runtime route from the mailbox before testing it.
[Wire format](../analysis/online/protocol.md#daily-event-rivals)

### Local Open Course roster

After applying the Matching2 lobby bridge from the mailbox, add
`--local-lobbies` to the combined server command or to `host.py` with its
default loopback bind. Both commands require an IPv4 loopback address for
this mode. Set `GOLF_LOCAL_LOBBIES=1` for each runtime. Give each instance a separate
`--data-dir` and a distinct `GOLF_ONLINE_ID` of up to 16 ASCII letters,
digits, underscores or hyphens. Use the same `--discovery-port` and
select the same Open Course world. Abandoned membership expires after
15 seconds. The host also serves the Daily OUT schedule for Eagle City,
along with a schedule for each of its first nine holes.
Guest presence and peer gameplay are unverified.

The lobby retry patch reuses a single seat if the first join response
is lost. It was checked with two native clients and a listener that
dropped the first accepted reply. [Wire format](../analysis/online/protocol.md#loopback-lobby-membership)

The same flag enables `POST /nmg-us/local-lobby/v1/packets` for native
relay clients with a lobby or room relay token. The endpoint queues up to 64 packets
and 65,536 payload bytes per member.
A packet payload can be up to 65,535 bytes. Each exchange carries
at most 16 frames and 65,536 payload bytes. Clients can retry an upload without
duplicating delivery and acknowledge received packets in order. See the
[relay frame layout](../analysis/online/protocol.md#loopback-packet-relay).
The server tests and a two-process Windows runtime HTTP probe exercised
the relay. Guest RUDP integration is NOT_RUN.

The local `/nmg-us/local-lobby/v1/channels` route reports channel
readiness when both roster members register complementary virtual
ports. Registrations expire with either peer's roster lease. See the
[channel request and response](../analysis/online/protocol.md#loopback-channel-readiness).

The local `/nmg-us/local-lobby/v1/rooms` route uses the same leases for
room creation, search, join, leave and listing updates. The server
enforces capacity and owner permissions, and removes members when their
leases expire. The staged runtime bridge exercises create, search, list,
join and leave through scoped Matching2 imports. See the
[room contract](../analysis/online/protocol.md#loopback-room-management).

After applying the room transport patch, the runtime fetches a relay
token for its current room or lobby from `/nmg-us/local-lobby/v1/transport`.
The server rotates the token when a member joins or leaves a room. Packets
and channel registrations stay within the current room or lobby. See the
[room transport formats](../analysis/online/protocol.md#loopback-room-transport).
Two Windows AddressSanitizer clients verified bidirectional room data,
queue cleanup on departure, and delivery after rejoining. Guest room
play is NOT_RUN.

The room message patch adds local broadcast, unicast, and multicast
through `/nmg-us/local-lobby/v1/room-messages`. It uses the current room
relay token and clears queued messages when a member leaves. See the
[room message format](../analysis/online/protocol.md#local-room-message-replay).
The native Windows probe verified callbacks and rejoin. Guest delivery
is NOT_RUN.

Explicit mesh and star rooms apply the declared topology to Matching2
status, channel readiness, and packet delivery. The room owner is the
star hub. The [signaling trailer](../analysis/online/protocol.md#local-room-signaling)
records the topology and hub ID.

For the title login rejection probe, use the local account,
`--discovery-port 8765` and `--local-auth 1`.
For builds without the launcher flag, set `GOLF_LOCAL_AUTH=1`.

```sh
python -B server/make_discovery_fixture.py work/game-1.17-prepared/eboot.elf work/online/ss-info-local-login.bin --login-rejection
python -B server/golf_server.py --ss-info-file work/online/ss-info-local-login.bin --login-rejection
```

The service checks the primary local account and synthetic authorization
string before returning the game's login rejection status. Guest
acceptance is unverified.

Replace `--login-rejection` with `--login-completion` in both commands
to probe the title's completion branch. The 24-byte reply then carries
`0x2020` with value 1. This mode uses the same synthetic account and
authorization checks. The runtime owner observed login completion
on `da28e84` and the following national board-list POST.

For the national board-list request that can follow login completion,
add `--empty-national-boards` to the discovery generator and listener
commands. Use the runtime bridge from the mailbox to route this POST.
The fixture accepts login selectors 0 and 1 and entry selector 3.
It sends a 28-byte reply that takes the completion branch without
a download. Host replay passed, and runtime `0198f25` completed the
title login queue after a 378-byte board request received HTTP 200.

For one synthetic tournament, use `--national-tournament` in both
commands with the tournament runtime rows from the mailbox. Set
`--server-time 2018-09-14T12:00:00` on the listener. Selectors 0
and 3 download one board row, and the game-data POST supplies the
archive path. Selector 1 returns the empty reply. Create a cache
folder in the test profile and pass `--mount /download0=<folder>`
to the guest launcher. The guest cached the archive and enabled
the menu. The join route supplies the synthetic event's first-entry
reply. To enable score registration, add `--score-registration` to
discovery and `--score-db PATH` to the listener. The best primary
score and its secondary score persist by event date. Own score,
score list, and distribution replay that saved score. The listener
passed loopback replay. Guest tournament entry is NOT_RUN.
[Wire format](../analysis/online/protocol.md#local-national-tournament)

#### Collab cups

`--collab-cups classic` or `--collab-cups hardcore` (with
`--national-tournament`, `--server-time` and `--score-db`) runs the 2018
tie-in cups as the International Tournament, one after the other: the
FINAL FANTASY 30th Anniversary Cup, LEVEL-5 20th Anniversary Cups 1 and 2,
and the Famitsu Collab Cup. `--collab-cup KEY` runs one cup only.
`host.py` takes the same options; the launcher passes `--collab-cups`
when settings.ini has `collab_items=classic` or `hardcore`. The catalog
is `collab_cups.py`:

| Cup | Number, group | Qualifier | Final |
|---|---|---|---|
| ff30 | 4, `FF30CollabCup` | 41: Vortex Valley, row 1013; Cactuar outer 8953 and caps (set 8962) | 42: row 1034 (champion tees, strong wind); Moogle 8958 |
| level5-1 | 5, `Level5Collab1` | 51: Alpina Forest, row 1014; set 9000 | 52: set 9001 |
| level5-2 | 6, `Level5Collab2` | 61: Kanaloa Beach, row 1014; set 9002 | 62: Jibanyan 8984, Komasan 8985 |
| famitsu | 7, `FamitsuCollab` | 71: Eagle City, row 1014; set 9128 | 72: Akigase Keikoku (course 10); 3,000 coins (item 5716 by `score_reward`) |

Only the FF30 course and rules are from 2018 records; the others are
picks, and the numbers, groups and event ids are this server's own. The
Famitsu final's ranger suits have no textures, so it pays coins. Row 1014 shows as Regular Tee, Normal Cup,
Mirror off. The Notices box names each cup "EG Cup No." and its number
(the server sends `tournamentId` = number - 1; the game adds 1).

| Option | Meaning |
|---|---|
| `--cup-cut N` | Qualifier pass line in strokes against par. Default +3 (classic), -3 (hardcore). |
| `--cup-holes N` | Test rounds of N holes (3 or more). |
| `--cup-course N` | Another course (1 Eagle City ... 5 Imperial Garden). |

Hardcore also puts every final on row 1034 and allows 3 rounds per
stage per day: `resetThreshold` is 3, and `gameapi_noticejoinnational`
answers with the rounds this player started today in that stage (real
date), this one included. The entry screen compares the two (0xc4b8f3).
In both modes the game itself charges an S Ticket for a second round of
a stage (seen in game; `limitation_reentry` 1 makes it "Limited to 1
entry" instead), so Hardcore's limit only applies to S Ticket retries.

How the server runs the cups:

- Board selector 1 fills the game's single current entry. The game
  copies every selector-1 row of the same group over that entry, so the
  last row wins, whatever the windows say. The server sends only the
  current stage for selector 1 and both stages for selectors 0 and 3.
  The board download follows the selector of the last board POST.
- The schedule follows the player, not the calendar. The clock the
  server sends (at login and after each round) is the `--server-time`
  day plus a cup day counter, at 12:00. Every registered cup round adds
  a day. The current stage's window is the three days ending on the
  clock's day. After a round the game saves a result record with the
  window's last day, and Notices lists it once the clock is past that
  day, which is the clock the game gets right after the round.
- Opening a result notice grants the `reg_reward_*` items (and
  `score_reward`) of the current entry whose event id matches the
  record. So a stage stays current until its notice is opened: the
  qualifier until it is opened with the cut made, then the final until
  its notice is opened, then the next cup (back to the first after the
  last). The Notices box sends `gameapi_getbonuslist` when it opens, then
  `gameapi_getmyscorenational` when a result notice is opened; the
  tournament and entry screens send that request after a board request.
  The server counts an own-score request after the bonus list, with the
  stage's notice due, as opened, and applies it at the next board or
  time request. Everything happens in one sitting.
- Scores are kept per stage and per pass through the list (groups
  `Cup5_51`, then `Cup5_51_r1`, ...). The counters (cup day, finished
  cups, opened qualifier notice, each stage's last round day) are rows
  of the score database with player `-`. A cup on a shared server
  follows one player's progress.
- Own score sends `0x42d1` = 1 when the qualifier score is at or under
  the cut. The game reads that flag to open the final's entry screen.
- The notice list (selector 0) holds one `<nid>N</nid>` item per played
  stage of the current cup, dated 00:0N of the day after its last round
  (the game hides notices dated after its clock and remembers opened
  ones by date). The game shows it as a tournament introduction; it
  carries no prize.
- Opening Notices first requests `gameapi_getbonuslist`. Host fixtures
  v2 answer it with an empty list (`empty_bonus_list`).

The runtime must accept a notice reply and board download larger than
the fixed probes (tourney branch, `src/runtime_net.c`).

For the empty board-list probe, generate discovery with `--empty-boards`
and give the server `--empty-board-block PATH`. Use the same encrypted
block as the daily score probe. The reply has zero rows.

With both runtime routes from the mailbox applied, the same options
enable the empty finish-board and sign-board lists.
[Finish-board format](../analysis/online/protocol.md#finish-board-list)
· [Sign-board format](../analysis/online/protocol.md#sign-board-list-and-download)

For an empty event-regulation reply, set `--empty-regulations` on
the discovery generator and listener. Give the listener the daily
score fixture with `--daily-score-block PATH`. The runtime route in
the mailbox forwards both the current-day and dated calendar POSTs.
Both shapes passed loopback replay. Guest acceptance is NOT_RUN.
[Event regulation format](../analysis/online/protocol.md#event-regulations)

To advertise the property and telemetry routes, pass `--cached-property`
and `--discard-telemetry` to the generator and listener.

| Route | Local behavior |
|---|---|
| Property | Accepts a 118-byte multipart request for index 1 and returns a 24-byte reply that keeps the cached version. |
| Telemetry | Accepts the title's fixed telemetry URL, discards JSON bodies up to 8,192 bytes, and returns an empty HTTP 200 response. |

The runtime owner observed both replies in the guest on `648d038`
(05:35 mailbox entry). The property check completed without a retry or
download.

The generator flags can be combined. If using a port other than 8765,
set `GOLF_DISCOVERY_PORT` or launcher option `--discovery-port` to the
listener's port. The guest URLs in the fixture use the fixed authority
`127.0.0.1:8765`, which the bridge translates to the configured port.

To probe ticket consumption, start the server with `--ticket-grants`.

```sh
python -B server/golf_server.py --ticket-grants
```

The opt-in fixture serves one ticket under `EN0001` and ten under
`EN0002`. A matching PUT consumes that grant once per server process.
Repeating the PUT returns HTTP 409. Guest verification requires the
runtime to route its entitlement WebAPI calls to the local service.
The runtime owner verified the equivalent in-process fixture on `d91027d`
by consuming both grants and checking the balance after a reboot.

[Protocol](../analysis/online/protocol.md)
