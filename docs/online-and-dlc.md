# Online play, DLC, and limited-event gear

Scope: Everybody's Golf `CUSA04687` 1.17. Findings are separated into local package observations, historical reporting, and implementation hypotheses.

## Package inventory

`analysis/input-inventory.json` records hashes and Orbis metadata for 26 packages: base, update, and **24 DLC packages**. `analysis/dlc-content-inventory.json` records their readable filesystem contents.

**No DLC package contains a filesystem file.** They carry `sce_sys` metadata, icons, and license information, not course or costume payload files. The content itself must already ship in the base/update or be unlocked through game/server state. Do not infer completeness from package count alone.

Present content-ID suffixes:

- `EN00000000000001`–`EN00000000000003`: three carts.
- `04`–`08`: Green, Balata, Nam Rong, Pine Hills and Akigase courses.
- `09`–`10`: Custom Club Boosters 1–2.
- `11`–`15`: Character Box Expansions 1–5.
- `18`, `19`: Rabbit and Bear Kigurumi.
- `21`, `23`: the two special polo shirts.
- `27`: Commemorative Item Set.
- `28`: Final Fantasy 30th Anniversary Chocobo Cart.
- `29`: LEVEL-5 20th Anniversary Buggies.
- `EN00010000000000`, `EN00020000000000`: Special Ticket x1 and x10.

No local package currently represents suffixes `16`, `17`, `20`, `22`, `24`, `25`, or `26`. This is an inventory gap to investigate, not yet proof that all were released or required. There may be region-specific, promotional, withdrawn, or never-released slots.

## Limited-event gear is a separate restoration problem

Historical reporting confirms that some items were not ordinary permanent DLC:

- [BEAMS' announcement](https://www.beams.co.jp/en/news/673/) says wear parts were available through product-code cards and as prizes in an online BEAMS GOLF Cup. The tournament had qualifying/final windows, and its in-game gate was unavailable when no tournament was running.
- [Push Square's BEAMS report](https://www.pushsquare.com/news/2018/01/beams_golf_gear_swings_into_everybodys_golf_on_ps4) likewise describes tournament participation rewards.
- [Push Square's Atelier report](https://www.pushsquare.com/news/2018/04/everybodys_golf_adding_atelier_content_for_anniversary) says Lydie and Suelle costume parts were available for 500 in-game coins per part from 19 April through 17 May 2018.

Therefore restoring limited-event gear may require one or more of: the original assets, DLC entitlement records, a product-code redemption path, an event schedule, tournament/ranking services, or a shop/shop-price response. The correct mechanism must be established from the shipped code and data. Directly granting every item would be a separate optional convenience feature, not a behavioral restoration claim.

The 1.17 EBOOT contains recognizable `Month Item List`, `VsEventRegulation`, `NoticeBox`, tournament, and national-tournament strings, plus the networking modules listed below. These are analysis leads, not proof of a particular reward flow.

## What other projects do

### RPCN

[RipleyTom/rpcn](https://github.com/RipleyTom/rpcn) implements matchmaking rooms, scoreboards and title-user storage for RPCS3. It does not interoperate with real PS3s. Its server-side service split is useful, but its protocol and AGPL-3.0 license are not a drop-in fit for this PS4 project.

### psnr / re-psn

[psnr](https://github.com/sp00nznet/psnr) and [re-psn](https://github.com/undecuple/re-psn) provide rooms, matchmaking, leaderboards, peer addresses, NAT traversal and an optional relay for ps3recomp titles. Game traffic is peer to peer; the server handles discovery and scores. They are MIT-licensed and have useful C clients and NAT tests, but they target PS3 recomp integrations, not PS4 wire compatibility.

### shadNet

[shadNet](https://github.com/shadps4-emu/shadNet) implements PS4-oriented accounts, worlds, matchmaking and leaderboards. Its documentation describes TCP game/WebAPI services and optional UDP Matching2 signaling. The main repository had no detected license in the survey, so do not vendor it without permission. Evaluate a properly licensed fork or write against observed public behavior instead.

### DriveClub

[DriveClub's online documentation](https://github.com/OverkillLabs3/driveclub-recomp/blob/main/docs/online/README.md) is the closest process reference. It combines:

- local accounts and presence;
- hostname overrides to a community server;
- sessions, private lobbies and invitations;
- peer discovery, `sceNpSignaling` and reliable/unreliable RUDP traffic;
- profiles, statistics, clubs and leaderboards;
- a custom server with game-specific endpoints.

Its peer traffic works between compatible PC runtimes, not with consoles. Public matchmaking and ghosts remain incomplete in the documented branch. The server and runtime are GPL-2.0.

### God of War Ascension

The [Ascension repository](https://github.com/arnaldolima1/gow-ascension-pc) describes a custom Rust server with accounts, matchmaking, signaling and a UDP relay. Its server code is private, so its README supplies an architecture lead only, not a reusable implementation.

## Golf service map

The prepared 1.17 report lists these relevant required modules:

| Area | Modules | Initial responsibility hypothesis |
|---|---|---|
| Identity/session | `libSceNpAuth`, `libSceNpManager`, `libSceUserService`, `libSceSigninDialog` | Local/community account, sign-in state and session |
| Discovery/social | `libSceNpWebApi`, `libSceNpFriendListDialog`, `libSceNpUtility` | Presence, profiles, friends and notices |
| Rooms/matchmaking | `libSceNpMatching2` | World lists, rooms, tournaments and matchmaking |
| Peer transport | `libSceNpSignaling`, `libSceRudp`, `libSceNet` | Peer establishment and gameplay traffic |
| Cloud/event data | `libSceNpTus` | Title-user storage or event data; exact use remains unknown |
| Store/entitlement | `libSceNpCommerce`, `libSceAppContent`, `libSceNpAuth` | Store visibility, DLC ownership and possible item redemption |
| Transport/security | `libSceHttp`, `libSceSsl` | HTTP requests and TLS behavior |

Every row needs confirmation from imports, xrefs and captured requests. Do not implement a generic PSN service and assume Golf uses it.

## Built-in DLC policy

The user explicitly wants content shipped with the installed game unlocked in the native port. Implement an offline entitlement provider that reports all such built-in content as available by default, independently of the retired servers. Keep an original-entitlement mode for compatibility testing. This is separate from claiming historical limited-event rewards or filling currently unidentified content-ID gaps.

## Implementation sequence

1. **Offline native boot first.** Keep original Sony endpoints unreachable and document intentional offline stubs.
2. **Capture the request contract.** Use a logging local HTTP server and reference-runtime networking logs. Record methods, paths, schemas and expected errors without collecting real credentials.
3. **Implement minimal identity and presence.** Use disposable local accounts with no real PSN credentials.
4. **Implement rooms and peer transport.** Match Golf's Matching2, signaling and RUDP behavior; test two instances on one PC before LAN/VPN tests.
5. **Restore tournament and reward services.** Establish event schedule, notice, entry, ranking, result and reward flows from evidence.
6. **Handle DLC and limited items explicitly.** Record entitlement, redemption and shop behavior, including missing package slots and regional differences.
7. **Harden only after local correctness.** Public hosting needs authentication, rate limits, privacy rules, relay limits and a decision about persistent data. Do not expose an unauthenticated development server to the internet.

## Acceptance milestones

- Offline mode reaches the real menu without attempting Sony services.
- Two local instances sign into separate disposable identities and see each other.
- A room/lobby can be created, joined, left and rejoined.
- A multiplayer hole completes with consistent score/state on both instances.
- A scheduled test event can be entered and completed, with its intended reward granted once.
- Each owned DLC and limited-event item is accounted for by package, asset, entitlement, redemption or event evidence.
