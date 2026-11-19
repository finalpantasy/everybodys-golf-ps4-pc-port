# gameapi_getscorelist with appended account (session score list)

Static read of `work/analysis-cache/eboot.dis`, strings from `work/game-1.17-prepared/eboot.elf`, plus
`work/evidence/open-course-hole1-complete-1118.log`. No runtime trace. Extends `protocol.md` "Session score list"
and "Score registration and follow-up queries". Anything not read is UNVERIFIED.

## 1. URL builder

- One discovery key serves two request families: `gameapi_getscorelist` is copied to ctx `+0x5d268` (`0xb806c1`).
  - Daily event board, slots `0x07/0x08/0x09`: URL used as is (selectors `0xb5fe14`, `0xb58b65`). No account, 166..258 bytes.
  - Session list, slots `0x19/0x1b/0x1d`: selector `0xb60f96` (`leaq 0x5d268(%rbx),%rsi` then `callq 0xb5d300` at `0xb60fa0`).
- `0xb5d300` formats `"%s%llu&n=%d&s=1"` (string `0x120b1fa`) into the global URL buffer `0x2c8f250`
  (`0xb5d33c-0xb5d361`). Args: base URL (`rsi`), account = `*(0x2c8f2e0)+0x58`, counter = `0x2c8f240`.
  The counter is incremented after every formatted request (`0xb5d366`) and is shared by all gameapi POSTs, so `n` is the
  global request count, not a per-endpoint one.
- Slot test (`0xb5d30d-0xb5d33a`): state `ctx+0x121a80` of `0x03`, `0x21`, `0x19..0x1e`, `0x2b`, `0x39..0x3c` always formats.
  Other states format only if the base URL contains the literal `GET` (`0x120b1f6`, `strstr` at `0xb5d39a`).
- No `?account=` because the format has no separator. The base URL must end in `?account=` (or `/x?a=`) for a valid query.
  The observed run advertised the bare path: `server/make_discovery_fixture.py:45` sets `gameapi_getscorelist` to
  `DAILY_SCORE_PATH` (no suffix) when only the daily-score fixture is on. Lines 46-47 use `SCORE_BOARD_PREFIX`
  (`...gameapi_getscorelist?account=`) with `--empty-own-score` or `--score-registration`.
- Transport: the URL is `https://`, so the producer `0xec97d0` skips the body cipher (`0xec982f-0xec985f`, string
  `0x1218e93` = `https://`) and sends plain records inside the 66-byte multipart framing (`--xYzZY`, part `p`).
  The reply path likewise skips whole-response decrypt when byte `ctx+0x118` is zero (`0xb6d022`).

## 2. Request body (builder `0xb60c70`)

Signature: `rdi` ctx, `rsi` group string, `rdx` row limit (`-0x5c8`), `rcx` selector (`-0x5c0`). Callers: `0xb537a0`
(slots `0x19` and `0x1b`, shared tail `0xb5379a`) and `0xb5387a` (slot `0x1d`). Records are 4-byte words; the count
includes the header word. Written at ctx `+0x5f274` (`0xb60e7f-0xb60f81`).

| Record / count | Content | Evidence |
|---|---|---|
| `0x8000/1` | opener, 4 bytes | `0xb60e7f` |
| `0x0010/5` | `CUSA04687_00` + 3 bytes of 3, 20 bytes | `0xb60e89-0xb60ec6` |
| `0x0050/2` | language index (`[0x1361edc]`) + 1, 8 bytes | `0xb60dcf`, `0xb60e6c` |
| `0x0080/65` | 256 bytes copied from ctx `+0x1223b9`, 260 bytes | `0xb60d02-0xb60d1f`, `0xb60edb-0xb60eeb` |
| `0x0083/var` | session token string at ctx `+0x121e81`, NUL, padded to 4; count `=(((len+4)&~3)+7)>>2` | `0xb60d24-0xb60dc4`, `0xb60ef0-0xb60f12` |
| `0x4a00/2` | selector: 0 OneHole (slot `0x19`), 1 Daily (`0x1b`), 2 LongDrive (`0x1d`) | `0xb536a9`, `0xb53792`, `0xb5386f`, `0xb60f3a` |
| `0x4140/var` | group string, NUL, padded to 4 | `0xb60db2-0xb60e45`, `0xb60f44` |
| `0x4000/2` | value 1 | `0xb60f49` (`0x100024000`) |
| `0x4010/2` | row limit | `0xb60f6b-0xb60f7c` |
| `0x8010/1` | terminator | `0xb60f81` |

Fixed part: 4+20+8+260+8+8+8+4 = 320 bytes. Body bytes in the log add 66 framing bytes:
`434 = 66 + 320 + 0x0083 record + 0x4140 record`.

- No score, hole or stroke data. This request is a board query, not a submission. Only the group string and
  the row limit vary.
- Token: login stores a Blowfish+Base64 string at `+0x121e81` (`login-reply-and-national-boards.md`). The 8-byte
  fixture string `0_local` encrypts to 12 base64 chars, so the `0x0083` record is 20 bytes (UNVERIFIED that the guest
  held exactly this token in the run).
- Group string (`sprintf` at `0xb5369a`, `0xb53786`, `0xb53865`; args: ctx `+0x122398/+0x12239c/+0x1223a0` = Y/M/D, `+0x122390`
  and `+0x122394` = two small indices from queue item `+0x28/+0x2c`, stored at `0xa60ac4-0xa60ae0`):
  - slot `0x19`: `OneHole_%04d%02d%02d_%d_%d` (`0x120b086`), limit `>0 ? n : 100` (`0xb5369f-0xb536a6`)
  - slot `0x1b`: `Daily_%04d%02d%02d_%d_%s` (`0x120b0a1`), `%s` picks `0x1215c67` when `+0x122394 > 9`, else `0x1215c63` (`0xb53731-0xb53779`; which is `IN`/`OUT` UNVERIFIED),
    limit `>0 ? n : 200`
  - slot `0x1d`: `LongDriveContest_%04d%02d%02d_%d_%d` (`0x120b0ba`), limit fixed 5
- Size fit with the log: 434 = 66+320+20+28 means a 20-23 char group (OneHole or Daily). 442 = 66+320+20+36 means a
  28-31 char group, which only `LongDriveContest_YYYYMMDD_a_b` (29 chars) reaches. So the 434 runs are slots `0x19` and
  `0x1b` and the 442 runs are slot `0x1d` (inferred, not decoded from memory; UNVERIFIED which of `0x19`/`0x1b` is which).
- Why the log shows 3 groups x 4 identical posts (n=29..40, 51..58): see retry in section 3.

## 3. Response contract and guest behavior

Completions: `0xb6d00a` (slot `0x19`), `0xb6970d` (`0x1b`), `0xb67b29` (`0x1d`). Common record decoder `0xb85e00`.

- Transport: HTTP 200 required, buffer `0xa2800` (665,600) bytes at ctx `+0x7f280` (cleared `0xb60f5f-0xb60f61`).
  Max reply 665,600 bytes. Min 16 bytes (no-rows form). Every record is 4-byte aligned (count in words); no 8-byte
  alignment is needed because the HTTPS path skips the outer cipher (`0xb6d022`).
- Records in order: `0x8000/1`, `0x0000/2` status, optional `0x0072`, mandatory `0x0083` (`0xb6e6d4-0xb6e6e9`),
  optional `0x42e0` and `0x42f0` (tab-separated decimals, `0xb6e5e7-0xb6e612`, `0xb6e9c4-0xb6ead1`), optional `0x42d0`
  flag (`0xb6ead8-0xb6eaf9`), required `0x4200` row count and `0x4210` value, then rows, then `0x8010/1`
  (details and row layouts in `protocol.md`, "Session score list"). No `0x0060` in this family (slots `0x07-0x09` need it).
- Status field: `0x0000` record, 32-bit at offset 4. 1, 2 and 3 are success (`0xb85e95-0xb85e9f`, `0xb86087`, `0xb86208`).
  `0x90000310` is "completed, no rows": the completion checks `1227a4 == 0x90000310` (`0xb6d226`), clears
  the result (`0xb6d23d-0xb6d25d`) and ends the action through `0xb5c860`. A 16-byte reply
  `0x8000/1`, `0x0000/2 (0x90000310)`, `0x8010/1` is therefore the cheapest valid answer (as for own score).
- Row parsing (UNVERIFIED for the 0x19/0x1b/0x1d variants beyond protocol.md): `0x4200` count; per row `0x4250`,
  `0x4270` (32-bit), stats `0x4500..`, `0x0020` name, `0x0084` account decimal string, `0x4260` row end
  (`0xb79530-0xb79816`, `0xb7a00d-0xb7a0aa`, `0xb7a8f0-0xb7a990`). Results go to a per-slot table at global ctx
  `+0x6ab924 + n*0x24` (`0xb6e7ed-0xb6e81b`, `n` = 0 One Hole...) then the common callback `0xb7b34e`.
- No response (current behavior): transport failure leaves byte `ctx+0x48` zero and enters `0xb5b980`. If `ctx+0x5f270 != 0`
  and the retry counter `ctx+0x12718c <= 2`, it saves the request (state `+0x12716c`, params `+0x122390..`), doubles a
  backoff (`+0x127168`: 1, 2, 4), increments the counter and re-sends (`0xb5b9e0-0xb5baf7`). That is 1 send + 3 retries = 4
  identical posts per action, matching the log (4 x 434, 4 x 434, 4 x 442). After the third retry it falls to the error
  dialog path (`0xb5bb29` onward, message format `0x120b93a`). UNVERIFIED which dialog or whether it blocks hole play.
- To satisfy: serve the `?account=` URL, answer 200 with the 16-byte no-rows reply, or the success form with `0x4200/2/0`,
  `0x4210/2/1`. The server already has this behind `--empty-own-score` (`golf_server.py:614-621`, `SCORE_BOARD_TARGET`);
  the observed run just used the bare URL with the runtime bridge not routing `...getscorelist<account>&n=..`.
  Alternative: add `?account=` in `make_discovery_fixture.py:45` too. The bare daily route would then also need the exact
  `...getscorelist?account=` mapping (already present, `protocol.md` line 633).

## 4. Score submission

- The submit family is separate and not `getscorelist`: `gameapi_registscore` (`0x120b38e`, selector `0xb6481c`),
  `gameapi_registscoredaily` (`0x120b3ff`, `0xb64813`), `gameapi_registscorelongdrivecontest` (`0x120b418`, `0xb648a3`);
  URL keys at ctx `+0x5d2e8`, `+0x5d7e8`, `+0x5d768`. Dispatch slots `0x1a` (`0xb536b0`, OneHole), `0x1c` (`0xb537aa`,
  Daily), `0x1e` (`0xb53884`, LongDrive). Body builders `0xb63a30-0xb63c90` (OneHole), `0xb63d93-0xb63eac` (Daily),
  `0xb646ea-0xb64a0d` (LongDrive), sender `0xb650d0`; completion `0xb65735`, success decoder `0xb841b0`. Layout
  (`0x4a00 0x4140 0x4141 0x4142 0x4143 0x4144 0x42b0 0x4500 0x4501 0x4600..0x460d`) is in `protocol.md` "Score registration".
  Same `%s%llu&n=%d&s=1` formatting (slots `0x19-0x1e`).
- Queue sites: register `0x1a` at `0xa60a0e`, `0x1c` at `0xa60b0f`, `0x1e` at `0xa60bbf`; the score-list slots `0x19`
  (`0xa609e4`), `0x1b` (`0xa60a7f`), `0x1d` (`0xa60b95`) are in the same switch. The mode field `+0x18` of the queue item picks
  them (table `0x11c8958`; modes `0x04`, `0x09`, `0x0d`).
- Not seen in this log: zero `registscore*` strings in `open-course-hole1-complete-1118.log`, only `getscorelist`. So in this run no
  registration was sent during or after hole 1. Whether the 9 Hole Round queues a register at hole end or only at round end
  is UNVERIFIED (the queue mode used by Open Course and the score-queue trigger were not traced here). Registration needs a
  prior session (`0x0083`) and a nonzero byte `(*0x2c6b648)+0x1f1d80f` (`0xa60e23`, set by login record `0x2032`, `0xb8652e`).
- Open question for the next static pass: find who sets queue mode `0x04/0x09/0x0d` after a hole and what "9 Hole
  Round" maps to; the `0x14020229` mask at `0xa608b1`/`0xa60991` (modes 4, 7, 9, 13, 21, 30, 32) only picks the
  date/limit source, not the mode.
