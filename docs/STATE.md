# Project state

Status: Building. First guest frames reached on 2026-11-17 (the game's "NOW LOADING" screen). No real menu or gameplay yet.

## Goals

- Native Windows x86-64 port of Everybody's Golf `CUSA04687` 1.17.
- Unlock DLC content shipped with the installed game by default, with an original-entitlement test mode.
- Restore online multiplayer through a compatible community service and peer transport.
- Restore limited-event gear through evidenced event/redemption/shop behavior.

## Completed evidence

- `analysis/input-inventory.json`: 26 packages (base, update, 24 DLC), with sizes, hashes and Orbis metadata.
- `analysis/dlc-content-inventory.json`: all 24 DLC packages are metadata/entitlement-only; none contains a filesystem file.
- `work/base/uroot`: base 1.00 extraction using LibOrbisPkg. Its old validator reported several digest errors; do not treat that validator result as proof of corruption or authenticity.
- `work/update-1.17`: 1,196 update files extracted with Orbis after LibOrbisPkg's old PFS parser failed on the update.
- `work/game-1.17`: 1,778 hard-linked files, with update precedence and the non-empty base `libSceNpToolkit.prx` filling the update's zero-byte placeholder.
- `work/game-1.17-prepared/analysis.json`: 756 EBOOT imports, 43,099 relocations, 45 required modules; source SHA-256 `59d9dc8df97c2b39315afed269d33e63839d594c9f3357b8784ec0db7606e820`.
- `work/game-1.17-prepared/link.json`: 13 linked modules, 274 native bindings and 884 host imports.
- `analysis/import-names.json`: 713 host imports resolved to unique names, one ambiguous and 170 unresolved using the pinned Resogun/DriveClub symbol inventories.
- `analysis/ghidra/EverybodyGolf`: standalone Ghidra 12.2 import and auto-analysis completed. Ghidra reported decompiler warnings; coverage is useful but not complete.
- Project-local MSYS2 CLANG64 dependencies are installed and `external/resogun-recomp/out/resogun.exe` builds successfully. `tools/manifest.json` validates as JSON.
- A bounded boot on 2026-11-17 reached original guest entry, returned both initial linked-module initializers with 0, created 56 guest threads, initialized user login and AppContent, performed 32 direct-memory allocations/maps, and registered two 3200x1800 display buffers. This is not guest-rendering evidence.
- `sceNetInit` (`Nlev7Lg8k3A#libSceNet`) is now implemented as an offline initializer and its mapping is registered. The rebuilt runner advanced beyond it.

Preparation is not a byte-exact ELF reconstruction; the parser reports unavailable non-loadable metadata header 10. Execution must be verified separately.

## Current blocker

Latest bounded boot (90 s bound, 2026-11-17, build `EA10308E`, hidden desktop, windowed 1920x1080) ran the full 90 s and ended on the watchdog bound, with no fault and no missing import: 69 guest threads, 2,117 pad reads, 35 files opened, 202 MB read, 5,928 opens not found (mostly avatar model variants under `data/chara/model/avatar`; not yet checked whether those are expected probes or a path problem).

First guest frames (rendering VERIFIED for the loading screen only): `RESOGUN_FRAME_DUMP_TRIGGER` dumps at about 25, 50 and 75 s all show a black frame with the game's animated "NOW LOADING" text bottom right. Copy: `docs/media/2026-11-17-first-frame-now-loading.png` (1920x1080 output scaled to 960x540). The game did not leave that screen inside the bound. Unknown whether it is still loading under CPU load or waiting on something (a thread, a file, the silent audio, a network reply). Next: with the PC idle, run a longer bound and read the hang report's thread stacks (`CharacterObject*` threads were busy in guest code at the bound).

Two changes got there:

- Texture cache overlap: on a Pro (Neo mode) the game binds its tiled display buffer as a color target with `alt_tile_mode` set, while the VideoOut registration described the same surface without it (sizes 0x16a8000 vs 0x1770000), which hit `ResolveOverlap` unreachable. `ImageInfo` for VideoOut buffers now sets `alt_tile` when tiled and in Neo mode (`gpu/shadps4/video_core/texture_cache/image_info.cpp`). Upstream shadPS4 has the same gap. Evidence: `analysis/evidence/2026-11-17-texture-overlap.txt`.
- First flip faulted in `runtime_game_frame_rate` (`src/runtime_game.c`), a Resogun-only hook that follows a pointer at Resogun's frame-clock address. It is now skipped for `CUSA04687`. The Resogun wide-screen and cheat patches already check their bytes and do nothing here.

Fonts, same day: `libSceFont`/`libSceFontFt` (22 imports, hashes verified) are implemented in new `src/runtime_font.c`, drafted by a worker from DriveClub's file plus call-site evidence (`analysis/font-port/NOTES.md`). The PS4 system fonts are firmware files and absent from the dump, so every font set is served from one host face: `GOLF_FONT_FILE`, else Segoe UI or Arial (log line: `libSceFont serves system font sets from C:/Windows/Fonts/segoeui.ttf`). Glyph shapes differ from the PS4 font; weight and slant are stored, not applied; Japanese needs `GOLF_FONT_FILE` set to a CJK font. Boot verified past font startup; rendered text NOT_VERIFIED. That boot also opened seven audio ports.

Audio, same day:

- `libSceNgs2` (11 imports, names in `src/import_names.inc`, all NID hashes verified): new `src/runtime_ngs2.c` gives systems, racks and voices real handles and out-fields and renders silence. No mixing yet, so the game will be silent until a mixer exists. Evidence: `analysis/ngs2-contracts.md`. Boot verified through audio init (SystemCreateWithAllocator and the RackCreateWithAllocator calls); RackQueryBufferSize, RackCreate, VoiceGetState and SystemRender were not observed in a boot.
- `wVwPU50pS1c#libSceAudioOut` = `sceAudioOutSetMixLevelPadSpk(handle, level)`. Upstream had the port field and comment but no function. Added. Boot verified: advanced past it. The wrong-port-type error code was corrected to 0x8026000A after that boot; that one-line change is built into nothing yet (NOT_RUN).

Resolved on 2026-11-17 by the Claude orchestrator (each NID checked by recomputing the SHA-1 NID hash; each caller read with `llvm-objdump` on `work/game-1.17-prepared/eboot.elf`):

- `gky0+oaNM4k#libSceNetCtl` = `sceNetCtlInit`. Caller `0xc0f6c` passes no arguments (the logged first argument 0x1 is a leftover register) and tests the result for < 0. Returns 0. Boot verified: advanced past it.
- `htyBOoWeS58#libSceHttp` = `sceHttpsSetSslCallback(id, callback, arg)`. Caller `0xec9007` tests < 0. Accepted, returns 0; the callback never fires because nothing is sent. Boot verified: advanced past it.
- `qgxDBjorUxs#libSceHttp` = `sceHttpCreateConnectionWithURL(template, url, keepalive)`. Caller `0xec901d` keeps a result >= 0 as the connection id. Returns an id for an http/https URL. Boot verified: advanced past it.

- `f42K37mm5RM#libSceHttp` = `sceHttpsEnableOption(id, ssl flags)`. Caller `0xf6b8f` passes the connection id and 0x18 and ignores the result. Returns 0. Boot verified.
- `Qs0wWulgl7U#libSceMouse` = `sceMouseInit()`, result ignored at `0xbdaa9`; `RaqxZIf6DvE` = `sceMouseOpen(user, 0, 0, NULL)`, < 0 is failure at `0xbdaba` (stub identity inferred from the call shape); `x8qnXqh-tiM` = `sceMouseRead`. Ported from DriveClub: the port opens and never reports a connected mouse. Boot verified past Init and Open; Read not observed.

The same caller then makes three calls `(connection, 15000000)` at `0xec9034`, `0xec9048`, `0xec905c` (timeout setters by shape; identities not confirmed).

The bounded boot is load-sensitive. At idle the 20 s bound was enough; under full CPU load 90 s sometimes was not. Check CPU load before trusting a watchdog timeout as a hang. `run.py play` needs `MSYS2_ROOT` set, otherwise `resogun.exe` exits with 0xC0000135 (DLL not found).

Owner rule (2026-11-17): test boots must not appear on the monitor or take input. Launch through a hidden Windows desktop (`python <ghost_launch.py> python external/resogun-recomp/run.py play ...`) with `RESOGUN_DISPLAY_MODE=windowed`. Verified: the boot above ran that way and reached the same point as visible boots.

All 20 missing `libSceNet*`/`libSceHttp`/`libSceSsl` imports in `missing-imports.txt` resolve to names with matching NID hashes (list in `analysis/import-names.json`); only the ones listed above are implemented.

The import checker remains nonzero by design; `work/game-1.17-prepared/missing-imports.txt` was not regenerated in this session (NOT_RUN).

## Active source and ownership

- Orchestrator (sole integration owner since 2026-11-17 19:09 EST): Claude desktop Code-tab session `local_379ec4f6-3acc-450c-b6c7-f5aa8052c4c9`, title "Everybody's Golf PS4 runtime orchestration", model `claude-fable-5-2` (effort medium), local (not cloud). Pinned in the sidebar with the app's `set_pinned` control; `get_session` read back `pinned: true`. It owns `external/resogun-recomp`, builds, game execution, generated runtime state and shared docs. No workers started. The orchestrator is this lead session itself, not a separate background process: it runs only while the chat is active.
- Public repos (2026-11-17): main `https://github.com/finalpantasy/everybodys-golf-ps4-pc-port` (branch `main`), runtime fork `https://github.com/finalpantasy/resogun-recomp` (branch `everybodys-golf`, submodule at `external/resogun-recomp`). Commit only as `finalpantasy` with the GitHub noreply email; scan every push for personal names and user paths. The README has no screenshot by owner decision until the first rendered frame exists.
- Second agent: `docs/CODEX_GOAL.md` is the brief for a Codex session on the launcher/packaging and online side. It works in its own worktree (`external/resogun-recomp-launcher`, branch `golf-launcher`) and in `server/` and `analysis/online/`; it must not touch the boot path or run the game. Whether it has been started is not known to this file.
- Mailbox: `docs/MAILBOX.md` is the shared channel between the orchestrator and the Codex session (append-only, newest at the bottom).
- Integration owner before handoff: local Kimi lead (released). No runner process was intentionally left alive.
- Candidate: Resogun commit `e0fc29454f42f2948080e30f9b095b1297b99d00`, branch `everybodys-golf`, project changes committed on top (ten files). `out/resogun.exe` SHA-256 `94C990B6AA7C0D064F2675D3726ED7D345C38F02846751F7DCB384FBB7AB5CA0`. `git diff` SHA-256 `deb01deab7a12ebe15022719e01a39ea04b03820a1e76662b83a09287532ec7e`. Building through `usr/bin/bash.exe -lc` created the MSYS2 home `tools/msys2/msys64/home/<user>` (first-login skeleton files only).
- Changed files: `gpu/CMakeLists.txt`, `src/import_names.inc`, `src/runtime_devices.c`, `src/runtime_kernel.c`, `src/runtime_memory.c`, `src/runtime_net.c`, `src/runtime_rtc.c`, `src/runtime_sema.c`, `src/runtime_thread.c`.
- These changes cover the path-space build fix, thread/kernel hooks, memory queries/reservations, semaphore cancellation, offline Remote Play initialization, RTC, thread destructors, and `sceNetInit`. Thread-atexit accounting remains incomplete.
- Claude handoff: `docs/CLAUDE_TAKEOVER.md`. The next lead must start and pin one orchestrator before implementation, then record its actual host ID and ownership here. No current host tool was used to claim that an orchestrator exists.

## Next actions

1. Done: orchestrator pinned (see ownership).
2. Find why the game stays on "NOW LOADING": idle-PC run with a longer bound, read thread stacks, check the not-found opens.
3. Continue one intentional runtime failure at a time until stable initialization; do not call a host window or registered display buffers gameplay.
4. Locate AppContent entitlement/list and redemption paths and implement the built-in-DLC unlock provider with an original-entitlement test mode.
5. Capture Golf's network request contracts before implementing local identity, rooms, peer transport, events, and rewards.

## Verification commands

Run from `F:/everybodys golf ps4` with `MSYS2_ROOT=F:\everybodys golf ps4\tools\msys2\msys64`:

```bash
python external/resogun-recomp/run.py check --game work/game-1.17 --out work/game-1.17-prepared --any-build
python external/resogun-recomp/run.py play --game work/game-1.17 --out work/game-1.17-prepared --any-build --timeout 20
```

Build through `tools/msys2/msys64/msys2_shell.cmd -defterm -clang64 -no-start`, then run `bash build.sh` in `external/resogun-recomp`.

## Evidence boundaries

Guest rendering is shown for the loading screen only. No real menu, playable hole, multiplayer session, DLC unlock, or event reward has been demonstrated. The downloaded shadPS4/Golf-fix reference binaries have not been run. REA cannot currently analyze this ELF on Windows: Ghidra P0 accepts PE/raw targets only there, and REA's ELF-layout provider is Linux-only. Use the existing standalone Ghidra project until a supported REA route is configured.
