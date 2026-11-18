# Matching2 online-entry contract (CUSA04687 1.17)

Static read of `work/analysis-cache/eboot.dis` (image offsets). Nothing here was executed. `obj` is the Matching2 object (the one global `0x2c82ff8` points to; the dispatch code only runs when `*0x2c82ff8 != 0`, `obj+0x100 != 0` and `obj+0x48 != 0x2a`, `0xa80d1b-0xa80d3f`). Update function `0xa80ab0` (state at `obj+0x48`, jump table `0x11c8c54` indexed by state-5, 0x29 entries). Request callback `0xa79430`.

Related existing notes: `protocol.md` "Matching2 discovery callbacks" (same facts for worlds, lobby list and JoinLobby). This file adds the full chain through state 0x17, the UI driver, row layouts and the locking.

Event identities (the game's own log strings confirm the ones marked S):
- `0x6F01` = CONTEXT_EVENT start-over / "context cannot continue" (string `0x1204d36`). Game treats it as fatal: state 0x2a. Never send it.
- `0x6F02` = CONTEXT_EVENT_STARTED (S, `0x1204d01`). `0x6F03` = stopped.
- `0x0002` GET_WORLD_INFO_LIST (string `0x12048fb` "failed to get world info").
- `0x0006` GET_LOBBY_INFO_LIST (inferred: adjacent to the lobby-list request, string `0x1204939` "failed to get lobby info").
- `0x0201` JOIN_LOBBY (S, `0x12049a2`). `0x0202` LEAVE_LOBBY (inferred, sets state 0x0d).
- `0x7207` GET_LOBBY_MEMBER_DATA_INTERNAL_LIST (S, `0x12049d9`).
- Dispatched but not on the entry path: `0x103` leave room, `0x108` send room message, `0x7005`, `0x7101`, `0x7102`, `0x7106` (room phase). `0x102` is only a range-check constant in the dispatcher; `0x101`/`0x102` fall to the default epilogue.

Callback argument layouts (from the registers the game reads):
- Request callback: `(ctxId u16 edi, requestId esi, event u16 dx, errorCode ecx, data r8, arg r9=obj)`.
- Context callback `0xa7e820`: `(ctxId edi, event si, eventCause dx (ignored), errorCode ecx, arg r8=obj)`.
- Lobby event callback `0xa7e8b0`: `(ctxId edi, lobbyId rsi (ignored), event dx, data rcx, arg r8=obj)`.
- Signaling callback `0xa7eef0`: `(ctxId edi, subjectId rsi, event edx, cause ecx, r8d, arg r9=obj)`.

## 0. Before state 5 (context start, `0xa7dfd0`)

Every call below must return 0 or the function jumps to `0xa7e0cb` -> `0xa76f60` (teardown, state 0x2a path):
`sceSysmoduleLoadModule` 0x1c, 0xb5, 0x21; `sceNpMatching2Initialize` (param: u64 from `*(0x2c82440)+0x40`, u64 `0x3f` at +8, u32 `0x100` at +0x10, 16 constant bytes at +0x18; `0xa7e06c-0xa7e0a5`); `sceNpSignalingInitialize(0x20000,0x100,0x3f,0x4000)`; `sceRudpInit`; `sceNpMatching2CreateContextA(param, &obj+0x44)` with param = u32 userId at +0, u64 `0x10` at +8 (`0xa7e1b0-0xa7e1e1`; the u16 context id must be nonzero, zero means "no context" everywhere); if `0x2c82ff0 == 0` `sceNpSignalingCreateContextA` (`0xa7e4f0`); `sceNetCtlRegisterCallback`; `sceNpMatching2RegisterContextCallback(cb, obj)` (no ctx argument); Register{Lobby,LobbyMessage,Room,RoomMessage,Signaling}Callback(ctx, cb, obj); `sceRudpSetEventHandler`; `sceRudpEnableInternalIOThread`; `sceNetCtlGetInfo(0xe)`, `sceNetCtlGetNatInfo` (NAT type stored at `obj+0x57c`); `sceNpMatching2ContextStart(ctx, 0)` (`0xa7e482`, must return 0).
On success it sets `obj+0x100 = 1` and state 4 (`0xa7e5c2-0xa7e5c9`). State 4 has no handler; only the context callback leaves it.

Pre-start states for reference (title controller, not the Matching2 library): state 1 (`0xa80ef1`) waits for `0x2c905f0 == 1` and `0x2c8f338 == 2` (NP ready), runs `sceNpSetContentRestriction`, with a 300-tick counter `0x2c83020` -> error 0x2a. State 2 (`0xa80f74`) needs `0x2c8f358 == 3`, calls `0xb979d0` (NP check) and a non-empty `sceNetCtlGetInfo(0xe)` string, 150-tick counter `0x2c83024` -> error 0x2a, then calls `0xa7dfd0`. The title HTTP and NpAuth work (discovery, server time, property info, async NpAuth code at `0xa60c54-0xa60d19`, login POST) is queued by the title controller before it starts Matching2 (see `protocol.md` "Title requests before NpAuth"). None of it runs between state 5 and the lobby join.

## 1. State path (obj+0x48)

| State | Handler | Leaves when |
|---|---|---|
| 4 | none | context callback `0x6F02` with `errorCode >= 0` sets 5 (`0xa7e84d`). `0x6F02` with `errorCode < 0`, or `0x6F01` at any error code, calls `0xa7a8f0(obj, 0x2a, ...)` (error path below). `0x6F03` calls `sceNpMatching2DestroyContext` and clears `obj+0x44`. |
| 5 | `0xa81330` | GetServerId < 0 -> error 0x2a (`0xa81847`, msg `0x1204e45`). GetWorldInfoList < 0 -> error 0x2a (`0xa81a11`, msg `0x1204ed5`). Both OK -> state 6 (`0xa813c5`). |
| 6 | none | callback `0x0002` (below) sets 7. |
| 7 | `0xa813d3` | Waits. Only if `obj+0x7d0 != 0` (already in a lobby) and `*0x2c82ff8`, its `+0x100 != 0`, state != 0x2a -> 0x17. Otherwise the UI driver (section 2b) moves it. The UI copies the chosen world row into `obj+0x58..0x7f` and sets 8. |
| 8 | `0xa81417` | Same shortcut to 0x17. Otherwise waits for the UI to send GetLobbyInfoList (-> 0x0e). |
| 0x0e | none | callback `0x0006` sets 0x10. |
| 0x10 | `0xa8153e` (paging) | Either sends another GetLobbyInfoList page (stays 0x0e, `0xa819f5`) or sets 0x0f (`0xa81a03`). |
| 0x0f | `0xa814fa` | Waits for the UI to call JoinLobby. Shortcut to 0x17 if already in a lobby. |
| 0x13 | none | JoinLobby submitted (`0xa83f95`). Callback `0x0201` sets 0x14 (`0xa79803`). |
| 0x14 | `0xa81596` | Sends GetLobbyMemberDataInternalList, then sets 0x15 (`0xa816b6`). |
| 0x15 | none | callback `0x7207` sets 0x16 (`0xa79881`). |
| 0x16 | `0xa816c4` | Calls `0xa82a10` (allocates the 0x48-byte object at `obj+0xd8`, `0xea6c90` with 0x8000-byte buffers; no network), sets 0x17. |
| 0x17 | `0xa8128d` | End of the entry phase. Each tick runs `0xa82af0` (member table sync, uses `obj+0x2c0[]`, `obj+0x450`) and `0xa831b0` (room/game traffic). No NpAuth, no HTTP. |

Error path: `0xa7a8f0(obj, nextState esi, errCode edx, fmt rcx, ...)` formats the message into `obj+0x479`, stores `nextState` at `obj+0x4c` and sets state 0x2b (`0xa7ab9b-0xa7ab9f`). Special dialog text for codes `0x80550d18`, `0x80550d19`, and (when `0x2c8f338 == 1` or `0x2c905f0 == 0`) `0x80550c2f`, `0x80550c26`. State 0x2b (`0xa80aec`) shows the dialog through `0xf38a20(0x2ccbae8, 2, 0xc, obj+0x479)` and sets 0x2c, or skips straight to `obj+0x4c`. State 0x2c waits for the dialog to close, then `obj+0x48 = obj+0x4c`. State 0x2a has no handler in the table: it is terminal for this object; the title controller and UI test `*(obj+0x48) == 0x2a` and leave online mode (`protocol.md` state 6 table). Only callback `0x7207` with NULL data uses 0x2a without the dialog for the first four failures (`0xa7a142-0xa7a15e`, counter `0x2c83004`, fifth failure goes through `0xa7a8f0`).

Timeouts: the library never times out on the game side. State 5 to 0x17 has no tick counter. The only timer is the per-request optParam timeout, so a request that never completes leaves the game in 6 / 0x0e / 0x13 / 0x15 forever. A replacement that wants a failure must deliver the response with `errorCode < 0`.

## 2a. Requests issued from the state machine

All requests pass `(ctxId u16 = obj+0x44, &request, &optParam, &requestId)` and the game calls `sceNpMatching2SetDefaultRequestOptParam(ctx, &optParam)` first on the same 24-byte buffer (zeroed beforehand, so the default fills the rest).

optParam (24 bytes): `+0x00` callback ptr `0xa79430`; `+0x08` userdata = obj; `+0x10` u32 timeout in microseconds = `*(u32*)*(0x2c82440) * 1000000` (the game's config value; NOT_VERIFIED, seconds unknown); the rest stays at the SDK default (appReqId, flags).
requestId: u32 written at `obj+0x54`. Nothing in the callback compares it. The JoinLobby wrapper returns `obj+0x54` and the caller treats 0 as failure (see JoinLobby).

| Request | Site | Request struct the game fills |
|---|---|---|
| `GetServerId(ctx, &obj+0x50)` | `0xa8133b` | out u16 at `obj+0x50`; return must be >= 0. Value is reused as the world request's serverId. |
| `GetWorldInfoList` | `0xa813b6` (also `0xa72312` UI, `0xa0a0f4`, `0xa0dd3e`, `0xa0f005`, `0xa1768f`, `0xa740bc`) | `+0x00` u16 serverId (= `obj+0x50`). Nothing else is written (the 0x140(%rsp) buffer is zeroed before). Return < 0 at `0xa813bf` -> error 0x2a. Then `obj+0x48 = 6` after return. |
| `GetLobbyInfoList` | state 0x10 `0xa819e8`; UI `0xa72b79`, `0xa73246`, `0xa73497`; `0xa0e018` | 0x20-byte zeroed buffer. `+0x00` u32 worldId; `+0x08` u32 first index, 1-based; `+0x0c` u32 count (UI paths always 0x14 = 20). Return < 0: state 0x10 retries every tick (`0xa819ef`); UI paths ignore it and wait forever. On success `obj+0xb0 = obj+0xa8` (UI paths, clears the row vector) and `obj+0x48 = 0x0e` after return (`0xa819f5`, `0xa72b90`, `0xa7325a-0xa73261`). |
| `JoinLobby` via `0xa83e20(obj, u64* lobbyId)`; only caller `0xa73ab8` | `0xa83f8c` | `+0x00` u64 lobbyId (from the chosen lobby row `+0x10`). Other bytes are zero. First it clears `obj+0x2c0[0..0x31]` member structs and `obj+0x130` (0x320 bytes) when `obj+0x100 != 0`. On return >= 0 sets `obj+0x48 = 0x13` and returns `obj+0x54`. A returned 0 (API failure or request id 0) makes the UI show an error dialog (`0xa73abd-0xa73ac1`). Return a nonzero request id. |
| `GetLobbyMemberDataInternalList` | `0xa816b1` | `+0x00` u64 lobbyId = `obj+0x7d0`; `+0x08` ptr to u16[] member ids (copy of the vector at `obj+0x88..0x90`, built on the stack); `+0x10` u64 count; `+0x18..+0x1f` zero. Return value is not checked; state 0x15 is set unconditionally after the call (`0xa816b6`). |

Other requests on the path: none. `LeaveLobby` (`0xa7dd79`) is teardown only. `SendRoomMessage`/room requests start at state 0x1a/0x1e, after 0x17.

## 2b. UI driver that actually picks the world and lobby

Object `ui` (state at `ui+0xa0`, matching obj at `ui+0xa8`, table at `0xa72200-0xa72d6f`, jump table `0x11c8b64` for states 1..7: 1 `0xa7226f`, 2 `0xa7235d`, 5 `0xa72338`, 6 `0xa724e5`, 7 `0xa725d0`, 3 and 4 no-op).
1. UI 1: unless already in a lobby, sends GetWorldInfoList (`0xa72312`) -> matching 6, UI 2. So a second GetWorldInfoList can arrive after state 5's; handle repeated requests (the world vector is rebuilt each time).
2. UI 2: waits for matching state 7 (`0xa72364`). Builds candidate entries from the game's local table `*0x2c7e0a0` (stride 0x18, entries whose `+4`/`+8` match `ui+0x8c`/`ui+0x98`). If none: error dialog and UI state 0 (`0xa7290d`, `0xa72957`). Picks a world index (`ui+0x90`; negative -> weighted random in `0xa72d70`). `0xa72d70` skips any candidate whose index is >= server world count and uses weight = `tableA[i] - (world.+0x14 / *(0x2c7e0a0+0x70)) * tableB[i]`, dropping weights <= 0. The explicit-index path (`0xa72a0e`) clamps the index to `worldCount-1`. If the world vector is EMPTY it skips the copy and still sets state 8 with the default world id (`obj+0x60`, zero) (`0xa72a23`, `0xa72a6c`).
3. The chosen 40-byte world row is copied to `obj+0x58..0x7f` (so `obj+0x60` = worldId, `obj+0x64` = numLobbies, `obj+0x6c` = total members), state 8 (`0xa72a6c`), then GetLobbyInfoList for page 1 (`start = 1, count = 20`; if `ui+0x94 >= 0` it re-requests the page holding that lobby; if the world has more than 20 lobbies and a population bucket is nonzero it picks a random page in `0xa73130`/`0xa7326d`). UI 5.
4. UI 5 (`0xa72338`): waits for matching state 0x0f. If `ui+0x94 >= 0` calls `0xa73a90(ui, idx)` directly, else `0xa73530` picks a lobby: for each row i (<= min(rowCount, |tableA|)) reads u16 at row `+0x1a`; rows with value > 50 are skipped; weight = `tableA[i] - (cnt / *(*(0x2c7e0a0+0x128))) * tableB[min(i, |tableB|-1)]`, zero if `cnt >= *(0x2c7e0a0+0x140)`, floored at 0. Random weighted pick, index stored at `ui+0x94`. If the sum is 0 (no rows, or all full) it re-requests a page up to `*(0x2c7e0a0+0xf8)` times (`ui+0xd4`), then an error dialog and UI state 0 (`0xa737a2-0xa738ec`). Then `0xa73a90` calls `0xa83e20` with `&row[idx]+0x10` (`0xa73a9d-0xa73ab8`) and sets UI 6.
5. UI 6 (`0xa724e5`): done as soon as `obj+0x7d0 != 0` and the global flags pass; if matching state is 0x2a it retries lobby selection up to `*(0x2c7e0a0+0xfc)` times (`ui+0xd0`), then fails (`0xa7257a-0xa725ac`).

All values in `*0x2c7e0a0` (world/lobby weight tables, thresholds, retry limits, divisors at +0x70 and +0x128) are game config loaded at startup (built by the constructor at `0xbc678`, filled later). The code divides by `+0x70` and `*(+0x128)`; zero there would fault. Their contents are NOT_VERIFIED. A server that returns one world and one lobby with zero members passes the weight code as long as `tableA[0] > 0`, which is NOT_VERIFIED.

## 3. Response events

Common: the callback ends every event at `0xa7a685` by inserting `(requestId -> errorCode >= 0)` into the std::map at `obj+0x808` (head node `obj+0x810`, key u32 at node `+0x1c`, flag at `+0x20`). That insert takes no lock. Each handler is reached with `arg r9 = obj`.

### 0x0002 GetWorldInfoList (`0xa79f8e`)
- errorCode < 0 or `data == NULL` -> `0xa7a8f0(obj, 0x2a, errorCode, msg 0x12048fb)`.
- `data+0x00` ptr to rows, `data+0x08` u32 count (only the low 32 bits are read). Rows are contiguous, stride 0x28. The game copies each row verbatim into the vector at `obj+0x7e8` (begin) / `0x7f0` (end) / `0x7f8` (cap); end is reset to begin first.
- Fields later read per row: `+0x08` u32 worldId (compared against `obj+0xc8`, copied to `obj+0x60`); `+0x0c` u32 lobby count (`obj+0x64`, bounds the paging in state 0x10); `+0x14` u32 population (weights, `obj+0x6c`). Other fields are copied but not read on this path.
- Then `obj+0x48 = 7` (`0xa7a0c7`), and if `obj+0x7d0 != 0` with the global online flags -> 0x17.
- Empty list (count 0): skips the copies, state 7. The UI then falls back to world id 0 (section 2b step 2). One row is enough.

### 0x0006 GetLobbyInfoList (`0xa798ac`)
- Only `data == NULL` is an error (`0xa7a16a`, msg `0x1204939`, state 0x2a). `errorCode` is not tested.
- `data+0x08` u32 count (low 32 bits), `data+0x10` ptr to rows, stride 0x50. Rows are appended (`obj+0xa8` begin, `0xb0` end, `0xb8` cap; end is reset only by the UI request sites, not by the paging in state 0x10). Then state 0x10 (`0xa799e0`). `data+0x00` is not read.
- Row fields the game reads: `+0x10` u64 lobbyId (passed to JoinLobby); `+0x1a` u16 member count (see weight rule above, values > 50 are skipped). Everything else is copied but unused on the entry path (other readers not found in `0xa70000-0xa86000`).
- State 0x10 (`0xa8153e`): `T` = world row `+0x0c` for the world whose `+0x08 == obj+0xc8`, else `obj+0x64`. With `rows = (obj+0xb0 - obj+0xa8)/0x50`: if `obj+0xc4 <= 0`, or `rows >= obj+0xc4`, or `obj+0xc0 + rows >= T` -> state 0x0f. Otherwise another page is requested with `+0x08 = rows + obj+0xc0 + 1` and `+0x0c = (obj+0xc4 - 20)` when that is below 21, else 20. Consequence: with the UI's initial `obj+0xc4 = 0x14`, the count goes 0. So if `T` is larger than the rows returned, the game re-requests forever (count 0, then -19 once `obj+0xc4` is reset to 1). Keep world `+0x0c` equal to the number of lobby rows returned (up to 20).
- `T = 0` (world says no lobbies) with zero rows: state 0x0f at once, but the lobby picker finds no row and the UI runs its retry/error path (section 2b step 4). Zero lobbies is a failure for this game.

### 0x0201 JoinLobby (`0xa79703`)
- errorCode < 0 or `data == NULL` -> `0xa7a8f0(obj, 0x2a, errorCode, "SCE_NP_MATCHING2_REQUEST_EVENT_JOIN_LOBBY = [%d](0x%x)")` (`0xa7a12a`). Lobby full or any server error lands here.
- `P = *(data+0x00)` (pointer to the lobby record). Reads: `P+0x10` u64 lobbyId -> `obj+0x7d0` (must be nonzero: zero means "not in a lobby" everywhere); `P+0x28` u16 own member id -> `obj+0x7d8`; `P+0x20` u64 count n and `P+0x18` ptr to u16[n] member ids -> copied into the vector at `obj+0x88` (end reset to begin first). Then state 0x14.
- No lock is taken. `P` and the array only need to live until the callback returns (they are copied).
- n = 0 still works but the next request then carries count 0 and a garbage pointer. Include at least the own member id.

### 0x7207 GetLobbyMemberDataInternalList (`0xa79833`)
- `errorCode` is not tested. `data == NULL` -> failure path described in section 1 (state 0x2a).
- `data+0x00` ptr to the first record, `data+0x08` u64 count. Records form a singly linked list: `+0x00` next ptr (NULL ends it). For each of `count` records the game calls `0xa7b4a0(obj, rec+0x20, rec+0x34, rec+0x10)`: `rec+0x34` u16 memberId; `rec+0x20` 20 bytes copied into the member (looks like a SceNpOnlineId); `rec+0x10` 16 bytes copied to member `+0x1490`. `0xa7b4a0` takes the mutex `(*(obj+0xd0))+8`, finds an existing member by u16 at struct `+0x1488` or allocates a 0x14a0-byte member in the first free slot of `obj+0x2c0[0..0x31]`, and for the record whose memberId equals `obj+0x7d8` (own id) stores its slot in `obj+0x450`. If no record carries the own id, `obj+0x450` stays 0 (NOT_VERIFIED whether that breaks the 0x17 loop).
- After the loop: `obj+0x48 = 0x16` and counter `0x2c83004 = 0`.

### 0x0202 LeaveLobby (`0xa799ec`)
Sets state 0x0d unconditionally (teardown; clears `obj+0x7d0`, `0x7d8`, rejoins state 8). Do not send it during entry.

## 4. Minimal answers that pass every check read above

1. ContextStart returns 0. Then deliver context event `0x6F02`, errorCode 0, never `0x6F01`.
2. GetServerId returns 0 and writes a u16 (any value, for example 1).
3. GetWorldInfoList: event `0x0002`, errorCode 0, data = `{rows*, u64 count}` with 1 row of 0x28 bytes: `+0x08` u32 worldId (any, for example 1), `+0x0c` u32 = 1 (lobby count), `+0x10` u32 = a max, `+0x14` u32 = 0 (population), `+0x00` ptr = 0. Zero rows also gets through, falling back to world 0.
4. GetLobbyInfoList: event `0x0006`, data = `{+0x08 u32 count = 1, +0x10 ptr to one 0x50-byte row}`. Row: `+0x10` u64 lobbyId nonzero, `+0x1a` u16 member count 0 (< 50, below the game's threshold), the rest zero. Request echo: worldId at +0, start 1 at +8, count 20 at +0xc; return exactly `T` rows.
5. JoinLobby: return 0 and write a nonzero request id. Event `0x0201`, errorCode 0, data `{P*}`, `P+0x10` u64 = the same lobbyId, `P+0x18` ptr to u16[1] = {own id}, `P+0x20` u64 = 1, `P+0x28` u16 = own id (for example 1).
6. GetLobbyMemberDataInternalList: return anything >= 0. Event `0x7207`, data `{rec*, u64 1}`, one record: `+0x00` next = 0, `+0x10` 16 bytes, `+0x20` 20-byte online id, `+0x34` u16 = own id.
7. Every response is delivered after the request call has returned, and after the caller's state store (see section 6).
8. No lobby event is needed: do not send `0x3203` (forces state 0x0d). `0xa201` (member joined) is optional and uses the same record layout as the 0x7207 records.

## 5. After the join

- Immediately after `0x0201`: state 0x14 (next tick: GetLobbyMemberDataInternalList), 0x15, 0x16 (`0xa82a10`), 0x17 (`0xa82af0` and `0xa831b0` every tick). The UI's own check is `obj+0x7d0 != 0`.
- NpAuth: `sceNpAuthCreateAsyncRequest` is at `0xa60ca9`, `sceNpAuthGetAuthorizationCodeA` at `0xa60d12`, delete at `0xa60d21` (title action 0x14 inside the title queue `0xa60120`); `sceNpAuthPollAsync` at `0xb97f4c`. None is called from the Matching2 object code (`0xa76000-0xa86000`) and none after the join. They run before Matching2 starts. No `sceHttp*` or WebApi call exists in `0xa70000-0xa86000`.
- Lobby event callback `0xa7e8b0` (ignores events when `ctxId != obj+0x44`): `0xa201` -> `0xa7b4a0(obj, data[0]+0x20, +0x34, +0x10)` (member joined); `0xa202` -> finds the member by u16 at `data[0]+0x34` and sets bit 0 of its `+0x1484` and `obj+0x46 = 1` (member left); `0x3203` -> sets state 0x0d, except when the state is 0x2a, or is 0x2b/0x2c with `obj+0x4c == 0x2a` (`0xa7e8ea-0xa7e936`). Nothing is required during or after the join.
- Lobby message callback `0xa7e950`: the function is a bare `ret`. Required: nothing.
- Signaling callback `0xa7eef0`: pushes a 16-byte record `{u64 subject, u16 event, u16 cause, u32 r8}` into a ring buffer at `obj+0x820` (capacity `obj+0x118c`, head `+0x1180`, tail `+0x1184`, count `+0x1188`), dropping the oldest when full, with no lock. Required: nothing on the entry path.
- Room event callback `0xa7e960` and room message callback `0xa7ec30`: room phase only.
- Context stop: shutdown (`0xa77750`) loops up to 300 times calling `sceNpCheckCallback` and `sceKernelUsleep` until `obj+0x44 == 0`; only context callback `0x6F03` clears it. A replacement must deliver `0x6F03` after `ContextStop`.

## 6. Threads and locks

- The callbacks do not need a particular thread. The game only calls `sceNpCheckCallback` in the shutdown wait (`0xa77750`) and the NpAuth poll (`0xb97f28`), so the Sony library is expected to run Matching2 callbacks on its own thread (the Initialize param carries a thread affinity `0x3f` and priority `0x100`).
- Locks the callbacks take: `(*(obj+0xd0))+8` in `0x7101` (held to `0xa79f55`), `0x103` (`0xa79c1a-0xa79cbf`), `0x7102` (`0xa79d78`), and inside `0xa7b4a0` (so `0x7207` records and lobby event `0xa201`). No lock in `0x0002`, `0x0006`, `0x0201`, `0x0202`, the context callback, the signaling callback, or the `obj+0x808` map insert. Lobby event `0xa202` reads `obj+0x2c0[]` unlocked.
- The update step holds a different mutex, `(*(obj+0xd0))+0x48`, from `0xa80d51` to `0xa81307` (states >= 5), and the title table mutex `(*0x2c825c8+0x30)+8` around `0xa812ac-0xa812f6`. The `0x0002`/`0x0006`/`0x0201` handlers write `obj+0x48` without either lock. So the only safe discipline is ordering, not locking:
  - Never call a callback from inside the request function. The caller stores the pending state after the call returns (`0xa813c5` state 6, `0xa819f5` state 0x0e, `0xa83f95` state 0x13, `0xa816b6` state 0x15). A callback that runs first sets 7/0x10/0x14/0x16 and the caller then overwrites it with the older value: permanent hang.
  - Deliver from a worker thread after a short delay (at least a few ms; the store is a few instructions after the return, but it runs inside the update mutex, so one full frame is safer). Serialize deliveries, one callback at a time, and keep `data` and every array it points to valid until the callback returns.
- Polling: the game polls only its own state word each tick, plus `*(0x2c82ff8)+0x100` and the `0x2a` state. It does not poll request ids or the `obj+0x808` map on this path.

## NOT_VERIFIED

- Contents of the `*0x2c7e0a0` config (weights, thresholds, divisors, retry limits) and the timeout seconds at `*(*0x2c82440)`.
- Real SDK names and widths of world/lobby/member row fields not read by the game (`+0x10`, `+0x18`, `+0x1c`, `+0x20` of world rows; most of the lobby row; member record fields beyond `+0x10`, `+0x20`, `+0x34`).
- Whether a `0x7207` list that omits the own member id breaks the state 0x17 loop (`0xa82af0`).
- Event `0x0006` and `0x0202` bindings are inferred from request/state pairing, not from a log string.
- Whether the UI object at `0xa72200` runs before or after state 5's own GetWorldInfoList in a live boot.
- Runtime behavior of any of this: no run was made.
