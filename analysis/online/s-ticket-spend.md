# S Ticket storage, spending and shop tabs

Static analysis of base 1.00 + update 1.17 (CUSA04687). Addresses are image
addresses from `work/analysis-cache/eboot.dis`. Data offsets in `eboot.bin` are
image address + `0xa0b0` for the `.rodata` strings and jump tables used here.
Items marked NOT_VERIFIED were not confirmed by code or a guest run.

## 1. Where the count lives and why it is 101

- The S Ticket balance is one save-resident consumable, not a sum computed at
  display time. Item inventory slots are 0x44-byte records at
  `*(0x2c6b648) + 0x3723e8 + slot * 0x44`, slot limit `0x752f`. The count is the
  dword at record `+8` (`0x3723f0`), clamped to 0..10000 (`0x2710`).
- The ticket is the node with key `0` in the type-`0x24` item tree
  (`*(0x2c7cc70) + 0x350`, key at node `+0x30`, slot index at node `+0x24`).
  The leaf function `0x461460(delta)` adds `delta` to that slot
  (`0x4614e6–0x46154a`). It has three callers, all in the Blacksmith code
  (section 2). It is the only direct ticket writer found; `0xcd0250` also adds
  to the same slot (below).
- Grants come through `0xcd0250(itemRecord, add, count)`, the generic
  "add or remove an item" function. Type `0x24` is handled at `0xcd085b` and
  `0xcd0ecb–0xcd1201`: `slot += record[+0x14] * count`, or minus when `add`
  (the `esi` argument) is 0. Every caller found passes add = 1.
- The entitlement consume path calls it at `0xc77248` after a successful
  `PUT /v1/users/me/entitlements/EN000x` (`0xc762be–0xc762c6` moves
  `use_limit` into `use_count`). The record is the shop item behind the product
  label; its `+0x14` equals the shop sheet's `sales_num`
  (`+0x14` = `sales_num` is inferred from the arithmetic, NOT_VERIFIED in code).
- Arithmetic that gives 101: product `EN0001` (item 8783, `sales_num` 1) with
  `use_count` 1 gives 1; product `EN0002` (item 8784, `sales_num` 10) with
  `use_count` 10 gives 100. Total 101. It is not the sum of use_counts (11).
  It persists across boots because it is saved inventory data
  (`work/evidence/s-ticket-grant-101-2026-11-18.png`).
- Wallet fields in the same save object: `+0x56c984` coins, `+0x56c988` a second
  coin total, `+0x56c98c` gems (clamped to 9999).
- Boot dialog: the consume path formats a message with
  `use_limit * use_count + row[+0x18]` (`0xc77b29–0xc77b6c`) and shows it
  (`0xf38a20`). That is the "S Ticket dialog" dismissed with one Cross.

## 2. What tickets can be spent on

| Use | Evidence | Needs network? |
|---|---|---|
| Blacksmith / Custom Club Workshop: upgrade or repair a custom club, or pay for a new set, in gems or tickets | `blacksmith.xb` (stream `0x88`): `smith00_price_upgrade_ticket_00` 1, `smith01_price_upgrade_ticket_00` 1, `smith00_price_repair_ticket_00` 1, against `*_jewel_*` 10 (5 on the 50% sale columns). Code: `0x4717e4` compares price with the held count, `0x4719c7–0x4719cf`, `0x471d..–0x471df2` and `0x472d59` call `0x461460(-price)`; the other payment branch (`0x47191b`) spends gems at `+0x56c98c`. Messages "I'll take payment in S Tickets or gems", "Hang on, you haven't got enough tickets!" and the `MG7_Blacksmith%02d_common_payment_%04d` family belong to `EventFieldSmith::Manager` (`Menu Smith`). | No. No NpWebApi, `gameapi_*` or commerce call sites in `0x45xxxx–0x47xxxx` (`callsites.py NpWebApi` and `Commerce`). Local save change only. |
| Shop, red "ticket" tab ("Exchange S Ticket for item", help text `T_MG7_shop_ticket_exchange_default`) | Bundled sheet floor 20: one row, item 8823 (Turf War Warp Medal x10), `price` 1, `sales_num` 10. Item type `0x24` selects the "ticket" panel animation (`0xce8bd8–0xce8c6a`). That the price is paid in tickets is inferred from the tab icon, help text and price 1. The shop payment function was not found. | NOT_VERIFIED. No NpWebApi call in the shop region. |
| Tournament re-entry ("Use S Ticket x%d to re-enter", "Using %d S Ticket to try again in this tournament") | Strings in `message_text.US_01.xb`. The deduction code is not `0x461460`; not found. | Probably yes (tournament entry is online). NOT_VERIFIED. |

The Blacksmith is the one confirmed local spend. It needs no title server.
Its location on the island is NOT_VERIFIED (`EventFieldSmith`, name string
at image `0x11e8897+`).

The lottery boxes (floor 21, items 9004 "Normal Parts BOX" 3000 and 9005
"Hair/Extension BOX" 1000, item type `0x29`, random draw at `0xcd0966`) have
unknown currency. NOT_VERIFIED.

## 3. Shop tabs and a button sequence

Evidence for tab switching: the tab row in
`work/evidence/shop-limited-tab-online-2026-11-18.png` has an `L1` glyph at the
left end and an `R1` glyph at the right end, and the layout defines `btnl0`
and `btnr0` (`0x1213805`, `0x121380b`). Triangle is labeled "Switch display".
Cross confirms and Circle cancels (footer "Select / Camera controls / Cancel /
Confirm"). Wrap-around at the ends is NOT_VERIFIED.

Tabs, left to right in the screenshot (6 tabs): Last Month's Items (coin icon,
active on entry), three more coin tabs, a blue PlayStation Store tab, a red
ticket tab. The ticket tab is the last one, next to the `R1` glyph. Likely
sheet floors: 14 Last Month's Items, then 16, 17 and 21 as coin tabs, 18 PS
Store, 20 ticket. The floor-to-tab mapping is inferred from row counts and
prices, NOT_VERIFIED in code. Floor 22 (1,541 rows at price 99999) is not a
buying tab.

Sequence from the home island (keyboard keys in parentheses, from
`runtime_pad.c`):

1. Options (Tab or P) opens the Menu. The cursor starts on "Online".
2. D-pad Down once to "Shop" (Down arrow), Cross (Space or Enter).
3. Wait for the Shop to load on "Last Month's Items".
4. R1 five times (O or Page Down) to the red ticket tab. One L1 (Q) may also
   reach it if the tab list wraps. Check the help text "Exchange S Ticket for
   item".
5. Cursor to the item (D-pad), Cross, then Cross on the Yes/No panel
   (`panel_yn`). Expect a price of 1 for Warp Medal x10 (NOT_VERIFIED).

Blacksmith route: reach the Blacksmith NPC (location NOT_VERIFIED), Cross to
talk, choose an upgrade or repair, then pay with "S Ticket" instead of gems
in the payment prompt. The ticket branch is selected by state `1` at
`0x4718ba` and gems by state `0`; which input sets it was not traced.

## 4. What the `sdk:commerce` container reply controls

- `GET /v1/users/me/container/<label>:<label>...?size=128&serviceLabel=0`
  carries the shop sheet's `ProductLabel` values (floor 18 plus the two ticket
  labels). Per reply entry the callback (`0xcf1ee0`, `0xcf2221–0xcf2335`)
  updates an existing product entry only: `price` at entry `+0x154`,
  `display_price` at `+0x158` (64 bytes), SKU label at `+0x198`,
  top-level label at `+0x1b8`, `is_purchaseable` byte at `+0x1f8`,
  `use_count` at `+0x1fc`. Category entries use `size` and `links`.
- Floor 18 is the blue PlayStation Store tab: 19 rows with a `ProductLabel`
  and price 0. Product labels: `EN00000000000001–15`, `28`, `29`, plus
  `EN00010000000000` (item 8783, S Ticket x1, `sales_num` 1) and
  `EN00020000000000` (item 8784, S Ticket x10, `sales_num` 10). The
  `EN000000000000xx` labels are add-on DLC products (courses, carts,
  character box expansions, custom club boosters, Chocobo cart, buggies).
  Other labels in the batch (for example `EN00000000000021`) have no sheet
  row; they are not shown in the tab.
- `is_purchaseable:false` reads as "owned or not buyable": `0xcf055f–0xcf0586`,
  `0xcde633–0xcde659` and `0xce30fe–0xce3121` treat a false flag as true for the
  "already have it" check (`shop_already00`). When true, the check falls back
  to `count > 0` from `0xcefd30`. So with the loopback reply every product
  panel in the PS Store tab shows as already owned and cannot start a
  purchase. This does not affect spending tickets (section 2) or tab
  navigation. A nonzero product `use_count` makes the post-purchase handler
  (`0xce8b7c`) skip the local item add, because the entitlement path grants
  consumables instead.
- A real purchase opens `sceNpCommerceDialogInitialize/Open` (`0xf035b`,
  `0xf0418`); `0xce7134` and `0xce714c` show and hide the PS Store icon.
  Purchasing tickets is outside the offline port; the grant path
  (`GOLF_TICKET_GRANTS=1`) already covers it.

## 5. Limited-event gear: data and gating

- Bundled table: `xbdata/param/serverFile/info.US_01.xb`, zlib stream at
  `0x2a0`, a 2,056-row shop sheet whose path string is
  `data/param/serverFile/shop_price_sheet.txt`. Columns: `shop_id, floor_id,
  sort_id, change_item, announce_notice, announce_report, player_rank,
  item_id, ProductLabel, drawing_group, drawing_candidates, drawing_bias,
  intl_group, intl_bias, price, sales_num, attention_flug, rare_reward,
  month_limited, month_limited_weight, sale_sun..sale_sat, sale_open_hour,
  sale_open_min, sale_close_hour, sale_close_min, sale_open_year,
  sale_open_month, sale_open_month_shop, sale_open_day, sale_close_year,
  sale_close_month, sale_close_day`.
- Floor 14, "Last Month's Items": 382 rows, 375 at 3,000 coins, all with
  `month_limited` set to a calendar month (1-12, plus 7 rows `1_off`) and
  `sale_open_month_shop` set to the following month. Tutorial text: items
  that were "This Month's Items" last month. The tab header shows the sale
  period to month end (09/30/2018 23:59 for server date 09/14/2018). Which
  month is "last" follows the server date; the code that compares
  `month_limited` with the month was not located (NOT_VERIFIED).
- Floor 16: 99 rows (500, 300, 400 coins) of which 63 carry explicit windows:
  2018-08-31 to 09-28 (40 rows, includes the BEAMS GOLF and Atelier items),
  2018-10-10 to 10-31 (11), 2018-12-06 to 12-26 (6), 2018-01-01 to 01-10 (6).
  Floor 22 has 40 rows opening Oct 20 of an unset year (NOT_VERIFIED meaning).
- Floor 17: 12 balls (100-360). Floor 21: lottery boxes. Floor 20: warp
  medals. Weekday, hour and minute columns are empty in the bundled sheet.
- Time source: shop rows are checked against the cached game tick at
  `+0x85cbf8` of the object at `0x2c8f2e0`, refreshed from
  `sceRtcGetCurrentNetworkTick + 0x10520` or `sceRtcGetCurrentTick + 0x10518`
  (`0x5eb715–0x5eb7c2`), window test `0x5eb908–0x5eb91f`, extra eligibility
  `0x5eba18–0x5eba5a`. The `gameapi_getservertime` reply decoder writes
  those offsets (`0xb86194–0xb861c5`, `0xb86598–0xb865d2`). The guest's
  09/14/2018 date therefore comes from the loopback server time.
- Server-updatable files: `data/param/serverFile/*.txt` includes
  `shop_price_sheet.txt`, `event_mission_schedule.txt`,
  `nmg_global_alart_settings.txt`, `Fightingroom_bonus_coin_settings.txt`,
  `capture_the_flag_game_settings.txt`. The `gameapi_getgamepropertyinfo`
  download (index property, saved as `DATA5.BIN`; image strings at
  `0x120452f` and `0x120c128`) is the likely route for a newer sheet. That the
  downloaded file replaces `info.xb`, and the 32-byte metadata meaning, are
  NOT_VERIFIED (loader at `0xa719c7`, `0xa71dbc`, gate `cmpl $0, 0x1f1d368`
  at `0xa71cb9`).
- Practical consequence: with no `getgamepropertyinfo` data the bundled sheet
  is used, and moving the loopback server's date selects which month's items
  appear under "Last Month's Items" and which floor-16 windows are open.
  Tournament and mission rewards use `event_mission_schedule.txt` and the
  online tournament services; not traced here.
