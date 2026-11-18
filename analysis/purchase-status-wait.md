# "Checking purchase status on PlayStation Store" wait (CUSA04687 1.17)

Static read only. VERIFIED = I read the instructions or data. INFERRED = deduced, not read directly.
Addresses are image offsets. Windows eboot dis: `work/analysis-cache/eboot.dis`.

## Bottom line

1. The dialog is not part of the 0xa5a2a0/0xa5ada0 NP gate. VERIFIED: its text is message group 40, item 2
   (`xbdata/menu/message_text.US_01.xb`, zlib stream at 0x17ae4, text at decoded 0x2918). Only two code
   sites select group 40 item 2 (entry offset `0x1e0`, count `0x1e4`, item offset `+8`): `0xc76b30`
   (call at `0xc76b60-0xc76ba6`) and `0xf17c3-0xf1821`. The gate never selects group 40.
2. The gate has already finished successfully when the dialog appears. VERIFIED: the purchase controller
   `0xc77c10` only reaches `0xc76b30` after `0x1361ee0 == 2`, `sceNetCtlGetInfo(14)` is non-empty,
   `0x2c905f0 == 1` and `0x2c8f338 == 2` (`0xc77d0e-0xc77d92`, `0xc77f44`). Failing any of them shows
   group 40 item 8 "Could not connect to PlayStation Store" instead (`0xc77dab-0xc77e02`).
3. While the dialog is up the game waits for ONE WebApi call: `GET /v1/users/me/entitlements?entitlement_type=service`
   in API group `sdk:entitlement`, sent by a worker thread, answered by `sceNpWebApiSendRequest2` +
   `sceNpWebApiReadData`. VERIFIED. Nothing else (no NP stub, no AppContent call) is polled.
4. No send was logged, so the request dies before `sceNpWebApiSendRequest2`. Candidate blockers, in the
   order the game reaches them (all INFERRED as to which one fires; the gates themselves are VERIFIED):
   a. the per-frame pump at `0xefa11` never runs or never pops the task (state words `mgr+0x8`, `mgr+0x50`);
   b. `0xecdee0` returns silently with no callback when the WebApi lib id `[0x2c8f310+0]` or context id
      `[0x2c8f310+4]` is -1 (`0xecdf11-0xecdf1c`). Those ids come from `sceNpWebApiInitialize` and
      `sceNpWebApiCreateContextA(lib, user=*0x2ccbdb4)` inside `0xecdd30` (`0xecde9d`, `0xecdebd`);
   c. `sceNpWebApiCreateRequest` returning < 0 (`0xece37f-0xece386`), or the `WebApiRequest` thread not
      starting (`0xea6c90` at `0xece40f`).
5. Timeout: even a dropped request ends the wait. VERIFIED: the pump arms a counter of 0xe10 (3600) frames
   (`0xefc2f`); at expiry it calls `0xecdd30` again, pops the task and calls it with flag 0, which shows
   group 40 item 4 "Failed to retrieve purchase information ... Attempt again?" (`0xc784a6`). A dialog that
   never changes means fewer than 3600 game frames ran, or the pump (4a) never runs.

## Imports whose answer matters (in call order)

| Order | Import (PLT) | Game arguments | Needed to move on | Runtime today (INFERRED from source) |
|---|---|---|---|---|
| 1 | sceNpWebApiInitialize (0x10fe4e0), in `0xecdd30` | (`*0x13643a0` = http ctx id from `0xc0fa5`, pool 0x20000) | return >= 0, stored at `[0x2c8f310]` | `lib_init_id` (runtime_services.c:1190) returns a new positive id |
| 2 | sceNpWebApiCreateContextA (0x10fe4f0) | (lib id, user `*0x2ccbdb4`) | return >= 0, stored at `[0x2c8f310+4]` | golf `webapi_context` (runtime_golf.c:80) needs `local_account`; lib id must be < 0x8000. Without `local_account`, `runtime_np.c:270` returns SIGNED_OUT and the game keeps ctx -1 |
| 3 | sceNpWebApiCreateRequest (0x10fe500) | (ctx, `"sdk:entitlement"`, `"/v1/users/me/entitlements?entitlement_type=service"`, method 0 (GET; method arg is `[req+0x50]`, 0 for type 4), NULL content, &reqId at `[req+8]`) | return >= 0 | golf `webapi_create` ok; services/np tables return SIGNED_OUT |
| 4 | sceNpWebApiSendRequest2 (0x10fe510), worker thread | (reqId, data=`[req+0x30]`, size=`[req+0x38]`, &respInfo at `req+0x1080`) | return >= 0; `*respInfo` = HTTP status | golf `webapi_send2` answers `{"entitlements":[],"start":0,"size":0,"total_results":0}`, status 200 (`runtime_golf.c:142`) |
| 5 | sceNpWebApiReadData (0x10fe480) | (reqId, buf+off, 0x80000-off) | bytes copied, then 0; negative aborts and sets status -1 | golf `webapi_read` copies the body then 0 |

Stale map: `analysis/plt-import-map.json` still flags sceNpCreateRequest, sceNpCheckNpReachability and several others
`implemented:false`. `runtime_services.c:1239-1241` implements them. Ignore that flag.

## Correction to the brief

The job at `0xb9aa20` calls `sceNpCreateRequest` (0x10fdbc0), `sceNpCheckNpReachability` (0x10fdc30, args
(reqId, `*0x2ccbdb4`)) and `sceNpDeleteRequest` (0x10fdc70), not `sceNpCheckNpAvailabilityA` (0x10fdbd0).
VERIFIED at `0xb9aa2d`, `0xb9aa45`, `0xb9aa5d`. It stores `2` if reachability returned 0, else `0`, in `*arg`
(`0xb9aa4a-0xb9aa55`). Runtime maps both names to `np_availability` (runtime_services.c:1240), so the answer is the same.

## Gate state machine (`0xa5a2a0` enter, `0xa5ada0` update)

Object (r15): `+0` state, `+4` queued-state bitmask (bit k = state k+1, lowest bit first; empty = finish and
reset via `0xa5a0f0`), `+8/+0xc` failure code pair, `+0x10` word-filter obj, `+0x18` show-messages flag,
`+0x20` sign-in obj, `+0x28` frame counter, `+0x30` Plus obj. Global instance pointer: `0x2c82420`.
Enter stores the new state, then dispatches on state-1 through the table at `0x11c83ac` (VERIFIED).
Update dispatches on `(obj+0)-1` through `0x11c83d0` (11 entries, VERIFIED).

| State | Enter (`0xa5a2a0`) | Update (`0xa5ada0`) | Next |
|---|---|---|---|
| 1 | `0xa5a2ea`: if `0x2c905f0==1` and `0x2c8f338==2` enter 10. Else `0xa5a62b`: alloc sign-in obj; `sceSigninDialogUpdateStatus` (0x10fe800) must be 0; `sceSigninDialogInitialize` (0x10fe820, 0 or 0x81350002 ok); `sceUserServiceGetInitialUser` (0x10fd160); `sceSigninDialogOpen` (0x10fe7a0). Failure sets +8=2 and shows an error. | `0xa5ade2`: UpdateStatus == 3 (finished): GetResult (0x10fe850), Terminate (0x10fe880). Result code 0 and ret >= 0 sets obj[1]. Waits until finished. | obj[1]=1: state 10. Else error (2,2), reset |
| 2 | `0xa5a316`: `*0x1361ee0 = -1`; schedule job `0xb9aa20` via `0xea71f0(0x2c9c428, fn, &0x1361ee0, 0)` | `0xa5ae4f`: `*0x1361ee0 < 0` waits. `==2`: `sceNetCtlGetInfo(14)`, non-empty string ok. Else counter `+0x28` +1 per call, at 60 error (1,...) `0xa5b202-0xa5b223` | next queued bit, or finish |
| 3 | `0xa5a341`: if `0x2c8245c==0` post request code 1 to object `0x2c82548` via `0xa62080`; else code 0x14 (`0xa5a3c1`) | `0xa5aee2`: wait until `0x2c82548` idle (`[0]==0` and its vector empty). If `0x2c8245c==0` needs `0x2c905f0==1`, `0x2c8f338==2`, else messages (3,3)/(3,4)/(4,3) | next queued bit |
| 4 | none (`0xa5ad6c`) | `0xa5af8f`: call `0xa6e2b0` | next queued bit |
| 5 | `0xa5a3ce`: alloc Plus obj; `sceNpCreateAsyncRequest` (0x10fe5b0, size 0x18, user `*0x2ccbdb4`); `sceNpCheckPlus` (0x10fe5f0, param 0x38: user, features=1). Failure: `sceNpDeleteRequest`, error (4,5) | `0xa5afd2`: `sceNpPollAsync` (0x10fe620) == 0, then delete request; authorized byte 0 opens `sceNpCommerceDialog*` (0x10fe5c0/5d0/600/5a0/610) | next queued bit, or error (4,1) |
| 6 | `0xa5a426`: start Matching2 through `0xa76c10`/`0xa7dfd0` unless reusable (`0x2c82ff8`) | `0xa5b029`: error (7,1) if `0x2c8f358==3 && 0x2c8f354==2` or matching `+0x48==0x2a`; else wait | next queued bit |
| 7 | `0xa5a517`: word-filter title ctx (`sceNpWordFilterCreateTitleCtxA`, 0x10fe550, user `*0x2ccbdb4`) | `0xa5b05e`: `sceNpWordFilterPollAsync` (0x10fe540) | 8 or 9 on result |
| 8 | `0xa5a57f`: report word-filter result (message group 0x22 or 5) | `0xa5b096`: wait until dialog manager `0x2ccbae8` closes | 9 |
| 9 | `0xa5a5ff`: tell object `0x2c72f10` (vtable +0x10, arg 2) | `0xa5b0cd`: wait `0x2c72f10+0x28 == 0` | 7 |
| 10 | no enter case (set directly) | `0xa5b0f6`: needs `0x2c905f0==1 && 0x2c8f338==2`; `sceNpSetContentRestriction` (0x10fdbe0); schedules job `0xb9adf0` | 11 |
| 11 | no enter case | `0xa5b179`: waits `0x2c8f358==3`, then `0x2c8f354 >= 2` ok | finish |

Cases 8 and 9 and state 10/11 details are not on the observed path; rows are VERIFIED reads, intent is INFERRED.
Callers pick a mask: boot-style callers set `+4 = 0x76` (states 2,3,5,6,7 after 1) at `0x6c0cf`, `0x6d6d5`, `0xa0a1f8`;
the purchase controller sets mask 2 or 3 (`0xc77cff`, `0xc77e83`), so it runs states 1 then 2 only.

## Purchase controller `0xc77c10` (VERIFIED unless noted)

Args: this (r14, state at `+8`), label or NULL, callback, userdata, bool. Callers: `0xefeda`, `0x35ed13`, `0xb4c4d1`, `0xce9413`.

| Step | Address | What |
|---|---|---|
| 1 | `0xc77c3b` | `this+8 != 0` returns (busy) |
| 2 | `0xc77cec-0xc77e8a` | no label and flag set: run the gate (mask 2/3) and set state 7 = waiting on gate. Gate per-frame at `0xf01c1`. Gate finished with no error goes to `0xf031c` |
| 3 | `0xc77d0e-0xc77d4b` | needs `0x2c8f2e0 != 0`, `0x2c905f0 == 1`, `[0x2c8f2e0+0x1d0] != 0`, `0x2c8f338 == 2`, `0x1361ee0` < 0 or == 2 |
| 4 | `0xc77d65-0xc77d90` | `sceNetCtlGetInfo(14)` success and non-empty |
| 5 | `0xc77ea..-0xc77f44` | collect every entitlement label of length 6 from map `*0x2c92690` into the pending vector (`0xc77f60`) |
| 6 | `0xc77f47` -> `0xc76b30` | show group 40 item 2 (`0xf38a20(0x2ccbae8, 0, text, 0xc)`), clear result vector, push task `0xc781e0` (functor vtable `0x1332e98`, type 0) on queue `*0x2c92698 + 0x30` (`0xc764d0`); state = 1 |

## Request pump (per frame, `0xefa11-0xefc53`) and completion

| Item | Detail |
|---|---|
| Queue object | `*0x2c92698`: `+8` state (0 idle, 1 in flight), `+0x30` deque, `+0x48` head index, `+0x50` count, `+0x58` frame timer |
| State 0 and count != 0 | front task `vtbl+0x10`: 0 means list request. Builds `"entitlement_type=service"` (`0x1211837`), request type 4, callback `0xc75ea0`, userdata mgr; calls `0xecdee0(0x2c8f310, req)`; sets timer 0xe10, state 1 (`0xefc2f`). Type 1 builds a per-label consume request (type 5, `/v1/users/me/entitlements/%s`) |
| `0xecdee0` | drops the request silently if `[0x2c8f310]==-1` or `[0x2c8f310+4]==-1`; path/group for type 4: `/v1/users/me/entitlements?%s`, `sdk:entitlement` (`0xece2d8`, `0x121911a`, `0x1219154`); thread `WebApiRequest` runs `0xece440` |
| Worker `0xece440` | `sceNpWebApiSendRequest2`, then `sceNpWebApiReadData` until 0 (cap 0x80000), sets `req+0x18 = 2`. Send failure writes status -1 |
| Response `0xc75ea0` | flag (ecx) nonzero fails. Else parse JSON: `size` (int), `entitlements` array of `{id, use_count, use_limit}`. Callback `queue head vtbl+0x18(task, ok)` |
| Timeout | state 1: timer-1 per frame; at <= 1 `0xecdd30` re-inits WebApi, task called with 0 (`0xefb2f-0xefbb8`) |
| Task `0xc781e0(ok, ud)` | ok=1: each pending label found in the response with `use_count != 0` stays pending (then consume tasks `0xc76cb0`, type 5, group 40 item 3 "You've purchased ..."); labels absent or count 0 are dropped. Pending empty: close all dialogs on `0xc783b0` (vtable +0x18, arg 1), `ud+8 = 0`, call stored callback. ok=0: group 40 item 4 retry dialog |

## Success and "nothing purchased"

- Nothing purchased (what the runtime already serves): status 200, body `{"entitlements":[],"start":0,"size":0,"total_results":0}`.
  The game reads `size` = 0, no array rows, calls the task with ok=1, the pending list empties, the dialog closes, `0x2c92698+8` returns to 0.
  Needs: `sceNpWebApiCreateRequest`/`SendRequest2`/`ReadData` as in the table, `*respInfo` status 200 (INFERRED: status 200 is not compared; only `ecx` flag and JSON parse decide).
- Something purchased: rows `{"id":"EN00xx","use_count":N,"use_limit":M}`; N != 0 triggers the consume request `PUT /v1/users/me/entitlements/EN00xx` (type 5, body `{"use_count":N}`) and the group 40 item 3 dialog.

## What to log next (no change needed to answer this)

1. Is `0x2c92698+8`, `+0x50` and `+0x58` moving? (pump alive)
2. Returns of `sceNpWebApiInitialize`, `sceNpWebApiCreateContextA` (and whether they print `local_account` is on), `sceNpWebApiCreateRequest` from caller `0xecdd30`/`0xece37f`.
3. Whether `scePthreadCreate` for `WebApiRequest` (`0xece40f`) runs.
4. Frame count since the dialog appeared (needs 3600 for the timeout path).

## Unresolved

- The caller condition around `0xef9a0` (which screen state runs the pump). The enclosing function start was not located.
- Whether `0xb995c0` (`0xb995f4`, `cmpl $-1, 4(0x2c8f310)` then `0xecdd30`) has already run by the time of the request.
- Sources of `0x2c905f0` (written at `0xc7add`, near `sceNetTerm`; likely "network initialized") and `0x2c8f338` (2 set at `0xa80d03` after sign-in dialog success, 1 at `0xa811cb`).
