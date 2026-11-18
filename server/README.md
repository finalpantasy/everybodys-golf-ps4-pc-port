# Local Golf service

Run these commands from the project root.

```sh
python -B server/golf_server.py --port 8765
python -B -m unittest discover -s server -v
```

The listener binds to `127.0.0.1`.

| GET request | Local response |
|---|---|
| `/nmg-us/ss.info` | `503`, or exact ciphertext bytes from a fixture given with `--ss-info-file PATH`. The fixture must contain complete eight-byte blocks. |
| `/v1/users/me/entitlements?entitlement_type=service` | Empty by default. With `--ticket-grants`, two synthetic ticket rows. |
| `/v1/users/me/container/?size=128&serviceLabel=0` | Empty storefront catalog. |
| `/v1/users/5932163534510096385/friendList?friendStatus=friend&limit=2000&presenceType=incontext` | Empty friend list for the runtime's primary synthetic account. |

The server-time probe accepts `POST /nmg-us/replay-probe/gameapi_getservertime`
with the plaintext multipart request described in the protocol notes.
Enable it with a fixed date and time.

```sh
python -B server/golf_server.py --ss-info-file work/online/ss-info-local-v4.bin --server-time 2026-11-17T23:18:42
```

The fixture supplies an HTTPS URL to the guest so it uses plaintext
title records inside the HTTP body. The runtime must map that exact URL
to this HTTP listener. Guest acceptance is unverified.

To generate the v4 fixture, use the prepared 1.17 EBOOT and an OpenSSL
libcrypto library with Blowfish support. Supply `--libcrypto PATH` if
Python cannot find the library.

```sh
python -B server/make_discovery_fixture.py work/game-1.17-prepared/eboot.elf work/online/ss-info-local-v4.bin
```

For the EULA display probe, supply a local UTF-8 text file of up to
32,767 bytes. Generate a separate discovery fixture with `--eula`
and use the EULA transport patch in `docs/MAILBOX.md`.

```sh
python -B server/make_discovery_fixture.py work/game-1.17-prepared/eboot.elf work/online/ss-info-local-eula.bin --eula
python -B server/golf_server.py --ss-info-file work/online/ss-info-local-eula.bin --eula-file work/online/eula-local.txt
```

The service answers only the documented EULA fetch with that file's
text. The guest's agreement flow is unverified.

For the empty notice list probe, pass `--empty-notices` to both commands
and use the notice transport patch in `docs/MAILBOX.md`.

```sh
python -B server/make_discovery_fixture.py work/game-1.17-prepared/eboot.elf work/online/ss-info-local-notices.bin --empty-notices
python -B server/golf_server.py --ss-info-file work/online/ss-info-local-notices.bin --empty-notices
```

The probe replies with a synthetic `0x0083` string and a zero-count notice
list for selectors 0 and 1. Guest acceptance is unverified.

To probe ticket consumption, start the server with `--ticket-grants`.

```sh
python -B server/golf_server.py --ticket-grants
```

The opt-in fixture serves one ticket under `EN0001` and ten under
`EN0002`. A matching PUT consumes that grant once per server process.
Repeating the PUT returns HTTP 409. Guest verification requires the
runtime to route its entitlement WebAPI calls to the local service.

[Protocol](../analysis/online/protocol.md)
