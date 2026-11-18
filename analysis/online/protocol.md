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
(`0xecb280–0xecb3e5`). The original ciphertext and guest acceptance of a local fixture remain unverified.

The tag lookups start from 32-byte slots at `0x11b7260–0x11b7440`, copied at
`0xb7be8f–0xb7bf91`. Slot names include `msg3`, `client_ver_msg3`,
`gameurl3`, `capone_url3`, `game_analytics_system_url3`,
`cds_gamedata_down_url3`, `cds_gamedata_up_url3`,
`cds_property_down_url3`, `interval3`, `client_ver3`, `msg_busy3`,
`capone_envtag3`, `game_analytics_system_envtag3`, `displaytime_telop3`,
`getscorelist_teedistance3` and `lang1`. The code can rewrite the suffixes
(`0xb7bf99` onward). Values include a nested tag map parsed at `0xb7dd74`,
then looked up by keys such as `ssinfo` and `getservertime`
(`0xb7ddd0–0xb7df3f`). Mandatory fields and region selection still need a
fixture accepted by the guest. The startup `ss_info_ver` lookup at
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
references in the request dispatcher and its traced helpers. `gameapi_getuploadinfo` appears in the
validation loop. Its destination and consumer remain untraced.

Three later lookups fall outside the validation loop. The decoder reads
`gameapi_uploaddata` into `+0x5d368` (`0xb808a9–0xb80925`),
`gameapi_getregulationdata` into `+0x5d468` (`0xb82774–0xb827ef`) and
`gameapi_getfinishboardlist` into `+0x5d4e8` (`0xb8289d–0xb8298a`). The
finish-board branch clears its field when the lookup misses (`0xb829e6`).
The original endpoint values remain unknown.

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
and framing. Guest acceptance is unverified.

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
pads to an eight-byte boundary with `0x04` and enters a Blowfish-shaped
forward cipher using the context at object offset `0xe8`
(`0xec9865–0xec99cc`). Delivery of the transformed bytes and the reply
formats require a capture.

`0xb5d300–0xb5d38b` provides the dynamic URL and request span for the
multipart path. One branch appends the format `%s%llu&n=%d&s=1`
(`0x120b1fa`) at `0xb5d361`. Another copies the input URL at `0xb5d3ae`.

The `gameapi_*` names below are operation labels. The EBOOT relocates the
`ssinfo` and `gameapi_login` string pointers at `0x132f010` and `0x132f060`.
The deployed paths, hosts and values remain unknown.

| Operation labels | String region |
|---|---|
| Login, EULA, notices, boards, server time, user status and course-world assignment | `0x120b332–0x120b3fe` |
| Score lists, score registration, upload, daily and long-drive registration, rivals, player rankings and distributions | `0x120b379–0x120b4b5` |
| Bonuses and national boards, scores, entry notice and registration | `0x120b4b6–0x120b5f2` |
| Character download boards, registration, scores, count, assignment, regulations, finish/sign boards and upload info | `0x120b5f3–0x120b70d` |

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

The event-queue telemetry path builds on a separate libSceHttp stack. It
composes a URL from `https://mingol.api.dev.wwsga.me/games/` at `0x1206ab6`
and `/telemetry` at `0x1206add` (`0xb7f705–0xb7f734`). The queue logs a POST
and attaches `Content-type: application/json`, `Authorization` and
`X-WWS-SCHEMA-ID` at `0x643b5–0x643fd`. Its HTTP stack initializes
Net → pool → SSL → HTTP → template (`0x67130–0x671bc`), connects
(`0x6778d`), creates and configures the request (`0x67f8e–0x67fee`),
and sends and reads it (`0x67c4e–0x67d6b`). The telemetry service has no
role in local discovery replay.

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
| `0x2031` | Clears the string at context `+0x5e5f0` on a header-only record. Other lengths copy a string starting at payload `+4` (`0x11cddc8`, `0xb86511–0xb86529`, `0xb86588–0xb86594`). |
| `0x0080` | Supplies up to `0x100` bytes of string data to two buffers (`0x11cdd60`, `0xb8621e–0xb86254`). |
| `0x0083` | Copies a NUL-terminated payload, pads it to eight-byte blocks, and transforms it using the cipher context at `+0x121a88`. It Base64-encodes the result and writes the string back to context `+0x121e81` (`0x11cdd6c`, `0xb86259–0xb863d4`, `0xb86402–0xb86417`). The payload's meaning remains unverified. |
| `0x0086`–`0x0088` | Copies whole records into context fields at `+0x1224c4`, `+0x122548` and `+0x122550` (`0x11cdd78–0x11cdd80`, `0xb86485–0xb864f9`). |

A success callback by itself cannot verify an established session. The
local server still returns `404` for login.

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
the exact 28-byte reply. Guest routing and acceptance remain unverified.

The latest ignored fixture, `work/online/ss-info-local-v4.bin`, keeps
this server-time URL and includes all 37 keys in the URL map. The three
additional discovery values use synthetic loopback URLs. The v4 ciphertext
round-tripped through the standalone decoder and the loopback server
returned it byte for byte. Guest acceptance is unverified.

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
selectors 0 and 1. It replies with `0x8000/1`, `0x0000/2` with status 1,
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
Verifying rows requires checking the parsed result buffer. The loopback service leaves `gameapi_getscorelist` unanswered while the
inner `0x0060` exchange and row field meanings remain unresolved.

## NP, matching and peer transport

Each sequence below is a static path or adjacent group. The call-site index
covers repeats and alternate branches.

| Path | Calls and order |
|---|---|
| Title startup | Net init → net pool → NetCtl init → SSL init → HTTP init → NP title ID (`0xc0f3c–0xc0fc0`). The title registers its NP state callback at `0xf6d85`. |
| Availability and account checks | Create request → check NP availability or reachability → delete request (`0xb9ae2a–0xb9aead`). The parental-control path registers a reachability callback, creates a request, reads parental controls, then deletes it (`0xb9af0b–0xb9af63`). Online/account ID reads at `0xb97c92`, `0xb97ca2`. |
| Auth and PS Plus | Create async auth request → get authorization code → delete on submission failure (`0xa60ca9–0xa60d21`). Poll → delete at `0xb97f4c`, `0xb97f59`. The Plus path creates an async request then checks Plus at `0xa5a9e1`, `0xa5aa2b` and polls at `0xa5affc`. |
| Matching startup | Matching2 init → Signaling init → RUDP init → Matching2 context creation (`0xa7e0a5–0xa7e1e1`). Context, lobby, room and signaling callback registration follows (`0xa7e220–0xa7e2a7`). RUDP event handler and internal thread setup (`0xa7e2be`, `0xa7e2d5`), NAT query (`0xa7e467`), context start (`0xa7e482`), then signaling context creation (`0xa7e4f0`). |
| Discovery, rooms and lobbies | Server ID (`0xa8133b`), world list (`0xa813b6`) and lobby info (`0xa819e8`). Room operation handlers include create/join (`0xa779d8`), join (`0xa77db9`), external list (`0xa77f5e`), search (`0xa78155`), leave (`0xa78291`), and room messages (for example `0xa6d939`). Join lobby at `0xa83f8c`, leave at `0xa7dd79`. This is a set of operations with different callers, not a single mandatory sequence. |
| Peer path | Matching2 peer-net information (`0xa82167`) and signaling lookups (`0xa822d1–0xa823ed`), with activation (`0xa74243`, `0xa74616`) and status checks (`0xa7434b`, `0xa74380`, `0xa7479e`, `0xa747d7`). The transport opens and binds sockets (`0xa7494f–0xa74b48`), sets up the RUDP context and options (`0xa74d2f–0xa74e3d`), and initiates (`0xa74e90`). Data transfer uses `sceRudpWrite` (`0xa7f5b5`, `0xa7f71b`), readability query and read (`0xa7f9ef`, `0xa7fa15`). Exact peer payloads and callbacks are unresolved. |
| TUS | Title-context setup (`0xaa6a28`), request creation (`0xeccce2`), then get or set async data (`0xeccd44`, `0xeccda7`). Poll (`0xecd487`) and delete (`0xecd5b9`). A title-context delete also appears at `0xaa69b3`. |
| WebAPI and presence | WebAPI init and context creation (`0xecde9d`, `0xecdebd`), handle and push filter creation (`0xecdc88–0xecdcd0`), callback registration (`0xb98ccd`, `0xb98cf3`, `0xb99674`, `0xb996a1`). Request creation (`0xece37f`) uses a JSON content-type literal at `0x12190a6`. The worker sends at `0xece463`, then reads into a buffer with a total cap of `0x80000` (`0xece490–0xece4a4`). See the WebAPI request table for relative paths and response fields. |
| Word filter and social dialogs | Word-filter title context (`0xee75a`), async request and comment filter (`0xece741`, `0xece756`), poll and deletion (`0xeec4a`, `0xeed24`). Friends dialog initialize → open → update → close → terminate (`0xab5089–0xab51d6`), result elsewhere (`0xef69b9`). |

Any later attempt to implement local session, room, signaling or event
behavior needs the corresponding request/response contract and a loopback
capture coordinated by the runtime owner. Credentials, title secrets,
telemetry IDs and gameplay traffic were excluded from the server.


## Matching2 discovery callbacks

The primary path creates a context with a 16-byte parameter, including the
current user ID, and receives a 16-bit context ID at object offset `0x44`
(`0xa7e1b0–0xa7e1e8`). It registers the context callback at `0xa7e820`
with the Matching2 object as userdata (`0xa7e216–0xa7e220`) and requests
context start at `0xa7e482`.

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
| Row storage | The loop copies 40 bytes per row and advances the source index by 40 (`0xa7a024–0xa7a029`, `0xa7a095–0xa7a0bc`). Provide a contiguous array. The reference struct names its first eight bytes as a next pointer and the six following 32-bit fields as world ID and lobby/room counts. |
| Empty list | A zero count skips copies, leaves an empty guest vector and enters state 7 (`0xa79fae–0xa79fbf`, `0xa7a0c2–0xa7a0c7`). Supply a real response object even for an empty list. |

The same request callback is passed by the six alternate world-list call
sites at `0xa0a0f4`, `0xa0dd3e`, `0xa0f005`, `0xa1768f`,
`0xa72312`, and `0xa740bc`. The public type names match the local
DriveClub shadPS4 reference in
`gpu/shadps4/core/libraries/np/np_types2.h`. Actual server/world IDs
and population values require capture or a local multiplayer design.

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

## Matching2 rooms and peer transport

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
`OrbisNpMatching2RoomMemberDataInternalListA`. The contents of the
title's attachment attributes remain unverified.

`sceNpSignalingActivateConnectionA` supplies a context, peer identity
and writable connection ID (`0xa74239–0xa74243`, `0xa74616`).
`sceNpSignalingGetConnectionStatus` fills status, IPv4 address and
16-bit port (`0xa7436b–0xa74393`, `0xa747c0–0xa747ec`). The transport
setup checks for status 2 at `0xa7480d–0xa74811`. The guest then uses
an IPv4 P2P datagram socket, family 2 and type 6
(`0xa74931–0xa7494f`). The type name comes from the local reference
`network/net.h`. The peer-net information result at `0xa82167`
has a 24-byte size field initialized at `0xa82157`; the remaining
output fields have yet to be traced.

In one active-peer setup loop, the guest creates four RUDP contexts
with callback `0xa74ff0` and the peer as userdata
(`0xa74d0f–0xa74d36`, `0xa74e9c–0xa74ea7`). The bind uses virtual
port `0x14` and multiplex mode 1
(`0xa74d43–0xa74d56`). After per-context options, initiate at
`0xa74e90` receives a 16-byte address with IPv4, physical port and
virtual-port fields filled at `0xa74e51–0xa74e86`.

The receive loop uses the positive return of RUDP NID `Px0miD2LuW0`
as a read-loop budget (`0xa7f9c0–0xa7f9d2`). Its symbol name is
unverified. The loop queries `sceRudpGetSizeReadable` before
`sceRudpRead`. Read takes context, buffer, capacity, flags and an
information pointer, with zero flags on this path
(`0xa7f9e3–0xa7fa15`). The two write sites pass context, data, length
and byte flags (`0xa7f5a3–0xa7f5b5`, `0xa7f709–0xa7f71b`).
Guest transport, packet formats and interoperability remain unverified.

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
Guest acceptance of the loopback responses remains unverified.

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
(`0xcf1f85–0xcf1f87`, `0xcf2ab7–0xcf2abe`). The loopback service
returns `[]` for the default root, representing its empty local catalog.
Individual and batched label requests have no catalog entries and return
404. Guest storefront behavior remains unverified.

Catalog entries carry `container_type` and `label`. The callback compares
the type with the literal `category` (`0xcf1fd6–0xcf2011`). Product
fields include `skus`, `price`, `display_price`, `is_purchaseable` and
`use_count` (`0xcf2221–0xcf2335`). Categories use `size` and a
`links` array (`0xcf2343–0xcf23aa`). Original catalog contents remain
unresolved.
