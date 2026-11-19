# Everybody's Golf 1.17 network protocol

Scope is the CUSA04687 1.17 EBOOT. Addresses are guest virtual addresses.
The dumped EBOOT SHA-256 is
`59d9dc8df97c2b39315afed269d33e63839d594c9f3357b8784ec0db7606e820`.
The disassembly input was `work/game-1.17-prepared/eboot.elf`. The
[call-site index](call-sites.tsv) maps each direct call or tail jump into a
network/AppContent PLT stub using [the stub map](../plt-import-map.json).
It records 550 static sites across 189 imports. It does not establish that the guest executes every
site, or cover indirect calls, SDK internals and dynamically invoked PRX code.

## Discovery

| Field | Confirmed by static trace |
|---|---|
| Target | `https://ssps4.scej-network.jp:443/nmg-us/ss.info`. Literal `0x120b046` copied to `0x1361e40` at `0xf6b2b–0xf6b5b`. The same runtime URL is loaded at `0xb50856` and passed to connection setup at `0xb5086a`. |
| Method | GET. `0xb50923` writes method index zero. The table at `0x123999c` is `[0,2,1]` and `0xec9165` loads its numeric libSceHttp method. |
| Body | Empty. `0xb5093f` zeroes the pointer and 64-bit length fields that `0xec9349–0xec9351` sends. |
| User-Agent | `PS4Application nolib/0.0 (U-UP9000-CUSA04687_00-EVERYBODYSGOLF07/2017022700/1170)` at `0x120b831`, passed via `0xf6b42`, `0xf6b63`, then `sceHttpCreateTemplate` at `0xec8f5c`. The discovery caller empties both custom header vectors at `0xb507cd–0xb50860`. |
| Required HTTP result | `sceHttpSendRequest` must succeed and status must be `200` (`0xec9351–0xec9371`). The worker queries content length, then calls `sceHttpReadData` until EOF (`0xec937f–0xec93af`). A read failure clears success (`0xec93d9–0xec93dd`). |
| Buffer | `665600` bytes (`0xa2800`) at `0xb5092f`. The worker stores the accumulated count at object offset `0x50` and success at `0x48` (`0xec93a8–0xec93b9`). |
| Body decoder | Jump-table slot 0 pairs the GET (`0x11cd83c` to `0xb50704`) with the completion handler (`0x11cdb50` to `0xb6b7a9`). The handler calls the decoder at `0xb7bbc0`. |

The decoder copies the received bytes from object offset `0x28` and uses the
dedicated context at object offset `0x121a90` to transform eight-byte blocks
(`0xb7bbe8–0xb7bd5d`). The round tables and reversed round-key order are
consistent with Blowfish. When either context word at `+0x1048` or `+0x104c`
is nonzero, the decoder XORs the first decoded block with those words and
subsequent blocks with the previous ciphertext (`0xb7bc74–0xb7bc8d`,
`0xb7bd10–0xb7bd39`). The decoded bytes go to `0xecb1d0` at `0xb7be82`.
That parser consumes opening tags, values and matching closing tags
(`0xecb280–0xecb3e5`). The deployed ciphertext remains unavailable.

The tag lookups start from 32-byte slots at `0x11b7260–0x11b7440`, copied at
`0xb7be8f–0xb7bf91`. Slot names include `msg3`, `client_ver_msg3`,
`gameurl3`, `capone_url3`, `game_analytics_system_url3`,
`cds_gamedata_down_url3`, `cds_gamedata_up_url3`,
`cds_property_down_url3`, `interval3`, `client_ver3`, `msg_busy3`,
`capone_envtag3`, `game_analytics_system_envtag3`, `displaytime_telop3`,
`getscorelist_teedistance3` and `lang1`. The code can rewrite the suffixes
(`0xb7bf99` onward). Values include a nested tag map parsed at `0xb7dd74`,
then looked up by keys such as `ssinfo` and `getservertime`
(`0xb7ddd0–0xb7df3f`). The startup `ss_info_ver` lookup at
`0xf69ce–0xf6b26` runs before the GET and comes from a separate table.

The discovery context is allocated and installed at `0xf6cf6–0xf6d4e`.
Its initializer call at `0xf6d55` expands an eight-byte seed with the
Blowfish tables (`0xec87e0–0xec89e1`). An OpenSSL Blowfish-CBC encryption
of synthetic tags round-tripped through an independent implementation
of the guest's little-endian rounds and CBC chaining. The ignored local
fixture is `work/online/ss-info-local.bin` (200 bytes). It includes a
loopback game URL, a build-version value, and sample interval values.
The format checks cover cipher compatibility. The values and tag
acceptance need a guest run.

The original tags ending in `3` are rewritten to end in `1` before lookup
(`0xb7bfb6–0xb7c18a`). The `lang1` key is built separately from a cached
language index plus one (`0xb7c197–0xb7c20f`). The decoder checks for
`ss`, the selected message key, `gameurl1`, `interval1`, `capone_url1`,
`game_analytics_system_url1`, the three `cds_*_url1` keys,
`client_ver1` and `msg_busy1` (`0xb7cbf3–0xb7ce4b`). A missing key
calls the discovery failure handler. The code reads `ss` as an integer
and takes the normal path on zero (`0xb7c558`, `0xb7c6bb–0xb7c6c1`).
The client version check compares the parsed integer to `0x4f6` (1270)
at `0xb7d2c8`.

`gameurl1` holds another tag map. The decoder looks it up at `0xb7fdb4`
and parses its value at `0xb7fecc`. The validation loop checks 34
`gameapi_*` keys from the relocations at `0x132f060–0x132f168`.
The loop requires all keys except index 8, `gameapi_getsignboardlist`
(`0xb8001a–0xb80088`). Present values must be shorter than 127 bytes
(`0xb8018e–0xb801a0`). The decoder copies the login entry into the
title object's URL buffer at offset `0x5d068`
(`0xb80227–0xb8026e`). The [URL map](title-url-map.tsv) lists the 34
validation entries, all 36 traced destination fields and their direct
references in the request dispatcher and its traced helpers.
`gameapi_getuploadinfo` enters validation through the table entry
at `0x132f090` (literal `0x120b6f8`). Its destination and consumer
remain untraced.

Three later lookups fall outside the validation loop. The decoder reads
`gameapi_uploaddata` into `+0x5d368` (`0xb808a9–0xb80925`),
`gameapi_getregulationdata` into `+0x5d468` (`0xb82774–0xb827ef`) and
`gameapi_getfinishboardlist` into `+0x5d4e8` (`0xb8289d–0xb8298a`). The
finish-board branch clears its field when the lookup misses (`0xb829e6`).
The original endpoint values remain unknown.

For `gameapi_uploaddata`, `gameapi_getnationalholescoredistribution`,
and `gameapi_gettopplayerlistnational`, the executable segments expose
these direct MOV/LEA displacement references to their URL fields.

| URL field | Discovery reference |
|---|---|
| `+0x5d368` | `0xb808f9` |
| `+0x5dbe8` | `0xb817b0` |
| `+0x5dee8` | `0xb81e93` |

Consumers that use indexed addressing or derive the field pointer
remain unverified.

The second ignored fixture, `work/online/ss-info-local-v2.bin`, contains
these outer tags and all 34 nested entries. Each synthetic URL points to
`127.0.0.1:8765` under `/nmg-us/replay-probe/`. The default local
skeleton returns `404` for those paths. The fixture round-trips through the
standalone decoder. Guest acceptance and follow-up requests remain
unverified.

The runtime must bound reads by the remaining guest buffer size. The generic
worker passes the original pointer and capacity to successive reads rather
than advancing either (`0xec9387–0xec93af`). Replay should preserve one
complete response or verify the guest's partial-read behavior before
implementing incremental host reads.

The local server implements the observed request target and framing on IPv4
loopback. Without a fixture it returns a bodyless `503`, which exercises the
guest's HTTP failure path. With an explicit local ciphertext fixture it returns `200` and those bytes
with their `Content-Length`. The server checks size and block alignment.
The fixture content type is local. The synthetic test bytes verify replay
and framing. On `e549b2c`, the runtime owner observed discovery accept the
7,656-byte combined fixture and request its server-time URL (04:45 mailbox
entry). The minimal and earlier experimental fixtures remain unverified
in the guest.

```http
GET /nmg-us/ss.info HTTP/1.1
Host: 127.0.0.1:8765
User-Agent: PS4Application nolib/0.0 (U-UP9000-CUSA04687_00-EVERYBODYSGOLF07/2017022700/1170)
```

The original Host would be selected by libSceHttp from the URL. No live host
was contacted. The runtime would need an explicit offline mapping for this
original authority before using the server. The skeleton uses local HTTP.

## Title HTTP operations

The request and completion dispatchers each accept indices 0 through 61
(`0xb5059a–0xb505cd` and `0xb6570f–0xb65733`). The
[dispatch table](title-dispatch.tsv) gives both guest targets for all
62 indices. The assembly contains a path to GET for seven slots and to
multipart POST for 53 slots. Twenty of those POST slots call a separate
helper before reaching `0xb5d300`. Slots `0x29` and `0x33` clear the request
state and return through `0xb5a6f3–0xb5a6fe` and `0xb50219–0xb5023c`.
These are static paths. Runtime inputs can bypass the send.

Slot `0x20` includes a six-way branch at `0xb53c2a` using the table at
`0x11cd934`. The final URL selector chooses `gameapi_getboardlist` or
`gameapi_getboardlistcharactordownload` at `0xb561af–0xb561c1`. The helper
shared by slots `0x1a`, `0x1c` and `0x1e` selects one of three score
registration URLs before calling the producer at `0xb650d0`. The URL
loads are `0xb64813`, `0xb6481c` and `0xb648a3`.

The title's request worker at `0xec9120` has three producers. The discovery
path calls it directly. The generic producer at `0xec9630` accepts the URL,
method index, response span and optional body span (`0xec9642–0xec9715`).
These callers pass method index zero and a zero-length body:

| Generic GET call sites | URL source |
|---|---|
| `0xb549f9`, `0xb6eccb` | An indexed URL in the global object at `0x2c6b648`, base offset `0x1f1d380` (`0xb549bf–0xb549d4`, `0xb6ec9f–0xb6ecbc`). Slot `0x18` enters the `0xb549f9` caller with a different source, the string at global offset `0x1f1ccc0` (`0xb53648–0xb53654`). |
| `0xb556c9` | String at request-object offset `0x128070` for slot `0x32` (`0xb55697–0xb556ab`). Slots `0x30`, `0x35` and `0x38` enter the same caller with the string at `0x1280d8` (`0xb505cf–0xb505fa`). |
| `0xb72ff0`, `0xb730a2`, `0xb73117` | String at request-object offset `0x1280d8` (`0xb72fbd–0xb72fce`, `0xb7306f–0xb73080`, `0xb730e4–0xb730f5`). |
| `0xb76b9d` | Pointer in `r14` in the preceding branch (`0xb76b81`). |
| `0xb7afdb` | Indexed URL beside the first table, base offset `0x1f1ccc0` (`0xb7afb3–0xb7afba`). |

The producer at `0xec97d0` sends method index two (POST) with
`Content-Type: multipart/form-data; boundary=xYzZY` (`0xec9e9c–0xec9ead`,
`0xec9f8b–0xec9fb5`). It writes one form-data part named `p`.
The opening boundary, disposition line, blank line and final boundary
come from `0x1218e9c`, `0x1218ea6`, `0x1218ed1`, and `0x1218ed4`
(`0xec9a73–0xec9acd`, `0xec9b48–0xec9b74`, `0xec9d1e–0xec9d43`).
For a URL starting with `https://`, it copies the caller's bytes into
the part (`0xec982f–0xec985f`, `0xec99de–0xec9a68`). The other branch
pads a stack copy to an eight-byte boundary with `0x04` and applies
a Blowfish-shaped forward cipher using the context at offset `0xe8`
(`0xec9865–0xec99cc`), then restores the stack without appending the
result (`0xec99d2–0xec99d9`). The composer reads the cleared part buffer
(`0xec9842–0xec984d`, `0xec9b4d–0xec9b60`), leaving 66 bytes of framing
(`0xec9a6a–0xec9acd`, `0xec9b65–0xec9b74`, `0xec9d1e–0xec9d43`).
The runtime owner observed that length on the property request
(04:45 mailbox entry).

`0xb5d300–0xb5d38b` provides the dynamic URL and request span for the
multipart path. Slots `0x03`, `0x19–0x1e`, `0x21`, `0x2b`, and
`0x39–0x3c` format the URL with `%s%llu&n=%d&s=1` (`0x120b1fa`).
Other slots use that format if the POST URL contains the literal `GET`
(`0x120b1f6`, `0xb5d30d–0xb5d361`, `0xb5d390–0xb5d3a2`).
The `strstr` symbol hashes to NID `viiwFMaNamA`, imported at
`0x10fcdd0`. The other branch copies the input URL at `0xb5d3ae`.

The `gameapi_*` names below are operation labels. The EBOOT relocates the
`ssinfo` and `gameapi_login` string pointers at `0x132f010` and `0x132f060`.
The deployed paths, hosts and values remain unknown.

| Operation labels | String region |
|---|---|
| Login, EULA, notices, boards, server time, user status and course-world assignment | `0x120b332–0x120b3fe` |
| Score lists, score registration, upload, daily and long-drive registration, rivals, player rankings and distributions | `0x120b379–0x120b4b5` |
| Bonuses and national boards, scores, entry notice and registration | `0x120b4b6–0x120b5f2` |
| Character download boards, registration, scores, count, assignment, regulations, finish/sign boards and upload info | `0x120b5f3–0x120b70d` |

### Shared title HTTP request lifecycle

| Stage | Guest calls and conditions |
|---|---|
| Template | `sceHttpCreateTemplate` at `0xec8f5c`, then connect, send and receive timeout setters at `0xec8f7f–0xec8f9f`. The setup registers callback `0xec9070` through `sceHttpsSetSslCallback` at `0xec9007`. |
| Connection | `sceHttpCreateConnectionWithURL` at `0xec901d` with keepalive argument 1, then the three timeout setters (`0xec9034–0xec905c`). A later setup path deletes the prior request and connection before opening another URL (`0xec9094–0xec90be`). |
| Request | `sceHttpCreateRequestWithURL` at `0xec9174` with the method and body length. When both vectors have entries, the worker adds paired header names and values using `sceHttpAddRequestHeader` (`0xec918d–0xec923a`). It sets all three request timeouts at `0xec925e–0xec927c`. |
| TLS options | When the masks at `+0xa0` and `+0xa4` are nonzero, the worker applies them to the request through `sceHttpsDisableOption` and `sceHttpsEnableOption` (`0xec92f7–0xec933f`). A send error of `0x80431075` invokes `sceHttpsGetSslError` (`0xec93c3–0xec93d4`). |
| Send and release | Send, read the HTTP status, then query content length and read the body when the status is 200 (`0xec9351–0xec93b9`). The exit path deletes the request and passes zero masks to the connection's HTTPS option calls (`0xec92b3–0xec92d5`). |

### Capone report POST

Discovery rewrites `capone_url3` (`0x11b72c0`) to `capone_url1`
(`0xb7beb9–0xb7bed9`, `0xb7c009–0xb7c017`). The value is looked up
and copied to title context `+0x5e2e8` (`0xb7e699–0xb7e7ea`), then
passed to the report client at `0xb7f850–0xb7f871`. The client copies it
into its URL string at `+0x5120` (`0x855642–0x85565b`,
`0x8557ae–0x8557d8`). The POST reads that URL at `0xc5ede0–0xc5edf1`.
The deployed host and path depend on discovery and remain unknown.

The caller adds `Authorization` and `Content-Type: application/json`
(`0xc5eda1–0xc5edd2`). It sends the serialized JSON as POST with a
`0x100`-byte response buffer (`0xc5eb46–0xc5eb8e`, `0xc5edf4–0xc5ee1c`).
The report body uses these field names.

| Fields | Builder evidence |
|---|---|
| `envtag`, `platformId`, `reporter` | `0xc5e14a`, `0xc5e1ac`, `0xc5e215` |
| `reporterAccountId`, `reporterCountryCode`, `reporterDescription`, `reportLanguageId`, `reportReasonId`, `sourceId` | `0xc5e273`, `0xc5e2e3`, `0xc5e350`, `0xc5e3ad`, `0xc5e3fd`, `0xc5e44f` |
| `item.sourceItemId`, `item.contentLanguageId`, `item.creationDate`, `item.mimeType`, `item.owner`, `item.ownerAccountId`, `item.ownerCountryCode` | `0xc5e4b7`, `0xc5e51a`, `0xc5e56f`, `0xc5e5d6`, `0xc5e643`, `0xc5e6a4`, `0xc5e70b`. The `mimeType` value is `text/plain` (`0xc5e5ac`). |
| `item.extraInfo` and enclosing `item` | `0xc5eab4–0xc5eadc`, `0xc5eaf1–0xc5eb31` |

Response contents and required fields are unverified. The loopback service
returns `404` for report submission.

### Event telemetry

| Stage | Observed behavior |
|---|---|
| URL | Uses the discovery base if present (`0xb7f6ee–0xb7f703`) or `https://mingol.api.dev.wwsga.me/games/` from `0x1206ab6` (`0xb7f705–0xb7f734`). Appends the fixed title UUID from `0x1206a70` and `/telemetry` (`0xb7f726–0xb7f774`). |
| Headers | Sends a POST with `Content-type: application/json`, `Authorization` and `X-WWS-SCHEMA-ID` (`0x643b5–0x643fd`). |
| Body | A JSON object with `count` and an `events` array. The opening template is at `0x115e520` (`0x6475f–0x64778`). The batch writer formats the count with `%5u` at `0x115e0d2` and closes the array and object at `0x64648–0x646b0`. |
| HTTP stack | Initializes Net → pool → SSL → HTTP → template (`0x67130–0x671bc`), connects (`0x6778d`), configures the request (`0x67f8e–0x67fee`), then sends and reads it (`0x67c4e–0x67d6b`). |
| Transfer sizes | The descriptor stores total JSON bytes and a 2,048-byte transfer buffer size separately (`0x64482–0x6448d`, `0x682b3–0x682c2`). CreateRequest receives the total (`0x67f7d–0x67f8e`). The provider (`0x65d60`, selected at `0xb7f6d6–0xb7f6eb`) copies the lesser of the remaining bytes and the buffer capacity (`0x64be0–0x64c0d`). Each SendRequest receives that count (`0x67c35–0x67c4e`). A zero count enters the status phase (`0x67c41`, `0x67dc3`). |

The runtime owner observed a 1,161-byte telemetry POST at startup
on `e549b2c` (04:45 mailbox entry). The opt-in `--discard-telemetry`
fixture supplies `http://127.0.0.1:8765/nmg-us/replay-probe/analytics/`
as the base, including its trailing slash. The bridge accepts the exact
title URL and forwards the JSON body as `application/json` without the
original Authorization and schema headers.

The listener accepts a UTF-8 object or array up to the fixture's 8,192-byte
limit, discards the contents, and replies HTTP 200 with `Content-Length: 0`.
The guest reader has an empty-body branch at `0x67cf5–0x67cfa` and `0x67ec0`.
The runtime owner observed HTTP 200 with an empty body in the guest on
`648d038` (05:35 mailbox entry). In a later log snapshot, request ID
65546 had a matching HTTP 200 send entry. The other telemetry opens in
that snapshot had no matching send entry. The bridge only logs sends
after accepting the handle and the length, so the log cannot distinguish
a skipped send from a refused send. A host probe reproduced the length
rejection for a batch larger than the transfer buffer. The proposed
transport patch assembles those chunks into one request up to 8,192 bytes.
The owner verified the patch in `d91027d`. The guest log had 37 telemetry
opens and 37 answers, up from one answer across 6,268 opens (07:05 mailbox
entry). Individual guest chunk sizes remain unrecorded.

### EULA fetch

Slots `0x01` and `0x02` send multipart POST to `gameapi_geteula`
(`0xb505ff–0xb506ff`, `0xb55b4a–0xb55bb2`). Both send binary records
`0x8000`, `0x0010`, `0x0050`, `0x1050`, and `0x8010` in that order.
Slot `0x01` uses `CUSA04687_00` in `0x0010` and takes the current revision
for `0x1050` from global object offset `0x1f17cfc`. Slot `0x02` instead
uses `NPJA00086_PUB` and a zero revision
(`0xb50602–0xb50686`, `0xb506d9–0xb506ff`, `0xb55b4a–0xb55b92`).
The two requests have 44 record bytes and 110 bytes with multipart framing.

On the text-bearing response path, the completion checks these records.
Lengths count four-byte words, including each record's header.

| Record | Payload and evidence |
|---|---|
| `0x8000`, `0x0000` | Header and status 1 (`0xb65b0c–0xb65b4d`). |
| `0x1050`, `0x1000` | Revision at `0x1050+4` is saved for slot 1. The parser checks the next type and advances over it (`0xb65b53–0xb65b93`). |
| `0x1010` | Sixteen-byte MD5 digest (`0xb65b97–0xb65bb4`). |
| `0x1030`, `0x1020` | The first carries a 32-bit byte count. The parser hashes that many bytes beginning at `0x1020+4` and compares all 16 digest bytes (`0xb65bbd–0xb65d4f`). The digest routine starts at `0x124c0`. Its first step at `0x12bb4–0x12bc4` adds MD5 constant `0xd76aa478` and rotates left by seven bits. |
| `0x8010` | Required final record. The guest copies the text as a NUL-terminated string and passes it to its completion path (`0xb65d55–0xb65d85`, `0xb7ba38–0xb7bbaf`). |

The local probe uses revision 1 and a header-only `0x1000` record. It
hashes the supplied UTF-8 text before adding a NUL terminator and padding.
The server holds no agreement state. Original record values remain unknown.
Guest acceptance still needs a run.

### Login and server time

| Operation | URL buffer and request | Completion entry |
|---|---|---|
| Login (dispatch slot 3) | The discovery decoder copies `gameapi_login` to object offset `0x5d068` (`0xb80227–0xb8026e`). Slot 3 passes it at `0xb50cd0` and branches to the common multipart caller at `0xb5a6da`. | `0xb6b7b6`. If object byte `0x118` is set, the loop reads the buffer in eight-byte blocks using context offset `0xe8` (`0xb6b7b6–0xb6b835`). The common record reader is called at `0xb6b900`. |
| Server time (dispatch slot 4) | The discovery decoder copies `gameapi_getservertime` (literal at `0x120b3b5`) to `0x5d3e8` (`0xb809c3–0xb80a3f`). Slot 4 uses that buffer at `0xb50d7a` and goes to the same multipart caller. | `0xb6b49d`. The decrypt path uses the same flag and context (`0xb6b49d–0xb6b4e8`). The success path parses binary records. |

The shared caller at `0xb5a6dd` invokes `0xb5d300`, which passes a
request span beginning at object offset `0x5f274` to `0xec97d0` for
multipart POST (`0xb5d36c–0xb5d38b`). The login case always appends
the unsigned value from global context `+0x58`, followed by
`&n=<counter>&s=1` (`0xb5d30d–0xb5d361`). The format string at
`0x120b1fa` supplies no separator between the configured URL and the
unsigned value. The deployed URL prefix is unknown. The server-time case
uses the supplied URL directly unless it contains the literal `GET`
(`0xb5d390–0xb5d3b3`). That check selects the URL formatting branch.
The caller still reaches the multipart builder.

The record reader takes a little-endian 16-bit type at offset 0 and
advances the cursor by four times the 16-bit count at offset 2
(`0xb85e28–0xb85e2b`, `0xb865ef–0xb865f8`). The ordinary server-time
completion checks types `0x8000`, `0x0000`, `0x0072`, `0x5000`
and `0x8010` in order (`0xb6b5d2`, `0xb6e84c`, `0xb713e7`,
`0xb73604`, `0xb79234`). The `0x0072` check leaves the cursor
unchanged when the type differs (`0xb85e31–0xb85e3a`).
The `0x5000` record stores a packed-decimal date and time in seven
bytes at offsets 4–10. The guest splits them into century, year, month,
day, hour, minute and second and calls the RTC conversion at
`0xb86194` (`0xb860db–0xb86194`). The record status fields and the
complete login response are still unresolved.

#### Login record framing

The request contains the following records in order. Each count includes
its four-byte header. The string lengths determine the multipart size.

| Type | Count | Payload and source |
|---|---:|---|
| `0x8000` | 1 | Header only (`0xb50bc6`). |
| `0x0010` | 5 | NUL-terminated title ID and three bytes of value 3 (`0xb50965–0xb5096d`, `0xb50ba5–0xb50c09`). |
| `0x0050` | 2 | Selected language index plus one (`0xb50958–0xb509b1`, `0xb50a6f`, `0xb50c11–0xb50c20`). |
| `0x0020` | Variable | NUL-terminated string from global context `+0x20` (`0xb509b7–0xb50a5c`, `0xb50c27–0xb50c37`). |
| `0x0084` | Variable | The decimal text of the global context value at `+0x58`. The URL suffix uses the same value (`0xb50a44–0xb50abc`, `0xb5d300–0xb5d361`). |
| `0x0070` | 3 | Six bytes from global context `+0x181`, followed by the little-endian payload word `0x0202` (`0xb50b96–0xb50bb5`, `0xb50c5c–0xb50ca2`). |
| `0x0071` | 5 | Sixteen zero bytes (`0xb50c6b`, `0xb50caa–0xb50cba`). |
| `0x0085` | Variable | NUL-terminated string from the global object at `0x2c8f320`, offset `+0x08` (`0xb50a90–0xb50b8d`, `0xb50c6f–0xb50cc1`). |
| `0x2032` | 2 | Little-endian 32-bit value copied from request-object offset `0x122390` (`0xb5095e`, `0xb5097a`, `0xb50cc6–0xb50ce1`). |
| `0x8010` | 1 | Header only (`0xb50ce6`). |

The completion starts at the response buffer and calls the common decoder
with expected type `-1` (`0xb6b8c7–0xb6b900`). It continues for up to 101
reads when the decoder returns zero (`0xb6b8e3`, `0xb6b933–0xb6b944`).
The terminator `0x8010` yields decoder state 4 (`0xb85e81–0xb85e86`,
`0xb86041–0xb86046`). The completion then tests `+0x5e5e8` in the title
context (`0xb6e617–0xb6e63c`). Below 4 it clears retry state at `0xb71250`
and calls the operation completion with success 1 (`0xb7b33f–0xb7b349`).
For dispatch slot 3, the completion table at `0x11cda50` selects event
`0xec` on success (`0xb5c961–0xb5c96f`). At 4 or above the guest takes
the failure path with `0x90000002` (`0xb6e637–0xb6e63c`, `0xb73153`,
`0xb79214–0xb79219`).

The common decoder recognizes the following state-bearing records. Dispatch
comes from the tables at `0x11cdd28` and `0x11cdd84`. These handlers also
serve other title operations. Which records an actual login response carries
and which the next guest state needs remain unverified.

| Type | Observed effect |
|---|---|
| `0x2020` | Copies the 32-bit payload at `+4` to the login completion gate at context offset `0x5e5e8` (`0x11cdd84`, `0xb86074–0xb86082`). |
| `0x2022` | Stores the 32-bit payload from `+4` at context offset `0x1224bc` (`0x11cdd8c`, `0xb864fe–0xb8650c`). Initialization clears that field at `0xf667e`. Its meaning remains unverified. |
| `0x2031` | Clears the string at context `+0x5e5f0` on a header-only record. Other lengths copy a string starting at payload `+4` (`0x11cddc8`, `0xb86511–0xb86529`, `0xb86588–0xb86594`). |
| `0x2032` | Stores the first payload byte at offset `0x1f1d80f` of the object at `0x2c6b648` (`0x11cddcc`, `0xb8652e–0xb86541`). A nonzero byte forces the next login request's `0x2032` word to 1 (`0xa60883–0xa608bb`, `0xa606e2–0xa60742`). It also enables the slot `0x1f` dispatch at `0xa60c23–0xa60c4f`. |
| `0x0080` | Supplies up to `0x100` bytes of string data to two buffers (`0x11cdd60`, `0xb8621e–0xb86254`). |
| `0x0083` | Copies a NUL-terminated payload, pads it to eight-byte blocks, and transforms it using the cipher context at `+0x121a88`. It Base64-encodes the result and writes the string back to context `+0x121e81` (`0x11cdd6c`, `0xb86259–0xb863d4`, `0xb86402–0xb86417`). The payload's meaning remains unverified. |
| `0x0086`–`0x0088` | Copies 132, 8 and 8 bytes, including the record headers, to context offsets `+0x1224c4`, `+0x122548` and `+0x122550` (`0x11cdd78–0x11cdd80`, `0xb86485–0xb864f9`). Slot `0x1f` later reuses those records. |

The `0x0085` string comes from `sceNpAuthGetAuthorizationCodeA`.
The title allocates one async request at `0xa60ca9`, stores its
ID at global `0x2c8f320+0`, and passes a 32-byte parameter plus
output pointers at `+8` for the code and `+4` for the issuer
(`0xa60cb6–0xa60d12`). The poller deletes the request on completion
or error (`0xb97f2d–0xb97f5e`). A later title state requires a
nonempty code (`0xa60863–0xa6087d`), and the login builder reads it
from `+8` (`0xb50a90–0xb50b8d`). Consumers of `0x2020` and
`0x2031` also pass the message to a UI routine when the gate is
at least 2 and the message is nonempty (`0xa5af2d–0xa5af57`,
`0xa5eab4–0xa5eaf1`).

The opt-in rejection probe uses a local synthetic `GolfLocalProbe`
authorization code and the primary local account. The discovery
fixture supplies an HTTPS URL ending in `?account=` so the client
appends its account number and signed counter using
`%s%llu&n=%d&s=1` at `0x120b1fa`. The service validates the exact
query and request records before returning the 24-byte sequence
`0x8000/1`, `0x0000/2` with parser status 1, `0x2020/2` with gate 4,
and `0x8010/1`. Gate 4 selects the failure path at `0xb6e62a–0xb6e63c`.
The fixture creates no title session. Guest acceptance remains
unverified.

The opt-in `--login-completion` probe keeps the same URL, account and
request validation and changes the `0x2020` value to 1. The common
decoder stores it at `0xb86074–0xb86082`. At the terminator the check
at `0xb6e62a–0xb6e631` takes the completion branch for values below 4.
Its event `0xec` reaches `0xa5d82a`, which advances a matching action
`0x04` (`0xa5feaa–0xa5febf`). The next default action is `0x26`
(`0x1232a34`). Unless the screen state read at `0xa6136d` is `0x10`,
it dispatches slot `0x2f`, `gameapi_getboardlistnational`
(`0xa613c2–0xa613eb`, `0xb55624`). The runtime owner observed
login completion and the next POST on `da28e84`. That run used the
HTTP placeholder for the board URL and sent an empty multipart frame
(mailbox entry on the login run).

#### Server-time loopback probe

The outgoing server-time data is 36 bytes (`0xb50d59–0xb50dda`). Its
records are type/count `0x8000/1`, `0x0010/5`, `0x0050/2` and
`0x8010/1`. Type `0x0010` carries the NUL-terminated title identifier
`CUSA04687_00` followed by three bytes of value 3
(`0xb50d01–0xb50d09`, `0xb50d4f`, `0xb50d81–0xb50db9`).
Type `0x0050` carries the selected language index plus one in a
32-bit field (`0xb50d78–0xb50d9d`, `0xb50dc8`).

For a type-zero response record, the reader loads a 32-bit status from
offset 4. Positive statuses 1, 2 and 3 return success
(`0xb85e95–0xb85e9f`, `0xb86087–0xb86089`, `0xb86208–0xb86219`).
The opt-in local replay uses status 1 and emits four records in order.

| Type | Count in four-byte units | Value |
|---|---:|---|
| `0x8000` | 1 | Header only |
| `0x0000` | 2 | Status 1 |
| `0x5000` | 3 | Seven packed-decimal date and time bytes, then zero padding |
| `0x8010` | 1 | Header only |

The request builder sets object byte `0x118` when the configured URL
doesn't begin with `https://` (`0xec982f–0xec985f`). The completion
handler uses that byte to choose whether to decrypt the response
(`0xb6b49d–0xb6b4e8`). The ignored `work/online/ss-info-local-v3.bin`
fixture changes only the server-time URL to
`https://127.0.0.1:8765/nmg-us/replay-probe/gameapi_getservertime`.
For this probe the runtime must map that exact guest URL to the local
HTTP socket while preserving the guest's HTTPS prefix. The loopback
server enables the route only with `--server-time` and validates the
complete multipart request. Tests replay the host-side request and check
the exact 28-byte reply. The runtime owner observed the guest accept that
reply on `e549b2c`, after a 7,656-byte discovery response (04:45 mailbox entry).

The v4 fixture keeps this server-time URL and includes all 37 keys in
the URL map. Its three additional discovery values use synthetic
loopback URLs. The ciphertext round-tripped through the standalone
decoder. With the combined v5 fixture on `648d038`, the guest displayed
"Golf Island Time 09/14/2018 12:00" (05:35 mailbox entry).

### Notice list

Slot `0x05` passes `gameapi_getinfolist` at object offset `0x5d168` to
the common multipart POST builder (`0xb8048b`, `0xb50fca–0xb50ff6`).
It sends `0x8000`, `0x0010` and `0x0050` as in the server-time request,
then sends these records in order (`0xb50e4a–0xb50ff6`).

| Type | Count in four-byte units | Payload |
|---|---:|---|
| `0x0080` | 65 | 256 bytes from context `+0x1223b9` (`0xb50e4a–0xb50e6c`). |
| `0x0083` | Variable | NUL-terminated string from context `+0x121e81`. Any bytes after the NUL are each set to the number of padding bytes, zero to three (`0xb50e71–0xb50f1e`). |
| `0x3050` | 2 | 32-bit request selector from context `+0x122390` (`0xb50ded`, `0xb50fb8–0xb50fdb`). |
| `0x4000`, `0x4010` | 2 each | 32-bit values 1 and 10 respectively (constant at `0x119d4e0` copied at `0xb50fbd–0xb50fdf`). |
| `0x8010` | 1 | Header only (`0xb50fe6`). |

The completion reads `0x8000`, `0x0000`, optional `0x0072` and `0x0083`,
then requires `0x3000` with a 32-bit count at record offset 4
(`0xb68bb2–0xb68c22`). The reader transforms the `0x0083` string with
the title cipher before Base64 encoding and storing it at
`+0x121e81` (`0xb86259–0xb86417`). The title initializes that cipher
at `0xf6b4c` and `0xf6cda–0xf6ce5`. The original value and its
server-side purpose remain unknown.

The completion caps the local list at 10 (`0xb68c36–0xb68c5a`). With a
positive count it reads these records for each item.

| Type | Payload and handling |
|---|---|
| `0x3010` | Required item header. The cursor advances by the count in the header (`0xb68d1d–0xb68d3d`). |
| `0x3030` | Required NUL-terminated string starting at `+4`, passed to the same tag parser as discovery (`0xb68d42–0xb68d6a`, `0xb68de6–0xb68dfa`). For selector 0 the parser's result can supply `nid`. For selector 1 it can supply `bid`. The decimal values start at -1 when absent. When a tag is found the copied string starts immediately after `</nid>` or `</bid>` (`0xb68d4d–0xb68d59`, `0xb68e0b–0xb68f5b`, `0xb68f5f–0xb690dc` and literals at `0x120b2df`, `0x120b2ea`). |
| `0x3040` | Required NUL-terminated string at `+4`, copied to the per-item text buffer (`0xb69149–0xb69189`). |
| `0x3064` | Optional seven-byte packed-decimal date/time at `+4` through `+10` (`0xb6918d–0xb69283`). |
| `0x3063` | Required 32-bit value at `+4`, stored per item. Its meaning is unknown (`0xb69288–0xb6929d`, `0xb693ca–0xb693d2`). |
| `0x3020` | Required item terminator. The cursor advances past intervening records by their counts until it finds this type (`0xb692a5–0xb692ef`). |

A zero count skips item parsing. The completion stores the count and
requires `0x8010` before calling the operation completion with success 1
(`0xb68ceb–0xb68cf2`, `0xb69353–0xb69370`, `0xb6948f–0xb69531`).
The opt-in `--empty-notices` fixture validates the request frame and accepts
selectors 0, 1, and 2. The action reads the selector from `+0xe78`
(`0xa608c0–0xa608e0`), and the completion increments it and sets the
login-sequence flag on the third success (`0xa5e977–0xa5e999`).
The fixture replies with `0x8000/1`, `0x0000/2` with status 1,
`0x0083/3` with the synthetic string `local` and zero padding,
`0x3000/2` with count zero, and `0x8010/1`. The guest would update its
`0x0083` state if it accepts this reply. Guest acceptance and a complete
session remain unverified.

### Daily event score queries

Slots `0x07`, `0x08` and `0x09` send multipart POST to the same
discovery-supplied `gameapi_getscorelist` URL. Discovery writes the URL to
`+0x5d268` (`0xb806c1`). Slot `0x07` selects that field at
`0xb5fe14` and slots `0x08` and `0x09` use the selector at `0xb58b65`.
The event-state check for slot `0x07` can skip the request
(`0xb5f94d–0xb5fac5`). Slots `0x08` and `0x09` derive their event date
and index from a packed value and skip the request when it is zero
(`0xb5102c–0xb51078`, `0xb5132a–0xb51376`).

All three start with the usual `0x8000`, `0x0010` and `0x0050`,
then append these records in order (`0xb5fd34–0xb5fe34`,
`0xb5123e–0xb51325`, `0xb51532–0xb51637`).

| Type | Payload |
|---|---|
| `0x0020` | NUL-terminated string from global object `0x2c8f2e0` at `+0x20` (`0xb5fbcb–0xb5fc7d`, `0xb510d0–0xb51181`, `0xb513ce–0xb5147c`). |
| `0x0060` | Eight-byte aligned ciphertext produced by `0xb65110`. The caller writes the record header and word count after the helper returns (`0xb5fc61`, `0xb5fd07–0xb5fd55`, `0xb51165`, `0xb51212–0xb51260`, `0xb51529–0xb5155e`). |
| `0x4140` | NUL-terminated event name. Slot `0x07` formats `Daily_%04d%02d%02d_%02d`. Slot `0x08` appends `_score` and slot `0x09` appends `_holescore` (`0xb5fb38–0xb5fb75`, `0xb5104b–0xb51078`, `0xb51349–0xb51376`). |
| `0x4000`, `0x4010` | 32-bit values 1 and 1 for slot `0x07`, 1 and 1,000 for slot `0x08`, and 1 and 18 for slot `0x09`. The pairs come from `0x119d500`, `0x119d4d0` and `0x119d4c0` respectively (`0xb5fe07`, `0xb5131d`, `0xb5161b–0xb51628`). |
| `0x8010` | Header only (`0xb5fe24`, `0xb5162e`). |

For `0x0060`, the helper writes four prefix characters from two RTC
values and appends the result of the format `%lu%s` at `0x120b17f`.
That format combines a value derived from the tick difference and the
string at context `+0x121a98`
(`0xb65139–0xb6523c`). After checking the plaintext length, it includes the NUL, pads to
eight-byte blocks, and transforms the payload using the cipher context at `+0x121a88` (`0xb65241–0xb6537b`).

All three success readers check `0x8000`, then `0x0000` with status 1,
then `0x0060` (`0xb6a706–0xb6a74d`, `0xb6a0a2–0xb6a0da`,
`0xb6bb04–0xb6bb45`). The HTTPS branch bypasses whole-response
decryption but still decrypts the inner `0x0060` payload with the title
cipher (`0xb6a5e1–0xb6a6f2`, `0xb6a75c–0xb6a858` for slot `0x07`).
After decrypting `0x0060`, the guest searches the payload for `_`, copies the substring
starting at that character to `+0x121a98`, and records a fresh tick at
`+0x122270`. A missing underscore takes the fallback path
(`0xb6a858–0xb6a88b`, `0xb6a1ff–0xb6a232`,
`0xb6bc5e–0xb6bc91`, `strchr` PLT at `0x10fd070`). That string
and tick feed the next request's `0x0060` helper. Their original values
and the server-side validation rules remain unknown.

| Completion | Records after `0x0060` |
|---|---|
| Slot `0x07` at `0xb6a5e1` | Requires `0x4200`, `0x4210`, `0x4220` with a nonzero payload, `0x4230`, `0x4270` and the start of the `0x4500` sequence. It reads `0x4210` and `0x4270` as 32-bit values. The follow-on `0x46xx` scan recognizes decimal strings at `0x4614` and `0x4615` (`0xb6a899–0xb6a96d`, `0xb6aa3d–0xb6aad4`). |
| Slot `0x08` at `0xb69f66` | Reads the row count from `0x4200`. It enters the row loop when the count is positive and `0x4210` is followed by `0x4220` with a zero payload. Each row starts with `0x4250` and `0x4270`. The local result count is capped at 512 and stored at `+0x1f1ad38` of the global context plus the selected index times four (`0xb6a249–0xb6a2ed`, `0xb6a406–0xb6a424`, `0xb72dfc–0xb72e49`). |
| Slot `0x09` at `0xb6b94b` | Checks the same list header and row conditions as slot `0x08`, then uses a different row parser and result buffer (`0xb6bc9f–0xb6bd36`, `0xb71376–0xb713a5`). |

Slot `0x08` routes errors and parsed counts through
the same result-copy path before the common callback
(`0xb712f2–0xb71301`, `0xb72df4–0xb72e49`, `0xb7b2e5–0xb7b349`).
Verifying rows requires checking the parsed result buffer.

The opt-in daily score fixture accepts only the slot `0x08` shape with a
`Daily_YYYYMMDD_NN_score` event name and the `0x4010` value of 1,000.
It checks framing and block alignment and treats the incoming
`0x0060` ciphertext as opaque. Replies contain `0x8000/1`, `0x0000/2`
with status 1, `0x0060/3` with one ciphertext block, `0x4200/2` with
count zero, `0x4210/2` with value 1, `0x4220/2` with value zero, and
`0x8010/1`. The zero count skips the row loop at `0xb6a2a3–0xb6a2a6`.
The `0x4210` value and the terminator are fixture choices on this branch.

The generator encrypts the synthetic string `0_local` and its NUL
using the Blowfish seed and IV loaded by the title initializer
(`0xf6cc6–0xf6ce5`, `0xec87e0–0xec89e1`). An independent translation
of the reply decoder recovered the string from the generated block.
The bridge and service returned a byte-exact 52-byte reply to a
synthetic request. Guest acceptance and session continuity are
unverified.

### Event regulations

Slots `0x12` and `0x15` POST to `gameapi_getregulationdata`.
Discovery supplies the URL at context `+0x5d468` (`0xb82774–0xb827ef`).
The builders load it at `0xb52cf4` and `0xb60bee` before entering the
shared multipart producer at `0xb5d300`. For these slots the producer
uses the supplied URL (`0xb5d30d–0xb5d33a`, `0xb5d390–0xb5d3a2`).

| Slot | Records after the shared title and language envelope |
|---|---|
| `0x12` | `0x0020` carries the padded NUL-terminated string from `(*0x2c8f2e0)+0x20`. The `0x0060` payload comes from the same cipher helper as the daily score requests. `0x8010/1` follows immediately (`0xb52a4b`, `0xb52b78–0xb52c1d`, `0xb52cc4–0xb52cf4`). |
| `0x15` | The same `0x0020` and `0x0060`, then `0x6010/2` and `0x8010/1`. The extra payload is four packed decimal bytes for `YYYYMMDD`, derived from the list at context `+0x124e1c` using the signed index at `+0x127070` (`0xb60963–0xb609ab`, `0xb60a0a–0xb60a53`, `0xb60a9c–0xb60b1c`, `0xb60bf8–0xb60c36`, date format at `0x120b172`). |

Before sending slot `0x12`, the guest compares the first nonzero
packed date in its three cached entries against the current title
date. A mismatch clears those rows and their count
(`0xb52a52–0xb52b1b`).

Both success readers check `0x8000`, `0x0000` with status 1, and the
inner encrypted `0x0060` (`0xb6876d–0xb687c5`,
`0xb68446–0xb684a7`). After decrypting that record, the guest saves
the suffix from the first underscore and refreshes the tick used by
the next `0x0060` request (`0xb688d3–0xb68906`, `0xb685a8–0xb685db`).
The next record is `0x6000`. Its payload is newline-delimited text with
tab-separated columns. Both readers replace the last payload byte
with NUL and skip an initial UTF-8 byte-order mark when present
(`0xb6890b–0xb689c9`, `0xb685e0–0xb68657`, `0xb74c6f–0xb74c91`,
tab at `0x1215df9`, newline at `0x124ec58`).

| Slot | Row and completion behavior |
|---|---|
| `0x12` | An empty text record writes a cached result count of zero, then checks for `0x8010`. The populated path shown at `0xb791ad–0xb791ec` copies a 104-byte row and sets the count to one (`0xb689c9–0xb689d4`, `0xb76b67–0xb76b70`, `0xb791ad–0xb79202`). |
| `0x15` | Each parsed line increments the row count. The calendar cache at `(*0x2c6b648)+0x1f1d814` copies rows only when it sees `0x8010` and the count is positive. The month and day use zero-based strides `0x4a1c` and `0x264`, and successive entries use stride `0xcc` (`0xb74c68–0xb74d78`). The next step advances the selected date and can post another slot `0x15` request (`0xb712b2–0xb712d7`). |

The slot `0x15` row reader takes 35 tab-separated columns into a
104-byte record. Its numeric conversion uses base 10 and `_Stoul`
at `0x10fcee0`. Each row advances by `0x68` (`0xb73726–0xb73862`,
`0xb74c68–0xb74c91`).

| Columns | Slot `0x15` destination and evidence |
|---|---|
| 1 | The unsigned decimal text representation of the packed date, stored at row `+0x40` (`0xb737c8–0xb73862`). Bits 31–28 are year minus 2011, bits 27–24 are month, and bits 23–19 are day (`0xb74b77–0xb74b91`, `0x14a791–0x14a7e7`). |
| 2 | Text at the row start, copied by `strcpy` (`0xb7385a–0xb7388f`). Keep it to 63 bytes to leave room for the NUL before the date. |
| 3–6 | Four bytes at `+0x44` through `+0x47` (`0xb7390f–0xb73b57`). |
| 7–10 | A 32-bit word at `+0x48`, bytes at `+0x4c` and `+0x4d`, and a 16-bit word at `+0x4e` (`0xb73b5f–0xb73da7`). |
| 11–32 | One byte each at `+0x50` through `+0x65` (`0xb73db0–0xb74a60`). |
| 33–35 | Converted values have no stores into the row. The guest writes the date helper’s return value to `+0x66` (`0xb74a68–0xb74c18`). |

The 36-byte local reply begins with `0x8000/1` and `0x0000/2`
with status 1. It carries the encrypted daily score fixture in
`0x0060/3`, `0x6000/2` with four zero bytes, and `0x8010/1`.
The empty text clears the slot `0x12` result count and leaves
the slot `0x15` calendar untouched while advancing to the next
date (`0xb689c9–0xb689d4`, `0xb76b67–0xb76b70`,
`0xb791ec–0xb79202`, `0xb74c96–0xb74cb6`, `0xb712b2–0xb712d7`).

Loopback tests replayed both POST shapes with requests from 122
through 222 bytes, including invalid dates and record framing.
The saved Open Course traces contain no regulation request. Guest
acceptance and populated regulation replay are NOT_RUN. The
populated columns' gameplay meanings and the deployed text are
unverified.

### Daily event rivals

Slot `0x22` sends a multipart POST to `gameapi_getrivallist`.
Discovery writes the URL to context `+0x5d868` (`0xb80fc9`).
The builder scans 0x258-byte rows from the vector at `+0x122580`
and compares the first five bytes to the current selection.
The first comparison adds `0x20` to the selected byte. A missing
match skips the request (`0xb53ff4–0xb54059`). The shared producer
uses the supplied URL for this POST (`0xb5abd4–0xb5ac0e`,
`0xb5d325–0xb5d3a2`, GET literal at `0x120b1f6`).

| Request records | Payload and evidence |
|---|---|
| `0x8000/1`, `0x0010/5`, `0x0050/2` | Title header and language index plus one (`0xb5a74f–0xb5a7b6`, `0xb5aa59–0xb5aabd`). |
| `0x0080/65`, `0x0083` | The 256-byte context field and the padded session token (`0xb5a7bb–0xb5a855`, `0xb5aac4–0xb5aafd`). |
| `0x4a00/2` | 32-bit value 1 (`0xb5ab02–0xb5ab23`). |
| `0x4140` | Padded `Daily_%04d%02d%02d_%d_%s`; the last field is `OUT` for selections through 9 and `IN` for selections above 9 (`0xb5a708–0xb5a74a`, `0xb5a864–0xb5a916`, literals at `0x120b0a1`, `0x1215c63`, `0x1215c67`). |
| `0x4141/3`, `0x4142` | Eight bytes from row `+8` in little-endian order, followed by the padded NUL-terminated string at row `+0x18` (`0xb5a909–0xb5a999`, `0xb5aa0e–0xb5aa34`, `0xb5ab3c–0xb5abc2`). |
| `0x4143/2`, `0x4144/2`, `0x8010/1` | The two 32-bit values from row offsets `+0x10` and `+0x14`, then the terminator (`0xb5aa3d–0xb5aa54`, `0xb5abc7–0xb5ac0e`). |

The completion reads `0x8000`, status `0x0000`, optional `0x0072`,
and `0x0083` (`0xb6d70d–0xb6d75a`, `0xb6e573–0xb6e5ab`).
An optional `0x42e0` and up to two `0x42f0` records come next.
When present, the `0x42f0` payloads are split on tabs and parsed
as unsigned decimal values (`0xb6e5e7–0xb6e612`,
`0xb6f685–0xb6f782`, `0xb708e0–0xb709df`, delimiter at `0x1215df9`).
The guest optionally reads bit 0 of the `0x42d0` payload and
requires a signed row count in `0x4930`
(`0xb709e4–0xb70a44`). A positive count enters the `0x4931`
row parser, which can read the `0x4500` series
(`0xb70a97–0xb70afc`).

A count of zero skips the row parser, fills ten default entries, reads
the `0x8010` terminator, and dispatches success (`0xb70f19–0xb71117`).
With a Daily event configured, the localhost service accepts only the
matching event name. It returns a 36-byte reply with status 1, the
synthetic `local` token, a zero `0x4930` count, and `0x8010`.
Windows AddressSanitizer verified both request bounds (438 and 1,574 bytes)
and the exact reply through the scratch runtime bridge. The Open Course
hole-1 trace has no rival-list calls. Guest acceptance and populated rival
rows are NOT_RUN.

### Score registration and follow-up queries

The title-queue request stores its mode at offset `0x18`.
The queue builder reads that field at `0xa632a9` and selects a case
in the table at `0x11c8958` (`0xa639db–0xa639f6`). The table below
shows the actions appended by those cases in order.

| Mode | Queue actions and insertion sites | HTTP slots after the first action |
|---|---|---|
| `0x04` | `0x15` at `0xa64600`, `0x0a` at `0xa64f64`, `0x09` at `0xa652e3`, `0x18` at `0xa654dd` | Register `0x1a` (`0xa60a0e`), score list `0x19` (`0xa609e4`), own score `0x23` (`0xa60e8f`). |
| `0x09` | `0x15` at `0xa647bb`, `0x0e` at `0xa650ae`, `0x0d` at `0xa65381`, `0x19` at `0xa65407` | Register `0x1c` (`0xa60b0f`), score list `0x1b` (`0xa60a7f`), own score `0x24` (`0xa60f0c`). |
| `0x0d` | `0x15` at `0xa64898`, `0x12` at `0xa65145`, `0x11` at `0xa65434`, `0x1a` at `0xa65507` | Register `0x1e` (`0xa60bbf`), score list `0x1d` (`0xa60b95`), own score `0x25` (`0xa60f86`). |

The registration builder selects `gameapi_registscore` at `0xb6481c`,
`gameapi_registscoredaily` at `0xb64813`, or
`gameapi_registscorelongdrivecontest` at `0xb648a3`. It sends a multipart
POST via `0xb650d0`. For slots `0x19` through `0x1e`, the shared
formatter appends the decimal account ID, counter and `s=1`
(`0xb5d31d–0xb5d366`).

All three requests use the title, language and context records,
then the variable `0x0083` token. Serialization copies each record
using its count in four-byte words.

| Records in send order | Count or size evidence |
|---|---|
| `0x8000`, `0x0010`, `0x0050`, `0x0080`, `0x0083` | Counts 1, 5, 2, 65 and variable (`0xb63a30–0xb63bcd`, `0xb64e2b–0xb64ede`). |
| `0x4a00`, `0x4140`, `0x4141`, `0x4142` | Counts 2, variable, 3 and variable. `0x4a00` holds the request selector 0, 1 or 2. The builder replaces `0x4142`'s initial count of 33 with the padded string size plus its header (`0xb5ac13–0xb5acd6`, `0xb63ba6–0xb63c90`, `0xb63d93`, `0xb64ee7–0xb64f6e`). |
| `0x4143`, `0x4144`, `0x42b0`, `0x4500` | Counts 2, 2, variable and 3. `0x42b0` carries the formatted name and timestamp using the string at `0x120b015`. `0x4500` copies a little-endian 64-bit value (`0xb639cb–0xb63a19`, `0xb63da1–0xb63eac`, `0xb646ea–0xb64742`, `0xb64f77–0xb65003`). |
| One Hole and Daily tail | `0x4501/3` holds a second little-endian 64-bit value. It is followed by 14 indexed records `0x4600`–`0x460d` in order. The builder writes slot 0, slots 1–12 using the index table at `0x1234110`, then slot 13 (`0xb630e5`, `0xb63213–0xb63318`, `0xb634f6`, `0xb64749–0xb647a9`, `0xb6502c–0xb6509d`). |
| Long Drive tail | Eleven indexed records `0x4600`–`0x460a` in order. The table at `0x11b7240` supplies indices 0–5, 8 and 9. The builder fills indices 6, 7 and 10 separately (`0xb64900–0xb64a0d`, `0xb64bf9`, `0xb64d71`, `0xb64df6`, `0xb65013–0xb6502a`, `0xb636a0–0xb63887`). |
| `0x8010/1` | All three variants end with this record (`0xb63ecc`, `0xb6509f–0xb650d0`). |

Registration takes its group from offset `0x98` in the schedule row
(`0xb5ac84`, `0xb5acb4`, `0xb63bd6–0xb63c69`).
When loading a schedule, the guest fills that string from response record `0x4140`,
then parses it using the One Hole, Daily or Long Drive format
(`0xb75c4e–0xb75ce1`, `0xb76176–0xb761ae`).

All three registration slots share the reply decoder at `0xb841b0`.
It takes `0x8000`, `0x0000` status, optional `0x0072` and mandatory
`0x0083` (`0xb84312–0xb84376`, `0xb85e28–0xb85e57`). Slots `0x1a`
and `0x1c` then require `0x4270`. Every slot requires `0x42a0` and
`0x8010`. After checking each type, the decoder advances by the count
without reading the payloads of `0x4270` or `0x42a0`
(`0xb843bf–0xb84413`) and posts the success event at `0xb84475`.

On runtime `e6fb120` with the v10 discovery fixture, the Open Course
trace recorded `gameapi_registscore` after holes 1 and 2.

| Hole | Registration request | HTTP body sizes in order | Stored group | Stored primary, secondary |
|---|---:|---|---|---|
| 1 | 65604 | 40, 120, 76 | `OneHole_20180914_1_1` | 1, 20 |
| 2 | 65636 | 40, 120, 76 | `OneHole_20180914_1_2` | 5, 60 |

Each registration, score-list and own-score request returned HTTP 200.
The primary values agree with strokes over par in the recorded round.
The secondary field and deployed server values remain unverified.
Evidence comes from `work/evidence/open-course-registscore-holes1-2-1118.log`
and a read-only query of `work/online/scores-local.db`.

### Session score list

Slots `0x19`, `0x1b` and `0x1d` POST to `gameapi_getscorelist`,
loaded from context `+0x5d268` at `0xb60f96`. URL formatting appends
the decimal account ID and `&n=<signed int32>&s=1`
(`0xb5d31d–0xb5d366`). These slots use the own-score selectors and
group formats below, then add `0x4000/2/1` and `0x4010/2/<limit>`
before the terminator (`0xb60f36–0xb60f81`). The One Hole and Daily
callers use a positive limit if supplied, otherwise 100 and 200
respectively (`0xb5369f–0xb536ab`, `0xb5378b–0xb537a0`). Long Drive
uses 5 (`0xb5386a–0xb5387a`).

All three completions handle `0x90000310` as a completed query
with no rows (`0xb6d219–0xb6d239`, `0xb698f1–0xb69911`,
`0xb67ddf–0xb67e63`). The `--empty-own-score` fixture advertises
`gameapi_getscorelist?account=` and accepts 418 to 1,450 bytes for
the synthetic account. It returns the same 16-byte reply as own score.
The bridge also maps the exact blank-account URL to the unsigned daily
`_score` route so that its existing 52-byte reply still works with
both fixtures enabled. Guest replay is unverified.

On success, the parsers read `0x0083`, optional tab-separated decimal lists
`0x42e0` and `0x42f0`, and an optional `0x42d0` flag before the
required `0x4200` row count and `0x4210` value
(`0xb6e6d4–0xb6e7c6`, `0xb72bbc–0xb735d6`, `0xb76352–0xb765a2`,
`0xb76608–0xb76685`). Long Drive rows start with `0x4250`, a 32-bit
`0x4270`, and consecutive 64-bit stats of type `0x4500` through
`0x4509`. The parser converts the first stat to float and divides by 100
(`0xb79cbb–0xb79cc0`, `0xb7932c–0xb7944a`, divisor at `0x1167840`).
After any indexed `0x46xx` fields it requires the display name at
`0x0020`, the decimal account at `0x0084`, and row end at `0x4260`
(`0xb79530–0xb79543`, `0xb79768–0xb79816`). The One Hole and Daily
parsers also check the name, account and row end
(`0xb7a00d–0xb7a0aa`, `0xb7a8f0–0xb7a990`).

### Own score

Slots `0x23`, `0x24` and `0x25` require a nonzero session byte at
`(*0x2c6b648)+0x1f1d80f` (`0xa60e23–0xa60e2a`, `0xa60ea0–0xa60ea7`,
`0xa60f1a–0xa60f21`). Record `0x2032` in the login reply sets it
(`0xb8652e–0xb86541`).

Slots `0x23`, `0x24` and `0x25` POST to `gameapi_getmyscore`, loaded
from context `+0x5d8e8` at `0xb612a7–0xb612c1`. This URL stays unchanged
when it lacks the literal `GET` (`0xb5d30d–0xb5d33a`,
`0xb5d390–0xb5d3b3`).

The multipart part contains the standard title and language records,
then `0x0080/65`, the padded `0x0083` token, `0x4a00/2` selector,
`0x4140` padded group name and `0x8010/1`
(`0xb61054–0xb611d0`, `0xb611d8–0xb612c1`).

| Slot | Selector | Group format and producer |
|---|---:|---|
| `0x23` | 0 | `OneHole_%04d%02d%02d_%d_%d` (`0x120b086`, `0xb5405e–0xb5409f`). |
| `0x24` | 1 | `Daily_%04d%02d%02d_%d_%s`, with `OUT` or `IN` (`0x120b0a1`, `0xb540a4–0xb540fc`). |
| `0x25` | 2 | `LongDriveContest_%04d%02d%02d_%d_%d` (`0x120b0ba`, `0xb540fe–0xb54148`). |

Status `0x90000310` is stored and returned by the common decoder as
result 2 (`0xb860a7–0xb860c4`). Each own-score completion recognizes
that status, clears its score result and takes the success path
(`0xb66b8b–0xb66be7`, `0xb69b5d–0xb69bc2`, `0xb6691b–0xb669a0`).

The opt-in `--empty-own-score` fixture returns HTTP 200 with
`0x8000/1`, `0x0000/2` carrying `0x90000310`, and `0x8010/1`.
Its supported request lengths are 402 to 1,434 bytes. Host tests cover
all three selectors. Guest acceptance is unverified.

For a nonempty own-score success, the guest reads optional `0x0072`,
required `0x0083`, optional `0x42d0` bit 0, and a record whose first
payload word indicates whether a row follows. These branches check that
word but skip validation of its record type
(`0xb6e694–0xb6e6c7`, `0xb6eb05–0xb6eb38`, `0xb6ef70–0xb6efa3`,
`0xb6fb8f–0xb6fcf5`). The row starts with `0x4230` and `0x4270`,
then one to ten consecutive 64-bit records starting at `0x4500` and optional
indexed `0x46xx` records. The parser checks `0x4240` at row end and
`0x8010` at the end of the reply
(`0xb74da6–0xb74ecd`, `0xb779dd–0xb77ab8`, `0xb75113–0xb7512b`).

### Top players and daily score distribution

The task runner first selects slots `0x26` and `0x2a` at `0xa61022`
and `0xa610da`. Both use the shared multipart POST producer. For the
two HTTPS-form loopback paths, it copies the discovery URL without
appending an account suffix (`0xb5d30d–0xb5d3ae`).

Top players uses `gameapi_gettopplayerlist` from context `+0x5d968`
(`0xb54824`). After the title and language, the builder writes these records in order.

| Record | Payload | Guest addresses |
|---|---|---|
| `0x0080/65`, `0x0083` | Title context and padded session token | `0xb54575–0xb54667`, `0xb5476c–0xb54808` |
| `0x4a00/2`, `0x4a30/2` | Selector zero and four-byte BCD date. The date uses task words `+0x30`, `+0x34`, and `+0x38`. | `0xa60ff3–0xa6102e`, `0xa61069`, `0xb5466c–0xb54765`, date format at `0x120b172` |
| `0x4a10/2`, `0x4a20/2`, `0x4010/2`, `0x8010/1` | Task words `+0x28` and `+0x2c`, limit nine, terminator | `0xa60fff–0xa61004`, `0xb5480d–0xb54872` |

The completion reads status, optional `0x0072` and the session token
before `0x4970` (`0xb66413–0xb6649a`). A zero count leads to the
terminator and completion callback (`0xb664cd–0xb664d1`, `0xb762b6–0xb76338`).

A positive `0x4970` count enters a loop over result groups. Each group
starts with `0x4971`, `0x4140`, and `0x4210`. The guest reads the signed
word in `0x4210`, then expects `0x4941` or the group terminator `0x4972`
when that word is positive (`0xb6f670–0xb6f680`, `0xb6efc5–0xb6f08a`).

The `0x4941` branch reads a little-endian word and requires `0x4250`,
`0x4270`, and at least `0x4500`. The score records can continue
through `0x4509`, followed by indexed `0x4600` records
(`0xb6f08a–0xb6f1ce`). The remaining fields are `0x0080`, `0x0020`
for the player name, `0x0084` for the account, `0x0040` with three
copied bytes, `0x4290`, and `0x4260` (`0xb6f1ce–0xb6f2fb`).
`0x4972` closes the group and `0x8010` closes the reply
(`0xb6f303–0xb6f336`, `0xb6f548–0xb6f59f`, `0xb762b6–0xb762cb`).
The live field values for `0x4941`, `0x0040`, and `0x4290` remain
unknown. Guest acceptance of a populated top-player reply is NOT_RUN.

Daily score distribution uses `gameapi_getscoredistribution` from
context `+0x5da68` (`0xb54d29`). After the same title, language,
context and token records, it writes `0x4a00/2` with selector one
and `0x4140` with `Daily_%04d%02d%02d_%d_%s`. It uses `OUT` or `IN`
according to the task's `+0x2c` word (`0xa610bc–0xa61121`,
`0xb54a03–0xb54a5a`, `0xb54ad9–0xb54d37`, strings at
`0x120b0a1`, `0x1215c63` and `0x1215c67`). After status and token,
the guest tokenizes the NUL-terminated payload of `0x4950`.
An empty array supplies no quoted keys and reaches the empty-vector
completion at `0xb73020–0xb73058` (`0xb6c4a5–0xb6c551`).

The local listener uses `--empty-own-score` for both routes and
`--score-db` also enables them. The top-player request is 410 to
1,410 bytes, and the daily distribution request is 402 to 1,414 bytes.
The 36-byte empty replies share the title header and token. The
top-player reply carries `0x4970/2/0`. The distribution reply carries
`0x4950/2` with the bytes `5b 5d 00 00` (a padded `[]`). The runtime
owner's 19:22 run reached both POSTs and received HTTP 200.

With `--score-db`, the distribution route also reads the exact requested
daily group. A stored score produces one `num`/`score` pair in `0x4950`.
The guest compares the keys at `0x120b29f` and `0x120b2ad` and scans the
values with the `%d` format at `0x1223d86` (`0xb6c55c–0xb6c617`). The
loopback reply is 60–68 bytes for one signed 32-bit score. Empty groups
and old scores outside that range keep the 36-byte empty reply. Loopback
tests cover the maximum reply and group isolation. Guest display of a
populated distribution is NOT_RUN.

### Recorded local scores

With `--score-registration`, discovery advertises the three registration
URLs with a blank `?account=` suffix for the guest formatter.
`--score-db` enables the 180-byte login reply, user status, personal
scores, and session score lists on the listener. After checking the
synthetic account, counter, selector and record layout, it commits the
player name and score words to SQLite. A One Hole submission replaces
its event-group row when the primary score is lower or equal. The
listener acknowledges worse submissions while retaining the stored row.
SQLite stores no title context, token or indexed detail payloads.

Registration uses the success decoder's record order above. It replies
with a synthetic token, `0x4270/2/1` for One Hole and Daily, and a
header-only `0x42a0`. A score query returns one row with the stored
64-bit values and rank 1 for the single local account. The personal
score uses `0x4200/2/1` for the count, matching the list's count record.
Board replies use `0x4210/2/1` for the first row and include the stored
name and synthetic account ID. Groups without a submission still return
`0x90000310`. One Hole registration and readback appear in the trace
above. Guest acceptance for Daily and Long Drive and the deployed service's
ranking rules remain unverified.

### Board list

Slot `0x16` sends a multipart POST to `gameapi_getboardlist`, loaded
from context `+0x5d1e8` at `0xb53412`. It starts with the title and
language records, then writes these fields in order.

| Type | Payload |
|---|---|
| `0x0020` | NUL-terminated name from global context `+0x20`, padded to a four-byte boundary with the pad count as the byte value (`0xb53275–0xb53325`). |
| `0x0060` | The title's encrypted inner record. The helper at `0xb65110` caps the string at 44 bytes before adding the NUL and padding to eight-byte blocks (`0xb65224–0xb6528d`, `0xb53336–0xb5335d`). |
| `0x4000`, `0x4010` | One 32-bit word each. The start is 1 and the limit is calculated from timestamps, with a minimum of 2 and a cap of 213 (`0xb53169–0xb5322c`, `0xb532f9–0xb53332`, `0xb53404–0xb53429`). |
| `0x8010` | Header only (`0xb5342e–0xb53437`). |

The completion checks the opening record, status 1, and the
`0x0060` inner record (`0xb678c0–0xb67929`). It decrypts the inner
payload, requires an underscore, and copies the suffix to context
`+0x121a98` (`0xb6792f–0xb67a3d`). The next record types must be
`0x4100` and `0x4110`. The first payload word of `0x4110` is
the signed row count (`0xb67a4e–0xb67af3`). A zero count followed by
`0x8010` reaches the success handler (`0xb77556–0xb77565`,
`0xb73053–0xb73058`). A positive count enters the row parser, which
starts with `0x4120`, `0x4140`, `0x4150` and `0x4151`
(`0xb725eb–0xb72671`).

The opt-in local probe sends a 40-byte reply with
`0x8000/1`, `0x0000/2` with status 1, `0x0060/3` with the synthetic
encrypted block, `0x4100/1`, `0x4110/2` with zero rows, and `0x8010/1`.
The block contains the same `0_local` text as the daily score fixture.
Guest acceptance and original board payloads remain unverified.

### Event schedule board

Slot `0x20` POSTs to the same `gameapi_getboardlist` endpoint, or to
`gameapi_getboardlistcharactordownload` for selector 5
(`0xb53b78–0xb53c2a`, `0xb561af–0xb561d2`). It uses the title and
language records, `0x0080/65`, and a padded `0x0083` token
(`0xb55e24–0xb55f37`, `0xb5603a–0xb560c8`).

| Selector | Records after the token |
|---|---|
| Other than 5 | `0x4a00/2` selector, `0x4a40/2` from context `+0x12239c`, and `0x4a50/2` from `+0x122394` (`0xb53ba1–0xb53baf`, `0xb55f3c–0xb56010`, `0xb5610a–0xb5613f`). |
| 5 | `0x4a40/2`, `0x4000/2/1`, and `0x4010/2` limit (`0xb560de–0xb56134`). |
| Both | If context `+0x122390` is positive, append `0x4a10/2` with that value, `0x4000/2/1`, and `0x4010/2` limit. Finish with `0x8010/1` (`0xb53ba8`, `0xb55e0c`, `0xb55f69–0xb5602d`, `0xb5613c–0xb561d2`). |

Reply parsing starts with the opening records and status, then optional
`0x0072` and required `0x0083`. Next come `0x4100` and `0x4110`
(`0xb66d59–0xb66ddf`).
In this slot, the count comes from the first word of `0x4100`
(`0xb66de5`). Slot `0x16` reads it from `0x4110` instead
(`0xb67a4e–0xb67af3`). A loopback fixture for slot `0x16` uses
a header-only `0x4100`, so it cannot serve as a slot `0x20` reply.

Each schedule row starts with `0x4120` and a group string at `0x4140`.
Optional records `0x4141` and `0x4148` can follow. The parser can advance
over `0x4150` or read `0x4142`, `0x4143` and `0x4144` first.
BCD timestamps can appear at `0x4177` and `0x4178` before the
required row end `0x4130` (`0xb75c15–0xb75dfb`,
`0xb75e10–0xb760e9`, `0xb760ec–0xb76128`). After the last row it
checks `0x8010` (`0xb762b6–0xb762cb`).

For the three session registration slots, a missing schedule row
skips the POST (`0xb59ec6–0xb59f1b`, `0xb5a067–0xb5a0ba`,
`0xb5a296–0xb5a2a8`). The send paths compare the first five bytes of
each 600-byte row. The schedule parser fills those bytes from the group
name, storing the low byte of the year plus 32 (`0xb75ce6–0xb75d2c`,
`0xb76176–0xb7620c`). For Daily, it maps the `OUT` suffix to 9 and
`IN` to 18 (`0xb761bd–0xb7620c`, string at `0x1215c63`).
The registration lookup compares the server date, course and hole or
round selection (`0xb59dd0–0xb59e2f`, `0xb59ee4–0xb59f09`,
`0xb5a083–0xb5a0a8`, `0xb5a272–0xb5a296`).

Repeat `--event-group` on the listener to serve up to 18 distinct rows per
board selector. The guest uses the count to allocate 600 bytes per row
and walks the records in sequence (`0xb66de5–0xb66e83`,
`0xb76264–0xb7629e`). Each group's date must match `--server-time`.
Records `0x4177` and `0x4178`
mark midnight and 23:59:59. A `0x4150` record precedes the timestamps,
which lets the parser skip `0x4142`, `0x4143` and `0x4144`
(`0xb75de7–0xb75e0b`). The bridge accepts 394 to 1,418 request bytes and
up to 1,696 reply bytes. Slot `0x16` keeps the separate 138- to 230-byte
request range.
Host replay verified both shapes. Event entry and completion are NOT_RUN.

### Character download board

Modes `0x15`, `0x16` and `0x21` of title task state `0x15` select
board selector 5 (table at `0x11c8874`, branch `0xa61a42–0xa61a4a`).
The branch clears the optional window value before calling slot `0x20`
at `0xa60685–0xa606c1`. The selector table at `0x11cd934` sets the
page limit to 2 at `0xb53c2c`.

The prefix is the shared title, language, context and token. The
selector-5 writer adds `0x4a40/2`, page start `0x4000/2/1`, page
limit `0x4010/2/2` and the terminator (`0xb55f5f–0xb5602d`,
`0xb560de–0xb56108`, `0xb56134–0xb561d2`). A positive window value
adds `0x4a10/2` and repeats the same page records at
`0xb56146–0xb561a1`.

The request clears the selector's vector before posting
(`0xb55e10–0xb55e1c`). On reply, a zero `0x4100/2` count followed by
`0x4110/1` and `0x8010/1` takes the common slot `0x20` empty-list
path (`0xb66de5`, `0xb75bf6–0xb75bfb`, `0xb762b6–0xb762cb`).
Discovery's `--empty-boards` flag advertises the plaintext route.
The enabled listener serves a 40-byte empty list to valid requests
from 394 to 1,418 bytes. Guest acceptance is NOT_RUN.

### Finish-board list

Slot `0x13` uses `gameapi_getfinishboardlist` from context `+0x5d4e8`.
It skips the send if the discovered URL is empty (`0xb52d07–0xb52d22`).
The multipart body starts with the title and language records, a padded
`0x0020` name, and a `0x0060` encrypted record built by `0xb65110`
(`0xb52de0–0xb52e71`, `0xb52f17–0xb52fe0`). The tail is `0x6500/1`,
`0x6520/2` with a packed-decimal date, and `0x8010/1`
(`0xb52fed–0xb53033`). For the date, the builder passes `-1` to
`sceRtcTickAddYears`, then converts and formats the tick with `%04d%02d%02d`
(`0xb52d28–0xb52d79`, `0xb52e77–0xb52f14`, literal at `0x120b172`).

| Reply records | Guest action |
|---|---|
| `0x8000`, `0x0000`, `0x0060` | Checks for status 1, decrypts the inner record, and saves the suffix from the underscore onward at `+0x121a98` (`0xb6ca6f–0xb6cc08`). |
| `0x6540`, `0x6560`, `0x6580` followed by `0x6550`, `0x6570`, `0x6590` | Checks six types in order and dispatches the two groups to `0xb94d70` (`0xb6cc0d–0xb6cccb`). |
| `0x8010` | Starts the follow-up score request in slot `0x14` if `+0x124e18` is nonzero (`0xb6ccd0–0xb6cd13`). |

The payload words in `0x6580` and `0x6590` control whether
`0xb94d70` reads each group's text from the next record's payload
(`0xb6cc47–0xb6cc6d`, `0xb6cca2–0xb6cccb`). A zero count skips that
read (`0xb94d8e–0xb94daa`).

After validating the packed date, the local fixture returns 60 bytes
with the configured inner cipher block, both zero counts, and
`0x8010`. The follow-up score request requires a nonzero cached count
at `+0x124e18` (`0xb6cce3–0xb6cd13`).

### Sign-board list and download

Slot `0x17` sends a multipart POST to `gameapi_getsignboardlist` from
context `+0x5d568` (`0xb53635`). Its records are the title and language
headers, `0x0080/65` with 256 bytes from `+0x1223b9`, `0x0083` with
the padded NUL-terminated string from `+0x121e81`, and `0x8010/1`
(`0xb534ba–0xb5363c`). Discovery treats this URL as optional
(`0xb82a85`, validation loop above).

The reply parser reads `0x8000`, `0x0000`, optional `0x0072`, and
`0x0083` (`0xb69ee5–0xb69f3d`). The first payload word of `0x7802`
gives the signed row count (`0xb6f851–0xb6f884`). For a positive count,
the parser reads these fields for each row.

| Reply type | Observed effect |
|---|---|
| `0x7800`, `0x7803` | Pass both records to the common decoder before reading the URL suffix (`0xb6f8ac–0xb6f8da`). |
| `0x41f5` | Append the payload string to the URL base from context `+0x5e3e8` and store it at global offset `0x1f1ccc0 + index * 0xd8` (`0xb6f892–0xb6f927`). Discovery writes the base at `0xb7ea8a–0xb7ea96`. |
| `0x7804`, `0x7805` | Write a 32-bit value to global offset `0x1f1cca8 + index * 0xd8` and copy a string to `0x1f1cd40 + index * 0xd8` (`0xb6f933–0xb6f980`). |
| `0x7806`, `0x7801` | Advance past `0x7806` by its count, then check `0x7801` with the common decoder (`0xb6f985–0xb6f9c9`). |

Discovery loads the URL base from `cds_gamedata_down_url1`. The decoder
starts with `cds_gamedata_down_url3` at `0x11b7300`, changes the suffix
at `0xb7c03e–0xb7c055`, and copies the lookup result to `+0x5e3e8`
(`0xb7e945–0xb7ea96`).

A zero count skips those rows and still requires `0x8010`. After the
terminator, the guest checks up to ten cache entries and can start a
GET based on the stored version comparison or the first three cache
checks (`0xb6f9ec–0xb6fb06`, `0xb7af88–0xb7afdb`). The download uses
slot `0x18`, the indexed URL above, and a `0xa2800`-byte response
capacity (`0xb7afa1–0xb7afdb`). If the cache loop falls through, the
guest resets its download fields and calls `0xb5c860` with result 1
(`0xb6fb0c–0xb6fb5e`, `0xb76320–0xb7632e`).

The local empty-board fixture serves a 36-byte sign-board reply with
the synthetic `local` token, a zero `0x7802/2` count, and `0x8010/1`.
Guest acceptance of both lists and reuse of previously cached sign
boards are NOT_RUN.

The GET completion checks the transport flag and allocates a buffer
using the reported body length (`0xb675a0–0xb675f5`). It stores a
16-byte descriptor and copies the body (`0xb6e8aa–0xb6e8ce`). With
the save object idle, it stages the descriptors and starts save job 6
(`0xb6e8f3–0xb6e95e`, `0xb6f83b–0xb6f83e`). Job 6 pairs up to seven
non-null buffers with names from the relocated table at `0x132f1a0`
(`0xb9f6f5–0xb9f774`, `0xb9f972–0xb9f9dd`). The names are `DATA6.BIN`,
`DATA7.BIN`, `DATA8.BIN`, `DATAA.BIN`, `DATAB.BIN`, `DATAC.BIN`, and
`DATAE.BIN`, in order (`0x120c132–0x120c16e`). The deployed board files
and cache contents needed for a guest test remain unverified.

### National board list after login

The default login queue at `0x1232a20` contains actions `0x26`,
`0x28`, `0x25` and `0x27` in that order. Actions `0x26` and
`0x25` both dispatch slot `0x2f` unless the screen state is `0x10`.
They set the selector at context `+0x122390` to 0 and 1 respectively
(`0xa61366–0xa613eb`, `0xa612ef–0xa61364`). Action `0x24` sets
selector 3 and dispatches the same slot (`0xa61298–0xa612ed`,
`0xa61358–0xa613eb`). Actions `0x28`
and `0x27` can dispatch slot `0x31` for national game data. The
former requires a selected record with a populated field at `+0x248`.
The latter checks the field at `+0x268` in the national-event object
(`0xa61427–0xa614bb`, `0xa613f0–0xa61425`, `0xa6079e–0xa607bd`).

Slot `0x2f` sends a multipart POST to `gameapi_getboardlistnational`,
loaded from context `+0x5dc68` (`0xb55624–0xb55649`).

| Request type and count | Payload |
|---|---|
| `0x8000/1`, `0x0010/5`, `0x0050/2` | Title header and language index plus one (`0xb554bd–0xb554c3`, `0xb55554–0xb555de`). |
| `0x0080/65` | 256 bytes from `+0x1223b9` (`0xb554ac–0xb554ce`, `0xb555e5–0xb555f5`). |
| `0x0083` | NUL-terminated string from `+0x121e81`, padded to four-byte alignment with the pad count as the byte value (`0xb554d3–0xb5554d`, `0xb55580`, `0xb555fa–0xb55615`). |
| `0x4a40/2`, `0x8010/1` | Selector from `+0x122390`, then the header-only terminator (`0xb5544f–0xb5546c`, `0xb5561a–0xb55639`). |

The completion reads `0x8000`, `0x0000`, optional `0x0072` and
`0x0083` (`0xb6d88c–0xb6d8db`). A `0x4a60` record next supplies a
download URL suffix (`0xb6d8e1–0xb6d950`, `0xb7305d–0xb730b4`). With
`0x8010` next, the cursor instead reaches `0xb848a0` and completes with
result 1 without a GET (`0xb6d8ec–0xb6d8f1`, `0xb6efb0–0xb6efc0`,
`0xb84975–0xb849dc`). A successful slot `0x30` GET also enters this
parser with the body at its first record (`0xb69f4d–0xb69f61`,
`0xb6efb8–0xb6efc0`).
The completion table at `0x11cda44` sends both slots to the same
event selector, `0xb5c8f8–0xb5c906`. It emits `0x142` on success
and `0x143` on failure.

The opt-in `--empty-national-boards` fixture accepts selectors 0, 1 and 3
and returns 28 bytes with `0x8000/1`, `0x0000/2` with status 1,
`0x0083/3` with the synthetic string `local`, and `0x8010/1`.
The Windows host bridge replayed both request-length bounds. The runtime
owner reported that a 378-byte national board request received HTTP 200 and
the login queue completed on `0198f25` (2026-11-18 09:45 mailbox entry).
Deployed national event data remain unverified.

### National event downloads

Four national-event POST completions append a reply string to the same
`cds_gamedata_down_url1` base. The suffix and GET route depend on the
operation slot. The deployed reply bytes remain unverified.

| POST operation | Suffix record and URL assembly | Subsequent GET |
|---|---|---|
| `0x2f`, `gameapi_getboardlistnational` | `0x4a60` payload at `+4` (`0xb6d8e1–0xb6d950`, `0xb7305f–0xb73065`). | Slot `0x30`, capacity `0xa2800` (`0xb7306f–0xb730b4`). |
| `0x31`, `gameapi_getnationalgamedata` | `0x41f5` payload at `+4`, followed by `0x41f6` and `0x41f7`. The guest stores the first word of `0x41f6` at `+0x12805c` (`0xb66687–0xb66739`, `0xb75a62–0xb75a68`). | Slot `0x32`, capacity `0x2dc6c0` (`0xb75a97`, `0xb76b77–0xb76baf`). |
| `0x34`, `gameapi_getscoredistributionnational` | `0x4292` payload at `+4` (`0xb6de9c–0xb6df06`, `0xb730d4–0xb730da`). | Slot `0x35`, capacity `0xa2800` (`0xb730e4–0xb73129`). |
| `0x36`, `gameapi_getscorelistnational` | `0x4291` payload at `+4` (`0xb72a0a–0xb72a72`, `0xb72fad–0xb72fb3`). | Slot `0x38`, capacity `0xa2800` (`0xb72fbd–0xb73002`). |

#### Local national tournament

`--national-tournament` serves tournament ID 1 in group
`LocalTournament` for the calendar day selected by `--server-time`.
The board POST returns a 60-byte reply with `0x4a60` set to
`/local-national-board.bin` for selectors 0 and 3. Selector 1 keeps
the 28-byte empty reply.

| Slot | Format and evidence |
|---|---|
| `0x30` board GET | A 136-byte body with row count `0x4100` at offset zero, where `0xb848a0` begins parsing (`0xb69f4d–0xb69f61`, `0xb6efb8–0xb6efc0`, `0xb84aa3–0xb84ada`) |
| `0x30` row | Marker `0x4120`, words `0x4145` and `0x4146`, group `0x4140` and ID `0x4147` (`0xb84b63–0xb84c12`). Optional `0x4142–0x4144` precede display string `0x4150` (`0xb84c16–0xb84cc5`). The BCD start and end `0x4177` and `0x4178` precede `0x4130` (`0xb84ccf–0xb84ebc`, `0xb85032–0xb85049`). |
| `0x31` game-data POST | The guest finds the row by ID and sends group `0x4140`, ID `0x4147` and version `0x41f6` after the title and session fields (`0xb5564e–0xb55692`, `0xb563a9–0xb56470`, `0xb56529–0xb5656f`, `0xb54fb4–0xb54fc9`). The local route accepts 406 to 1,406 bytes at four-byte increments. Its 72-byte reply sets `0x41f5` to `/local-tournament.xb`, `0x41f6` to 1 and `0x41f7` to 0. |
| `0x32` game-data GET | Raw buffer and byte count at completion (`0xb65de3–0xb65e07`), then a write under `/download0/` (`0xa4fda2–0xa4fe83`) and a reopen (`0xa4df32–0xa4dfd4`) |

The FB archive has two files for the settings and messages paths at
`0xa4e1be` and `0xa4f797`. US English uses the suffix at index 9
in `0x1339030` (`0xa4f7c3–0xa4f7e5`). Its hash-sorted index,
stream ordinals, four-byte alignment and UTF-8 BOM match the
corresponding structures in the bundled US parameter archives.

The completion matches the archived payload to the saved request ID.
The slot `0x31` builder copies the selected ID into `ctx+0x128058`
at `0xb56289`. The handler compares it with row `+0x108` at
`0xa5dfe6–0xa5dff2`. The `0x41f6` reply word goes to the separate
version field at `ctx+0x12805c` (`0xb66712`).

Runtime `8eae334` received HTTP 200 for both POSTs and both GETs,
wrote the 188-byte archive to `/download0/`, and enabled the
International Tournament menu. Selecting it led to four HTTP 400
board responses in `work/evidence/international-tournament-1118.log`.
The listener regression test now replays selector 3.

| Tournament screen state | Queue behavior |
|---|---|
| `0xc4bc96–0xc4bc9e` | Mode `0x19` queues action `0x24` alone (`0xa64232–0xa6427d`, `0xa64c6f–0xa64c8b`) |
| `0xc4becd–0xc4bed9` | Mode `0x1d` takes the selected ID and queues action `0x2b` (`0xa64368–0xa643b3`, `0xa64d4c–0xa64d6b`) for the national own-score POST (`0xa6158b–0xa615a8`) |

#### National own score

Slot `0x37` finds a national board row by its ID
(`0xb557c3–0xb557fa`) and POSTs to `gameapi_getmyscorenational`
from `ctx+0x5dce8` (`0xb57223–0xb5722a`).

The selector-3 board POST and its download received HTTP 200 in the
runtime owner's 19:05 run. Four follow-up own-score POSTs used the
plain-HTTP URL from the v1 fixture. Each capture in
`work/online/http-dump-3/059..063-gameapi_getmyscorenational.bin`
contains 66 bytes of multipart framing with an empty part. The
plain-HTTP branch encrypts a stack copy and discards it before the
request composer reads the part buffer (`0xec9865–0xec99d9`). The
slot skips the send when the ID lookup misses (`0xb557d4–0xb557fa`).
The v2 and later discovery fixtures give this slot an HTTPS URL.

| Request fields in order | Guest evidence |
|---|---|
| Title, language, `0x0080` context and `0x0083` token | Copies the context and padded token at `0xb56d93–0xb56e47`, then writes the header and both records at `0xb5705b–0xb570ff` |
| `0x0086`, `0x0087`, `0x0088` login records | Reads the three records from `ctx+0x1224c4`, `+0x122548`, and `+0x122550` (`0xb56e50–0xb56ed6`), then copies them in order using their stored counts (`0xb57104–0xb5716e`) |
| `0x4140` group, `0x4147` ID, `0x4142` string, `0x4143` and `0x4144` words | Takes the strings from row offsets `+0x98` and `+0x18`, the ID from `+0x108` and the words from `+0x10` and `+0x14` (`0xb56e38–0xb57056`, `0xb57173–0xb57204`) |
| `0x8010/1` | Terminates the request at `0xb57209` |

The runtime owner's 19:44 run sent a 582-byte HTTPS request at
`work/online/http-dump-4/058-gameapi_getmyscorenational.bin` and got
HTTP 200 with the 16-byte `0x90000310` reply. The game showed
“Connection failed.” That status skips the tournament update and
takes the generic completion (`0xb6b3dd–0xb6b3eb`, `0xb7b2e5–0xb7b349`).

The listener now returns a 36-byte success with `0x0083`, `0x4200/2/0`
and `0x8010` for the captured request when the player has no saved score.
The zero-count branch reaches `0xb776b0` and sets entry `+0x299` after
finding the row by the original request ID (`0xb731d7–0xb731f7`,
`0xb776ce–0xb776dd`, `0xb777dc–0xb7786b`). Guest acceptance is NOT_RUN.

With a saved score, the parser reads the token and optional `0x42d0`,
then a nonzero count followed by `0x4230` and `0x42d1`
(`0xb6b436–0xb6b476`, `0xb731d4–0xb73242`).

#### National join notification

Mode `0x20` queues action `0x2f` (`0xa64458–0xa644a3`,
`0xa64e45–0xa64e61`). This action sends slot `0x3a`,
`gameapi_noticejoinnational` (`0xa61698–0xa616b5`). The scene
queues that mode with the manager's selected ID at
`0x9e77dc–0x9e7810`. The request
has the same group and row fields as national own score, with only
the context and token before them (`0xb5585e–0xb55894`,
`0xb5734d–0xb574db`, `0xb57584–0xb576d6`).

After the common reply header and token (`0xb6ce4d–0xb6cec4`),
the parser requires record `0x4962` and stores its first word at
`ctx+0x5f268` (`0xb6e522–0xb6e56e`). Reply event `0x150` copies
that value to the selected tournament entry at `+0x1190`
(`0xa5e0a6–0xa5e0d4`, `0xa5e29b`).

The settings loader copies `resetThreshold` from the table at
`0xa4e367–0xa4e3ad` into entry `+0x229` through the copy at
`0xa4e4e8` and `0xa4f8c0–0xa4f8d2`. The entry screen branches
when the reply word exceeds that byte (`0xc4b8d6–0xc4b8f9`).
The loopback fixture accepts 422–1,422 bytes for the synthetic
event and returns a 36-byte success reply with `0x4962/2/0`.
With the fixture's threshold of 0, the zero word branches to
`0xc4c837`. A positive word enters a path that can look up and
request a ticket spend (`0xc4c794–0xc4c832`) or open a dialog
(`0xc4b91c–0xc4b992`). The zero is a local first-entry fixture
value. Deployed count semantics, repeat-entry behavior and guest
acceptance remain unverified.

#### National score distribution

Action `0x2e` sends slot `0x34` (`0xa64e20–0xa64e3e`,
`0xa61679–0xa61696`). The builder sends the title, language,
context and token, then group `0x4140`, tournament ID `0x4147`
and terminator `0x8010` (`0xb565f2–0xb56883`). The local route
accepts 398–1,398 bytes for ID 1 and returns 68 bytes with the
`0x4292` suffix `/local-national-distribution.json`.

Slot `0x35` requires a successful, nonempty download before
copying the text and tokenizing it on a double quote
(`0xb6e319–0xb6e391`, delimiter at `0x121ff24`). The local GET
returns `[]` as two bytes before any score is stored. It reaches the zero-row path at
`0xb6e87a–0xb6e8a3` without supplying `num` or row fields.
Both routes passed loopback replay. Guest acceptance is NOT_RUN.

#### National score list

Slot `0x36` selects the tournament row at `0xb55718–0xb557be`
and writes the same session and event records as the join POST
(`0xb568f8–0xb56c93`). A page size of 1 adds the `0x42f3/65`
record. Its string comes from the same context field as `0x0080`
(`0xb568f8–0xb5691c`, `0xb56b05–0xb56b3b`,
`0xb56c9a–0xb56cca`). It appends the `0x4000` and `0x4010`
paging words and `0x8010` (`0xb56cd1–0xb56d1e`). The loopback
request bounds are 438–1,698 bytes.

After the reply header and any `0x42e0`, `0x42f0`, and `0x42d0`
records, the guest checks for the download suffix at `0xb72a0f`.
Without a suffix record, it sends the current cursor to the
score-list parser (`0xb65f39–0xb65fa7`, `0xb6e9c4–0xb6ead8`,
`0xb6eb45–0xb6eb47`, `0xb72a77–0xb72a85`). The local 44-byte
reply uses the inline form with `0x4200/2/0` and `0x4210/2/1`.
Zero rows branch to `0xb85c8a` (`0xb853bb–0xb853fa`,
`0xb8544d–0xb8549f`). Both request forms passed loopback replay.
Guest acceptance is NOT_RUN. The SQLite-backed reply is described below.

#### National score registration

The action at `0xa615ad` checks the active tournament manager at
`0x2c81150`, reads the selected ID at `+0x28c`, and dispatches
slot `0x39` (`0xa615ba–0xa61674`). The builder finds that board
row (`0xb557ff–0xb55859`). It gets the two score words from
the action's `+0x28` and `+0x2c` fields via `ctx+0x122394`
and `+0x122398`. The builder sign-extends each word before
serializing it as an eight-byte value at `0xb5b649–0xb5b705`.

| Records in send order | Guest evidence |
|---|---|
| Title, language, `0x0080` context and `0x0083` token | Creates these at `0xb5ad89–0xb5aedf` and copies them at `0xb5b711–0xb5b7c4`. |
| `0x4140`, `0x4147`, `0x4142`, `0x4143`, `0x4144` | Reads the tournament row fields at `0xb5aefa–0xb5b0a8` and copies them at `0xb5b7cd–0xb5b878`. |
| `0x42b0`, `0x4500/3`, `0x4501/3` | Formats the same name and date pattern as daily registration at `0xb5ad2a–0xb5ad76`. Then it serializes the padded string and two signed scores (`0xb5b0b2–0xb5b181`, `0xb5b649–0xb5b705`, `0xb5b881–0xb5b8e4`). |
| 14 detail records and `0x8010` | Initializes 14 `0x4600`-family slots and calls `0xb62e20` with selector 1 at `0xb5b199–0xb5b70c`. Serializes all slots using their word counts and writes the terminator (`0xb5b8f6–0xb5b96b`). |

The POST uses `gameapi_registscorenational` from `ctx+0x5dfe8`
(`0xb5b959`) and appends the account ID and counter via the
slot-specific formatting branch at `0xb5d31d–0xb5d366`.
After the common reply header and token, completion requires
`0x4270`, `0x42a0` and `0x8010` (`0xb661e1–0xb662ce`).

With `--national-tournament` and `--score-db`, the loopback route
accepts 590–5,134 bytes for the primary local account and returns the
40-byte rank-1 acknowledgement after committing the submission.
The fixture keeps the lowest primary score and its associated secondary
score for the configured server date and tournament ID.

| Readback | Local wire format and guest evidence |
|---|---|
| Own score | An 84-byte reply with count `0x4200`, one `0x4230` row, `0x42d1/2/2`, rank `0x4270`, both score words and `0x4240`. The fixture uses `2` to clear the two entry-status bits in the parser (`0xb73200–0xb73256`, `0xb77575–0xb776a8`). |
| Score list | A one-row inline page with `0x4250`, rank, both score words, player name `0x0020`, synthetic account `0x0084` and `0x4260` (`0xb854f0–0xb85576`, `0xb85785–0xb8585c`, `0xb85c40–0xb85c4b`). Pages after the first rank use the empty reply. |
| Distribution | The GET returns one `num`/`score` pair as quoted decimal values. The parser recognizes the keys at `0x120b29f` and `0x120b2ad` and scans both values as signed decimal words (`0xb6e3c2–0xb6e4e2`). |

Loopback tests verify both request-size bounds, invalid accounts and tournament
IDs, score readback after listener restart, and isolation across event dates.
Guest registration, populated views and repeat-entry behavior are NOT_RUN.

### Title queue after national boards

Action `0x10` sets the current action and returns without making an
HTTP request (`0xa607d0–0xa607ed`, table `0x11c87a0`,
`0xa61cac–0xa61cd2`). The tick's table at `0x11c8a50` then
selects `0xa687eb` (`0xa686af–0xa686ca`).

| Condition read by the tick | Effect |
|---|---|
| `**0x2c90758` or fields `+0x181b0` and `+0x181a8` in `*0x2cea1c0` | Wait if any value is nonzero (`0xa687eb–0xa6881a`). |
| `*0x2c99d30` exists | Also wait while the word at `*(*0x2c99d30+0x90)+0x278` is zero. Call `0xa6e2b0` when it becomes nonzero (`0xa68820–0xa68845`). |
| Checks cleared | Advance through `0xa632f0` (`0xa68861–0xa68883`). |

Next are three `0x05` notice actions and `0x13` user status
(`0x1232a20`). The third notice completion sets sequence flag
`0x2c8245c` (`0xa5e977–0xa5e999`). The user-status action skips
the POST if `(*0x2c6b648)+0x1f1d80f` is zero and advances directly
(`0xa60c23–0xa60c4f`, `0xa61d8b–0xa61d93`).

### User status

Slot `0x1f` sends a multipart POST to `gameapi_getuserstatus`, loaded
from context `+0x5d668` at `0xb53b50`. The dispatch requires the reply
flag set by `0x2032` (`0xa60c23–0xa60c4f`). Its request has these records.

| Request type | Count | Payload |
|---|---:|---|
| `0x8000`, `0x0010`, `0x0050` | 1, 5, 2 | Title header and language index plus one (`0xb53915–0xb53966`, `0xb53a15–0xb53a9f`). |
| `0x0080`, `0x0083` | 65, variable | 256-byte field from `+0x1223b9` and the padded NUL-terminated string from `+0x121e81` (`0xb5396d–0xb53a0e`, `0xb53aa6–0xb53ad6`). |
| `0x0086`, `0x0087`, `0x0088` | Stored header counts | Copies the three records from `+0x1224c4`, `+0x122548`, and `+0x122550` in order, using each stored count times four for its byte length (`0xb53adb–0xb53b43`). |
| `0x2500`, `0x8010` | 2, 1 | One zero 32-bit payload, then the header-only terminator (`0xb53b48–0xb53b6c`). |

The completion uses the common decoder with expected type `-1`
(`0xb6d3b8–0xb6d3f1`). When `0x8010` yields state 4, the caller
reports success if the login gate at `+0x5e5e8` is below 4
(`0xb6d3fa–0xb6d3fd`, `0xb6e666–0xb6e68f`, `0xb7b33f–0xb7b349`).
The completion table entry at `0x11cdac0` selects event `0x126` for
success or `0x127` for failure (`0xb5cb16–0xb5cb24`). The deployed
response and the meanings of the three reused records are unverified.

With `--login-completion --empty-own-score`, the 180-byte login reply
sets `0x2032/2/1` and supplies synthetic zero payloads for
`0x0086/33`, `0x0087/2` and `0x0088/2`. The guest copies those
records at `0xb86485–0xb864f9`. The user-status fixture accepts
526- to 1,526-byte requests that echo the records and send a zero
`0x2500` word. It returns a 16-byte success reply for the path at
`0xb6e666–0xb6e684`. Guest acceptance is unverified.

### Bonus list and redemption

The guest enqueues mode `0x17` for the list at `0x6c0651` and mode
`0x18` for redemption at `0x6c5e9e`. The mode table at `0x11c8958`
leads to task states `0x22` and `0x23` (`0xa64192–0xa641dd`,
`0xa641e2–0xa6422d`, `0xa64c3e`, `0xa64c61`). State `0x23`
skips the redemption POST if the selected row's first `0x7504`
source byte is zero (`0xa6125b–0xa61293`). The menu names and any
connection to Lucky Chance remain unverified.

Slots `0x2d` and `0x2e` use the title's multipart POST builder
(`0xb54f93–0xb54fc9`, `0xb5541e–0xb55443`). Discovery stores
`gameapi_getbonuslist` at context `+0x5dae8` (`0xb81572`) and
`gameapi_getbonus` at `+0x5db68` (`0xb81686`).
Both start with `0x8000/1`, `0x0010/5`, `0x0050/2`, the
256-byte context field `0x0080/65`, and the padded session token
`0x0083` (`0xb54dba–0xb54e51`, `0xb54ee8–0xb54f85`,
`0xb54ff1–0xb550a8`, `0xb5526a–0xb5531d`).

| Slot | Remaining request records |
|---|---|
| `0x2d` | `0x4000/2` and `0x4010/2` carry the 32-bit values from context `+0x122390` and `+0x122394`, followed by `0x8010/1` (`0xb54d9d–0xb54dcc`, `0xb54f8a–0xb54fc2`). |
| `0x2e` | Copies the cached `0x0086`–`0x0088` records using their header counts, then writes the decimal account string as `0x0084` (`0xb5512f–0xb551c3`, `0xb55326–0xb553a3`, format `%zu` at `0x120b15b`). |
| `0x2e` continued | `0x7503/252`, `0x7504/5`, and `0x7505/46` use source offsets `+0x1f1b5bd`, `+0x1f1b5ad`, and `+0x1f1b5cd` in the object at `0x2c6b648`. `0x7506/2` contains the zero-extended word at `+0x1f1b682`. The builder adds the selected index times 256 to all four offsets, then writes `0x8010/1` (`0xb54fce–0xb55003`, `0xb55041–0xb55070`, `0xb551d3–0xb55250`, `0xb553ac–0xb55443`). |

Both completions check the header, status, optional `0x0072` and
the session token (`0xb69d2b–0xb69d84`, `0xb6a55e–0xb6a5a5`).
The list completion accepts a terminator immediately after the token
and jumps to the common completion at `0xb7b2e5`
(`0xb69d8a–0xb69dab`, `0xb73053–0xb73058`).
Its longer form reads optional `0x0086`–`0x0088` records into
the same cache echoed by the redemption request (`0xb6fcfa–0xb6fdca`).
The following `0x7502` carries a signed row count at payload offset
0. A positive count enters the `0x7500` row parser, which reads
`0x7504`, `0x7505`, a 16-bit `0x7506` value, optional date fields
in `0x7508`, and `0x7501` (`0xb6fdd1–0xb6fe62`,
`0xb6fec3–0xb70095`). The redemption completion instead reads a
32-bit result from `0x7507` into `+0x122790` before dispatching
completion (`0xb6a5ab–0xb6a5dc`).

The saved Open Course traces have no calls to these routes. The meaning
of the redemption result and any links to historical item grants remain
unverified.

`--empty-bonus-list` in the discovery generator advertises the local
HTTPS-form POST. The listener accepts 386–1,386-byte title requests
with both paging records. A valid request gets a 28-byte reply with
status 1, the synthetic session token and the terminator. Loopback
tests cover both size bounds and an invalid paging record. Guest
acceptance is NOT_RUN.

### Course-world assignment

Dispatch slot `0x21` takes the `gameapi_assignmentcourseworld` URL from
context offset `0x5d6e8` (`0xb53e0c–0xb53e1a`). The producer appends
the account number and signed request counter with `%s%llu&n=%d&s=1`
(`0xb5d30d–0xb5d31b`, `0xb5d33c–0xb5d366`).

| Request type | Count | Payload |
|---|---:|---|
| `0x8000`, `0x0010`, `0x0050` | 1, 5, 2 | The usual title header and language index plus one (`0xb53c39–0xb53c8a`, `0xb53d39–0xb53dc3`). |
| `0x0080` | 65 | A 256-byte field copied from context `+0x1223b9` (`0xb53c91–0xb53cb3`, `0xb53dca–0xb53dda`). |
| `0x0083` | Variable | The string at context `+0x121e81`, including its NUL, padded to a four-byte boundary with the pad count as the byte value (`0xb53cb8–0xb53d32`, `0xb53d56–0xb53d65`, `0xb53ddf–0xb53dfa`). |
| `0x8010` | 1 | Header only (`0xb53dff–0xb53e13`). |

The completion deciphering branch at `0xb6b614–0xb6b71f` precedes a
loop of up to 101 calls to the common record decoder
(`0xb6b741–0xb6b7a4`). Each call passes expected type `-1`, and the
decoder advances the cursor by four times the count
(`0xb85e28–0xb85e33`, `0xb865ef–0xb865f8`).
When the decoder returns 2 and the stored status is `0x90000002`
or `0x90000158`, the loop immediately reports failure
(`0xb6b767–0xb6b78c`, `0xb7920d–0xb7921e`). Decoder state 4 from the
`0x8010` terminator takes the success branch
(`0xb6b767–0xb6b76a`, `0xb6e221–0xb6e22a`, `0xb7b2e5–0xb7b349`).
The completion table entry at `0x11cdac8` selects event `0x12a` for
success or `0x12b` for failure (`0xb5cb3c–0xb5cb4a`). The success handler
at `0xa5dd7b` gets the title clock and reads bytes at `+0x170`, `+0x172`,
and `+0x174` of the object at `0x2c8f2e0`. It adds `0x20` to the first
byte and writes all three to `+0x1f1d67b` of the object at `0x2c6b648`,
then checks for the active action `0x16` before advancing the queue
(`0xa5e669–0xa5e6f2`, `0xa5feaa–0xa5fec6`). The deployed reply and
any further assignment data it supplies remain unverified.

The runtime owner's 16:23 Open Course run skipped the 66-byte POSTs
at the bridge because discovery advertised the HTTP URL. The 16:37
run with the updated fixture emitted a 382-byte HTTPS request.
For the local score session, discovery now advertises a base ending in
`?account=`. The bridge forwards the 370- to 1,370-byte plaintext
multipart form. The listener checks the primary local account, signed
counter, context record and padded token before sending the 16-byte
header, success status and terminator. The reply follows the common
decoder's successful completion branch at `0xb6e221–0xb6e22a`.
Windows host replay passed at 370, 382 and 1,370 request bytes.
In the runtime owner's 17:29 run with `e6fb120`, request 65563
received HTTP 200 and the 16-byte reply. The next frame dump followed
the reply in the trace. The downstream schedule and score submission
remain unverified.

### Character download assignment

Slot `0x3d` reads `gameapi_assignmentcharactordownload` from context
`+0x5e268` at `0xb55b37` and enters the shared POST builder at
`0xb5a6dd`. The URL is used as supplied for this slot
(`0xb5d325–0xb5d390`). The Open Course hole-1 trace contains 30
references to that URL, including a 66-byte HTTP POST reported as
having no replay route (`open-course-hole1-complete-1118.log:2837–2838`).

| Request records | Guest evidence |
|---|---|
| `0x8000/1`, `0x0010/5`, `0x0050/2` | Title and language at `0xb55a99–0xb55aee` |
| `0x0080/65` | Copies 256 bytes from context `+0x1223b9` at `0xb559bc–0xb559de` |
| `0x0083/2–252` | NUL-terminated token and four-byte padding at `0xb559e3–0xb55a90` |
| `0x8010/1` | Terminator at `0xb55b2f` |

The shared builder selects plaintext multipart for the HTTPS URL
(`0xec982f–0xec985f`). The local listener expects 370–1,370 bytes.
It checks the title envelope, record widths, token padding, and
terminator.

The completion parser checks `0x8000`, status `0x0000`, optional
`0x0072`, and `0x0083` in that order
(`0xb6da82–0xb6dade`). The token handler reads a C string at
`0xb86259–0xb86265` and writes the transformed value back to
context `+0x121e81` (`0xb86275–0xb86417`). The completion dispatcher
posts `0x158` on success and `0x159` on failure
(`0xb7b33f–0xb7b349`, `0xb5cc7a–0xb5cc82`).

The local score-session fixture advertises the HTTPS URL and serves a
28-byte reply containing success status 1, the synthetic `local`
token, and `0x8010`. Enable it through the existing
`--empty-own-score` discovery and listener options, or the score
registration configuration. The runtime owner's 16:23 Open Course run
logged five HTTP 200 replies with 28-byte bodies. Guest handler
completion remains unverified.

### Character download counts

Slots `0x2c` and `0x3c` POST to `gameapi_getcountcharactordownload`
through the same multipart builder at `0xb62b70`. Discovery writes
the URL to context `+0x5e1e8` (`0xb8257c`), and the builder passes it
to the shared producer at `0xb62dda–0xb62df3`.

After the title envelope and language records, the builder writes the
256-byte `0x0080` context, the padded `0x0083` token, a `0x7704`
account string formatted with `%zu`, and `0x8010`
(`0xb62bfc–0xb62d0c`, `0xb62d13–0xb62dec`, format at `0x120b15b`).

| Slot | Account source and URL |
|---|---|
| `0x2c` | Reads context `+0x1271a0` and uses the supplied base URL (`0xb54d91–0xb54d98`, `0xb5d325–0xb5d33a`, `0xb5d390–0xb5d3ae`). |
| `0x3c` | Reads the current account at `(*0x2c8f2e0)+0x58`. The URL formatter appends that account, `&n=<signed int32>`, and `&s=1` (`0xb5590e`, `0xb55953–0xb5595a`, `0xb5d325–0xb5d366`, format at `0x120b1fa`). |

Both completions call the parser at `0xb844a0`, which checks the
header, status, optional `0x0072`, and token
(`0xb66c1d–0xb66c27`, `0xb6df0b–0xb6df1a`, `0xb84609–0xb84655`).
A zero 32-bit payload in
`0x7707` or `0x7708` bypasses the corresponding data branch
(`0xb846a5–0xb846f3`, `0xb8476e–0xb84793`). The builder clears all
four cached values before sending (`0xb62ba0`). Slot `0x3c` takes the
result values from context `+0x127190` and the next three words and
copies them into two local entries (`0xb6df7e–0xb6dfbb`,
`0xb6dfc0–0xb6e0fd`).

For the primary synthetic account, the localhost score-session fixture
advertises an HTTPS base ending in `?account=` and accepts both forms.
Its 44-byte reply contains status 1,
the `local` token, zero `0x7707/2` and `0x7708/2` values, and
`0x8010/1`. Listener tests cover both forms, request sizes from 394 to
1,394 bytes, and invalid accounts or counters. Guest acceptance and
populated count replies are NOT_RUN.

### Character download score list

Slot `0x3b` scans 0x258-byte board entries from context `+0x122600`.
It parses each entry's group string at `+0x98` with the literal
`CharactorDownload_%d_%d` at `0x120b0de` and compares the first number
to the requested value at `+0x122390`. A missing match skips the
request (`0xb55899–0xb55909`, `0xb58a4b–0xb58a52`).
The matched entry produces a multipart POST using the
`gameapi_getscorelistcharactordownload` URL from context
`+0x5e168` (`0xb8245c`, `0xb57af1`). The producer appends the
current account and counter, followed by `&s=1`
(`0xb5d325–0xb5d366`).

| Request records | Meaning and evidence |
|---|---|
| `0x8000`, `0x0010`, `0x0050`, `0x0080`, `0x0083` | Title, language, context and token (`0xb5773b–0xb57860`, `0xb579e9–0xb57a83`). |
| `0x4140`, `0x4148/2`, `0x4142` | Padded group from board offset `+0x98`, 32-bit value from `+0x254`, then the padded string from `+0x18` (`0xb558c8`, `0xb5784a–0xb57925`, `0xb5792a–0xb579c4`, `0xb57a88–0xb57ad8`). |
| `0x4143/2`, `0x4144/2`, `0x4000/2`, `0x4010/2`, `0x8010/1` | The words from board offsets `+0x10` and `+0x14`, page start 1, requested limit from context `+0x122394`, and the terminator (`0xb558b4–0xb558c3`, `0xb579cd–0xb579da`, `0xb57add–0xb57b3d`). |

After the header, status, optional `0x0072`, and token, the response
reader requires `0x4200` for the signed count and `0x4210` for a
second 32-bit value (`0xb6c86e–0xb6c8cf`, `0xb70241–0xb702a9`).
With a zero count it copies the list header to `(*0x2c8f2e0)+0x85cba8`
and dispatches completion (`0xb7315d–0xb73197`, `0xb7796e–0xb779c7`).
A populated path checks `0x4270`, reads `0x7700` when present, and
consumes indexed `0x46xx` records (`0xb702dd–0xb703b4`).
Deployed list contents and guest acceptance are NOT_RUN.

### Game property download

Slot `0x27` posts to `gameapi_getgamepropertyinfo`, loaded from
context `+0x5d9e8` at `0xb54927`. After the title and language
records it sends `0x7604/2` with property index plus one,
`0x7605/2` with the cached 32-bit value for that index, and
`0x8010/1` (`0xb5487e–0xb5489a`, `0xb5492e–0xb549a7`,
constants at `0x119d470` and `0x119d480`).

The runtime owner observed a 66-byte POST to the discovery HTTP URL
at boot on `e549b2c` (04:45 mailbox entry). The opt-in cached-property
fixture advertises HTTPS to select the plaintext builder at
`0xec982f–0xec985f`, giving 118 bytes including multipart framing.
The property index starts at zero before the outgoing record adds one
(`0xb5023d`, `0xb5487e–0xb54945`), so the fixture accepts index 1 and a
32-bit cached version. Its 24-byte reply contains `0x8000/1`,
`0x0000/2` with status 1, `0x7603/2` with value 1, and `0x8010/1`.
The isolated Windows transport passed the reply byte for byte.
The runtime owner observed one guest request on `648d038`. It got the
24-byte reply without a retry or download (05:35 mailbox entry).

Discovery supplies the download URL base as `cds_property_down_url1`.
The key starts as `cds_property_down_url3` at `0x11b7340` and is
rewritten before the lookup copies its value to context `+0x5e4e8`
(`0xb7bf01–0xb7bf19`, `0xb7c066–0xb7c093`, `0xb7ec90–0xb7ed42`).

The reply parser asks for `0x8000`, `0x0000`, and optional `0x0072`
(`0xb67727–0xb67760`, `0xb85e28–0xb85e3a`). A following `0x7603` with payload word 1
completes the request without a download
(`0xb67766–0xb67797`, `0xb73053–0xb73058`). The branch that starts
a download reads these records in order.

| Reply type | Observed effect |
|---|---|
| `0x7600` | Advances past this record using the word count (`0xb6eb4c–0xb6eb66`). |
| `0x4290` | Copies the URL base from context `+0x5e4e8` into the indexed URL at global offset `0x1f1d380 + index * 0xd8`, then appends the payload string (`0xb6eb6e–0xb6ebe2`). |
| `0x7605` | Stores the 32-bit payload at `+0x127130 + index * 4` and in global property metadata at `0x1f1d368 + index * 0xd8` (`0xb6ebe7–0xb6ec38`). |
| `0x7601` | Copies up to 32 bytes from the payload into the indexed field at `0x1f1d400 + index * 0xd8` (`0xb6ec3f–0xb6ec71`). |

The parser changes the operation to slot `0x28` and sends a GET for
that URL with a response capacity of `0xa2800`
(`0xb6ec7b–0xb6eccb`). The GET completion requires a nonempty body
and copies its bytes into an indexed buffer (`0xb68a1d–0xb68a5d`,
`0xb6f789–0xb6f7bd`).

When the save object is idle, the completion stages the first buffer
descriptor and starts job 7 (`0xb6f7e2–0xb6f843`). That job assigns
`DATA5.BIN` to the descriptor when the pointer and length are valid
(`0x120c128`, `0xb9e81e–0xb9e847`, `0xb9f6f5–0xb9f711`,
`0xb9f77a–0xb9f7e3`). The worker builds the file path from the mount
result and descriptor name, then passes the buffer and length to
`sceKernelWrite` (`0xb9fe30–0xb9fe9d`, `0xb9ff00–0xb9ff38`).
The deployed property files and the meaning of the 32-byte metadata
field remain unverified.

## NP, matching and peer transport

Each sequence below is a static path or adjacent group. The call-site index
covers repeats and alternate branches.

| Path | Calls and order |
|---|---|
| Title startup | Net init → net pool → NetCtl init → SSL init → HTTP init → NP title ID (`0xc0f3c–0xc0fc0`). The title registers its NP state callback at `0xf6d85`. |
| Availability and account checks | Create request → check NP availability or reachability → delete request (`0xb9ae2a–0xb9aead`). The parental-control path registers a reachability callback, creates a request, reads parental controls, then deletes it (`0xb9af0b–0xb9af63`). Online/account ID reads at `0xb97c92`, `0xb97ca2`. |
| Auth and PS Plus | Create async auth request → get authorization code → delete on submission failure (`0xa60ca9–0xa60d21`). Poll → delete at `0xb97f4c`, `0xb97f59`. The Plus path creates an async request then checks Plus at `0xa5a9e1`, `0xa5aa2b` and polls at `0xa5affc`. |
| Matching startup | Matching2 init → Signaling init → RUDP init → Matching2 context creation (`0xa7e0a5–0xa7e1e1`). If the signaling context ID is zero, create it at `0xa7e4f0` and rejoin the path at `0xa7e1fb`. Register context, lobby, room and signaling callbacks (`0xa7e209–0xa7e2a7`), set up the RUDP event handler and internal thread (`0xa7e2be`, `0xa7e2d5`), query NAT (`0xa7e467`), then start the Matching2 context (`0xa7e482`). |
| Discovery, rooms and lobbies | Server ID (`0xa8133b`), world list (`0xa813b6`) and lobby info (`0xa819e8`). Room operation handlers include create/join (`0xa779d8`), join (`0xa77db9`), external list (`0xa77f5e`), search (`0xa78155`), leave (`0xa78291`), and room messages (for example `0xa6d939`). Join lobby at `0xa83f8c`, leave at `0xa7dd79`. This is a set of operations with different callers, not a single mandatory sequence. |
| Peer path | Matching2 peer-net information (`0xa82167`) and signaling lookups (`0xa822d1–0xa823ed`), with activation (`0xa74243`, `0xa74616`) and status checks (`0xa7434b`, `0xa74380`, `0xa7479e`, `0xa747d7`). The transport opens and binds sockets (`0xa7494f–0xa74b48`), sets up the RUDP context and options (`0xa74d2f–0xa74e3d`), and initiates (`0xa74e90`). Data transfer uses `sceRudpWrite` (`0xa7f5b5`, `0xa7f71b`), readability query and read (`0xa7f9ef`, `0xa7fa15`). Exact peer payloads and callbacks are unresolved. |
| TUS | Title-context setup (`0xaa6a28`), request creation (`0xeccce2`), then get or set async data (`0xeccd44`, `0xeccda7`). Poll (`0xecd487`) and delete (`0xecd5b9`). A title-context delete also appears at `0xaa69b3`. |
| WebAPI and presence | WebAPI init and context creation (`0xecde9d`, `0xecdebd`), handle and push filter creation (`0xecdc88–0xecdcd0`), callback registration (`0xb98ccd`, `0xb98cf3`, `0xb99674`, `0xb996a1`). Request creation (`0xece37f`) uses a JSON content-type literal at `0x12190a6`. The worker sends at `0xece463`, then reads into a buffer with a total cap of `0x80000` (`0xece490–0xece4a4`). See the WebAPI request table for relative paths and response fields. |
| Word filter and social dialogs | Word-filter title context (`0xee75a`), async request and comment filter (`0xece741`, `0xece756`), poll and deletion (`0xeec4a`, `0xeed24`). Friends dialog initialize → open → update → close → terminate (`0xab5089–0xab51d6`), result elsewhere (`0xef69b9`). |

The Plus check creates an async request with size `0x18` (`0xa5a9cd–0xa5a9e1`).
It passes a zero-initialized `0x38`-byte parameter with the current user at
offset `0x08` and feature mask 1 at offset `0x10` (`0xa5a9c2`,
`0xa5a9ea–0xa5aa2b`). After `sceNpPollAsync` returns zero, the guest deletes
the request and checks the first result byte (`0xa5affc–0xa5b003`,
`0xa5b5ff–0xa5b616`). The reference NP manager types identify that byte as
`authorized` and the following 32 bytes as reserved.

Any later attempt to implement local session, room, signaling or event
behavior needs the corresponding request/response contract and a loopback
capture coordinated by the runtime owner. The server receives synthetic local credentials for the login fixture.
Its telemetry route drops request bodies and receives no original auth
headers. It has no peer transport.

### Open Course entry failure

The English dialog "Server connection failed" is in message block `0x48`
of `xbdata/menu/message_text.US_01.xb`. The zlib stream starts at file
offset `0x17ae4`. The guest loads `data/menu/text/System_Dialog.to`
(`0x120ad3c`) into the global message table at offset `+0xe8` through
the relocated table at `0x132ee40` (`0xc6645–0xc66b7`). Group 34,
item 5 (zero-based) has a pointer at decoded offset `0x410` to text
at `0x1d36`. The controller at `0xa5ada0` selects this group and item
at `0xa5b893–0xa5b8b5` and calls the dialog routine at `0xa5b8c9`.
Its state dispatch table is at `0x11c83d0`.

| Check | Failure branch |
|---|---|
| State 2 schedules `0xb9aa20` (`0xa5a316–0xa5a337`). It calls `sceNpCreateRequest`, `sceNpCheckNpReachability`, and `sceNpDeleteRequest` (`0xb9aa2d`, `0xb9aa45`, `0xb9aa5d`). A reachability return of zero stores 2 at `0x1361ee0`. Any other return stores 0 (`0xb9aa4a–0xb9aa55`). | A negative stored value keeps the check pending. A completed check requires value 2 and a nonempty string from `sceNetCtlGetInfo(14)` (`0xa5ae4f–0xa5aea9`). Otherwise it reaches the dialog when the counter reaches 60 (`0xa5b202–0xa5b223`). |
| State 6 starts Matching2 at `0xa5a473` through `0xa76c10` and `0xa7dfd0`, unless an active matching task can be reused (`0xa5a456–0xa5a478`). | The controller selects the dialog with results 7 and 1 if global `0x2c8f358` is 3 and `0x2c8f354` is 2 (`0xa5b029–0xa5b059`), or if the Matching2 object's state at `+0x48` is `0x2a` (`0xa5b1b0–0xa5b1b6`, `0xa5b2fc–0xa5b302`). Context event `0x6f01` and `0x6f02` with a negative result feed that state into `0xa7a8f0` (`0xa7e834–0xa7e86d`, `0xa7e887–0xa7e8a4`). |
| State 5 polls the Plus task at `0xa5affc`. | When the task finishes, a zero byte at `+0x2c` or `+0x05` goes to the same dialog with results 4 and 1 (`0xa5b7de–0xa5b7f2`, `0xa5b85d–0xa5b870`). |

The availability worker at `0xb9adf0` calls
`sceNpCheckNpAvailabilityA` at `0xb9ae41`. A nonnegative return sets
`0x2c8f354` to 1 (`0xb9ae46–0xb9ae4c`). On a negative return, the
table at `0x11cddfc` maps error `0x8055000b` to `0xb9aee0`, which
sets `0x2c8f354` to 2 before `0xb9afb7` sets `0x2c8f358` to 3.
`0x80550006` falls outside that table and selects 7 at `0xb9af7b`.

#### Title requests before NpAuth

Controller state 3 submits title mode `0x01` when `0x2c8245c` is zero
or `0x14` otherwise (`0xa5a341`, `0xa5a3c1`, `0xa5a6fa–0xa5a70c`).
With the title queue idle, `0xa632a9–0xa632b8` passes this mode to
`0xa633d0` and advances to the first queued action. The default
initialization appends actions from the 14-entry table at `0x1232a20`
(`0xa63521–0xa63612`). Its first four actions are these.

| Action | Dispatch | Success event |
|---|---|---|
| `0x01` | Discovery, HTTP slot `0x00` (`0xa607ef–0xa60841`). | `0xe6` (`0xb5c94e–0xb5c95c`). |
| `0x07` | Server time, HTTP slot `0x04` (`0xa608e5–0xa608fd`). | `0xe8` (`0xb5c974–0xb5c982`). |
| `0x0f` | Property info, HTTP slot `0x27` (`0xa60b19–0xa60b31`). | `0x136` (`0xb5c8e5–0xb5c8f3`). |
| `0x14` | Creates the async NpAuth request and asks for a code (`0xa60c54–0xa60d19`). | The tick advances after the request ID is negative and the code is nonempty (`0xa68847–0xa68883`). |

The event dispatch table is at `0x11c8460`. Property success enters
`0xa5de46` and checks for active action `0x0f` at `0xa5ec32–0xa5ec3d`.
With a pending queue, `0xa5feaa–0xa5febf` requires both the current
action and the queue head to match before calling `0xa632f0`.
That function removes the completed action and dispatches the next one
through `0xa60120` (`0xa63361–0xa633c6`). Property failure enters
`0xa5de96` and selects failure state `0x33` (`0xa5dee1–0xa5dee8`,
`0xa5fec6–0xa5fece`).

At runtime revision `648d038`, a valid Matching2 context creation returns
`0x80550006` from `matching2_context_a`. The guest branches to cleanup on
any nonzero return (`0xa7e1e1–0xa7e1e8`, `0xa7e0ce`). The separate
context-start import at `0xa7e482` also maps to the signed-out handler in
that revision. The owner observed the dialog before any auth call or
login POST (05:35 mailbox entry). The branch that fired in that run still
needs a guest trace. The title login itself requires a nonempty auth
code at `0xa60879` before slot 3 can begin.

## Matching2 discovery callbacks

The primary path creates a context with a 16-byte parameter, including the
current user ID, and receives a 16-bit context ID at object offset `0x44`
(`0xa7e1b0–0xa7e1e8`). It registers `0xa7e820` as the context callback, passing the callback in
RDI and the Matching2 object in RSI (`0xa7e216–0xa7e220`).
The context ID argument appears in the separate lobby callback
registration (`0xa7e22d–0xa7e23b`). The guest requests context start
at `0xa7e482`.

The context callback checks the supplied context against the object's
ID at `0xa7e82b`. Event `0x6f02` with a nonnegative error code sets
state 5 (`0xa7e842–0xa7e84d`). The update loop dispatches state 5 to
`0xa81330` via table `0x11c8c54` (`0xa80de9–0xa80e08`). Event
`0x6f03` destroys the context and clears the ID
(`0xa7e872–0xa7e87a`).

| World-list ABI item | Guest evidence |
|---|---|
| Server ID | `GetServerId(context_id, &server_id)` at `0xa81330–0xa8134a`. A negative return takes the failure path. The ID output is read as a 16-bit value. |
| Request | `GetWorldInfoList(context_id, &request, &options, &request_id)` at `0xa81385–0xa813b6`. Request offset 0 holds the 16-bit server ID (`0xa81372`). The 32-bit request-ID output is at object offset `0x54`. |
| Options | A 24-byte object has the callback pointer at offset 0, userdata at 8, and a 32-bit timeout at 16. The title clears default options at `0xa81380`, sets the per-request fields, and converts the timeout from seconds with a multiplier of 1,000,000 (`0xa81385–0xa813ac`). |
| Request completion | The guest waits in state 6 after nonnegative submission (`0xa813bb–0xa813ce`). Callback `0xa79430` takes context, request ID, event, result, response and userdata. Event `0x0002` selects the world-list branch (`0xa79897–0xa7989d`). |
| Response | That branch requires a nonnegative result and a nonnull response object (`0xa79f8e–0xa79f9a`). It reads the row pointer at offset 0 and the low 32 bits of the count at offset 8 (`0xa79faa`, `0xa79fe0`). The reference ABI specifies a 64-bit count. |
| Row storage | The loop copies 40 bytes per row and advances the source index by 40 (`0xa7a024–0xa7a029`, `0xa7a095–0xa7a0bc`). Provide a contiguous array. The reference layout has a next pointer at `+0`, then six 32-bit fields at `+8` through `+0x1c`: world ID, lobby count, maximum lobby members, current lobby members, room count and room members. |
| Empty list | A zero count skips copies, leaves an empty guest vector and enters state 7 (`0xa79fae–0xa79fbf`, `0xa7a0c2–0xa7a0c7`). Supply a real response object even for an empty list. |

The same request callback is passed by the six alternate world-list call
sites at `0xa0a0f4`, `0xa0dd3e`, `0xa0f005`, `0xa1768f`,
`0xa72312`, and `0xa740bc`. The public type names match the local
DriveClub shadPS4 reference in
`external/driveclub-recomp/gpu/shadps4/core/libraries/np/np_types2.h`. Actual server/world IDs
and population values require capture or a local multiplayer design.

The lobby pager matches its selected world ID against row offset `+8`
(`0xa8153e–0xa8158c`). On a match it uses the selected row's lobby count
at `+0xc` to bound the request index (`0xa818c2–0xa8190e`). A world row
with a zero lobby count can test world completion. A local lobby test
needs a matching world ID and a positive count.

The lobby-list request at `0xa819e8` uses the same four arguments and
callback. It writes a 32-bit selector at request offset 0, a computed
one-based index at 8 and a page length capped at 20 at 12
(`0xa81927–0xa819a2`). A nonnegative submission sets state `0x0e`
(`0xa819ed–0xa819f5`). The adjacent event `0x0006` is the inferred
lobby-list completion. Its callback reads a 32-bit count at response
offset 8 and a row pointer at 16 (`0xa798a3–0xa798ba`, `0xa798f0`).
It copies 80 bytes per row and sets state `0x10`
(`0xa799a4–0xa799e0`). The remaining request and response fields for
lobbies and the event binding still need a runtime trace.

`JoinLobby` writes an eight-byte lobby ID at request offset 0
(`0xa83f7f–0xa83f8c`). On successful submission it saves the request
ID and sets state `0x13` (`0xa83f91–0xa83f9e`). The callback branches
on the reference JoinLobby event `0x0201` and requires a nonnegative
result and a response (`0xa796f8–0xa7970f`). Response offset 0 is a
pointer to an inner record. The guest caches the lobby ID from inner
offset `0x10` and a 16-bit value from `0x28`
(`0xa7971f–0xa79731`). It copies 16-bit member IDs from the pointer
at `0x18` using the 64-bit count at `0x20`
(`0xa79746–0xa79758`, `0xa797d9–0xa797f8`), then enters state
`0x14` (`0xa797fe–0xa79803`). The inner record and every referenced
array must remain valid for the duration of the callback.

`LeaveLobby` passes the cached lobby ID at request offset 0
(`0xa7dd67–0xa7dd79`). The adjacent `0x0202` callback takes the
teardown path through state `0x0d` (`0xa799ec–0xa799f8`).
That state clears the cached lobby ID and 16-bit value
(`0xa814d5–0xa814ec`). The event-to-operation pairing is inferred
from this teardown path. Runtime callbacks and multiplayer behavior
remain untested.

World, lobby and join request callbacks must be deferred until the caller
returns from submission. After the API call, the guest writes pending
state 6 for worlds (`0xa813b6–0xa813c5`), `0x0e` for lobbies
(`0xa819e8–0xa819f5`), or `0x13` for join (`0xa83f91–0xa83f9e`). An
inline callback can have its completion state overwritten by that store.

### Loopback lobby membership

The bridge uses the world ID from request offset 0 as the local lobby
ID, which the guest takes from the returned row when it calls JoinLobby
(`0xa81927–0xa819a2`, `0xa73a9d–0xa73ab8`). One roster snapshot supplies
the member IDs in the join reply and the linked list in event `0x7207`.
That handler reads the name at offset `0x20` and member ID at `0x34`
(`0xa79833–0xa7988b`).

After a successful join, the worker polls once a second. It delivers
additions as `0xa201` and departures as `0xa202`, using a pointer to one
member record. The guest can create the member or mark its existing slot
for cleanup (`0xa7e8b0–0xa7e8e5`, `0xa7e8ff–0xa7e92f`). When the server
reports an expired session, the worker sends `0x3203` for lobby teardown
(`0xa7e8ea–0xa7e8fd`, `0xa7e931–0xa7e93e`).

The native runtime calls `POST /nmg-us/local-lobby/v1` with
`application/octet-stream`. The 36-byte request is little-endian.

| Offset | Request |
|---:|---|
| 0 | Operation byte, 1 join, 2 renew and read, 3 leave. |
| 1 | World ID, 1 through 50. |
| 2 | Two reserved zero bytes. |
| 4 | A 16-byte join nonce on join, or the server-issued session token on renew and leave. A zero join value keeps the original one-shot behavior. |
| 20 | 16-byte online name, with zero padding on join and all zeros for renew or leave. |

HTTP 200 returns a 20-byte header containing the caller's 16-bit member
ID at offset 0, row count at 2, a reserved zero byte at 3, and the token
at 4. Up to 50 rows follow, each with a 16-bit member ID and 16-byte padded
name. After a successful leave, the server returns an all-zero header
with no rows. HTTP 404 indicates an absent lease. HTTP 409 indicates
a full world or a live join nonce reused with a different name. Tokens
and rosters stay in memory, with each lease expiring 15 seconds after
its owner's last renewal.

A runtime transport failure retries a join once with the same random
nonce. Within a world, the listener looks up that nonce before checking
capacity and returns the existing lease and current roster. Separate
joins use different nonces, even if their online names match. The join
nonce expires with the lease. A Windows AddressSanitizer probe dropped
the first reply after the listener accepted the join and verified that
the retry occupied one seat. Two native clients then joined the same
room, exchanged RUDP payloads in both directions, and observed the
room and lobby departure callbacks. Guest recovery is NOT_RUN.

Windows ASan probes exercised two clients, world isolation, and a full
50-member roster through the bridge. Avatar visibility and movement in
the game are NOT_RUN. Peer address exchange and room traffic remain open.

## Matching2 rooms and peer transport

### Capture-the-flag settings

The guest opens `data/param/serverFile/capture_the_flag_game_settings.txt`
at `0x9322ae–0x9322e6`. The name-table lookup at `0xea55d0–0xea572a`
resolves hash `0x1df3184f` to stream index 11 in `info.US_01.xb`, whose
compressed data starts at file offset `0x4658`. The one row supplies
these values to the local settings structure.

| Column | Value | Guest field and write |
|---|---:|---|
| `matching_create_room_avg` | 0 | Byte `+0`, `0x9323b7` |
| `matching_join_roomlist_check_value` | 5 | Byte `+1`, `0x932454` |
| `matching_join_roomlist_recall_sec` | 5 | Byte `+2`, `0x932500` |
| `matching_reception_sec` | 80 | 16 bits at `+4`, `0x93259d` |
| `matching_player_max` | 20 | Byte `+6`, `0x932650` |
| `matching_player_min` | 6 | Byte `+7`, `0x9326ed` |
| `matching_same_course_exclusion` | 0 | Byte `+8`, `0x932790` |
| `next_reception_countdown_sec` | 15 | Byte `+0xa`, `0x93282d` |

The settings loader establishes the supplied values. Their consumers
and the matchmaking thresholds used by other modes remain untraced.

### Room requests and callbacks

The room requests below reset default options and pass callback
`0xa79430` with a per-request timeout and a request-ID output
at object offset `0x54`. Examples are `0xa779a7–0xa779d8`
for creation and `0xa77d5c–0xa77db9` for joining.

| Operation | Confirmed request and completion fields |
|---|---|
| `CreateJoinRoomA` | The request at `0xa779d8` writes a 16-bit slot count at offset 0, flags at 8, and a 32-bit world selector at 12 (`0xa778b2–0xa778bf`). With a nonempty title-data span it attaches that span under attributes `0x57` and `0x55` (`0xa778e1–0xa7793b`). Event `0x7101` selects the account-ID creation result at `0xa794a1–0xa794e8`. |
| `JoinRoomA` | The request's first eight bytes hold the room ID (`0xa77da6–0xa77db9`). Nonnegative submission sets state `0x1d` (`0xa77dbe–0xa77dec`). Event `0x7102` dispatches to `0xa79d51` by `0xa79812–0xa79817`. |
| `GetRoomDataExternalList` | At `0xa77f17–0xa77f5e`, the request contains a room-ID pointer and count at offsets 0 and 8, plus an attribute-ID pointer and count at 16 and 24. The caller requests one room and one attribute, `0x55`. Event `0x7005` reads the returned row pointer from response offset 0 and uses the first row (`0xa79496–0xa7949b`, `0xa799fd–0xa79a73`). |
| `SearchRoom` | The request at `0xa78155` asks for attribute `0x55` (`0xa78115–0xa78144`). The account-ID result event is `0x7106` (`0xa7981d–0xa79822`). It uses the range's start and returned count at offsets 0 and 8 (`0xa79f63–0xa79f89`). With a positive count the row pointer is read at offset 16, and traversal follows the pointer at each row's offset 0 (`0xa7a41b–0xa7a466`). |
| `LeaveRoom` | The cached or supplied room ID is passed at request offset 0 (`0xa78254–0xa78291`). Event `0x0103` clears the cached room ID and member state (`0xa796e2–0xa796e7`, `0xa79bad–0xa79bee`). |

The local DriveClub shadPS4 reference selects the account-ID search result
from its context type even though the entry point is named
`sceNpMatching2SearchRoom` (`np_matching2.cpp`, call to `MmSearchRoom`).
Its `np_types2.h` definitions agree with the observed SearchRoom result
range and linked-list traversal.

Both account-ID create and join callbacks check the result and response
pointer. They then read the internal-room pointer at response offset 0
and its room ID at offset `0x18`
(`0xa794ac–0xa794e8`, `0xa79d51–0xa79d8d`). The response has the member
chain head and count at offsets 8 and `0x10`. The self and owner pointers
are at `0x18` and `0x20`. The callback reads member IDs at offset
`0x38` in both entries, then walks the chain using each member's pointer
at offset 0 (`0xa79640–0xa7966a`, `0xa79ed7–0xa79f40`). Supply valid
self and owner pointers for a successful result, including a creator who
owns their own room. The SDK layouts are in the local reference's
`OrbisNpMatching2CreateJoinRoomResponseA` and
`OrbisNpMatching2RoomMemberDataInternalListA`. The guest copies listing
bytes from external attribute `0x55` into a 256-byte field
(`0xa79a79–0xa79b27`). Room join also copies the first internal attribute
to a 256-byte field ending before `+0x7d0` (`0xa79d94–0xa79e24`). The
contents of the title's attachment attributes remain unverified.

The two direct callers of the create wrapper at `0xa77780` set mode 0
at `0xa57a2c` and `0xa76404` before calls at `0xa57efd` and `0xa76478`.
The second caller passes 224 listing bytes (`0xa7645d–0xa76470`). The
create wrapper stores that mode at object offset `+0x580` (`0xa778da`).
Command byte 2 in the dispatch table at `0x11c8d08` can also set this
field to -1, 0 or 1 from the next four bytes (`0xa82cfb–0xa82d13`).
The UI actions that send command 2 with value 1 remain unverified.

`sceNpSignalingActivateConnectionA` supplies a context, peer identity
and writable connection ID (`0xa74239–0xa74243`, `0xa74616`).
`sceNpSignalingGetConnectionStatus` fills status, IPv4 address and
16-bit port (`0xa7436b–0xa74393`, `0xa747c0–0xa747ec`). The transport
setup checks for status 2 at `0xa7480d–0xa74811`. The guest then uses
an IPv4 P2P datagram socket, family 2 and type 6
(`0xa74931–0xa7494f`). The type name comes from the local reference
`network/net.h`. At `0xa8214e–0xa82167`, the caller passes the context
ID, saved request ID, and a result pointer to
`sceNpMatching2SignalingGetPeerNetInfoResult`, with the leading eight
bytes of the result set to its size, 24. A zero return clears the
request ID and sets byte `0x50` in the peer object
(`0xa8216c–0xa82178`). Peer initialization zeros the request ID at
`+0x30` (`0xa743d1`, `0xa74f85`). Teardown passes that field to
`sceNpMatching2SignalingCancelPeerNetInfo` only when nonzero
(`0xa7414e–0xa74160`, `0xa746e7–0xa746f9`). The 1.17 EBOOT imports
the cancel and result NIDs. Its import table omits the request NID
`8CqniKDzjvg`. The request ID producer and the remaining result
fields are unverified.

#### Room attribute updates

The guest sends both room setters with 224-byte attributes
(`0xa8432a–0xa84540`, `0xa84862–0xa849d0`, `0xa84d12–0xa84e80`).
The internal setter also runs by itself at `0xa75732`.

| Matching2 call | Guest request |
|---|---|
| `SetRoomDataExternal` | Room ID at `+0`, binary attribute pointer at `+0x28`, and count 1 at `+0x30`. The attribute ID is `0x55` (`0xa842af`, `0xa8432a–0xa84350`). |
| `SetRoomDataInternal` | Room ID at `+0`, flag filter and value at `+8` and `+0xc`, binary attribute pointer at `+0x10`, and count 1 at `+0x18`. The attribute ID is `0x57` (`0xa843eb`, `0xa844a1–0xa844df`). |

Closing applies `0xd4000000` with that same filter, while reopening
uses `0x50000000` as the filter and zero as the value
(`0xa84679–0xa84684`, `0xa84958–0xa84970`, `0xa84b29–0xa84b34`,
`0xa84e08–0xa84e20`). Request events are `0x0004` and `0x0109` in
`OrbisNpMatching2RequestEvent` (`np_types2.h`).

### Loopback room management

`POST /nmg-us/local-lobby/v1/rooms` accepts `application/octet-stream`
under `--local-lobbies`. It uses the caller's lease for the same world.
The little-endian envelope is `<BBH16s>` for operation, world, version
and roster token. Versions 0 and 1 are accepted. A create request with
signaling is at most 603 bytes. Each
binary attribute is capped at 256 bytes to fit the guest's listing and
internal attribute reads.

| Operation | Payload after the envelope |
|---|---|
| 1 create | `<QHIBHH>` for nonce, capacity, flags, integer count, search tag length and listing length. Followed by that many `<HI>` integer attributes, the `0x54` search tag and the `0x55` listing bytes. |
| 2 join, 3 view, 4 leave, 6 external lookup | `<Q>` room ID. View and leave require membership. External lookup returns listing data within the same world. |
| 5 search | `<IIIIBBH>` for 1-based start, limit, flag mask, flag value, integer filter count, binary comparison and tag length. Followed by `<HBBI>` integer filters and the tag. Each filter holds attribute ID, comparison, reserved zero and value. |
| 7 update | `<QIIH>` room ID, closed/hidden flag mask, flag value and replacement listing length, followed by the listing. Requires the room owner. |
| 8 internal update | Version 1 only. Uses `<QIIH>` for room ID, flag mask, value and private attribute length, followed by the private data. Requires the room owner. The mask accepts the four create flags used by the guest. |

The eight integer attributes are `0x4c–0x53` in the ELF's mapping at
`0x11b2cc0`, used by create at `0xa77830–0xa7784a` and search at
`0xa78090–0xa780c0`. The local filter codes 1–6 implement equality,
inequality, less than, less than or equal, greater than, and greater
than or equal. Code 1 is exercised by the host replay. The title's
integer comparison codes beyond that remain unverified. Binary search
uses code 1 for an exact match against `0x54` (`0xa780d4–0xa78101`).
The local server evaluates closed, full and hidden flags independently
of the NAT restriction bit because all peers use loopback.

| Reply | Little-endian fields |
|---|---|
| Room view, create, join or update | `<QQIHHHHH>` room ID, revision, flags, capacity, count, owner member ID, caller member ID and listing length. Followed by `<H16s>` member rows and the listing. |
| Search or external lookup | `<III>` for start, total and returned rows. Each `<QQIHHHH16s>` row contains ID, revision, flags, capacity, member count, owner member ID, listing length and owner name. The listing bytes follow the row. |
| Leave | Empty HTTP 200 body. |

After the public listing, version 1 room views append a `<BBHH>`
record with signaling mode, reserved zero, hub member ID, and private
attribute length, followed by the private `0x57` bytes. Mode 0 uses a
zero hub. Version 0 retains the optional four-byte signaling suffix.

Create initializes both attributes with the same bytes the title
passes at `0xa778e1–0xa7793b`. Later owner updates store them
independently and an identical retry returns the current revision.
Loopback tests cover both view formats, owner checks, closing and
reopening, and late join with the latest private attribute.

Room IDs carry the world in the high byte and its room sequence in
the low 56 bits. Runtime `5ffb004` acquires the roster when
`CreateJoinRoomA` follows `GetWorldInfoList` without a `JoinLobby`
call. The follow-up patch uses the world byte for `JoinRoomA` and
external lookup when the roster is absent. Windows sanitizer tests
through the Matching2 worker covered worlds 1, 7, and 50, including
both attribute setters, public listing lookup, and private attribute
delivery on join. Guest verification is NOT_RUN.

An identical create retry on the same lease returns its current room
view. A repeated join leaves membership unchanged. The staged runtime
repeats the original room request once after a transport failure. The
Windows AddressSanitizer probe dropped both accepted replies and recovered
the same two-seat room, then exchanged RUDP packets in both directions.
A full or closed
room returns 409 for a new join. Departure or lease expiry removes the
member. When the owner-auto-grant bit is set, the earliest remaining
member becomes owner. An empty room is deleted.

Two Windows AddressSanitizer clients used the staged bridge's scoped
imports to create, search, fetch listing data, join, and leave a room.
The callbacks verified title-sized attribute buffers, linked member
records, and self and owner pointers. They also checked owner transfer
and an absent room. Guest room entry is NOT_RUN.

### Live room membership

The room callback at `0xa7e960` accepts context ID, room ID, event,
data and user argument. The worker polls the room once per lobby tick
while joined. It applies the new server revision before delivering
departures, additions, and then any owner change.

| Event | Guest reads |
|---|---|
| `0x8101` join and `0x8102` leave | The pointer at data offset 0 refers to a 0x58-byte account-ID member record. The callback copies it at `0xa7ea80–0xa7eaa5`. The tick reads the account/platform pair at `+0x10`, name at `+0x20`, and member ID at `+0x38` (`0xa81e5d–0xa81e78`, `0xa81ff3–0xa82011`). |
| `0x1105` owner change | The callback copies 0x28 bytes (`0xa7eacd–0xa7eae7`). The tick stores the incoming member ID at payload offset 2 (`0xa81ef3–0xa81efa`). |
| `0x1106` internal room change | Data offset `+0x38` points to the changed-attribute pointer array. The callback reads the first record's data pointer at `+0x18` and length at `+0x20` (`0xa7ea11–0xa7ea53`). The tick applies the payload for the current room (`0xa81f10–0xa81fcd`). |
| `0x1104` room destroyed | The callback copies 32 bytes (`0xa7eab0–0xa7eae7`). The tick clears the room ID and reads the cause byte at 0 and error word at 4 (`0xa81e9f–0xa81ecc`). |

The runtime copies each notification into the guest callback's layout
and invokes the callback outside the Matching2 mutex. Unregistration
and context teardown wait for a callback already in progress, with
reentrant calls from that callback allowed. An explicit leave clears
the client's room view and completes its outstanding leave request.

The scoped mode-1 call at `0xa7479e` checks the latest valid room
membership before returning status 2, the member's loopback IPv4
identifier, and port 3658 in network order. A peer absent from that
room returns inactive status and zero address fields. The room snapshot
expires after three seconds without a successful refresh. These
outputs identify local peers for the relay. The relay's packet routing
still uses the lobby lease.

Two Windows AddressSanitizer clients verified live join and leave,
owner transfer, destruction, and status before, during and after
shared membership. The test held the destruction callback while
unregistering and confirmed that unregistration waited for it.
Guest room notifications are NOT_RUN.

### Room messages

At `0xa81c12–0xa81c2a`, the guest passes the context ID, request pointer,
request options and request ID output to `sceNpMatching2SendRoomMessage`
through stub `0x10fd7d0`.

| Request offset | Field | Guest evidence |
|---|---|---|
| `0x00` | Room ID | `0xa81b76–0xa81bac` |
| `0x08` | Cast type, 1 for broadcast, 2 for unicast, 3 for multicast | `0xa81ac1`, `0xa81bc3`, `0xa81be6` |
| `0x10` | Unicast member ID or multicast member ID pointer | `0xa81bd4`, `0xa81bee` |
| `0x18` | Multicast member count | `0xa81bf6` |
| `0x20`, `0x28` | Payload pointer and byte count | `0xa81bfe–0xa81c06`, `0xa6d915–0xa6d923` |

Broadcast control calls pass 1 and 3 bytes at `0xa766e7–0xa76708`
and `0xa81ac6–0xa81ada`. At `0xa81bfe–0xa81c2a`, the targeted control
call passes 17 bytes. Three broadcast calls use 521 bytes
(`0xa6d923`, `0xa6dc45`, `0xa6e032`). Request completion uses event
`0x0108` (`0xa796ed–0xa796f2`). When the caller is in state `0x22`,
the completion checks the returned error (`0xa79d19–0xa79d47`).

Registration at `0xa7e282–0xa7e28c` installs callback `0xa7ec30`, which
accepts `0x9102` for the matching context and skips its own member ID.
Golf's callback reads the payload pointer at `+0x38` and size at `+0x40`.

#### Local room message replay

`POST /nmg-us/local-lobby/v1/room-messages` uses
`application/octet-stream`. All fields are little-endian.

| Record | Format | Fields in order |
|---|---|---|
| Request header | `<BBH16sQQ>` | World, operation, reserved zero, current relay token, room ID, send nonce or inbox ACK |
| Send, operation 1 | `<BBH>`, then targets and bytes | Cast type, target count, payload length, two bytes per target, payload |
| Poll, operation 2 | Header only | Last delivered inbox sequence or zero |
| Poll reply | `<H>`, then rows | Frame count |
| Poll row | `<QHBBH>`, then payload | Inbox sequence, sender member ID, cast type, reserved zero, payload length, payload |

Send succeeds with an empty body. An identical retry of the last send
nonce also succeeds. The server excludes the sender from broadcast and
requires every targeted member to be in the room. Payloads range from
1 to 1,024 bytes in this local implementation. Each inbox holds up to
32 messages, and a poll returns up to 8. If any destination queue is
full, the send returns 429 before enqueuing any copies.
Departure clears the member's inbox and prunes its messages from other
inboxes. The current relay token is required after rejoining.

The staged runtime polls after a lobby tick while a room message
callback is registered. Two Windows AddressSanitizer clients resolved
the guest imports and verified all three cast types, message data after
caller buffers were cleared, sending without a completion callback,
unregistration during delivery, and a clean rejoin. Guest room
messages are NOT_RUN.

### Signaling callback queues

Matching2 registers `0xa7eef0` with `sceNpMatching2RegisterSignalingCallback`
(`0xa7e299–0xa7e2a7`). The callback checks the context ID against
`userdata+0x44`, then queues 16 bytes with room ID at offset 0, member ID
at 8, event at `0xa`, and error code at `0xc`
(`0xa7eef0–0xa7ef70`). The tick reads the queue at `+0x820`
and dispatches on the event word at `0xa`. It uses the member ID at
offset 8 to locate the associated entry (`0xa82040–0xa820a3`).

The standalone signaling context created at `0xa7e4f0` uses callback
`0xa7e5e0`. Its separate queue at `+0x1190` holds four 32-bit fields
in order: context ID, connection ID, event, and error code
(`0xa7e4db–0xa7e4f0`, `0xa7e5ee–0xa7e65f`,
`0xa7e6a8–0xa7e715`). The tick compares each context ID against the Matching2 object's
`+0x44` field. It drops mismatches and looks up a missing connection ID with
`sceNpSignalingGetConnectionFromPeerAddressA`. It passes the member
address at `+0x1490` (`0xa8224a–0xa822e8`,
`0xa82343–0xa82378`, `0xa823cf–0xa82404`).

| Queue | Event | Observed effect |
|---|---|---|
| Matching2 | `0x5101` | Matches member ID and sets bit 1 at member offset `+0x1484` when allowed (`0xa82120–0xa8214a`, `0xa8217f–0xa8218c`). |
| Matching2 | `0x5102` | In mode 1, matches member ID and calls the peer's vtable entry `+0x48` with zero (`0xa820e0–0xa82110`, `0xa8218e–0xa821a0`). |
| Matching2 | `0x5103` | Looks up the peer by member ID and calls `sceNpMatching2SignalingGetPeerNetInfoResult` (`0xa820a9–0xa820ce`, `0xa8214e–0xa82178`). |
| Standalone | 0 | Sets bit 1 at member offset `+0x1484` and saves the error at peer offset `+0x28` when allowed (`0xa8239e`, `0xa82435–0xa82456`). |
| Standalone | 1 | Calls the peer's vtable entry `+0x48` (`0xa82282–0xa822a7`, `0xa8241b–0xa82433`). |
| Standalone | 10 | Outside mode 1, writes 2 at peer offset `+0x54` (`0xa8230e–0xa82338`, `0xa82458–0xa82465`). |

The layouts agree with `OrbisNpMatching2SignalingCallback` and
`OrbisNpSignalingHandler` in the local DriveClub shadPS4 reference
(`np_types2.h`). These handlers have no guest replay evidence.

#### Local room signaling

The create wrapper writes signaling type 1 or 2 to the option record
at `0xa77957–0xa7796f`. It stores the pointer at request offset
`0xb0` (`0xa77973–0xa77978`; request base at `0xa779b7`).
The local DriveClub reference identifies 1 as mesh and 2 as star
in `np_types2.h`.

For either type, append `<BBH>` to the room create request after the
listing with the type, zero flags, and zero hub ID. Room views carry
the same trailer, with the current owner's member ID as the star hub.
Rooms without a mesh or star option use the base frame.

The room snapshot drives Matching2 connection status at `0xa7479e`.
The channel and packet routes permit any pair of mesh members. Star
links require the hub at one end. The worker delivers membership
notices before signaling events, using the local DriveClub constants.

| Link change | Callback |
|---|---|
| Established | `0x5102`, success |
| Lost | `0x5101`, error `0x80550e10` |

Separate three-client Windows AddressSanitizer runs covered mesh and
star status, disconnects, owner transfer, and unregistration during
delivery. Server tests verify that a star blocks packets and channel
registration between leaves. Guest signaling is NOT_RUN.

Standalone signaling and Matching2 peer net-info callbacks remain open.

### Reliable UDP contexts

The active-peer loop creates four contexts and stores their IDs at
peer offsets `0x5c`, `0x60`, `0x64`, and `0x68`. It passes
callback `0xa74ff0` and the peer pointer to each create call
(`0xa74d0f–0xa74d36`, `0xa74e9c–0xa74ea7`). Each bind uses
one of the sockets at `0x2c82f98 + index * 4`, virtual port
`0x14`, and multiplex mode 1 (`0xa74d3c–0xa74d56`).

The four sockets bind IPv4 address `0.0.0.0` and physical port
3658. The guest uses a 16-byte address and puts local virtual ports
25000–25003 at offset 8 (`0xa74931–0xa749a7`,
`0xa749b8–0xa74a32`, `0xa74a43–0xa74abd`,
`0xa74ace–0xa74b48`). Initiate uses the address and physical port
from the signaling status call. Its destination virtual ports are
25001, 25000, 25003, and 25002 in context order
(`0xa747c0–0xa747ec`, `0xa7487f–0xa74913`,
`0xa74e42–0xa74e90`).

Every option is passed as a four-byte value. The table gives the
numeric IDs and initial values without inferring SDK names.

| Option ID | Value | Guest evidence |
|---|---|---|
| `0x05` | 0 for contexts 0 and 1, 1 for contexts 2 and 3 | `0xa74d63–0xa74d89` |
| `0x06` | 1 | Data at `0x1232c00`, call at `0xa74da4` |
| `0x02` and `0x03` | `0x64000` each | `0xa74da9–0xa74de6` |
| `0x10` | 0 | `0xa74deb–0xa74e07` |
| `0x04` | 0 in the ELF initializer | Data at `0x1361b64`, call at `0xa74e22` |
| `0x0b` | 30 in the ELF initializer | Data at `0x1361b68`, call at `0xa74e3d` |

The initiate call passes length 16 and a leading length byte of 8.
The physical and virtual ports are in network order at offsets 2
and 8, with IPv4 at offset 4. The caller copies the physical port
and IPv4 directly from the signaling outputs. The virtual port
comes from `sceNetHtons` (`0xa747d7–0xa747ec`,
`0xa7487f–0xa74913`, `0xa74e42–0xa74e90`). Four successful submissions set peer phase
`+0x6c` to 1 (`0xa74ea7–0xa74eb3`, `0xa74f04`). The next
setup tick reads a `0x30`-byte status for each context and sets phase
2 only if all four leading status words equal 4
(`0xa747f0–0xa747ff`, `0xa74bf4–0xa74cbe`). The write path
requires phase 2 before calling `sceRudpWrite`
(`0xa7f561–0xa7f569`, `0xa7f5b5`).

| Callback | Guest handling |
|---|---|
| Per-context event 1 | Sets peer phase `+0x6c` to 3 (`0xa74ff0–0xa74ff3`, `0xa75015–0xa7501c`). Phase 3 enters RUDP context teardown (`0xa747f0–0xa747f6`, `0xa74b68–0xa74bbb`). |
| Per-context event 2 | Uses `0x2c82ff8` and its index at `+0x450` to find an entry in the pointer array at `+0x130`, then sets bit 3 at entry offset `+0x64` (`0xa74ff5–0xa75014`). The send path tests that bit at `0xa7f51c` and selects the single-byte `0xfd` write at `0xa7f547`. |
| Global event 2 | Takes the mutex at `*(userdata+0xd0)+0x28` and calls `0xa75020` (`0xa7f0d0–0xa7f10c`). That routine aborts, shuts down, and closes all four live sockets, sets their IDs to -1, and clears the socket-ready byte (`0xa75024–0xa7510c`). |

The global handler is registered before enabling the internal I/O
thread with arguments `0x4000` and `0x100`
(`0xa7e2b4–0xa7e2dc`). Callback timing and peer interoperability
remain unverified.

The positive return of `sceRudpGetNumberOfPacketsToRead` sets how many
times the receive loop runs (`0xa7f9c0–0xa7f9d2`, `0xa7fdc0–0xa7fdc8`).
The symbol hashes to NID `Px0miD2LuW0` at import `0x10fd560`.
The loop queries `sceRudpGetSizeReadable` before calling `sceRudpRead`
with the context, buffer, capacity, zero flags and an information pointer
(`0xa7f9e3–0xa7fa15`).

| Operation | Observed behavior | Guest evidence |
|---|---|---|
| Single-byte write | Sends one byte from `0x1361b80` on channel index 0 with flags `0x40`. The ELF initializes the byte to `0xfd`. | `0xa7f547–0xa7f55e`, `0xa7f582–0xa7f5b5` |
| Write with both flag bits | The branch at `0xa7f4b9` selects flags `0x48`, which reach the same write call. | `0xa7f4aa–0xa7f4d7`, `0xa7f5a9–0xa7f5b5` |
| Other write site | Uses flags `0x08` when a nonempty payload starts with `0xfe`, and zero otherwise. | `0xa7f6ba–0xa7f6ce`, `0xa7f709–0xa7f71b` |
| Queue reset | Outside receive state 1, a positive-length payload starting with `0xfe` clears the queue and resets its indices and count before the normal enqueue path. | `0xa7fa26–0xa7fa49`, `0xa7fa60–0xa7fb18` |
| Queue entry | Stores the payload pointer at offset 0, returned byte count at 8, and a locally supplied 32-bit value at 12. Enqueue advances the write index modulo capacity. | `0xa7fbb9–0xa7fbd8`, `0xa7fd87–0xa7fdb0` |

The remaining packet fields and guest interoperability are unverified.

At `0xa7f5ba`, the guest keeps its pending write when `sceRudpWrite`
returns `0x80770016`. The loopback worker uses that return when a link
is pending or the send queue is full. The status call passes length
`0x30` and reads the first word (`0xa74c04–0xa74c15`).

The lobby member list passes record offset `0x10` at `0xa79866`.
Member creation copies those 16 bytes to `+0x1490` at `0xa7c1b6`.
The local DriveClub reference defines `OrbisNpPeerAddressA` as a
64-bit account ID, a 32-bit platform type, and 32 bits of padding.
The PS4 platform value is 3 (`np_types.h:78–90`).
`sceNpSignalingGetConnectionStatus` returns the IPv4 address and
physical port separately (`0xa74380`, `0xa747c0–0xa747ec`).

The loopback identity patch fills this field in list and notification
records. Its synthetic account ID encodes the world and member ID.
It remains valid for the local roster entry's lifetime. Windows ASan
probes checked the field in initial rosters, join and leave events,
separate worlds, and the default single-player lobby. Guest signaling
lookups for these identities are NOT_RUN.

### Local signaling status

The peer tick selects a Matching2 status call when mode `+0x580` is 1
and standalone `sceNpSignalingGetConnectionStatus` otherwise
(`0xa74774–0xa747d7`). The latter receives context and connection IDs,
then writes status, IPv4 and the physical port through three pointers.
The tick checks status 2 before setting up RUDP (`0xa7480d`).

The opt-in bridge answers standalone activation and status from the
current server roster. It gives each live remote member a connection ID
and the loopback identifier `127.0.<member high byte>.<member low byte>`,
with port 3658 in network order. A roster update that removes the peer
changes its connection status to 0. The bridge supplies this status
through polling. Standalone callbacks remain unimplemented. The
mode-1 Matching2 call uses the separate room snapshot described under
Live room membership.

Two Windows AddressSanitizer clients activated and looked up each
other on one live roster. Tests checked the exact address and port
bytes, same-connection lookup, cross-world rejection, and inactive
status after departure. Guest acceptance is NOT_RUN.

### Loopback channel readiness

The private `POST /nmg-us/local-lobby/v1/channels` endpoint accepts
`application/octet-stream`. It registers the initiating virtual ports
for one peer on the caller's roster lease. The guest's port pairs come
from the setup at `0xa7487f–0xa748c6`.

| Record | Little-endian format | Fields in order |
|---|---|---|
| 28-byte request | `<BBH16sQ>` | World, local port mask, peer member ID, roster token, revision |
| 12-byte response | `<QBBH>` | Echoed revision, ready local port mask, reserved zero, echoed peer member ID |

Bits 0–3 correspond to ports 25000–25003. The response reports a local
port as ready when the requested mask includes it and the peer has
registered its complementary port. A revision is a positive integer
per direction for the pair of roster leases. Repeating the current
revision and mask reads fresh readiness. A lower revision or a changed
mask at the current revision returns 409. Use a newer revision with
mask zero to clear registered ports. A missing lease returns 404. The
server drops both registrations when either member leaves or expires.

Two Windows AddressSanitizer clients used the native HTTP helper to
observe no ready channels, partial readiness, four ready channels, and
readiness clearing after one peer withdrew its mask. The staged RUDP
worker consumes these replies. Guest channel activation is NOT_RUN.

### Loopback packet relay

The local runtime bridge uses `POST /nmg-us/local-lobby/v1/packets`
with `Content-Type: application/octet-stream`. This format belongs to
the port. The guest virtual ports come from the socket addresses at
`0xa74931–0xa74b48` and `0xa74e42–0xa74e90`.

| Record | Little-endian format | Fields in order |
|---|---|---|
| Request header | `<BBH16sQQ>` | World, version zero in the lobby, frame count, relay token, upload sequence, inbox ACK |
| Request frame | `<HHHH>` plus payload | Recipient member ID, source virtual port, destination virtual port, payload length |
| Response header | `<QHH>` | Last accepted upload sequence, frame count, reserved zero |
| Response frame | `<QHHHH>` plus payload | Inbox sequence, sender member ID, source virtual port, destination virtual port, payload length |

Each exchange carries up to 16 frames and 65,536 total payload bytes.
A frame contains 1–65,535 payload bytes.
Lobby exchanges cap at 65,700 request bytes and 65,804 response bytes.
Virtual port pairs are `25000↔25001` and `25002↔25003`. Each member
inbox holds up to 64 frames and 65,536 payload bytes.

The first upload sequence is 1. Retrying the last accepted upload
with the same frame bytes does not redeliver it. The cumulative inbox
ACK starts at 0 and advances only through frames already returned to
the client. The server repeats unacknowledged frames in inbox order.
An empty request with upload sequence 0 can read and acknowledge
frames while an upload waits. An invalid sequence or ACK returns 409.
An absent lease or recipient returns 404. A full inbox returns 429.
The server accepts or rejects every frame in an upload together.

Two Windows AddressSanitizer clients used the runtime HTTP helper to
exchange and acknowledge packets through the server, including a
4,096-byte payload and repeated uploads and reads.

### Local RUDP worker

Under `GOLF_LOCAL_LOBBIES=1`, the staged worker completes each channel
only after the server confirms the peer's complementary port. It uses
the local address at `0xa749a7–0xa74b48` and paired port at `0xa74e86`.

| Worker behavior | Contract |
|---|---|
| Locking | HTTP runs outside the queue mutex |
| Queue limits | 64 messages and 65,536 payload bytes per direction, with up to 65,535 bytes per message |
| Upload lifetime | Retained until the server acknowledges the batch or confirms the recipient is gone |

Two Windows AddressSanitizer clients called the game's scoped imports
and exchanged ordered messages on all four channels in both directions,
including a 4,096-byte message. Status calls completed while the server
held an accepted upload reply. After the server dropped the reply,
the receiver read each message once. The clients also verified channel
withdrawal, restart on the same lease, and peer departure.

| Lifecycle change | Behavior |
|---|---|
| Write flags | `0`, `0x08`, `0x40` and `0x48` share one reliable ordered transport |
| Event 2 | Delivered after the guest has read state 4 for all four channels |
| Event 1 | Delivered after confirmed channel withdrawal or peer departure |
| Callback teardown | Callbacks run outside the queue lock. Termination waits for active delivery unless invoked by that callback. |

The Windows AddressSanitizer probe held a withdrawal reply until after
both hosts recreated their contexts on the same lease. Without a check
for binding changes during HTTP, the worker discarded the replacement
peer state. The lifecycle patch rejects that stale reply, and the new
contexts reach state 4 and exchange packets. The probe also checked
single callback delivery, concurrent teardown, and delivery with flags
`0x48`.

The receive worker allocates at least 8,192 bytes
(`0xa7f831–0xa7f84a`) and passes that capacity to `sceRudpRead`
(`0xa7f8b1`, `0xa7fa04–0xa7fa15`). The 4,096-byte relay cap was a
local implementation limit. The worker now accepts the full range of
the existing 16-bit length field, up to 65,535 bytes per message.
Two Windows AddressSanitizer clients exchanged a message of that size
in each direction. They verified byte equality, retention after a short
read, rejection above the limit, and single delivery.

Global RUDP callbacks remain open. Guest peer play is NOT_RUN.

### Loopback room transport

`POST /nmg-us/local-lobby/v1/transport` accepts
`application/octet-stream`. The little-endian request `<BBH16sQ>` carries
the world, two reserved zero fields, the roster lease token, and the
expected room ID. The reply `<Q16s>` carries the room ID and relay token.
Use room ID 0 for the lobby. An unknown lease or a room mismatch returns
404.

The roster lease stays valid across room changes. The server rotates the
relay token, clears that member's channel registrations and queues, and
resets packet sequences on each transition. It removes that member's
queued frames and channel registrations from the other peers. Relay
tokens from a prior membership return 404. An untouched lobby uses
the roster token as its initial relay token.

| Record | Room format | Change from lobby |
|---|---|---|
| Channel reply | `<QBBHQ>` | Adds the peer's membership generation after the member ID |
| Packet request header | `<BBH16sQQ>` | Sets the version byte to 1 and carries the relay token |
| Packet request frame | `<QHHHH>` plus payload | Adds the recipient's membership generation before the member ID |
| Packet response frame | `<QQHHHH>` plus payload | Adds the sender's membership generation after the inbox sequence |

Room packet exchanges cap at 65,828 request bytes and 65,932 response
bytes. The server rejects channel and packet requests for peers in a
different room or the lobby. It also rejects uploads targeting an older
membership of a peer who rejoined. Inbox sequences can have gaps after
the server removes a departed sender's frames. The client acknowledges
through the last frame it accepted or discarded.

The staged runtime resolves the relay token on its I/O worker and closes
old RUDP contexts when their membership ends. Two Windows
AddressSanitizer clients used the mode-1 status import at `0xa7479e` to
connect over all four channels. They exchanged data in both directions,
including 4,096-byte messages. The probe queued unread data on both
clients, checked that leaving the room cleared it, and exchanged new
messages after rejoining with fresh contexts. The lobby lifecycle probe
also passed with the same patch. Guest room play is NOT_RUN.

## Title User Storage

The guest gets the initial user and calls
`sceNpTusCreateNpTitleCtxA(0, user)` (`0xaa6a16–0xaa6a35`).
The first argument is the service label according to the local
DriveClub shadPS4 reference in `np_tus.cpp`. The guest creates a request
for that context at `0xeccc1f` and `0xeccce2`, saves the returned
handle at `0xeccceb`, and releases the title context through
`sceNpTusDeleteNpTitleCtx` at `0xaa69b3`.

The caller at `0xaa6a60` batches three account-ID blob requests.
Operation 0 selects GET and operation 1 selects SET
(`0xeccd0b–0xeccd52`). Confirmed call sites pass 0 at `0xb9772d`
and 1 at `0xb97801`. Each batch uses the same account ID copied at
`0xaa6cc4–0xaa6ccc`. The fixed outgoing slot sizes come from the
descriptor writes before submission.

| Slot | Outgoing bytes | Descriptor and submission evidence |
|---|---:|---|
| 1 | 2,008 (`0x7d8`) | `0xaa6ca9–0xaa6cb3`, `0xaa6d11` |
| 2 | 64 (`0x40`) | `0xaa6d2a–0xaa6d34`, `0xaa6d59` |
| 3 | 217 (`0xd9`) | `0xaa6d87–0xaa6d91`, `0xaa6dfd` |

GET passes the request handle, account ID, slot ID, status pointer,
status size `0x210`, data buffer, capacity `0x2800` and null option
(`0xeccd1c–0xeccd44`). SET passes the handle, account ID, slot ID,
equal total and send sizes, and the data pointer
(`0xeccd65–0xeccda7`). Optional author and timestamp inputs can be
null and the information pointer, information size and option are zero
on this path. The function signatures match the local reference's
`sceNpTusGetDataAAsync` and `sceNpTusSetDataAAsync`.

`sceNpTusPollAsync` receives a separate signed 32-bit result output.
A positive poll return keeps waiting, zero means the guest can inspect
the output, and a negative poll return takes the failure path
(`0xecd476–0xecd4a2`, `0xecd5a5`). The guest handles a negative output
separately. It tests `0x8055082b` and sets the special outcome flag
when that code matches (`0xecd69b–0xecd6bb`). The reference
`np_error.h` calls this code `USER_NOT_ASSIGNED`.

After a nonnegative GET result, the guest copies from the data pointer
at status offset `0x58` using the byte count at `0x60`, limited to its
expected slot size (`0xecd4c0–0xecd4ef`). It also copies eight-byte
metadata from status offsets `0x28` and `0x1f8`
(`0xecd4f7–0xecd50f`). The reference `OrbisNpTusDataStatusA` names those
fields the last-changed tick and last-changed author account ID.
The worker deletes the request before the caller's completion callback
(`0xecd5b1–0xecd624`).

The current runtime returns a signed-out result when creating a TUS
title context. The opt-in patch in `docs/MAILBOX.md` implements one
local context and the three observed blobs in process memory. It takes
the initial user and account from the existing local runtime and fills
the GET status fields above. An unpopulated slot returns
`USER_STORAGE_DATA_NOT_FOUND` as the operation result. An unknown
account returns `USER_NOT_ASSIGNED`. The optional SET author and tick
compare against the stored metadata before replacing a blob.

Host probes passed for all three slot sizes, request cleanup, and two
competing writes with the same tick. Guest acceptance and the original
service's missing-slot and conditional-write behavior remain unverified.
These operations use the TUS guest API. The HTTP service has no TUS routes.

## WebAPI requests

The `WebApiPushEvent` parent starts the worker at `0xecdb70` through
`0xea6c90`, then writes 3 to WebAPI context offset `+0x18`
(`0xb99758–0xb9978c`). The worker writes 4 after both filter creations
succeed, or 5 after a filter creation fails (`0xecdcac–0xecdd00`).
If the worker reaches that store before the parent writes 3, the
parent overwrites the completion state. A negative `CreateHandle`
result branches around the completion store (`0xecdc88–0xecdc91`).

Submission queues a request if the worker pointer at `+0x10` is set or
the state at `+0x18` is nonzero (`0xecdf1e–0xecdf55`, `0xece267–0xece278`).
The update checks for state 4 or 5 at `0xb98c31–0xb98c3a` and releases
the worker. State 4 tries to register both callbacks (`0xb98cb0–0xb98cfc`).
Both paths clear the state and submit the first queued request at
`0xb98d02–0xb98d3a`.

Runtime `845f548` delays new guest threads until the parent returns from
`scePthreadCreate`, plus one millisecond. The owner's boot log for that
revision records an in-process HTTP 200 for the entitlement list after
`CheckEntitlement` starts. The proposed patch that moves only the state
store at `0xb9978c` ahead of the thread-start call is guest NOT_RUN.

The request type selects a path at `0xece038–0xece055` using the jump table at
`0x11d1760`. The method comes from the request at `0xece360`. The enum in
the local DriveClub shadPS4 reference
(`gpu/shadps4/core/libraries/np/np_web_api/np_web_api.h`, `OrbisNpWebApiHttpMethod`)
maps 0 to GET and 2 to PUT. The SDK supplies the service authority and authentication.
Those values are unresolved.

| Service group | Method and relative target | Request evidence |
|---|---|---|
| `sdk:userProfile` | GET `/v1/users/%ld/friendList?friendStatus=friend&limit=2000&presenceType=incontext` | Template and group at `0xece05b–0xece075`. Caller sets method 0 at `0xb997d6`. |
| `sdk:userProfile` | PUT `/v1/users/%ld/presence/gameStatus` | Path at `0xece2ac`. The operation-2 body builder formats `{"gameStatus":"%s"}` at `0xece588–0xece5a4`. |
| `sdk:userProfile` | PUT `/v1/users/%ld/presence/gameData?notificationWithData=true` | Path at `0xece32a`. Caller sets operation 6 at `0xb98b88`. The body builder sets method 2 at `0xece541` and formats `{"gameData":"%s"}` at `0xece591–0xece5a4`. |
| `sdk:commerce` | GET `/v1/users/me/container/%s` | Path and group at `0xece2b9–0xece2d3`. Caller sets method 0 at `0xcf178d`. The guest appends `?size=%d&serviceLabel=%d` using `0x1213d31` at `0xcf1714–0xcf173d`. |
| `sdk:entitlement` | GET `/v1/users/me/entitlements?entitlement_type=service` | Operation 4 and method 0 at `0xefaf4`, `0xefb0f`. Query literal at `0x1211837` loaded by `0xefaa9`. Path and group at `0xece2dc–0xece2ef` and `0xece31d`. |
| `sdk:entitlement` | PUT `/v1/users/me/entitlements/%s` | Operation 5 queued at `0xefc12–0xefc2a`. The method is set to 2 at `0xece541`, the entitlement ID string goes into the path at `0xece2f1–0xece303`, and the body is `{"use_count":%u}` (`0xece5ab–0xece5cf`). |

For PUT, the request builder passes `application/json; charset=utf-8` and
the body length in its content parameter (`0xece308–0xece318`,
`0xece34b–0xece35b`, `0xece36a–0xece37f`). The presence values and
entitlement ID come from guest state.

The entitlement list reader looks up numeric `size` and the `entitlements`
array (`0xc75f87–0xc75fc0`). Each item supplies a string `id` and
integer `use_count` and `use_limit` (`0xc76040–0xc760c5`). The
guest queues the ID in a 17-byte field and takes the requested amount
from the cached `use_limit` (`0xc77340–0xc7736b`,
`0xc7745a–0xc77482`). The runtime formats that amount into the PUT's
`use_count` and inserts the ID with `%s` in the path
(`0xefbd7–0xefc2a`, `0xece54d–0xece55c`, `0xece2f1–0xece303`,
`0xece5ab–0xece5cf`). On a successful callback the guest adds the
cached `use_limit` to `use_count` and zeros `use_limit`
(`0xc76290–0xc762c6`).

The default loopback entitlement list is empty. With `--ticket-grants`,
it returns two synthetic grants for `EN0001` and `EN0002` and
accepts one exact-amount PUT per grant. Later GETs reflect the consumed
state until the service restarts. The six-character ID lookup is
documented in [Ticket balances](entitlements.md#ticket-balances).
The runtime owner verified the equivalent in-process fixture. The guest
sent `use_count` 1 for `EN0001` and 10 for `EN0002`, then showed and kept
an S Ticket balance of 101 across a reboot (07:05 mailbox entry).

### Friends and presence

The friend-list callback parses JSON at `0xb9a1a6` and counts
the `friendList` array at `0xb9a1b3–0xb9a1ce`. An empty array skips
iteration and reaches pending-request cleanup at `0xb9a6a9–0xb9a6b5`.
The loopback server returns `{"friendList":[]}` for the exact query above
against the existing runtime's primary synthetic account, `5932163534510096385`
(`NP_ACCOUNT_ID` in `src/runtime_services.c`). Other account IDs return 404.

The callback reads `user.accountId` as a decimal string and
`npId` from the friend entry (`0xb9a39b–0xb9a425`). Presence fields
include `presence.onlineStatus` (`0xb9a503–0xb9a543`) and
`presence.incontextInfoList[0].gameTitleInfo.npTitleId`
(`0xb9a55c–0xb9a5b1`). The `gameData` value is read from the
same array entry at `0xb9a21e–0xb9a25d` and decoded at `0xb9a316`.

For the outgoing game-data update, `0xb98b04–0xb98b73` passes a 96-byte
record to the encoder at `0xecace0`. The encoder uses the standard
Base64 alphabet at `0x1218f11` (`0xecad40–0xecad5d`) and pads short
groups with `=` (`0xecae73–0xecae8c`). For that 96-byte input the
wire field is 128 characters. The encoded string is inserted into the
JSON body at `0xece591–0xece5a4`. Presence mutations and the meanings
of the binary record's individual fields remain unresolved.

### Commerce catalog

The root request passes the empty label at `0x1223e54` and page size
128 to the formatter (`0xcf1714–0xcf173d`). The service-label field
is initialized to 0 at `0xcf10d0` and loaded by `0xcf1714`. With that
value, the request is `GET /v1/users/me/container/?size=128&serviceLabel=0`.
Later requests join labels with ASCII colons (`0xcf18d4`, `0xcf1b25`),
up to eight labels in one branch and 32 in the other
(`0xcf191d–0xcf1921`, `0xcf1b6d–0xcf1b71`). Both branches pass size 128
and the current service label (`0xcf1935–0xcf1959`, `0xcf1b85–0xcf1baa`).

The response callback at `0xcf1ee0` parses JSON (`0xcf1f6c`) and
iterates the top-level array via `Value::count` and the numeric
index operator (`0xcf1f80`, `0xcf1fce`). With a zero count it skips
the loop and decrements the pending-request count
(`0xcf1f85–0xcf1f87`, `0xcf2ab7–0xcf2abe`). A nonzero callback result
or a JSON parse error bypasses the decrement (`0xcf1efe–0xcf1f07`,
`0xcf1f71–0xcf1f73`). The default root returns `[]`.

| Fields | Guest behavior |
|---|---|
| `container_type`, `label` | Reads both as strings. The type comparison at `0xcf1fff` picks the category map for `category` and the product map otherwise. The callback hashes `label` at `0xcf2042–0xcf2074` and updates an existing entry only (`0xcf2076–0xcf2159`). |
| `skus[0].price`, `skus[0].display_price`, `skus[0].label` | Reads the first SKU and copies its integer price, 64-byte display-price field, and 32-byte SKU label field (`0xcf2221–0xcf22c1`). The top-level product label is copied separately (`0xcf22c6–0xcf22d5`). |
| `skus[0].is_purchaseable`, `skus[0].use_count` | Reads the boolean and integer through references (`0xcf2300–0xcf2335`). The guest uses the spelling `is_purchaseable`. |
| `size`, `links` | For a category, the integer `size` controls the loop over `links`. Each child has its own `container_type` and `label` (`0xcf2343–0xcf2422`). |

The runtime owner observed a colon-delimited batch containing both ticket
product labels and equipment labels (07:05 mailbox entry). With
`--catalog-fixture`, the loopback server accepts batches of up to 32
entries drawn from 31 known product labels. It returns one synthetic SKU
per entry with zero price and use count, an empty display price, and
`is_purchaseable: false`. The runtime owner verified that the Shop
still opens and shows Last Month's Items with equivalent in-process
replies on `da28e84`. Deployed catalog values remain unverified.
