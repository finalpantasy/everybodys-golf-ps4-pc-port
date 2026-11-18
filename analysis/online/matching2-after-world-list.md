# After the world list: what the Open Course screen waits for

Static read of `work/analysis-cache/eboot.dis` (image offsets). No runtime trace. Anything not read is marked NOT_VERIFIED.
Extends `matching2-entry-contract.md` (state table, row layouts); only new facts are here.

## Short answer

"Connecting..." is a mode-level overlay (`0x2c6b570`, shown by `0x116f00`, hidden by `0x1172f0`). It is hidden only when
the screen mode reaches its success or error exit. Matching2 state 7 is NOT the end: the mode must then start the
matching UI object (`*0x2c82738`, start function `0xa73ed0`), and that object must finish the whole chain
(lobby list, JoinLobby, member list, state 0x17) and set `ui+0x9c = 1`.

Most likely stall (inferred from code, NOT_VERIFIED at runtime): the mode only calls `0xa73ed0` from inside a loop that
needs a world row whose u32 `+0x08` equals the mode's selected-world field `mode+0x228` (see "Gate A"). If no row
matches, the mode sits in its state 11 (`0xef4ac`) polling `ui+0x9c` forever, nothing is requested, and matching stays in
state 7. That is exactly "state 7 idle".

## 1. The 0x28-byte allocation at 0xa7a685

Not a message to a consumer. It is the std::map node for `(requestId -> errorCode >= 0)` at `obj+0x808`
(`0xa7a685`: `r14b = (errcode >= 0)`, alloc 0x28 via `0xf8d860` or `malloc`, insert at `0xa7a6da..0xa7a703`, head `obj+0x810`).
Readers of `obj+0x808/0x810` in `0xa70000-0xa86000`: only `0xa776d3-0xa776fe` (looks like clear/teardown, NOT_VERIFIED) and
this insert. Nothing on the entry path consumes it. No event id or payload beyond the u32 key and bool.

## 2. Who reads the world list and what gates "Connecting..."

### Screen mode state machine (the thing that shows the overlay)

Big mode update function in `0xeec00-0xf1fff` (no frame pointer; mode object at `0x20(%rsp)`, state dword at `mode+0`).
Dispatch `0xeefce-0xeefed`: `state <= 0xf`, jump table `0x11baec4`. Relevant states:

| Mode state | Target | Behavior |
|---|---|---|
| 13 | `0xef596` | Calls controller `0xa5ada0(**0x2c82420)`. Waits until controller state `(rax)==0`. Controller error (`+8 != 0`) -> `0xef8a9` (hide overlay, `0xa69d80(mode,5)`). Success -> finds a child by name (`0x12120b7`), calls `0x116f00` (overlay), mode state 14. |
| 14 | `0xef619` | If matching obj `*0x2c82ff8` exists, `+0x100 != 0`, `+0x48 != 0x2a` -> `0xef770`. Else `0xa76c10(obj-or-null, 1)` (create/start Matching2); true -> mode state 10 (`0xef64f`), false -> `0xefa00`. |
| 10 | `0xef415` | Passes when matching `+0x48 == 7`, or (`0x2c905f0 == 1`, `0x2c8f338 == 2`, state in 8..0x29), or in a lobby. Then mode state 11 and the world scan (Gate A). State 0x2a -> `0xef8a4` error. |
| 11 | `0xef4ac` | Reads `ui+0x9c` (`ui = *0x2c82738`): `2` -> error exit `0xef8a9`; `1` -> success: calls `0xe9ee50` (0x198), hides overlay (`0x1172f0`), mode state 0. Any other value (0) -> does nothing, stays. |

`0xef770` (state 14 -> 11 shortcut) does the same Gate A scan as state 10 and sets mode state 11.

### Gate A: the world-row scan (the only place the UI object is started)

State 10 at `0xef44a-0xef4a7` and `0xef770-0xef7ce`: `count = (obj+0x7f0 - obj+0x7e8)/0x28`. If `count <= 0` return (stay).
Loop rows (stride 0x28, reads u32 at row `+0x08`): compare with `ebx = mode+0x228` (u32). On first match:
`0xef6b2` / `0xf1f9a`:
- `r14 = mode+0x230` (qword; `>>16` used), `r12 = *0x2c82738`.
- Loop the local config table `*(*0x2c7e0a0 + 0x38)..+0x40`, stride 0x18. For the entry with `(s32)entry[0] + 1 == (u16)mode+0x228`,
  call `0xa73ed0(ui, esi=entry+4, edx=entry+8, ecx=entry+0x14, r8d=(mode+0x230>>16)-1 (low 32), r9=1)`
  (call sites `0xef73a`, `0xf2022`). Other `0xa73ed0` callers (NOT_VERIFIED which screens): `0x7efa1e`, `0x7efb24`, `0x7f84dd`,
  `0x7f8715`, `0x9d3170`, `0xa16fca`, `0xa6aa08`, `0xb9ab01`, `0xb9adcb`.
- No match in either loop -> nothing is called, mode stays in state 11.

So two conditions: (1) a world row with `row+0x08 == (u32)mode+0x228` (our row has worldId 1, so `mode+0x228` must be 1, i.e.
`entry[0] == 0`); (2) a local table entry with `entry[0] + 1 == (u16)mode+0x228`. The local table `*0x2c7e0a0 + 0x38` is game
config, contents NOT_VERIFIED. The writer of `mode+0x228` was not found: no plain store to `0x228(%reg)` in `0xe0000-0x100000`
sets it from data except zero-init (`0xf7d0d`, `0xf7e02` ymm clears; `0xfdb34`, `0xfdb72` zero). NOT_VERIFIED who sets it (likely the
Auto Entrance button / world pick, or a struct copy I did not match).

Fields of the world row the mode checks: only `+0x08` (worldId). Population, max members, lobby count are not tested here.
The mode does NOT test `obj+0x7e0`; the vector is `obj+0x7e8` begin / `0x7f0` end (the `0x7e0` in the brief is the header).

### Matching UI object `*0x2c82738` (class code `0xa72200-0xa74100`)

Start `0xa73ed0(ui, esi=a, edx=b, ecx=c, r8d=d, r9d=e)`: `esi <= 0` -> returns 0 and does nothing (`0xa73eeb-0xa73ef5`).
Else stores `ui+0x8c=a, +0x90=c, +0x94=d, +0x98=b, +0x9c=0, +0xd0=0, +0xd8=e`, `ui+0xa8 = *0x2c82ff8`, `ui+0xe0 = network tick`.
- obj missing/inactive/0x2a: `0xa76c10(obj,1)`, UI state 2 (`0xa73ff9`) or error (`0xa74005`: `ui+0x9c = 2`).
- obj in a lobby (`+0x7d0 != 0`): UI state 1, `0xa7dcb0(obj,0)`.
- else (our case): `0xa74060-0xa740bc` sends a SECOND `GetWorldInfoList` (`serverId = obj+0x50`, callback `0xa79430`), `obj+0x48 = 6`,
  UI state 2. Our runtime must answer it again (rows vector is rebuilt, state returns to 7). The caller stores state 6 after the
  call returns, so deliver the reply later (see contract section 6).

Per-tick `0xa720d0` (this = ui; reached via vtable slot `0x132c0a8+0x?`, data refs `0x132c0a8`/`0x1436ad8`, caller not traced):
- Timeout: for UI states other than 6/7, `ui+0xe0 + 30 s` against network tick `0x2c8f2e0+0x85cbf8`; on expiry goes to `0xa72957`
  (`ui+0x9c = 2`, error dialog, UI state 0). So a stalled request ends in an error exit after about 30 s, NOT an endless
  "Connecting..." (once the UI object has been started). Endless means the UI object was never started (Gate A) or `0xa720d0` is not ticked.
- State 2 (`0xa7235d`): waits `obj+0x48 == 7`. Builds candidates from local table `*(0x2c7e0a0)+0x38` entries with
  `entry+4 == ui+0x8c` and `entry+8 == ui+0x98` into `ui+0xb0`. Empty -> `0xa7290d` (error: `ui+0x9c = 2`). Picks index
  (`ui+0x90`, negative -> weighted random `0xa72d70`), clamps to world vector size-1, copies the 0x28-byte world row to `obj+0x58..0x7f`,
  `obj+0x48 = 8` (`0xa72a6c`), sends GetLobbyInfoList (below), then `obj+0x48 = 0x0e` and UI state 5.
- State 5 (`0xa72338`): waits `obj+0x48 == 0xf`; `0xa73530` picks a lobby row, `0xa73a90(ui, idx)` -> JoinLobby.
- State 6 (`0xa724e5`): done when `obj+0x7d0 != 0`, matching active, state != 0x2a, `obj+0x458 > 0` (member count written at `0xa83704`, end of the
  per-tick room function `0xa831b0`, only runs in obj state 0x17), plus NP globals (`0x2c905f0 == 1`, `0x2c8f338 == 2`, obj state 8..0x29,
  or `obj+0x130[obj+0x450*8] == 0` check at `0xa72561`). Then UI state 7 (`0xa72d1c`).
- State 7 (`0xa725d0`): needs float `*(0x2cc94f0)+0xb4 == 0` (screen fade done), then builds the result and sets `ui+0x9c = 1` (`0xa728fd`).
  This is the ONLY write of 1 to `ui+0x9c`.

## 3. GetLobbyInfoList and JoinLobby call sites

- `sceNpMatching2GetLobbyInfoList` stub `0x10fd860`. Call sites: `0xa72b79` (UI state 2 first page), `0xa73246`, `0xa73497` (re-page, UI helper `0xa73130`),
  `0xa819e8` (state 0x10 paging), `0xa0e018` (other screen). Triggered only by the UI object after it picked a world (UI state 2)
  or by obj state 0x10 paging. Request struct at `0x180(%rsp)` (0x20 zeroed): `+0x00` u32 worldId (`obj+0x60`), `+0x08` u32 start index
  (1-based; `obj+0xc0+1`), `+0x0c` u32 count (0x14); `obj+0xc0 = start-1`, `obj+0xc4 = 0x14`, `obj+0xc8 = worldId`; optParam callback `0xa79430`, userdata obj,
  timeout `*(*0x2c82440) * 1000000`; requestId out `obj+0x54`. On success `obj+0xb0 = obj+0xa8` and `obj+0x48 = 0xe`.
- `sceNpMatching2JoinLobby`: only wrapper `0xa83e20(obj, u64* lobbyId)`, API call `0xa83f8c`, sole caller `0xa73ab8` inside `0xa73a90(ui, rowIndex)`,
  which passes `&lobbyRow[idx].+0x10` (row stride 0x50 at `obj+0xa8`, `+0x10` u64 lobbyId). Returns 0 -> error path `0xa73ad0`; nonzero -> UI state 6.
  `0xa73a90` is called from UI state 5 (`0xa725c6`) and `0xa73530`'s selection path. Trigger: obj state 0xf plus a lobby row passing the weight rule
  (row `+0x1a` u16 member count <= 50; weights from `*0x2c7e0a0`).
- Both are driven entirely by the UI object `0xa720d0` ticks, never by the Matching2 state machine itself (state 7/8/0xf are waits).

## 4. Other conditions (checked)

- No NpScore/NpTus/http/signaling/lobby-event-callback wait on this path. The mode and UI read only: `0x2c905f0 == 1`, `0x2c8f338 == 2`,
  `0x2c8245c` (title queue done, only in controller state 3), `0x2c82ff8` fields (`+0x48`, `+0x100`, `+0x7d0`, `+0x458`), world vector
  `+0x7e8/0x7f0`, local config `*0x2c7e0a0`, fade float `0x2cc94f0+0xb4`.
- Controller `0xa5ada0` (this is the pre-connection checker, not the world/lobby UI): object state `+0` 1..11, pending-step bitmask `+4`
  (bit n-1 = start state n, run lowest bit first via `0xa5a2a0`), result `+8/+0xc`, show-dialog flag `+0x18`. Its matching step is state 6
  (`0xa5b029`): passes at matching `+0x48 == 7` (or 8..0x29 with NP ready), error at 0x2a. Finish routine `0xa5a0f0` clears state, mask
  and hides the overlay (`0x1172f0`).
- Mode entry `0xa0a0f4` (also calls GetWorldInfoList) is a different entry (flags `0x6e/0x6f`, controller start `0xa5a2a0`); it sets matching state 6 itself.

## Most likely reason for the stall (ranked)

1. Gate A: no world row with `row+0x08 == mode+0x228` (and/or no local table entry `entry[0]+1 == (u16)mode+0x228`), so `0xa73ed0` is never called.
   Check at runtime: read `mode+0x228` and dump `*(*0x2c7e0a0 + 0x38)` entries; set our row `+0x08` to that world id.
2. `0xa73ed0` called but `esi (= entry+4) <= 0` returns immediately (`0xa73eeb`): also leaves state 7 idle.
3. UI tick `0xa720d0` not running (NOT_VERIFIED, vtable caller not traced).

---

# Update 2: the live evidence (mode `*0x2c82580` is NULL, controller idle with +8=5)

The mode in sections above (`0xeec00`, `*0x2c82580`) is NOT the running scene; Gate A there is moot for this screen.

## A. The controller ended in ERROR: result 5, code -1 (verified in code)

Live `**0x2c82420`: `+0=0, +8=5, +0xc=-1, +0x18=1` equals exactly the store at `0xa5acea-0xa5acf4`
(`movabsq $0xFFFFFFFF00000005,%rax; movq %rax,8(%r15)`), i.e. the word-filter step (start state 7, `0xa5a517`, body `0xa5aaa5-0xa5acfd`):
1. `0xa5a517`: `*(0x2c6b648)+0x2ad9ac` first byte == 0 -> step skipped (`0xa5a852`), else continue.
2. `0xa5aadb` `sceNpWordFilterCreateTitleCtxA(*0x2ccbdb4)`: return < 0 -> jump to `0xa5acaa` (ctx id stays -1).
3. `0xa5acbc` helper `0xece690(wf, text)`: returns 0 (-> error 5/-1 at `0xa5acea`) when text ptr NULL, `wf[0] < 0` (CreateTitleCtxA failed), text empty,
   `wf+4 >= 0` (request already pending), or `sceNpWordFilterCreateAsyncRequest(wf[0], &params)` returns <= 0 (`0xece741-0xece748`). Returns 1 after
   `sceNpWordFilterCensorComment(reqId, text)` is issued (any return; a negative one deletes the request, `0xece766-0xece777`, but still returns... NOT_VERIFIED, `0xece6cf` zeroes r14 so this is a failure too).
   Success keeps the overlay and waits (`0xa5ace5`); update state 7 (`0xa5b05e`) then polls `sceNpWordFilterPollAsync(wf+4, &res)`: 0 = done (res 0 -> `wf+0x14 = 0` ok,
   `0x8055080b` -> 1, other -> 2), >0 pending, <0 error.
4. With the word filter OK, `wf+0x14 == 0` clears the bit (`0xa5b46a`) and the controller finishes with +8=0.

Live values match: matching state 7 passed controller state 6 (mask went `0x6c -> 0x68`, `+0=3` then states 4, 6, 7). The controller then died at state 7.
So the screen never starts the lobby UI (`0xa73ed0`): the entry controller failed before that. State 7 idle is expected.

Peek list (`**0x2c82420 = C`): `C+0` state (7 while word filter runs, 0 idle), `C+4` mask (0x40 left at state 7), `C+8` result (0 = OK; 5 = this failure),
`C+0xc` code, `C+0x10` -> wf object (`wf+0` ctx id must be >= 0, `wf+4` request id, `wf+0x14` result: -1 unset, 0 ok), `C+0x18` show-dialog.
Also `*(*0x2c6b648 + 0x2ad9ac)` text (first byte must be non-zero for the step to run, string should be the name checked).
Expected on success: `wf+0 >= 0`, `wf+4 > 0` while polling, `wf+0x14 == 0`, final `C+8 == 0`.
Fix candidates (our runtime): make `sceNpWordFilterCreateTitleCtxA` return >= 0, `sceNpWordFilterCreateAsyncRequest` return > 0, `sceNpWordFilterPollAsync` return 0 with `*res = 0`
(buffer `-0x130(%rbp)` = the out param, 4 bytes) after at least one call, `sceNpWordFilterCensorComment` return >= 0 (it reads text from `wf+8`, size `wf+0x10`).

## B. Which scene polls the controller (what ends "Connecting...")

Entry that started this run (matches mask `0x6e`, `+0x18=1`): `0xa0a1f8-0xa0a208` (`movl $0x6e,4(%r14); movb $1,0x18(%r14); a5a2a0(r14,1)`) in the scene button
handler (function start `0xa08470`, called from `0xa06874`); needs `*(0x2c9a068)+0x2ec48 == 0` (else `0xa0a07a` path sends GetWorldInfoList itself with mask 0x20, no controller).
Scene class: screen object with state `+0x20` (setter `0xa0cb00`, 25 states, table `0x11c7e40`) and a second machine `+0x4a0` (update `0x9ff2c0`, table `0x11c7d3c`, setter `0xa02e50`).
- `+0x4a0 == 10` (`0x9ff7b3`), `== 18` (`0x9ffd46`), `== 19` (`0x9ffda1`) each call `0xa5ada0(**0x2c82420)` per frame and test `C+0 == 0`:
  - `C+8 == 0` -> success (10: `0xa006ca`, builds data, goes to state 0xf `0xa0094b`; 18 -> `0xa00a7c` state 0x10; 19 -> `0xa00a89`).
  - `C+8 != 0`: if `((*0x2ccbae8)->0x138)->0x168)->0x28 & 3 != 0` (an error dialog is still open) it WAITS; else state 5 (`0xa00bf2`, via `0xa02e50(this,5)`), 0x14 or 0x15.
  So with C idle at +8=5 the scene leaves "Connecting..." only after the controller's error dialog (`0xf38a20(0x2ccbae8,2,0xc,msg)`) is dismissed. If the dialog is not
  displayed or never reports closed, the scene stays. Peek `*(*(*(*0x2ccbae8+0x138)+0x168)+0x28) & 3`: nonzero = dialog pending.
- `0xa01844` (`+0x4a0` -> 10 with mask 0, start state 1) is the other start. Its `0xa5a2a0(1)` -> `0xa5a304` -> state 10 (`0xa5b0f6`, NP ready gate).
- Overlay: `0x116f00(*0x2c6b570, ...)` shows, `0x1172f0` hides; `0xa5a0f0` (controller finish) hides it. The controller error path hides it at `0xa5a0f0`, so a
  visible "Connecting..." after finish is either the error dialog (blank text if `0x2c8f160` text table lacks id) or a scene that is not polling (NOT_VERIFIED).
- Main scene tick `0xa14de0` (state `+0x20`): matching hand-off sits at `0xa16ebd`: runs only when matching `+0x48 == 7`, `*(0x2c7e0a0)+0x28 != 0` (cfg byte, see also `0xa151d4`),
  `eax != 1`; it hides the overlay and ends with `0xa73ed0` at `0xa16fca` (UI start, args from the config table). Also gated at `0xa151bf` on title queue idle (`**0x2c82548 == 0`) and `0x2c8245c`.
  Conditions between `0xa16ec6` and `0xa16fca` were only skimmed: NOT_VERIFIED. This is the real "state 7 -> GetLobbyInfoList" bridge; peek `*(0x2c7e0a0)+0x28` (must be non-zero).
- Population text "Total current connections" and the Auto Entrance button: not located (layout part names are data, no string in code). NOT_VERIFIED.

Not the cause: the 50-row world list, `0x2c82580`, Gate A.
