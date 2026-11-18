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
