# What queues gameapi_registscore* (slots 0x1a, 0x1c, 0x1e)

Static read of `work/analysis-cache/eboot.dis` (guest addresses) plus `work/evidence/open-course-holes1-2-1118.log`.
No runtime trace. Anything not read is UNVERIFIED. Corrects `scorelist-account-variant.md` section 4 on the flag byte (see 2).

## 1. Queue structure

- `0xa62080(queue=[0x2c82548], req)` is the only enqueue entry (44 call sites). Request `+0x18` is the mode.
  It calls `0xa633d0(queue, mode)` (`0xa632b0`), which builds a list of task states for that mode: a jump table at
  `0x11c8958` (modes 2..0x22), nodes pushed back, first node is state 0. `0xa632f0` pops the front and returns the next state.
- The task runner is `0xa60120(item, state)`. Its jump table `0x11c87a0` is indexed by task state. Task state to net slot:

  | task state | slot | request | handler |
  |---|---|---|---|
  | 0x09 / 0x0d / 0x11 | 0x19 / 0x1b / 0x1d | getscorelist OneHole / Daily / LongDrive | `0xa6097d`, `0xa60a18`, `0xa60b36` |
  | 0x0a / 0x0e / 0x12 | 0x1a / 0x1c / 0x1e | registscore / daily / longdrive | `0xa609ee`, `0xa60aef`, `0xa60b9f` |
  | 0x18 / 0x19 / 0x1a | 0x23 / 0x24 / 0x25 | getmyscore (3 boards) | `0xa60e1c`, `0xa60e99`, `0xa60f13` |
  | 0x15 | 0x20 | board-list prelude (`0xa60d31`, `0xa6062f`; `title-dispatch.tsv` line for 0x20) | |

- The register handlers copy `item+0x28..0x37` (and `+0x38/+0x3c` for LongDrive) into ctx `+0x122390..`, call `0xb501c0`.
  They have NO flag or reply gate. The byte `[[0x2c6b648]+0x1f1d80f]` (login record `0x2032`) gates only the getmyscore
  states 0x17..0x1a (`0xa60d92`, `0xa60e23`, `0xa60ea0`, `0xa60f1a`: zero jumps to `0xa61c2d` = skip to next state).
  `scorelist-account-variant.md` cited `0xa60e23` as the registration gate; that is state 0x18 (getmyscore), not registration.

## 2. Modes that contain a register state (list order, from `0xa633d0`, walked block by block)

| mode | list (after state 0) | meaning |
|---|---|---|
| 4 | 0x15, **0x0a**, 0x09, 0x18 | OneHole: prelude, REGISTER, list, getmyscore |
| 9 | 0x15, **0x0e**, 0x0d, 0x19 | Daily: prelude, REGISTER, list, getmyscore |
| 0xd | 0x15, **0x12**, 0x11, 0x1a | LongDrive: prelude, REGISTER, list, getmyscore |
| 2, 8, 0xc | 0x18,0x09 / 0x0d,0x19 / 0x11 | board refresh only, no register |
| 0xa | 0x15,0x18,0x1a,0x11,0x09,0x19,0x0d,0x17 | all three boards, no register |

The 4/9/0xd masks match the `0x14020229` test in the handlers (modes 4, 7, 9, 13, 21, 30, 32), which only picks the date source.

## 3. Who builds the register modes

- Mode 4: only `0xd91790` (`movl $0x4,-0xef0(%rbp)` at `0xd91939`, enqueue `0xd91964`). Callers: `0xd83a1b`, `0xd8d13e`,
  both in the result-screen state machine (state word `0x27c(obj)`, they set it to 0xb and byte `0x28c` to 1).
- Mode 9: only `0xd837df` (`movl $0x9,0x138(%rsp)` at `0xd837d4`), same state machine.
- Mode 0xd: no builder found (UNVERIFIED; no `$0xd` mode store before any of the 44 call sites).
- Game type word is `[[0x2c9a068]+0x2ec48]`. `0xdcc4a0` rewrites it: type 0x14 becomes 0x16 (`0xdcc4f7`), type 6 becomes 8
  (`0xdcc4eb`), original kept at `+0x2ec8c`. So 0x16 and 8 look like the online variants of 0x14 and 6 (inference, UNVERIFIED).

## 4. Conditions

Result-screen entry to the mode-4 call (`0xd82900-0xd83a1b`, `0xd8d049-0xd8d13e`):
1. Type in {6,7,8,0x14,0x15,0x16} (mask `0x1c007`, `0xd82901`) or 0x19 or 0x17.
2. Type not in 2..4 (`0xd82920`/`0xd8d075`), then state 0xb and `0xd91790` is called. At `0xd8d114`, flag `bl` selects state 0xa instead
   (no request): `bl` = online-capable byte found in `[0x2c6b648]+0x5df9..+0x5ff8` and `0xdcdae0(...)` true and type not in {2,8,0xb,0x12,0x17,0x19}
   (`0xd8cfe5-0xd8d047`). Meaning of state 0xa vs 0xb is UNVERIFIED (0xa may be the player "submit" prompt).
3. Inside `0xd91790` (`0xd917b5-0xd919b6`): continues only for type 0x13..0x16 (types 0x17 and 0x19 pass the first test then fail
   `sete/setne` at `0xd917e5-0xd917f3`; every other type, including 8, returns `0xd92f07` with no request). Also returns if
   `[[0x2c9c328]+0x90]+0x10 != 0` (already busy, `0xd919b0`), and `testb $4,0x2ec8a` set skips.
4. Mode 9 (`0xd835fd-0xd83654`): type must equal exactly 0x16, `testb $4,0x2ec8a` clear, queue exists, and
   `(signed char)[G+0x2eb0b] <= *(int*)(player+0x3b4)` (`0xd83654-0xd83664`; likely "holes played reached round length", UNVERIFIED).

## 5. Answers

1. Registration is queued by the result-screen state machine, not by getscorelist/getmyscore. Mode 4 (OneHole register) comes from the
   per-play result path (`0xd8d13e`, `0xd83a1b`), mode 9 (Daily register) only when the played-hole counter condition in 4 is met. Neither
   checks a "submit" pick before queueing; a prompt state (0xa) is an alternative branch (UNVERIFIED which UI maps to it). LongDrive: no builder found.
2. No. The send path reads nothing from the getscorelist/getmyscore replies. Order inside the task list is register first, then list, then
   getmyscore (section 2), so the replies cannot gate it. Status 0x90000310 only ends those actions (`0xb6d226`).
3. Gates are game type `[[0x2c9a068]+0x2ec48]` (0x13..0x16 for mode 4, 0x16 for mode 9), byte `0x2ec8a` bit 2, in-flight word
   `[[0x2c9c328]+0x90]+0x10`, and the online flag array near `[0x2c6b648]+0x5df9`. Reply fields read: none for queueing.

## 6. Observed log versus this

Each hole shows list then getmyscore x3 (n=29/31/33, then 40/42, then 48/50) and no register. The tail "list, getmyscore" of modes 4/9/0xd
matches that shape, but those lists put the register state first, so the producer is UNVERIFIED (mode 8 = Daily list + getmyscore at
`0xd8d611` fits one pair; modes 2/0xa have a different order). Simplest explanation: the Open Course round type (UNVERIFIED, likely 8 or 0x16)
never satisfies 4(3), so `0xd91790` returns without a request.

## 7. Next check (needs a runtime read, not done)

At the scorecard, read `[[0x2c9a068]+0x2ec48]`, `+0x2ec8c`, `+0x2ec8a`, and `[[0x2c9c328]+0x90]+0x10`. Type 0x16 with 0x2ec8a bit 2 clear
should queue mode 4 at hole end; type 8 cannot. If the type is 8, 9 Hole Round submission lives in a path not found here.

## 8. Runtime read (2026-11-18, runtime `4f1b424`, GOLF_PEEK)

Open Course 9 Hole Round, read every 250 ms:
- `[[0x2c9a068]+0x2ec48]`: 0x14 on the island, 0x16 once the Open Course round starts. `+0x2ec8c` = 0x14 (original type), so
  `0xdcc4a0` rewrote 0x14 to 0x16 as predicted.
- `+0x2ec8a` = 0: bit 2 clear.
- `[[0x2c9c328]+0x90]+0x10`: 0 before hole end, then 1, 2, 0 as the hole-end list and getmyscore run.

So the type, flag and in-flight gates all pass, and the branch that skips registration is `bl` at `0xd8d114`. For type 0x16,
`0xd8d029` gives 0x14 (outside the 0x10 bit range), and `0xd8d03b-0xd8d047` sets `bl` = (type==0x17) xor (type!=0x19) = 1 whenever
the online byte in `[0x2c6b648]+0x5df9..` is 1 and `0xdcdae0` returns true. `bl`=1 stores state 0xa (`0xd8d118`) and skips
`0xd91790`. Online rounds therefore take state 0xa; what state 0xa sends is the open question. The peek did not read the online
byte or `0xdcdae0`, so `bl`=1 is inferred from the missing request, not read.

## 9. State 0xa (static)

Static read of `eboot.dis` plus the jump tables in `work/game-1.17-prepared/eboot.elf` (file offset = guest address + 0x4000). Not run. Inferences are marked UNVERIFIED.

### 9.1 Dispatch

- `0x27c(obj)` is not the dispatch word. It is the REQUESTED next state. `0x278(obj)` is the CURRENT state. Commit at `0xd75f84` (`movl %eax,0x278(%r12)`): it copies `0x27c` to `0x278`, then jumps through the entry-action table `0x11d0194` (index = state-1, 16 entries). Entry for 0xa is `0xd7620e`: calls `0xe9ee50(obj+0, 0x1e, 0, 0)` (a UI/sound message, meaning UNVERIFIED), then at `0xd76292` zeroes sub-state `0x280`, `0x284`, `0x288`.
- Per-frame handler: the function containing `0xd81182` (`movl 0x278(%r13)`, `cmpq $0x10`, jump table `0x11d01d4`, one entry per state 0..0x10). State 0xa = `0xd821fd`, state 0xb = `0xd82238`, state 0xc = `0xd82285`. States 13 and 15 go straight to the end (`0xd8e560`). Sub-state is `0x280(obj)`.
- `0xd8d118` and `0xd89d1e` are inside this same function. `0xd89d1e` is a shared tail that sets byte `0x28c`=1. `0xd8d118` only stores `0x27c=0xa`; it calls nothing.

### 9.2 What state 0xa does

State 0xa is state 0xb's decision with a wait in front. It does not end in UI only.
1. Sub 0 (`0xd82202-0xd82233`): read `P=[0x2c77128]`. If P is null, or `((P+0x8c) | 2) == 2` (so `P+0x8c` is 0 or 2), set sub=1 (`0xd82271`). Otherwise wait this frame.
   P is a singleton built at `0xdbaeb8`, init `+0x8c=0`. The only store of 1 to `+0x8c` that I found is `0xd69d9a` (a UI function that also walks the per-slot byte array of 9.5, `0xd69dd7`). Reading it as a post-round player prompt or dialog is UNVERIFIED.
2. Sub 1 (`0xd828d7`): read `Q=[0x2c74698]`. If `Q` and `[Q+0x70]` are non-null and `*([[Q+0x70]+0x30]+0x160) == 0`, go to `0xd863e5`: stay while `[Q+4] > 0`, else fall into the next step. Then `0xd828fd`: type in {6,7,8,0x14,0x15,0x16} or 0x17/0x19, and type-2 >= 3 (`0xd82920`) jumps to `0xd83a05`, which stores `0x27c=0xb`, `0x28c=1` and CALLS `0xd91790` (`0xd83a1b`), the mode-4 registration builder. Types 2..4 and all others fall to `0xd8292a` (state 0xc, no request).
3. So for type 0x16 the bl=1 branch at `0xd8d118` does NOT drop registration. It defers it: state 0xa, then (after P and Q clear) the same `0xd91790` call as the bl=0 branch. This is the second caller `0xd83a1b` named in section 3.

### 9.3 Gates between state 0xa and a registscore request (type 0x16, online round)

In order, with what each reads:
1. `0xd8cfd7`, `0xd8cfe5-0xd8d047`: online byte array hit (9.5), `0xdcdae0` true (9.5), type not in {2,8,0xb,0x12,0x17,0x19}. All true gives bl=1, state 0xa. Both outcomes lead to `0xd91790` for 0x16.
2. State 0xa sub 0: `[0x2c77128]` null or `+0x8c` in {0,2} (`0xd82219-0xd82231`).
3. State 0xa sub 1: `[0x2c74698]` chain, `+4 <= 0` while `*(...+0x160)` is 0 (`0xd828d7-0xd828f7`, `0xd863e5`).
4. `0xd91790` internal gates from section 4(3): type 0x13..0x16, `[[0x2c9c328]+0x90]+0x10 == 0`, `0x2ec8a` bit 2 clear. Section 8 read these as passing.
5. State 0xb sub 1 for type 0x16 (jump table `0x11d02bc`, index type-7: types 8 and 0x16 go to `0xd835d2`): mode 9 (Daily) builder. Gates `0xd835d2-0xd83664`: `[0x2c74698]` chain as above (`+0x160==0` jumps to `0xd880b1`), type 0x16, `0x2ec8a` bit 2 clear, queue `[0x2c82548]` non-null, and `(signed char)[G+0x2eb0b] <= *(int*)(obj+0x3b4)` where `G=[0x2c9a068]` and obj is the state object (`r12`, saved at `0x8(%rsp)`). Else `0xd9047f` (state 0xc). The meanings of `G+0x2eb0b` and `obj+0x3b4` are UNVERIFIED (likely round length versus holes played, so only after the last hole). This is the only path I found that can queue mode 9 for 0x16.
6. Task list order for mode 4 is prelude 0x15, register 0x0a, list 0x09, getmyscore 0x18 (section 2). The register handler `0xa609ee` fills ctx `+0x122390..` and calls `0xb501c0(ctx, 0x1a)` (`0xa607bd`). If it returns 0, the task state machine goes to task state 0x33 (`0xa607c2`; what 0x33 does is UNVERIFIED, probably an error end) and no request is sent.
7. Inside `0xb501c0`, slot 0x1a is `0xb536b0` (table `0x11cd83c`). It reads the server-time object `[0x2c8f2e0]+0x170/0x172/0x174` (year, month, day, via `0xb59dde`/`0xb59d88`), then at `0xb59eb8-0xb59f1b` walks the schedule vector at ctx `+0x122560` (begin `+0x122560`, end `+0x122568`, row stride `0x258`) comparing the row's first five bytes: `[0]` = year low byte + 0x20 (year-2016), `[1]` = month, `[2]` = day, `[3]` = ctx `+0x122390` (item `+0x28`), `[4]` = ctx `+0x122394` (item `+0x2c`). A match goes to `0xb5ac13` and calls the request builder `0xb638a0(ctx, ..., row+0x98, ...)`; the row layout beyond the five bytes is UNVERIFIED. Slot 0x1c (Daily) walks `+0x122580` at `0xb5a04f` and slot 0x1e (LongDrive) walks `+0x1225a0`. The vector comes from gameapi_getboardlist (peer note `docs/MAILBOX.md` 2026-11-18 16:19 and `analysis/online/protocol.md#event-schedule-board`; not redone here).

### 9.4 Empty schedule

State 0xa's path does reach the comparison (item 7), through `0xd91790` -> mode 4 -> task 0x0a -> slot 0x1a. An empty vector (begin == end, `cmpq %rbx,%rsi; je 0xb5a6f3` at `0xb59ec6`) or no row matching (date, ctx+0x122390, ctx+0x122394) falls to `0xb5a6f3`: store 0 to ctx `+0x5f270`, return 0 from `0xb501c0`. No packet is built. This is the one gate in the chain that fails silently on an empty schedule, and it fits "no registscore sent while list/getmyscore still run". Whether the schedule was empty at run time is UNVERIFIED (not read).

### 9.5 `0xdcdae0` and the byte array

- `0xdcdae0(G, flag)` is an eligibility test, not a send. It returns 0 if any of: type in {0xf, 0x11, 0x12, 0x19} (mask `0x40d` over type-0xf); byte `G+0x2ec89` nonzero; `0xdcb600(G+0x2ebd0, type in 2..4)` false; byte `+0xebc` of the object from `0xdcd840()` nonzero; with flag set, byte `+0xec0` nonzero or `(signed char)G+0x2eb09 < 9`. Otherwise true for types in mask `0x4a50d` (over type-1) and `0x1c007` (over type-6, includes 0x16); the tail also special-cases 0x17/0x19 and `(type|1)==0x1b`. Callers pass flag 0 at `0xd8d013` and `0xd870ea`.
- `[0x2c6b648]+0x5df9 .. +0x5ff8` is 0x200 bytes indexed by player slot (loop to `0x1ff`, `0xd8cfee`). Values seen: 1 (set at `0xd871aa` for each entry of the player vector `[0x2c836b8]+0x178` for which `0xaf9970(player)` returns true; consumed at `0xd69dd7`), 2 and 3 (`0x4a0757`, `0x4a0780`, `0x4a062c`). Meaning UNVERIFIED; reads as a per-slot "online/ranking-eligible" state. Any slot at 1 makes the `0xd8cfee` loop hit, so bl depends on whether ANY local player slot is flagged.
- `0xd8cfd7` (`cmpq $0,[0x2c83698]; jne 0xd870e1`): if object `0x2c83698` is non-null, take the longer route `0xd870e1` first (call `0xdcdae0`, type masks, then the loop at `0xd8712e-0xd871c8` that sets byte[slot]=1 from `[0x2c836b8]`), else go straight to `0xd8cfe5`. What `0x2c83698` is stays UNVERIFIED (33 uses; the sibling `0x2c836b8` holds the player-object vector, so likely an online/session or player manager). `0xd870d3` is the mirror test (`je 0xd8cfe5`).

### 9.6 Answer and runtime reads

Online score registration exists in this path (mode 4 via `0xd91790`, mode 9 for type 0x16). State 0xa is a wait, then `0xd83a05` calls `0xd91790` like the bl=0 branch. A missing request means one of: (a) state 0xa never advances (P `+0x8c` stuck at 1, or Q `+4 > 0`), (b) `0xd91790` returns early (section 8 says its inputs pass), (c) the `0xb59eb8` schedule compare fails and `0xb501c0` returns 0. (a) and (c) are open.

GOLF_PEEK targets: result object `+0x27c` and `+0x278` (stuck at 0xa, or moving to 0xb/0xc); `[0x2c77128]` and its `+0x8c`; `[0x2c74698]` and `+0x4`; ctx `[0x2c8f2e0]+0x10378` fields `+0x122560/+0x122568` (schedule begin/end, equal means empty), `+0x5f270`, `+0x121a80` (last slot requested), `+0x122390/+0x122394`; date `[0x2c8f2e0]+0x170/0x172/0x174`; `[0x2c6b648]+0x5df9` for the first few slots.

## 10. Schedule load trigger (static)

Static only, same table method as section 9. Inferences are marked UNVERIFIED.

### 10.1 Who queues slot 0x20 and slot 0x16

- `0xb501c0(ctx, slot)` has only six callers: `0xa606c1`, `0xa60742`, `0xa607bd` (the task runner `0xa60120`) and three retry sites `0xb65679`, `0xb658cd`, `0xb659bf` that re-send `ctx+0x121a80` (the last slot). So a first send of any slot comes only from the task runner.
- Slot 0x20 is sent in exactly one place: task state 0x15 (handler `0xa60d31`, tail `0xa6062f`, `movl $0x20,%esi` at `0xa60651`, `callq 0xb501c0` at `0xa606c1`). There is no timer, menu or login hook that sends it on its own. It is the first task of the net action ("mode") lists, so it goes out when such a mode starts.
- Mode 4 (OneHole register) is one of them: list 0x15, 0x0a, 0x09, 0x18 (section 2). For mode 4 the dispatch table `0x11c8874` index 0 gives `0xa60621` (selector `esi=0`, `eax=1`, `r13=0` so `ebx=1`), so ctx `+0x122390 = item+0x28`, `+0x122394 = 0`, `+0x122398 = 0` (selector), `+0x12239c = 1`. Selector 0 is not negative, so case `0xb53b78` does not take the `js 0xb55d77` skip and a request WOULD be built. Modes 9 and 0xd and 0xa also begin with 0x15. Modes 2, 8 and 0xc do not.
- Other UI-driven enqueues whose lists start with 0x15 (by mode number, list contents not decoded for all, UNVERIFIED): mode 0xe (callers `0x34b20d`, `0x6c695e`, `0x6f5081`; fields: course-like value, `9+9*x`, limit 0x64), mode 0x13 (`0x6f3f30`, `0x700f70`), and modes 0x15, 0x16, 0x21 (selector 5, character download board, `protocol.md` "Character download board"). The enclosing UI functions are `0x6c66a0`, `0x6f3cb0`, `0x6f4dc0` (ranking/board screens; which menu is UNVERIFIED).
- Slot 0x16 (`0xb5305e`, 138 to 230 byte request) is NOT sent by the task runner (no `$0x16` immediate in `0xa60120-0xa62080`, no other `0xb501c0` caller passes it). I found no static queuer. The reply-side function `0xa5d3a0` has a case at `0xa5e6cc` with `r14d=0x16`, but that is the task state of slot 0x21 (`0xa60d6e`), where it caches today's date at `[0x2c6b648]+0x1f1d67b..d` (UNVERIFIED). Treat slot 0x16 as unreachable from the title net queue in this build, so a fixture for it cannot be what the guest is waiting on.
- At hole end the game queued mode 8 at `0xd8d61c` (`movl $8,0x138(%rsp)`, limit `0xc8`, date from `[0x2c8f2e0]+0x170/172/174`), whose list has no 0x15 (section 2). That fits the logged "list, getmyscore" without a board list. The mode-4 call `0xd91790` (`0xd83a1b`/`0xd8d13e`) is a different enqueue. UNVERIFIED which of the two ran: no `0xa62080` call was traced at runtime.

### 10.2 Gates before slot 0x20

In order for the mode-4 route (all static):
1. Reach `0xd91790`: bl=1 gives state 0xa (section 9.2), whose sub 0 and sub 1 wait on `[0x2c77128]+0x8c` and `[0x2c74698]+4`. These are UI/object states, not server replies.
2. `0xd91790`: type 0x13..0x16, `[[0x2c9c328]+0x90]+0x10 == 0`, `0x2ec8a` bit 2 clear (section 4(3)).
3. `0xa62080` entry (`0xa620a8-0xa620e6`): reads `[0x2c6b648]+0x1f1bab0`; if `<= 2` it zeroes `+0x1f1d368` and stores 3 (a state fix-up, not a refusal). Then `cmpl $3,[0x2c8f358]` and `cmpl $2,[0x2c8f354]`: if BOTH match it calls `0xb979d0` and returns -1 with nothing queued (meaning UNVERIFIED, reads as a net-unavailable or offline state pair; `0xa5b030`, `0xa5b179`, `0xa61cd3` test the same words). Else it queues. If the queue state `(%r15)==0` the first task starts at once (`0xa624ae`), otherwise it waits behind the running action.
4. Task start `0xa60120` reaches state 0x15 first; no login or reply gate sits on 0x15 (the login-record byte `[0x2c6b648]+0x1f1d80f` gates only states 0x17..0x1a, section 1).
5. Inside slot 0x20 (`0xb53b78`): a negative selector skips to `0xb55d77`, else builds. Needs the title/language records and padded `0x0083` token (`protocol.md`). Server time is read from `[0x2c8f2e0]+0x170..` (cached via `+0x85cbf8` or `0x10fd370/0x10fd0c0` time calls); no reply from getinfolist or getuserstatus is read on this path in what I traced.

So I found nothing that a local reply (getinfolist, getuserstatus, property) can fail BEFORE slot 0x20. The missing request means the mode-4 enqueue was not reached (items 1 to 3), not that slot 0x20 was gated. The vector stays empty because the fetch is the first step of mode 4, not a separate load: the compare in 9.3 item 7 runs only after that fetch's reply fills `+0x122560`.

### 10.3 Shortest route

- Mode 4 route (online round): finish a hole in the Open Course round so the result state machine runs (section 9). It needs state 0xa to clear: `[0x2c77128]+0x8c` in {0,2} and `[0x2c74698]+4 <= 0`. A prompt or dialog that stays open at the scorecard would hold it (UNVERIFIED). Confirm by peeking `0x278/0x27c` while on the scorecard, before any pad input.
- UI route (UNVERIFIED which menu): a ranking or board screen that enqueues mode 0xe or 0x13 (`0x6c66a0`, `0x6f3cb0`, `0x6f4dc0`) sends slot 0x20 as its first task. The route to it is the course ranking or leaderboard entry on the island or in the Open Course lobby; I could not name the menu from code alone. A runtime breakpoint or GOLF_PEEK on `0xa62080` (log the mode at `[rsi+0x18]`, return address) will name the screen and the first caller in one run.
- Extra peeks for this section: `[0x2c8f358]` and `[0x2c8f354]` (refusal pair), queue state `[[0x2c82548]]` (`(%r15)` at `0xa62125`), `[0x2c6b648]+0x1f1bab0`.

## 11. International Tournament gate (static, partly open)

Same method. This section answers less than asked: I did NOT find the island Online submenu builder or the greyed-out test. What I did find is below, with the dead ends so the next pass skips them.

### 11.1 Correction to sections 9 and 10

Runtime says `0xd8d118`, `0xd8d128`, `0xd821fd` and `0xd91790` never ran in Open Course free play. So the result-screen machine's mode-4 path is not what free play uses, and sections 9.2 to 9.4 describe a path this mode does not take (the static reading of those addresses stands, the claim that it explains the missing register does not). The hole-end pair came from caller `0xa5d4c2`, which is the call at `0xa5d4bd` inside the reply-completion function `0xa5d3a0` (switch on reply id `esi-0x8a`, table `0x11c8460`). At `0xa5d4ad` it stores mode `0x12` (`movl $0x12,0x1b0(%rsp)`) and enqueues. So the hole-end enqueue is a reply-driven follow-up of mode `0x12` (list and getmyscore, no register state seen), not a UI call (UNVERIFIED: that the runtime `rdx 8` call is this site; its `rsi 0x13f7258` is not a stack address, so my reading of the arguments may be off by one layer). The other runtime callers: `0xdbc360` is the call at `0xdbc35b` (stores `$0x12` or `$0x1` into `0x158(%rsp)`), `0xa5a711` is the call at `0xa5a70c` (stores `$0x1` into `0x38(%rsp)`).

### 11.2 Submenu builder and the disabled test (open)

- No item text is in the eboot (checked: "Turf War", "International Tournament", "Open Course", "Hole Round", "Game Room", "Tournament" as UTF-8 and UTF-16 in `eboot.elf`). The text is in the packed `xbdata/**/message_text.US_01.xb`, which has no plain strings either, so I could not go from the screenshot text to a message id and then to code.
- Name leads in the eboot (all addresses are string addresses): layouts `online_menu/real_entry/entry.xb` (`0x1206082`) and `real_tournament_check`, `real_tournament_list`, `real_tournament_detail/tournament_info.xb` (`0x120327e`); classes `FightingRoomEntryLayouterReal` (`0x12356f0` family, `0x1211d5c`), `Online::TimeToTournament` (`0x122e8f0`; its name getter is `0x75ff40`, so the widget code sits near `0x75ff00`), `OpenCourseRanking` (`0x122e740`), and the debug sequence list at `0x11db480` ("Tournament(0-)", "OnlineTournamentInfo", "OnlineMenu"). `online_menu/online_command` layouts (`0x11f8bff`, ctor near `0x757fd0` and `0x758550`) look like the in-lobby command bar, not the island menu (UNVERIFIED).
- Nothing in `0x74d000-0x760000` or the three string xrefs I opened (`0xa443d0`, a debug TournamentInfo object; `0x117e70`, a rule-list parser for the `Mode_Everybody`, `Mode_FightRoom`, `Mode_International` flag bits 3 to 5 of a 16-bit field) is an enable test.
- The only code tied to tournament DATA is the manager at `0xa4d890-0xa4fd30` (name getter `0xa4da40` returns "NationalTournamentDataManager"). Singleton `[0x2c81150]` (UNVERIFIED that this is the same object as the queue hosting it). State word `+0x11dc`: tick `0xa4d890`; `0xa4dd60` returns if state != 0, if its request list `+0x11f0/+0x11f8` is empty, or if `[0x2cea1c0]+0x24ec == 0x3c`. If `[[0x2cea1c0]+0x181b0] != 0` or byte `[[0x2cea1c0]+0x181a8] != 0` it takes the local path `0xa4fd30`; otherwise it sets state 4 and starts a job named "tournament Manager" (`0xea6c90`, entry `0xa4ffe0`, stack `0x4000`). The big worker `0xa4de30-0xa4fd30` opens `data/sponsor/param/International_Tournament_settings.txt` (`0xa4e1be`, loader `0xf3caf0`) and `.../International_Tournament_messages.txt` (`0xa4f797`) and builds `tournamentName_%s` keyed by the language index `[0x13641c0]`. If the settings open fails it takes `0xa4e34a`.
- That file is not shipped: no `sponsor` directory under `xbdata`, and the archive name hashes (`31*h+byte` over the lowercased path, same method as `entitlements.md`, tried for the full path and two shorter forms, upper and lower case) match no `.xb` header in `base-orbis` or `game-1.17`. The one hash hit for the messages path was a false positive in `course10/hole_out.xb` data. So the settings are probably not local data: either another store or server-provided (UNVERIFIED, hash scheme might differ). If server-provided, the International Tournament item stays disabled until that file exists, which is independent of the event schedule vector.
- Which of the `0x181a8`, `0x181b0`, settings-file presence, schedule vector `+0x122560`, server time or a login reply field the menu tests is UNVERIFIED. The vector is read only by net code (`0xb59eb8`, `0xb66e22`, parsers `0xb75xxx`, reset `0xb9c740`/`0xb9df20`), never by a menu function I found, so I rate the schedule vector as an unlikely direct menu gate.

### 11.3 Slot 0x20 for a tournament (partly answered)

- The vectors at ctx `+0x122560` are indexed by selector (`ctx+0x1224c0`, stride `0x20`): selector 0 `+0x122560`, 1 `+0x122580`, 2 `+0x1225a0`, then `+0x1225c0` and on (reset loops `0xb9c7f0`, `0xb9dfc0`). The registration compare in slot 0x1a, 0x1c and 0x1e reads vectors 0, 1 and 2.
- Task state 0x15 maps mode to selector through three tables read at `0xa60d4a-0xa60d66` for modes `0xe..0x13` only: `0x1232ae0` = {0,0,0,3,0,0}, `0x1232b00` = {6,0,0,0x1e,0,6}, `0x1232b20` = {1,-1,-1,1,-1,1}. Mode `0x11` (idx 3) is the odd one (value 3, 0x1e, selector 1). Modes 4 to `0x21` otherwise use the jump table `0x11c8874` (selector 5 for modes `0x15`, `0x16`, `0x21`: character download board).
- Mode lists come from small `.rodata` tables or inline pushes in `0xa633d0` (table `0x11c8958`); for example mode 3 is `{0x18,0x09}` x9 (`0x1232a60`), mode 6 is `{0x0b}` x9 (`0x1232ab0`). I did not decode every mode, so I cannot say which mode a tournament entry enqueues. Modes `0xe` and `0x13` come from UI functions `0x6f4dc0` and `0x6f3cb0` (callers `0x6f5081`, `0x6f3f30`); `0x6c66a0` (`0x6c695e`) also sends mode `0xe`. Whether any of them is the tournament board is UNVERIFIED.

### 11.4 Is the tournament the type 0x13..0x16 machine?

UNVERIFIED, no evidence either way from code. Observed in code: the game-type word `[[0x2c9a068]+0x2ec48]` is set from menu code as 0x14 (`0x796b2b`, `0x7ac135`, `0x88c36b`) with 0x6 or its saved copy `+0x2ec8c` as the alternate, and as 0x15 or 0x7 at `0x7aeab5`/`0x7aeaae` (6 maps to 7, otherwise 0x15), so 0x14 and 0x15 pair like 6 and 7. `0xdcc4a0` rewrites 0x14 to 0x16 and 6 to 8 on round start. Type `0x13` has no immediate store (UNVERIFIED who sets it). Without a tournament type value I cannot map it.

### 11.5 Suggested runtime reads (fastest way to close this)

1. On the greyed item, GOLF_PEEK `[0x2cea1c0]+0x181a8` (byte) and `+0x181b0` (qword), and `[0x2c81150]+0x11dc` and `+0x11f0/+0x11f8`.
2. GOLF_BREAK `0xa4dd60` and `0xa4ffe0`: if they never hit, the manager never starts. If `0xa4e34a` hits, the settings file open failed (check the path the guest asks `0xf3caf0`/`0xf3b820` for).
3. Break `0xa62080` while pressing the greyed item and again on a "Turf War" or Open Course item to compare modes.
4. Break the type setters `0x796b30`, `0x7ac142`, `0x88c370`, `0x7aeace`, `0x9eb66e` and log `eax` and the return address to see which menu choice sets which type.

## 12. Tournament manager at runtime (static, with the runtime values from the coordinator)

Static reading of `eboot.dis`; runtime values are as reported (a4dd60 hit every frame, rdi `0x1000dcaa80`, `[0x2cea1c0]+0x181a8` toggling, `+0x181b0` = `0x80b79f0`). Inferences are marked UNVERIFIED.

### 12.1 What the object is and why `0xa4dd60` returns

- `0xa4d890` (tick) loads `rbx=[0x2c81150]` and tail-jumps to `0xa4dd60(rbx)`, so the runtime caller `0xe9ec36` is the caller of `0xa4d890` and `rdi=0x1000dcaa80` should equal `[0x2c81150]` (peek it as an 8-byte pointer, then read `+0x11dc`). `rsi` and `rdx` are not used by `0xa4dd60`. The object has a request list at `+0x11f0` (begin) and `+0x11f8` (end), a counter at `+0x11d8`, state at `+0x11dc` (0 idle, 4 loading, 1 means `0xa4d890` runs `0xa4de30` on the head request), and the thread job at `+0x11e0`. The class name getter `0xa4da40` says "NationalTournamentDataManager".
- Path inside `0xa4dd60(rbx)`, in order:
  1. `0xa4dd6a` state `+0x11dc != 0`: return.
  2. `0xa4dd78-0xa4dd86` request list empty (`+0x11f0 == +0x11f8`): return. This is the test I expect to fail every frame (UNVERIFIED, no peek of `+0x11f0/+0x11f8`).
  3. `0xa4dd88-0xa4dd96` `[0x2cea1c0]+0x24ec == 0x3c`: return.
  4. `0xa4ddcc-0xa4dde4`: if `[[0x2cea1c0]+0x181b0] != 0` or byte `[[0x2cea1c0]+0x181a8] != 0`, call `0xa4fd30` directly (inline path, `0xa4dde6`). Only if BOTH are zero does it set state 4 and start the "tournament Manager" job (`0xa4ddf0-0xa4de1d`: `0xea6c90`, entry `0xa4ffe0`, stack 0x4000).
- `0xa4ffe0` is only a thunk: `call 0xa4fd30; xor al,1; ret`. So the thread and the inline path run the same worker. `0xa4ffe0` never hitting is expected with a scene set; it is not a failure.
- `+0x181a8` (byte, not dword) is the "inside the frame update" flag of the app object: set to 1 at `0xfb753f` just before the frame callback `call *%r14` (`0xfb7546`) and cleared at `0xfb7602`. Its toggling is the frame loop. Since `0xa4dd60` itself runs inside the update, it sees 1.
- `+0x181b0` (qword) is the current scene or screen object: `0xfb2b50(app, scene, flag)` stores it at `0xfb2c06` after tearing down the old one (`0xfb2b92`); many teardown sites zero it. `0x80b79f0` is therefore the island scene object (UNVERIFIED which class). Nonzero is normal in the island and means "take the inline path".
- Net effect: with a scene set the manager always uses the inline path, and that path does nothing until a request is on the list. `0xa4e34a` (settings file open failed) lives in `0xa4de30`, which runs only from `0xa4d890` (state 1) or from `0xa4fd30` after it has cached a payload (`0xa4ff83`). So it not hitting means no request ever reached the worker; it says nothing about a file.

### 12.2 Where a request comes from (this is the download path)

- Requests are built in the title reply handler `0xa5d3a0`. Reply id `0x144` (jump table `0x11c8460`, `esi-0x8a`) = `0xa5dfc1`: it walks the vector `ctx+0x1225c0` (selector 3, rows of `0x258` bytes), compares each row's `+0x108` with `ctx+0x128058`, and on a match (`0xa5e1b2`) copies the row name string (`row+0x98`) and the reply buffer (`ctx+0x128048`, length `ctx+0x128050`) into a new 0x48-byte request with type `0x2` (`0xa5ff33`, fields `+0x28` id, `+0x2c` type, `+0x30` data copy, `+0x38` and `+0x40` length). It pushes it on `[0x2c81150]+0x11f0..0x11f8` (`0xa5ffc7-0xa60042`) and calls `0xa4dd60` (`0xa6004a`). Other request types: 1 (`0xa5082b`, `0x9dff8c`), 2 (this one).
- `0xa4fd30` for type 2 (`0xa4fd90-0xa4fecc`): opens a cache file named from the row string plus the locale suffix table `0x13390c0` (`0xea4730`), writes the data and a 4-byte value (`0x10fdd80`), then runs the parser `0xa4de30` (`0xa4ff83`), then completes the request (`0xa4da50`). `0xa4de30` is what opens `data/sponsor/param/International_Tournament_settings.txt` (`0xa4e1be`) and `..._messages.txt` (`0xa4f797`) and reads `tournamentId` and `tournamentName_%s`.
- Reply id `0x144` is the completion of slot `0x32`, the GET that follows `gameapi_getnationalgamedata` (slot `0x31`, `analysis/online/protocol.md` "National event downloads": `0x41f5` URL suffix, `0x41f6` word stored at `ctx+0x12805c`, GET capacity `0x2dc6c0`). The row key `ctx+0x128058` is that `0x41f6` word (cited, UNVERIFIED that the row `+0x108` is the same field).
- So the settings are NOT read from the package: no `sponsor` directory exists in `xbdata`, and no archive hash matches (section 11). They arrive in the body of the slot `0x32` GET, found via a row of the national board list. Transport is the title HTTP stack (the `gameapi_*` POSTs and their follow-up GETs to `cds_gamedata_down_url1`), not TUS, NP title storage or DLC. The imports are the same libSceHttp/libSceNet ones the title queue already uses; there is no separate API.
- The producer chain is in the boot mode (mode 1, list `0x1232a20`, 14 entries read from `0xa63562`): states 1, 7, 0xf, 0x14, 4, **0x26**, **0x28**, 0x25, **0x27**, 0x10, 5, 5, 5, 0x13. State 0x26 (`0xa61366`) sends slot `0x2f` (`gameapi_getboardlistnational`, `0xa613e6`) unless the game type is `0x10`. State 0x28 (`0xa61427`) takes the next item from the manager (`0xa546d0`), needs `item+0x248 != 0`, and sends slot `0x31` (`gameapi_getnationalgamedata`, `0xa607a6`) for it. State 0x27 (`0xa613f0`) is skipped when `[0x2c81150]+0x268 == 0` (`0xa613f7`). So an empty national board list gives the manager no items, no state 0x28 request, no reply `0x144`, no request on `+0x11f0`, and the manager stays idle. The `--empty-national-boards` fixture in `protocol.md` does exactly that (no `0x4a60` record, completes with result 1 and no GET). UNVERIFIED: which manager field the slot `0x30` body fills (`+0x250`/`+0x268`) and that the greyed menu item tests that list, but the chain fits the observation that selecting it enqueues nothing.

### 12.3 Your three questions

1. The test that fails is the empty request list at `0xa4dd86` (UNVERIFIED, peek). `+0x181a8` is the frame-update flag; `+0x181b0` is the current scene object. Neither blocks anything; they only choose inline versus thread.
2. Downloaded, via the title queue: `gameapi_getboardlistnational` (slot `0x2f`) then GET slot `0x30` for the list, then `gameapi_getnationalgamedata` (slot `0x31`) then GET slot `0x32` for the data. The server needs to serve a non-empty national board (a `0x4a60` suffix plus a body) and a game-data reply, not an empty board.
3. GOLF_BREAK sites, in order of usefulness: `0xa4dd88` (hit only if the list is non-empty and state is 0; if never hit, the list is empty), then `0xa4dde6` versus `0xa4ddf0` (inline versus thread). For the producers: `0xa613f0` (state 0x27, check `[0x2c81150]+0x268`), `0xa5e1b2` (reply `0x144` matched a row) and `0xa4fd6d` (worker entry; `edx` is the request type at `0xa4fd6d`).

## 13. Registration observed (2026-11-18, runtime `e6fb120`, fixture v10)

Correction to sections 10-12: Open Course free play does register. Once the course-world assignment route
(`gameapi_assignmentcourseworld?account=..&n=..&s=1`, slot 0x21) is answered and the listener serves schedule rows
(`--event-group OneHole_20180914_<course>_<hole>`), hole 1 ends with `gameapi_getboardlist` (1,192-byte schedule reply),
then `gameapi_registscore?account=..&n=21&s=1` (200, 40 bytes). The listener stored `OneHole_20180914_1_1`, player
`Golfer`, values 2 and 20, so Eagle City is course 1 and holes are numbered from 1. In the earlier runs the missing
course-world reply kept the hole-end chain from reaching the schedule load. The GOLF_BREAK sites in the 0xd8xxxx machine
were still not the path taken; which caller enqueues this registration is not traced. Log: `work/evidence/open-course-registscore-1118.log`.
The International Tournament item stays greyed; sections 11-12 cover that separate gate.
