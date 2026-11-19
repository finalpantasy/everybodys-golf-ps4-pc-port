# Title queue completion handler and the flag at 0x2c8245c

Static analysis of the 1.17 eboot (image offsets). Every claim was read from `eboot.dis` and the prepared ELF unless
marked NOT_VERIFIED. No runtime trace was taken.

## Summary

- `0x2c8245c` is the "title sequence completed" flag. It becomes 1 only on the third completion of the info-list
  request (action 5, HTTP slot 5, `gameapi_getinfolist`) inside the mode-1 run of the 14-action table at `0x1232a20`.
  No single server field sets it. The run must get past NpAuth, login and five more actions first.
- The three replies we already send (ss.info, server time, property info) satisfy their parsers by static trace. The
  stop is after property info. Static reading says property success advances to action `0x14` (NpAuth, `0xa60c54`).
  Since the runtime logs no NpAuth request, the property completion does not reach that advance. The break point needs
  one runtime probe (see "Where it stops").
- `--login-rejection` makes the run abort at login by design (login success needs gate `+0x5e5e8 < 4`, the rejection
  reply sets it to 4). With that flag the flag can never reach 1. See Q4/Q5.

## Q1. The handler

`0xa5d3a0` is `title_queue::on_event(this, event, result)`:
- rdi = title queue object (`*0x2c82548`). State (current action) at `+0`, action list (std::list, sentinel `+0x10`,
  size `+0x18`), pending-request vector `+0xf10..+0xf18`, info-list counter `+0xe78`, retry count `+0x1590`.
- esi = event id. Dispatched at `0xa5d455`: `esi - 0x8a`, bound `0xcf`, jump table `0x11c8460`, default `r14d = 0x1e`.
- edx = result code. Success events carry 0 (`0xb7b2e5` tail: `xorl %edx,%edx; call 0xb5c860`). Failure events carry
  the error in `obj+0x1227a4` (`0xb5b980`: `r14d = edx ? edx : esi`).
- Callers: ring-buffer dispatcher `0xb980fb`, vtable thunk `0xa5d370/0xa5d380` (`this+0x90`), `0x35ef6a`.

The switch value is the event id, not the action id. Events are produced by `0xb5c860(obj, ok, code)` using the
slot-to-event table at `0x11cda44` (`ebx = base | (ok == 0)`): even id = success, odd id = failure of the same slot.

| HTTP slot | Request | Success event | Failure event | Case target (ok / fail) |
|---|---|---|---|---|
| 0 | ss.info (discovery) | `0xe6` | `0xe7` | `0xa5d6d1` / `0xa5d721` |
| 1,2 | geteula | `0xea` | `0xeb` | `0xa5d818` / `0xa5fec6` |
| 3 | login | `0xec` | `0xed` | `0xa5d82a` (`r14d = 4`) / `0xa5fec6` |
| 4 | server time | `0xe8` | `0xe9` | `0xa5d771` / `0xa5d7c1` |
| 5 | info list | `0xee` | `0xef` | `0xa5d840` / `0xa5d89a` |
| 0x27 | property info | `0x136` | `0x137` | `0xa5de46` / `0xa5de96` |

Action ids (what the queue holds; `0xa60120` jump table `0x11c87a0`, state = action):

| Action | Target | What it does |
|---|---|---|
| `0x01` | `0xa607ef` | `0xb501c0(cfg, slot 0)` ss.info GET |
| `0x07` | `0xa608e5` | slot 4 server time |
| `0x0f` | `0xa60b19` | slot `0x27` property info |
| `0x14` | `0xa60c54` | `sceNpAuthCreateAsyncRequest` (`0xa60ca9`), `sceNpAuthGetAuthorizationCodeA` (`0xa60d12`, scope `psn:s2s`). A negative return goes to `0xa6027f`, state `0x33`. |
| `0x04` | `0xa60863` | login (slot 3). Needs `*0x2c8f320 != 0` and `[0x2c8f320+8] != 0` (auth code), else state `0x33`. |
| `0x05` | `0xa608c0` | slot 5 info list. Request index = `obj+0xe78` (`0xa608d3`). |
| `0x13` | `0xa60c23` | slot `0x1f` user status, gated by byte `0x2c6b648+0x1f1d80f` |
| `0x26` | `0xa61366` | slot `0x2f` (meaning NOT_VERIFIED) |
| `0x25,0x27,0x28` | `0xa612ef,0xa613f0,0xa61427` | local calls (`0xa505d0`, `0xa546d0`) and/or requests, not traced |
| `0x10` | `0xa61cac` | no body (returns); the `0x33` cleanup `0xa617f2` looks for it. How it advances is NOT_VERIFIED. |
| `0x33` | `0xa617f2` | abort: clears the action list (`0xa6025c`), then state `0x1d`. Entered from `0xa5fec6` (`esi = 0x33`). |
| `0x34` | `0xa61827` | success terminal: `obj+0x20 = 1`, `obj+0x1590 = 0`. Entered by `0xa632f0` when the list is empty. |

Cases asked about:
- Event `0xe6` (`0xa5d6d1`): stamp time into `0x2c82460`, then `0xa5e7ca`: abort via `0xa5eb94` if `[cfg2+0x124] != 0`
  or `[cfg2+0x5c750] != 0x4f6` (client version 1270 from `client_ver1`; protocol.md, `0xb7d2c8`). Otherwise `r14d = 1`, advance.
- Event `0xe8` (`0xa5d771`): stamp `0x2c82488`, `r14d = 7`, advance (`0xa5e8c1`).
- Event `0x136` (`0xa5de46`): stamp `0x2c82490` (`0xa5ec2b`), `r14d = 0xf`, advance (`0xa5ec32`).
- Events `0xee`/`0xef`: Q2.
- Advance logic (`0xa5fea3..0xa5fece`): empty list calls `0xa632f0`; otherwise it requires `[obj] == r14d` and list head
  action `== r14d` (`0xa5feaa..0xa5feba`) and then calls `0xa632f0`; any mismatch calls `0xa60120(obj, 0x33)`.
  `0xa632f0` pops the head and dispatches the next head through `0xa60120`, or state `0x34` when empty.
- Top of the handler (`0xa5d3d0..0xa5d455`): `edx|1 == 0x80000201` sets `0x2c82460 = 1` and clears the flag (`0xa5d3e7`).
  `edx|1 == 0x90000115` clears the flag (`0xa5d3ff`) and, if `obj+0x40` is not 0 or 0x12 and `obj+0x1590 <= 2`, clears the
  action list and re-submits the saved request (`obj+0x28`), up to 3 times.

## Q2. Counter `obj+0xe78` and the flag

- Event `0xee` (info list success), `0xa5d840 -> 0xa5e970`: `ecx = [obj+0xe78]`, `r12 = sext(ecx)`,
  `0x2c82460[8 + r12*8] = stamp`, `r14d = 5`, `[obj+0xe78] = ecx + 1`, `flag |= (ecx > 1)` (`0xa5e977..0xa5e999`).
  No condition on the result code.
- Event `0xef` (info list failure), `0xa5d89a -> 0xa5e9f2`: stamps the same slot. If `ebx == 2` (ebx = edx = the result
  code of the failed request) it does the identical increment (`0xa5ea03..0xa5ea27`). Any other code goes to `0xa5ea3d`,
  state `0x33` abort. Where code 2 comes from is NOT_VERIFIED. Success replies carry 0, and status record values 1..3 parse
  as success (`0xb86208`), so 2 is probably an app-level "no data" code.
- `r12` indexes the per-category fetch-time array at `0x2c82460` (28 qwords, filled from `0x11b5740` at `0xa5d675`; slot 0 =
  ss.info time). Slot `1 + counter` holds the info-list timestamp.
- The flag is set when the old counter was >= 2, which is the third increment (counter 2 to 3). The first two never set it.
  The `or` keeps it once set.
- The counter is also the info-list category index in the request (`0xa608d3`), so the three fetches are categories 0, 1, 2.
- Reset: copied from the request struct at run start (`0xa62bc2`, `0xa62e7e`: `obj+0xe78 = req+0xe50`; the controller
  memsets the request to zero at `0xa5a35f`/`0xa5a69d`). Also set to 0/1/2 by three single-action-5 blocks at `0xa67a94`,
  `0xa67b00`, `0xa67b6c` inside the idle-state request processor `0xa660a0` (their mode ids are NOT_VERIFIED).
- Mode-1 run: the table at `0x1232a20` is `01 07 0f 14 04 26 28 25 27 10 05 05 05 13` (u32 each, 14 entries), appended at
  `0xa63562..0xa63612`. It has three action-5 entries, so the third completion sets the flag, then action `0x13` runs.
- The flag is cleared at `0xa5d3e7`, `0xa5d3ff`, and `0xa5eb94`. `0xa5eb94` is the shared abort
  (`movb $0,0x2c8245c; jmp 0xa5fec6`). It is reached from the ss.info checks above, event `0xe7`, and the `0xa5eb0d` case.

## Q3. What each reply must satisfy

All three go through the per-slot HTTP completion code (`0xb5c860` posts the result). The record reader is
`0xb85e00(obj, &cursor, expected_id)`: header `0x8000` (always accepted), a status record id `0x0000` (values 1..3 =
success; negative codes store `obj+0x1227a4` and fail), an optional `0x72` record (a missing `0x72` returns 0), then the
slot-specific records. A missing mandatory record calls the failure handler `0xb5b980`. An HTTP-level failure
(`obj+0x48 == 0`) retries up to 3 times (`0xb5b9e0..`); a parse failure does not retry and posts the failure event at once.

| Reply | Our bytes (`golf_server.py`) | Parser requirement | Verdict |
|---|---|---|---|
| ss.info | 7656-byte fixture | decoder keys incl. `client_ver1`; handler needs `[cfg2+0x124]==0` and `[cfg2+0x5c750]==0x4f6` (`0xa5e7ca..0xa5e7ee`) | passes if the fixture has `client_ver1 = 1270` (`make_discovery_fixture.py:64` sets it) |
| server time | 28 bytes: `8000/1`, `0000/2/1`, `5000/3` + 8-byte date, `8010/1` | slot 4 parse (`0xb6b49d`): header, status, optional `0x72`, record `0x5000`: BCD year/month/day at `+4..+7` and BCD hour/minute/second at `+8..+0xa` (`0xb860db–0xb86194`) converted to RTC ticks; stores offsets at `cfg2+0x10518/0x10520` (`0xb865c2`) | satisfied; a normal success, not "not modified". |
| property info | 24 bytes: `8000/1`, `0000/2/1`, `7603/2/1`, `8010/1` | slot `0x27` parse (`0xb675fa`, `0xb6770b..0xb67797`): header, status, optional `0x72`, then record `0x7603`. Value `== 1` jumps to `0xb73053 -> 0xb7b2e5`, the success tail. Value != 1 needs the full `0x7600/0x4290/0x7605/0x7601` update (`0xb6eb4c..`). | `7603 = 1` is the "cached, no update" success, not a failure. The `0x8010` terminator is not checked on this path. |

The success tail `0xb7b2e5` also clears the byte at `cfg+0x10554` and posts the success event with result 0.

`0xa5e83c..0xa5e879` (event `0xe7`, ss.info failure): `strcmp(cfg+0x10554, "P-130183")` (string at `0x1204344`), then
`strcmp(cfg+0x10554, "P-130190")` (`0x120434d`). `cfg+0x10554` is the on-screen error code built by `sprintf("%c-%s")`
(`0xb656aa..0xb656c8`). Both outcomes jump to `0xa5eb94` (`je 0xa5eb94`; the fall-through `testl; jmp 0xa5eb94`), so the compare
changes nothing: an ss.info failure always clears the flag and aborts.

## Q4. What comes next, and the gate

After property info (`0x0f`): action `0x14` NpAuth (`0xa60c54`), then `0x04` login, `0x26`, `0x28`, `0x25`, `0x27`, `0x10`,
`05 05 05`, `0x13`.

- NpAuth: `sceNpAuthCreateAsyncRequest` (id stored at `*0x2c8f320`), then
  `sceNpAuthGetAuthorizationCodeA(id, {size 0x20, user=*0x2ccbdb4, client=cfg2+0x60, scope "psn:s2s" at 0x1218f55}, code at
  0x2c8f320+8, issuer at +4)`. Both must return >= 0. The runtime logs `Runtime: NpAuth request created`
  (`runtime_golf.c local_auth_create`); `local_auth_poll` completes it.
- Gate to enqueue: none beyond the list. The action list is appended unconditionally for mode 1 (`0xa63521..0xa63612`). The
  request is refused earlier by `0xa62080` only if `0x2c8f358 == 3 && 0x2c8f354 == 2` (`0xa620c9..0xa620e6`). The measured
  values `0x2c8f354 = 1`, `0x2c8f358 = 3` pass.
- Login (`gameapi_login?account=..&n=..&s=1`, slot 3): needs a nonempty code at `[0x2c8f320]+8` (`0xa60879`). Success needs
  gate `cfg2+0x5e5e8 < 4` (protocol.md "Login and server time"). The `--login-rejection` reply is `0x2020 = 4`, so login
  completes as failure (event `0xed`) and aborts the run.
- The flag needs three info-list fetches (categories 0, 1, 2) in the same run, not repeated server-time syncs.

## Q5. Smallest legitimate change

There is no single reply field. For `0x2c8245c = 1`:
1. Property success must advance the queue (statically it does). Confirm with the probe below.
2. NpAuth must complete (runtime answers exist).
3. Login must succeed: serve a login reply without the `0x2020 = 4` rejection (drop `--login-rejection`, or reply with
   `0x2020 < 4`). The other records slot `0x1f` needs are NOT_VERIFIED.
4. Actions `0x26, 0x28, 0x25, 0x27, 0x10` must complete (requests and success replies NOT_VERIFIED).
5. Three `gameapi_getinfolist` replies must parse as success. The `--empty-notices` reply matches the parser
   (`8000, 0000/1, 0083 "local", 3000/0, 8010`). `0x0083` is mandatory: only `0x72` is optional.

If the stop is right after property, the smallest fix is the single guest-side step that breaks there, not a server field.

## Where it stops (NOT_VERIFIED, needs a runtime probe)

Static candidates after a property reply with HTTP 200:
- A. Event `0x137` (parse failure) to `0xa5de96`, then `0xa5fec6`, state `0x33`. No retry on parse failures, which fits
  "only three requests".
- B. Event `0x136` but `[obj] != 0xf` or list head `!= 0xf` at `0xa5feaa..0xa5feba`, then `0xa5fec6`.
- C. `0xa632f0 -> 0xa60120(0x14)` and `sceNpAuthCreateAsyncRequest` returns negative (`0xa60cb0`). The runtime would log the
  create line, so this is unlikely given the observation.

Probe: `GOLF_PEEK="*2c82548:4,*2c82548+18:8,2c8245c:1"` at 50 ms. State `0xf` then `0x14` means NpAuth runs. State `0x33`
then `0x1d` means an abort at the property step. To split A from B, log hits at `0xa5de96` (A) versus `0xa5feaa` (B).
