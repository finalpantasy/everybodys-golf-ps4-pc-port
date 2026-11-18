# Telemetry request loop (sceHttp, local title server)

Static analysis of `work/analysis-cache/eboot.dis`, 1.17. Addresses are image offsets.
VERIFIED = read in the disassembly or the runtime source. INFERRED = deduced, not read directly.

## Summary

The game sends the telemetry body in chunks of up to 0x800 bytes, one `sceHttpSendRequest`
call per chunk, but declares the full body length in `sceHttpCreateRequestWithURL`.
`http_send` in `runtime_net.c` accepts only a single call whose length equals the declared
length, and returns `HTTP_NETWORK` silently (no log line) for any other length. The game
then treats the request as failed (status 0), deletes it, and the result handler asks the
poster to re-post the same payload. That cycle repeats without end.

## 1. Functions

This is the `otg-dataposter` / `otg_gestalt` library (source string
`D:\Temp\otg_gestalt\otg-dataposter\ps4-dataposter\ps4-dataposter.cpp` at 0x115e5e8). It is
not the generic job client at `0xec9120`, which serves the title-server calls.

| Address | Role | Status |
|---|---|---|
| 0xb7f5xx (code at 0xb7f649-0xb7f850) | Telemetry client setup. Builds the URL in global buffer 0x2c83290: base from config `game_analytics_system_url`, else the string at 0x1206ab6 (`https://mingol.api.dev.wwsga.me/games/`), then the 36-char UUID at 0x1206a70, then `/telemetry`. Starts thread `OtgLogSendThread` (string 0x1206ae8, entry 0xad6330). | VERIFIED |
| 0xad6330 | Thread loop: while obj+0x38==1 { obj[8]->vtbl[0x10](16); obj[0]->vtbl[0x28](); usleep(0x3e80 = 16 ms) } | VERIFIED |
| 0x65680, 0x63b80 | Gestalt init. Creates two streams (index 0 and 1, stride 0x4c0, at +0x380 and +0x840) and the poster. | VERIFIED |
| 0x65d60 -> 0x64b60 | Poster handler "provide data" (vtbl+0x10): copies min(total - offset, *size) bytes from the stream payload (+0x448, total at +0x450). | VERIFIED |
| 0x65e10 (thunk 0x65ee0) -> 0x64c40 | Poster handler "request finished" (vtbl+0x18): decides success or retry from the HTTP status. | VERIFIED |
| 0x678c0 | Connection constructor. Starts thread `dataposter-request` (string 0x115ea3a). | VERIFIED |
| 0x67f20 | Post (vtbl 0x12fbdb0 slot +0x10). Builds the request object, calls `sceHttpCreateRequestWithURL`, queues it. | VERIFIED |
| 0x67a50 (start; body 0x67a8f-0x67ef6) | Tick state machine, run per connection from 0x675d6. Switch on request state+1 at 0x67b2a, table 0x115e5d4. | start INFERRED, body VERIFIED |
| 0x6448d | Constant 0x800 stored in the setup frame (chunk size). Link to the request getter at 0x682b3 is INFERRED. | INFERRED |

## 2. Import call sequence

Post (0x67f20):
1. 0x67f8e `sceHttpCreateRequestWithURL(template, method=1 (POST), url, contentLength = full body length)`. Result < 0 goes to the error log at 0x6809c.
2. 0x67fb5 `sceHttpSetChunkedTransferEnabled(id, 0)`, only when the declared length is 0 (test at 0x67faa). Skipped here.
3. 0x67fee `sceHttpAddRequestHeader(id, name, value, 1)` once per header; result < 0 aborts.
4. The request is queued with state 0.

Tick, one call per thread loop, per request (VERIFIED, 0x67bb3 onward):
- State 0 (sending): call the provider (offset = bytes sent so far, capacity = chunk size). If it returns 0 bytes, jump to 0x67dc3, log "Request finished sending", state=1, call nothing. Otherwise 0x67c4e `sceHttpSendRequest(id, buf, chunkBytes)`. Result < 0 goes to 0x67e66 (log "sceHttpSendRequest error", state=-1). On success the offset advances by chunkBytes and the state stays 0, so the next tick sends the next chunk.
- State 1: 0x67c8a `sceHttpGetStatusCode(id, &status)`. Error: state=-1. Else state=2.
- State 2: 0x67ce8 `sceHttpGetResponseContentLength(id, &result, &len)`. Error: state=-1. If len==0: log "Empty response body", state=3. Else loop `sceHttpReadData(id, buf, 0x200)` while it returns > 0, then state=3.
- State 3 (0x67b4b) and state -1 (0x67b43, which first sets status=0): 0x67b4f `sceHttpDeleteRequest(id)`, then handler vtbl+0x18(kind, status). If it returns 1, call Post (vtbl+0x10 at 0x67b81) with the same request object, which creates a new request.

The header, timeout and TLS-option calls in `0xec9120` belong to the other client, not this path.

## 3. Why it loops

1. VERIFIED: `0x64c40` treats status 199..299 as success (drains the queue at 0x64d8e-0x64e27, returns 0). Any other status, including 0 and negative values, logs an error, increments counter +0x49c, and returns 1. No retry cap in this function.
2. VERIFIED: a return of 1 makes 0x67b78-0x67b87 re-post the request: a new `sceHttpCreateRequestWithURL` with the same descriptor and payload (copy at 0x68280).
3. VERIFIED: state -1 sets status 0 (0x67b43), so every send, status or content-length error becomes a retry.
4. VERIFIED (runtime): `http_send` (runtime_net.c line 186) logs and answers only when `length==discovery.request_size`. Otherwise it returns `HTTP_NETWORK` with no output. `request_size` is the length passed at create, the full body.
5. VERIFIED: the provider limits each chunk to the capacity passed in, and 0x800 is the chunk constant (see the INFERRED row above), so a body over 2048 bytes needs two or more `sceHttpSendRequest` calls, each shorter than the declared length.
6. INFERRED: the first request had a body under 2048 bytes (docs/MAILBOX.md records 1,161 bytes), so it went out as one matching call. Later batches, up to the 8,192 limit in the route table, are larger. Their first chunk fails the length check, the game sees `HTTP_NETWORK`, deletes the request (freeing the replay slot, so "opened" prints again) and re-posts. This fits 6268 "opened" lines and one "sent" line.
7. Not confirmed by a run: that later bodies really exceed 2048 bytes. A `printf` of `id`, `length`, `request_size` in `http_send` when they differ would confirm it (expect length 2048).

Less likely alternative: the provider returns 0 bytes on the first tick, which skips the send (0x67c41); `sceHttpGetStatusCode` then fails (the runtime has no status for an unsent id) and the same retry follows. It needs an empty payload with a declared length >= 1, which the stream code does not appear to produce (INFERRED).

## 4. Smallest runtime change

Edit `http_send` in `external/resogun-recomp/src/runtime_net.c`. No export changes: every sceHttp import this path uses is already exported (CreateRequestWithURL, AddRequestHeader, SendRequest, GetStatusCode, GetResponseContentLength, ReadData, DeleteRequest).

- Keep a byte counter and a `request_size` buffer in `discovery`.
- On `sceHttpSendRequest(id, data, length)` with `length < request_size - sent`: copy the chunk into the buffer, add to `sent`, return 0 (no loopback exchange yet).
- When `sent + length == request_size`: copy the last chunk, run `discovery_exchange(buffer, request_size)`, return 0 or `HTTP_NETWORK` as now.
- Reject `length > request_size - sent` and null `data` with nonzero length, as now.
- Free the buffer in `http_delete_request`.

Result: the game gets 0 for each chunk, the state machine advances, status 200 reaches `0x64c40`, the payload leaves the queue, and no new request is posted.

## 5. Non-empty JSON response

- Game side, VERIFIED: a 200 reply with a body such as `{}` does not loop. State 2 reads it with `sceHttpReadData` (capacity 0x200); `http_read` returns the length once and 0 after, which ends the read loop; state 3 passes status 200 to `0x64c40` (success). The body is never parsed on this path.
- Runtime side, VERIFIED: the telemetry row in `replay_routes` has `response_max = 0`. `discovery_exchange` rejects a longer body (`length>max_body` goes to `done`), so `http_send` would return `HTTP_NETWORK` and the game would loop again. To serve `{}`, raise `response_max` on that row first. The current empty 200 reply is sufficient.
- Any status outside 199..299 also loops, because there is no retry cap.
