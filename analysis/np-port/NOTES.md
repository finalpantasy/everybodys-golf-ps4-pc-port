# NP port draft: notes

Files: `np_additions.c` (PART A for `runtime_np.c`, PART B for `runtime_services.c`), `exports.txt`
(two tables, one per file), `import_names.txt` (188 lines, NIDs recomputed with SHA1+suffix: all 210
requested names matched; 9 were then dropped as already present and 13 are unresolved, see below). Syntax-checked only: the code was
compiled with `clang -fsyntax-only -Wall -Wextra -Werror` against a stub harness (current
`runtime_np.c` head + stubs for the services helpers). Nothing was linked or run (NOT_VERIFIED at runtime).

Source key: S = existing runtime files, P = shadPS4 main (`src/core/libraries/np/*`, `np_error.h`),
R = RPCS3 `cellRudp.h`, C = eboot call site (static disassembly only). driveclub-recomp implements
none of these names.

Dropped because they already exist in the tree while this was written (`runtime_np.c`/`runtime_golf.c`):
`sceNpLookupCreateTitleCtxA`, `sceNpGetOnlineId`, `sceNpGetAccountCountryA`, and the six `sceSigninDialog*`.

## Counts (implemented / requested, after the drops)

| library | impl | | library | impl |
|---|---|---|---|---|
| NpTus | 46/46 | | NpSignaling | 9/9 |
| NpScore | 22/22 | | NpAuth | 4/4 |
| NpMatching2 | 28/28 | | NpCommerce | 2/2 |
| NpUtility | 13/14 | | NpCommon | 1/1 |
| NpWebApi | 13/13 | | NpManagerForToolkit | 3/3 |
| NpManager | 8/10 | | NetCtlForNpToolkit | 3/3 |
| NpTrophy | 6/9 | | Rudp | 14/14 |
| NpProfileDialog | 6/6 | | GameCustomDataDialog | 7/7 |
| InvitationDialog | 2/2 | | ImeDialog | 1/1 |
| SigninDialog | 0/6 (exists) | | NpSns, NpSnsFacebookDialog, UserServiceForNpToolkit | 0/10 |

(NpUtility and NpManager each lose one to the existing-export skip.)

## Convention used

Families whose arguments never change the offline answer use a `(void)` helper (`community_no_id`,
`signed_out`, `matching2_no_context`, `ok`), as the existing Tus/Score/Matching2 entries do. The SysV
ABI ignores extra arguments. The real argument list is in the contract comment. Real prototypes are
written out where an argument decides the result (title/user/matching context creation, request id
checks, callbacks, dialogs).

## Per library

- **NpTus** (P np_tus.cpp, S): `CreateNpTitleCtx(label, NpId*)` null NpId INSUFFICIENT_ARGUMENT, bad
  label INVALID_ARGUMENT, else SIGNED_OUT. All 45 request calls (incl. VUser, AVUser, CrossSave,
  Friends, `sceNpTssGetData`) INVALID_ID, because no request can exist.
- **NpScore** (P np_score.cpp, S): `CreateNpTitleCtx` as Tus (P order: label first). Ranking, game data,
  board info, record calls: SIGNED_OUT (as the existing Async forms). `SetPlayerCharacterId`: INVALID_ARGUMENT
  for pcId < 0 else INVALID_ID.
- **NpUtility** (P np_utility.cpp, S): non-A title contexts SIGNED_OUT (null NpId INSUFFICIENT_ARGUMENT), request/ctx calls
  INVALID_ID, BandwidthTest InitStart/GetStatus/Shutdown SIGNED_OUT (P stubs return OK, not copied),
  Abort OK. C: `sceNpLookupCreateTitleCtxA` at 0xa8b263 takes the user id from a global, stores the
  result only when >= 0; every `Lookup*Delete*` is guarded by id >= 0, so a failed create is harmless.
  `sceNpLookupPollAsync` callers (0xf070b, 0xa87389) are also guarded by id >= 0. Argument lists of BandwidthTest: NOT_VERIFIED.
- **NpManager / ForToolkit** (P np_manager.cpp, S, C): `sceNpCreateRequest` (sync id via `np_create(0)`),
  `sceNpCheckNpReachability` (= `np_availability`), `sceNpCheckNpAvailability(req, onlineId*)`
  (INVALID_ARGUMENT / USER_NOT_FOUND), `sceNpGetUserIdByAccountId`, reachability callback (once), toolkit
  state callback register/unregister/check, InGameMessage non-A (SIGNED_OUT) and `GetMemoryPoolStatistics` (OK, nothing written).
  C: 0xb9aa2d/0xb9ae2a call `sceNpCreateRequest` (> 0 used as id, <= 0 takes a failure path) then
  `sceNpCheckNpReachability(id, user)`: result 0 stores state 2, anything else 0. The game treats
  SIGNED_OUT as "unreachable". `sceNpRegisterNpReachabilityStateCallback` (0xb9af0b) result is ignored.
  `sceNpGetUserIdByAccountId` follows the comment above `np_account_id` (the one user); P returns
  SIGNED_OUT/USER_NOT_FOUND instead.
- **NpTrophy** (S trophy section, P np_trophy.cpp): AbortHandle OK (C: tail-call wrapper at 0xef78b0 passes `*handle`),
  ShowTrophyList OK after id checks, CaptureScreenshot SCREENSHOT_DISABLED (P returns OK from a stub),
  Game/Group/Trophy icons from the TRP via `trp_file`/`trophy_icon` (trophy icon needs the trophy unlocked, as P).
  Group-icon file name `GR%03d.PNG` and negative group ids: NOT_VERIFIED. Block must go after the `TROPHY_*` macros
  in `runtime_services.c`, since it uses its static helpers.
- **NpAuth** (P np_auth.cpp, S, C): `CreateAsyncRequest(param{size=0x18,...})` null/size checked; `GetAuthorizationCode`
  reuses `auth_code_a`; `GetIdTokenA` SIGNED_OUT; `PollAsync` INVALID_ID (no operation is ever left running;
  P returns that for an async request that never started). C: 0xa60ca9 creates the async request, calls
  `GetAuthorizationCodeA(id, param{0x20,...}, code, issuer)` and continues only if >= 0; the failure path deletes the
  request. The poll at 0xb97f4c runs only on that success path, so it is not reached while SIGNED_OUT is returned at once.
  `sceNpAuthDeleteRequest` is `ok_void` in the services table: fine.
- **NpCommerce** Show/HidePsStoreIcon: OK (runtime_np.c header rule). **NpCommon** `sceNpCmpNpId`: real compare (P).
- **NpWebApi** (P np_web_api*.cpp, S): `CreateContext(lib, onlineId*)` SIGNED_OUT; push-event and service-push
  filters created at library level (as the Extd filter); register callbacks = `webapi_callback_a`; unregister/delete OK;
  header calls REQUEST_NOT_FOUND after null checks; `GetMemoryPoolStats` writes zeros (pool size NOT_VERIFIED).
  P gives USER_CONTEXT_NOT_FOUND for unregister of a callback on a user context that does not exist; OK was kept to match the Extd sibling.
- **NpMatching2** (P np_matching2.cpp, S): `CreateContext(param{...,size@+32=0x28}, ctx*)` INVALID_ARGUMENT/SIGNED_OUT;
  everything with a ctx id INVALID_CONTEXT_ID; Get(Ssl)MemoryInfo OK (nothing written, struct layout NOT_VERIFIED).
  Argument lists of the `*Local`, `SetSignalingOptParam`, `SignalingGet/CancelPeerNetInfo*` calls: NOT_VERIFIED (P has none).
  C: the bring-up at 0xa7e0..0xa7e260 runs `sceNpMatching2Initialize`, `sceNpSignalingInitialize(0x20000,0x100,0x3f,0x4000)`,
  `sceRudpInit(pool,size)`, `sceNpMatching2CreateContextA`, then `sceNetCtlRegisterCallback`, then the lobby/room callback
  registrations. Every step jumps to one cleanup (0xa7e0cb) on a non-zero result, so CreateContextA failing with
  SIGNED_OUT ends setup cleanly and no other Matching2 call in the list is reachable.
- **NpSignaling** (P np_signaling.cpp): Initialize/Terminate keep a local flag (ALREADY_INITIALIZED/NOT_INITIALIZED),
  `CreateContextA` NOT_INITIALIZED, INVALID_ARGUMENT, SIGNED_OUT; all context calls CTX_NOT_FOUND. P's `DeleteContext` returns OK for
  a missing id; CTX_NOT_FOUND here because no id was ever issued.
- **Rudp** (R error codes: PS3 header, so the PS4 values are NOT_VERIFIED; arguments from the SDK API, NOT_VERIFIED; P has only OK stubs, not copied):
  Init/End/EnableInternalIOThread/SetEventHandler local state; CreateContext makes a local id; Bind INVALID_SOCKET (no socket can exist);
  everything else INVALID_CONTEXT_ID or NOT_BOUND. C: `sceRudpInit(ptr, int)` at 0xa7e1a3 (result tested < 0); Bind/Create/Initiate/
  Write/Read sit in the connection code (0xa74c..0xa7fa), reachable only after a matching room exists.
- **NetCtlForNpToolkit** (P netctl.cpp): Register (null cb/cid INVALID_ADDR, id), Unregister/Check OK.
- **Dialogs**: Profile (OpenA), GameCustomData (Open/OpenA, GetResult/A) use the runtime_np.c dialog framework: finish at once,
  cancelled, errorCode SIGNED_OUT. Needs the enum edit shown in `np_additions.c` (PROFILE, GAME_CUSTOM). `sceInvitationDialogOpen`/`GetResult`
  reuse `invitation_open`/`invitation_result`. Result layouts are from P headers; profile result `{s32 result,s32 userAction,void* userData}`
  with result = SIGNED_OUT is NOT_VERIFIED (invitation precedent). C: profile dialog at 0xef6aca..0xef6be0: Initialize/OpenA tested < 0,
  status 3 then GetResult (only tested < 0).
- **ImeDialog** `sceImeDialogAbort` (P ime_dialog.cpp): NOT_IN_USE 0x80BC0107 / NOT_RUNNING 0x80BC0105 / running ends as aborted (end status 2).
  C: 0xef5aa4 returns (result == 0). Found while checking: `ime_result` in `runtime_services.c` returns 0x80BC0101 for "not finished",
  but P's DIALOG_NOT_FINISHED is 0x80BC0106 (0x80BC0101 is INVALID_TITLE).

## Unresolved (left out)

- `sceNpSnsFacebookCreateRequest`, `GetAccessToken`, `DeleteRequest`; `sceNpSnsFacebookDialogInitialize/Open/UpdateStatus/GetResult/Terminate`:
  no source (shadPS4 has only UpdateStatus as a stub; not called by the eboot). Pattern if needed: friend-list dialog, request objects as NpAuth.
- `sceUserServiceRegisterEventCallback`, `sceUserServiceUnregisterEventCallback` (ForNpToolkit): no source, argument list unknown.
- `sceNpTrophyGetGameInfo`, `GetTrophyInfo`, `GetGroupInfo`: need TROP.SFM parsing (grade, hidden, group, name/description); the runtime
  keeps only unlock bits, 65 ids and optional names. P's layouts: `details{u64 size, ids, grade, hidden, name[128], description[1024]}` + `data{size, id, unlocked, timestamp}`.
  Not called by the eboot; callers are in the bundled NpToolkit PRXs (NOT_VERIFIED).

## Call-site coverage

Only 59 of the 210 names have a PLT stub in the eboot (`plt-import-map.json`); the rest (all Tus, Score, most Matching2/WebApi/Trophy/Utility
names) are imported by the bundled `libSceNpToolkit(2).prx` modules (`analysis.json` `bundled_modules`). Their callers were not disassembled
(NOT_VERIFIED): how the toolkit uses these results is unknown. Disassembly was of `eboot.elf` only.

## Where the offline model looks wrong for this game

1. `runtime_golf.c` (new) reports the user as signed in (`sceNpGetState`=2, online id, NpId, country, local WebApi). All SIGNED_OUT answers here
   (title contexts, `CreateContextA`, auth, reachability) become inconsistent with that mode. They need a switch on `runtime_golf_local_account()`.
   Reachability in particular: `sceNpCheckNpReachability` == 0 gives the game state 2 (reachable), so a signed-in claim and SIGNED_OUT here disagree.
2. `sceNpScoreCreateRequest` in `runtime_services.c` returns an id for any argument; P (and the model) give INVALID_ID for a context that cannot exist.
   `sceNpScoreSetPlayerCharacterId` here answers INVALID_ID for every id, including ids that call issued.
3. Signaling and Rudp initialize successfully while Matching2 context creation fails; the game tolerates it (cleanup), and a real signed-out console also behaves so.
