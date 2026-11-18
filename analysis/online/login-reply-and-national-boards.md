# Login reply and the empty `gameapi_getboardlistnational` body

Static analysis of `eboot.dis` (image offsets) and `work/prepared-1.17/eboot.elf` (jump tables read at file offset image+0x4000). Nothing was run.

## Result

The empty payload is not caused by the login reply. It is caused by the URL scheme. The request encoder `0xec97d0` encrypts the payload and then drops the result whenever the target URL does not start with `https://`. In `server/make_discovery_fixture.py` every key except the ones listed explicitly defaults to `http://127.0.0.1:8765/nmg-us/replay-probe/<key>` (`PROBE_ROOT`, line 16, 32). `gameapi_getboardlistnational` is set to `https://` only when the fixture is built with `--empty-national-boards` (lines 45-46). Making that URL `https://...` fixes the empty body.

## Minimal login reply

The 24-byte reply already in use is a valid minimal login reply (little-endian, record header `u16 type, u16 words`, record length = 4 * words):

| Offset | Bytes | Record |
|---|---|---|
| 0 | `00 80 01 00` | 0x8000, 1 word, header only |
| 4 | `00 00 02 00  01 00 00 00` | 0x0000, 2 words, status u32 = 1 (1..3 = success) |
| 12 | `20 20 02 00  01 00 00 00` | 0x2020, 2 words, completion gate u32 = 1 (stored at ctx `+0x5e5e8`; below 4 is success) |
| 20 | `10 80 01 00` | 0x8010, 1 word, terminator |

Evidence: the cursor advances 4 * count at `0xb85e28`, `0xb865ef`; type switch at `0xb85e5c-0xb85e8f`; status read `0xb85e95`; `0x2020` store `0xb86074-0xb86082`; terminator returns state 4 at `0xb86041`; gate check `0xb6e617-0xb6e63c`; the loop runs up to 100 reads (`0xb6b8e3-0xb6b946`). The 0x0000 status record must come before the other records; unknown types fall to `0xb861ca`.

Optional records for a session that later requests can echo (all parsed by the common decoder `0xb85e00`, so any order between 0x0000 and 0x8010 works):

| Record | Size | Stored where | Used by |
|---|---|---|---|
| 0x0080 | exactly 65 words (4 header + 256 bytes). The handler copies 0x100 bytes from payload `+4` without a length check, so a shorter record over-reads (`0xb8621e-0xb86254`). | ctx `+0x1223b9` and global object `0x2c6b648` + `0x1f1b4aa`. This is the only writer besides the init clear at `0xf6983`. | Copied back as the `0x0080/65` record by slot 0x2f and 20+ other builders (`0xb554ac-0xb554ce`, `0xb555e5`). |
| 0x0083 | 2..252 words, NUL-terminated string, strlen at most about 740 (the target buffer is 0x3e9 bytes and the output is Base64 after Blowfish) | The handler pads the string to 8 bytes, encrypts it with the Blowfish-shaped cipher at ctx `+0x121a88`, Base64-encodes it, and strcpy's it to ctx `+0x121e81` (`0xb86259-0xb86417`). | Copied back as the `0x0083` record, padded to 4 bytes with the pad count as the fill byte (`0xb554d3-0xb55615`). |
| 0x2032 | 2 words, first byte stored at `0x2c6b648` + `0x1f1d80f` | Nonzero forces the next login `0x2032` to 1 and enables slot 0x1f | Not needed by slot 0x2f. |
| 0x0086-0x0088 | 132, 8, 8 bytes with headers | ctx `+0x1224c4`, `+0x122548`, `+0x122550` | Slot 0x1f only. |
| 0x2022, 0x2031 | 2 words / string | ctx `+0x1224bc`, `+0x5e5f0` | UI message only. |

Session key: not from the login reply. The cipher key is a static blob copied at init (`0xf6b4c-0xf6b81`: key at `0x1361ec0` into the context at `+0xe8` via `0xec87e0`, IV words at `0x1048/0x104c` zeroed, so ECB). Slot 0x2f needs no session id or token field beyond the 0x0080 and 0x0083 echoes.

Slot 0x2f does not fail if 0x0080/0x0083 were never delivered. The builder copies whatever is in those buffers (zeros and an empty string), so the request is still non-empty: 0x8000, 0x0010, 0x0050, 0x0080/65, 0x0083, 0x4a40, 0x8010. A server that wants a real session must put 0x0080 (65 words) and 0x0083 in the login reply. NOT_VERIFIED: that the deployed login reply carries them; the only observed writers of those buffers are the common decoder handlers, and the boot-time requests before login send none.

Recommended full reply (not required to get a body): `8000/1`, `0000/2 (1)`, `2020/2 (1)`, `0080/65 (256 bytes)`, `0083/N (token string, NUL, pad to 4)`, `8010/1`.

## 1. Where slot 0x2f's payload is built

1. Action `0x26` at `0xa61366`: screen state `[[0x2c9a068]+0x2ec48] == 0x10` skips the request (`0xa61374`). Otherwise it zeroes selector `+0x122390` (and `+0x1223a0`, `+0x1223a4 = -1`), sets `esi = 0x2f`, and jumps to `0xa607bd`, which calls `0xb501c0` with rdi = `[0x2c8f2e0 + 0x10378]`.
2. `0xb501c0`: slot `0x2f` is above `0x29`, so it goes to `0xb502ac`. If object byte `0x120` is 0 the call takes the offline path through `0xb5b980` and returns failure. With `0x120` set it falls to `0xb5020f`. A nonzero in-flight state `+0x5f270` returns 0; otherwise `0xb5023d` stores the slot at `+0x121a80`, reads the network tick, and runs the global state checks (`0x2c8f338`, `0x2c905f0`, `0x2c8f354`, `0x2c8f358`, `0xb50347-0xb50528`). The request was observed, so these passed. `0xb50528` sets `+0x5f270 = 1`, clears per-request state, and jumps through the table at `0x11cd83c`: entry `0x2f` is `0xb55448`.
3. `0xb55448-0xb55649` builds the payload at `+0x5f274`: `0x8000/1` then `0x0010/5` (`CUSA04687_00`, three bytes of 3), `0x0050/2` (language `[0x1361edc]` + 1), `0x0080/65` from `+0x1223b9`, `0x0083` from `+0x121e81`, `0x4a40/2` (selector from `+0x122390`), `0x8010/1`. It stores the end pointer at `+0x7f278`, loads the URL from `+0x5dc68`, and jumps to `0xb5a6da`.
4. `0xb5a6da` calls `0xb5d300`. Slot 0x2f is not in the `%s%llu&n=%d&s=1` set and has no "GET" in the URL, so `0xb5d3ae` copies the URL to `0x2c8f250` unchanged. Length is `[+0x7f278] - (obj + 0x5f274)` and it tail-calls `0xec97d0(obj, resp +0x7f280, body, len)` (`0xb5d36c-0xb5d38b`). So the title-side payload is complete and nonzero at this point.
5. The empty body appears inside `0xec97d0` at `0xec982f-0xec985f`. It calls strncmp (`0x10fd100`) on `0x2c8f250` against `0x1218e93` (`https://`, 8 bytes) and does `setne 0x118(%r13)`. Equal: `0xec99de` appends the payload bytes one at a time to the std::string at obj `+0xf0`. Not equal: object byte `0x118` is set, the payload is copied to a stack buffer, padded with `0x04` to 8 bytes, encrypted in place with the Blowfish-shaped rounds (`0xec9865-0xec99cc`), and the code jumps to `0xec99d2` and restores the stack. The ciphertext is never appended. The part string stays empty (cleared at `0xec9842-0xec984d`).
6. The framing that remains is `--xYzZY\r\n` (9) + `Content-Disposition: form-data; name="p"\r\n` (42) + `\r\n` (2) + empty payload + `\r\n` (2) + `--xYzZY--\r\n` (11) = 66 bytes, matching the observed body (`0xec9a73-0xec9acd`, `0xec9b48-0xec9b74`, `0xec9d1e-0xec9d43`).

Not the cause: object byte `0x118` is not read by the slot 0x2f builder. It is the scheme flag set inside `0xec97d0`, and it is read again only by the completion handlers to decide whether to Blowfish-decrypt the response in place (login `0xb6b7b6`, server time `0xb6b49d`). A missing session buffer or a zero length would still produce a body with the title record, so none of those explains an empty part.

Retry: a failed completion goes through `0xb5b980` (retry counter `+0x12718c`, saved selector copy at `+0x127170`, backoff `+0x127168`, up to 2 retries after the first try) and resends the same request, so every retry has the same empty body. After that the queue aborts (action 0x33).

## 3. HTTP versus HTTPS

It decides everything for this symptom, and no other encryption context is involved on the request side.

- `https://` URL: plaintext records go into the multipart part. The response is read as plaintext (completion skips the decrypt loop because `0x118` is 0). This is the path of every request that worked (`ss.info` follow-ups, server time, property, login).
- Any other prefix (`http://`): request body is empty (bug in the original code path, as read), and a response is expected to be Blowfish-ECB encrypted with the static key (completions `0xb6b49d`, `0xb6b7b6`, `0xb6b94b` decrypt in place when `0x118` is set). Sony production URLs are all https, so this branch is dead in a shipped service.
- The runtime already supports mapping a guest `https://127.0.0.1:8765/...` URL to the local plain-HTTP socket (see `protocol.md`, server-time loopback). Do the same for `gameapi_getboardlistnational`.

## What to change

1. Rebuild the discovery fixture with `--empty-national-boards`, or set `urls["gameapi_getboardlistnational"]` to an `https://127.0.0.1:8765` URL for any run that reaches action 0x26 and later (the same applies to `gameapi_getnationalgamedata`, `getscoredistributionnational`, `getscorelistnational`, `getgamepropertyinfo` follow-ups, and every other key that still defaults to `PROBE_ROOT` over http).
2. Make sure the host bridge maps that exact guest URL to the local server, as for server time.
3. The server model expecting `0x0080` (65 words), `0x0083` and `0x4a40` is then correct for the request. The 24-byte login reply can stay as is.

NOT_VERIFIED: the global gate values at `0x2c8f338`, `0x2c905f0`, `0x2c8f354`, `0x2c8f358` and byte `0x120` at run time (inferred from the request being sent); the content of the 0x0080 and 0x0083 payloads in the deployed service; guest behavior on the national-board reply after the fix.
