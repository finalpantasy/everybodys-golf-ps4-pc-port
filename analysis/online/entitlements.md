# AppContent in CUSA04687 1.17

## Guest call path

| Address | Observation |
|---|---|
| `0xc74366`, `0xc7438f` | System module `0xb4` loads before `sceAppContentInitialize` (`R9lA82OraNs`). The init parameter is zeroed. |
| `0xc74d9c` | `sceAppContentGetAddcontInfoList(0, NULL, 0, &count)` (`xnd8BJzAxmk`, PLT `0x10fde10`). The guest tests the return for zero. |
| `0xc74db3–0xc74e06` | The guest allocates `count * 24` bytes and requests the same list again with the allocated buffer and capacity. |
| `0xc74e40–0xc74e84` | The guest steps through 24-byte rows and hashes the NUL-terminated label starting at byte zero. The hash starts at zero and updates as `hash = 31 * hash + signed_byte`, with 32-bit wrap. |
| `0xc74ea0–0xc74efe` | The guest looks up that hash in its own entitlement map and marks a match by writing one at offset `0x30` of the corresponding object. This loop derives availability from row presence and label alone. |
| `0xc48502`, `0xc48522`, `0xc48a07` | `sceAppContentTemporaryDataMount2`, `sceAppContentTemporaryDataGetAvailableSpaceKb` (`SaKib2Ug0yI`), and `sceAppContentTemporaryDataUnmount` (`bcolXMmp6qQ`). The guest builds `%s/data.dat` (`0x1210b74`) under the returned mount. |
| `0xaf1d19` | `sceAppContentDownloadDataFormat` (`CN7EbEV7MFU`) receives a local copy of `/download0` (`0x1208794`). |

The EBOOT's PLT contains no direct call to `sceAppContentGetAddcontInfo`,
`sceAppContentGetEntitlementKey` or `sceAppContentAddcontMount` in the call-site
scan. The title can still call other APIs through shipped PRX modules or an
indirect path.

## Shipped entitlement table

The path `xbdata/param/entitlement/entitlement_param.xb` appears at `0x12117df`.
The guest loads it at `0xc743e9` and hashes the first column of each data row
in the loader at `0xc743b0`. The file is 328 bytes. The fields at offsets
`0x1c` and `0x20` give a 290-byte zlib stream at `0x24` and a 1,266-byte
expanded size. The expanded columns are `EntitlementLabel`, `ProductLabel`,
and `ItemSaveDataID`. There are 31 data rows.

| Entitlement label | Product label | Item save-data ID | Expanded row offset |
|---|---|---:|---:|
| `EN0001` | `EN00010000000000` | 8783 | `0x4b6` |
| `EN0002` | `EN00020000000000` | 8784 | `0x4d4` |

The other 29 rows use the same value in both label columns. Seven labels
appear in the table without a supplied package. The save-data IDs join to
`savedataID` in the 1.17 item index at
`xbdata/param/ItemIndex/Item_index_list.US_01.xb`. Its zlib stream starts
at file offset `0x38`. The EBOOT points to the locale-neutral filename at
`0x11fcae7` and loads it in the path at `0x876da9`.

| Entitlement suffix | Save-data ID | Item index row | Asset label | Name from Japanese item-index text |
|---|---:|---:|---|---|
| `16` | 6260 | 5789 | `tops_047_a00` | Attendant staff costume |
| `17` | 2380 | 4278 | `kigurumi_000_a00` | Cat kigurumi |
| `20` | 8811 | 5790 | `tops_048_a00` | Ama polo |
| `22` | 8831 | 5792 | `tops_049_a00` | GEO Idol Club polo |
| `24` | 8785 | 178 | `acce_040_a00` | Clinging Necky accessory |
| `25` | 8786 | 179 | `acce_041_a00` | Polytan mask |
| `26` | 8891 | 6800 | `item_set_003` | BEAMS GOLF collaboration set |

The row numbers count from the first data row. The names are working
translations. Package release dates and regional availability remain open.

Run the [local decoder](decode_entitlements.py) from the project root.

```sh
python -B analysis/online/decode_entitlements.py work/game-1.17/xbdata/param/entitlement/entitlement_param.xb --inventory analysis/dlc-content-inventory.json
```

## Runtime contract

Return success and the number of available labels for the zero-capacity
count query. In the second call, return up to the stated capacity and set the
written count. Each row contains 17 bytes for the NUL-terminated label, three
zero padding bytes, and the 32-bit installed status `4` at offset `20`. The
24-byte stride is confirmed by the guest. The status offset and value match
the existing single-item provider in `external/resogun-recomp/src/runtime_content.c`.

For the local built-in mode, report the 31 `EntitlementLabel` values once
each. In original-entitlement mode, derive the rows from the installed
add-on directories. Resolve a ticket product folder to its short
entitlement label before deduplication, while retaining the physical
folder path. The supplied packages have zero filesystem payloads.
The item update loop at `0xc74fd0–0xc75022` checks the availability byte, skips
six-character labels, and looks up the record's item ID. For a matched item
it passes the installed state to `0xcd0250` at `0xc7522a`. Course selection,
consumable balances, store purchases and historical event/redemption rewards
remain unverified.

## Installed package inventory

Each product label is the suffix of `UP9000-CUSA04687_00-<label>` in
[dlc-content-inventory.json](../dlc-content-inventory.json). The inventory
covers 24 packages.

| Product label | Package title |
|---|---|
| `EN00000000000001` | Everybody's Golf - Cart (Premium) |
| `EN00000000000002` | Everybody's Golf - Cart (Standard) |
| `EN00000000000003` | Everybody's Golf - Cart (Off-Road) |
| `EN00000000000004` | Everybody's Golf - Green Country Club Course |
| `EN00000000000005` | Everybody's Golf - Balata Country Club Course |
| `EN00000000000006` | Everybody's Golf - Nam Rong Bay Country Club |
| `EN00000000000007` | Everybody's Golf: Pine Hills Golf Club |
| `EN00000000000008` | Everybody's Golf - Akigase Keikoku Country Club |
| `EN00000000000009` | Everybody's Golf - Custom Club Booster 1 |
| `EN00000000000010` | Everybody's Golf - Custom Club Booster 2 |
| `EN00000000000011` | Everybody's Golf - Character Box Expansion 1 |
| `EN00000000000012` | Everybody's Golf - Character Box Expansion 2 |
| `EN00000000000013` | Everybody's Golf - Character Box Expansion 3 |
| `EN00000000000014` | Everybody's Golf - Character Box Expansion 4 |
| `EN00000000000015` | Everybody's Golf - Character Box Expansion 5 |
| `EN00000000000018` | Kigurumi (Rabbit)-01 |
| `EN00000000000019` | Kigurumi (Bear)-01 |
| `EN00000000000021` | Polo Shirt (Special ①) |
| `EN00000000000023` | Polo Shirt (Special ②) |
| `EN00000000000027` | Everybody's Golf Commemorative Item Set |
| `EN00000000000028` | Final Fantasy 30th Anniversary Chocobo Cart |
| `EN00000000000029` | Everybody's Golf - LEVEL-5 20th Anniversary Buggies |
| `EN00010000000000` | Everybody's Golf - Special Ticket x 1 |
| `EN00020000000000` | Everybody's Golf - Special Ticket x 10 |


## Ticket balances

The ticket refresh passes the entitlement registry at `0x2c92690`
through its default path at `0xc77eac–0xc77ef3`. The registry is
initialized at `0xe7401–0xe7406`. The local table loader copies column
0 (`EntitlementLabel`) into its row at offset 8
(`0xc747c5–0xc747d0`, `0xc74913–0xc74940`). The refresh calls
`strnlen_s(label, 17)` at `0xc77edd`, then queues labels of length 6
at `0xc77ef3`. The two six-character rows are `EN0001` and `EN0002`.

The WebAPI list reader copies its string `id` into a 17-byte buffer
(`0xc76040–0xc76083`). The refresh and consume paths compare those IDs
directly to the queued labels (`0xc78230–0xc78274`, `0xc77315–0xc7736b`).
A local fixture can therefore use `EN0001` and `EN0002` as the IDs.
The longer product labels identify the package records.

In the consume path, `0xc7736b` reads the matching row's `use_limit`
and `0xc77482` stores it in the queued request. The PUT sends that value
as `use_count` (`0xefbd7–0xefc2a`, `0xece5ab–0xece5cf`). On success,
`0xc762be–0xc762c6` adds the old `use_limit` to the cached
`use_count` and clears the cached `use_limit`. The loopback fixture
uses these transitions for two synthetic grants. Retail service
responses and guest use of the fixture are unverified.
[WebAPI request table](protocol.md#webapi-requests)


## BEAMS GOLF and Atelier items

The item index's set table (zlib at file offset `0x18f9c`) maps set 3
to the nine BEAMS GOLF pieces with save-data IDs 8882–8890. The primary
table contains `item_set_003` as item 8891. Entitlement suffix `26`
points to the set and is included in the proposed built-in mode.

The bundled shop table at `xbdata/param/serverFile/info.US_01.xb`
has a zlib stream at `0x2a0` with `item_id`, `ProductLabel`, `price`,
`sales_num`, and sale-window columns. Its path appears at `0x1204539`
and is referenced at `0xdc5c5`, `0xe7788`, `0x64d53d`, `0x65f663`,
`0xa719c7`, and `0xa71dbc`. In that table, the nine individual BEAMS
pieces and eight Atelier pieces (8965, 8966, and 8969–8974)
each have price 500 and sales quantity 1. All 17 rows use shop 0,
floor 16 and dates August 31 through September 28, 2018. These dates
describe the bundled table. Historical records describe other sale
windows and distribution paths. [Project background](../../docs/online-and-dlc.md)

The Atelier items cover Lydie's and Suelle's hair accessories, outfits,
boots and socks. Their IDs are absent from the AppContent entitlement
table. Guest verification is needed for the BEAMS bundle grant and to
establish which shop table the local runtime uses and how the sale
window is evaluated.
