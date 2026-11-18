# Project state

Status: Building. On 2026-11-18 the game finished the character creator and reached the home island with the walking tutorial. Later that day hole 1 of Eagle City G.C. was finished twice (bogey, then par) and hole 2 was started. There is no sound.

## Goals

- Native Windows x86-64 port of Everybody's Golf `CUSA04687` 1.17.
- Unlock DLC content shipped with the installed game by default, with an original-entitlement test mode.
- Restore online multiplayer through a compatible community service and peer transport.
- Restore limited-event gear through evidenced event/redemption/shop behavior.

## Completed evidence

- `analysis/input-inventory.json`: 26 packages (base, update, 24 DLC), with sizes, hashes and Orbis metadata.
- `analysis/dlc-content-inventory.json`: all 24 DLC packages are metadata/entitlement-only; none contains a filesystem file.
- `work/base-orbis`: base 1.00 extracted with the Orbis CLI (1,114 files). The earlier LibOrbisPkg extraction in `work/base/uroot` is damaged (zero-filled holes in 805 files) and is no longer staged.
- `work/update-1.17`: 1,196 update files extracted with Orbis after LibOrbisPkg's old PFS parser failed on the update.
- `work/game-1.17`: 1,778 hard-linked files (base files from `work/base-orbis`), with update precedence and the non-empty base `libSceNpToolkit.prx` filling the update's zero-byte placeholder.
- `work/game-1.17-prepared/analysis.json`: 756 EBOOT imports, 43,099 relocations, 45 required modules; source SHA-256 `59d9dc8df97c2b39315afed269d33e63839d594c9f3357b8784ec0db7606e820`.
- `work/game-1.17-prepared/link.json`: 13 linked modules, 274 native bindings and 884 host imports.
- `analysis/import-names.json`: 713 host imports resolved to unique names, one ambiguous and 170 unresolved using the pinned Resogun/DriveClub symbol inventories.
- `analysis/ghidra/EverybodyGolf`: standalone Ghidra 12.2 import and auto-analysis completed. Ghidra reported decompiler warnings; coverage is useful but not complete.
- Project-local MSYS2 CLANG64 dependencies are installed and `external/resogun-recomp/out/resogun.exe` builds successfully. `tools/manifest.json` validates as JSON.
- A bounded boot on 2026-11-17 reached original guest entry, returned both initial linked-module initializers with 0, created 56 guest threads, initialized user login and AppContent, performed 32 direct-memory allocations/maps, and registered two 3200x1800 display buffers. This is not guest-rendering evidence.
- `sceNetInit` (`Nlev7Lg8k3A#libSceNet`) is now implemented as an offline initializer and its mapping is registered. The rebuilt runner advanced beyond it.

Preparation is not a byte-exact ELF reconstruction; the parser reports unavailable non-loadable metadata header 10. Execution must be verified separately.

## Current state and blocker

State on 2026-11-18 (runtime branch `everybodys-golf`, commit `ae6b409`, local only). Every boot below ran hidden with `RESOGUN_DISPLAY_MODE=windowed`, pad input from `RESOGUN_PAD_FILE` and frames from `RESOGUN_FRAME_DUMP_TRIGGER`.

Reached, with frames in `docs/media`:

- Title screen, autosave warning and the main menu's offline Store dialog (`2026-11-17-title-screen.png`, `-autosave-warning.png`, `-store-offline-dialog.png`).
- Course 00 drawn in 3D behind "NOW LOADING" (`2026-11-17-course00-loading-render.png`).
- The opening event with Suzuki and Hikari, with correct geometry and dialogue text (`2026-11-17-intro-event-fixed-geometry.png`).
- Nickname Entry: the keyboard dialog returns a name and the game asks "Are you happy with ...?".
- Customize Character, the character creator (`2026-11-17-character-creator.png`).
- 2026-11-18: "Finish editing" in the creator, the home island with Hikari's dialogue, the Walking Controls panel and the free-roam view with its HUD (`2026-11-18-home-island-after-creator.png`). The left stick walks the character across the island (`2026-11-18-home-island-walking.png`).

- 2026-11-18: the Specs dialogue ("Introduction to your EG life") plays to its end and the game auto-saves. The save holds seven files, about 38 MB, and the next boot reads them.
- 2026-11-18: the save resumes where it stopped. A boot from it reaches free roam in about 66 s (one Cross dismisses the S Ticket dialog). Hikari's "Offline Play Introduction" plays to its end and the island then shows the Tournament Desk, Solo Stroke Play, Shop and Menu markers.
- 2026-11-18: Tournament Select with Beginners' Cup No. 1 and its 16-player list (`2026-11-18-tournament-select.png`), the pre-round screen (`2026-11-18-pre-round.png`), and the Solo Stroke Play course list with six courses (`2026-11-18-solo-stroke-course-list.png`).
- 2026-11-18, first hole reached: Eagle City G.C., 9 holes OUT, Solo Stroke Play. Course Preview (`2026-11-18-course-preview-eagle-city.png`), hole 1 at the tee with "Set Up Tee Shot" (`2026-11-18-hole-1-tee.png`) and the shot view with power bar, club, wind and hole map (`2026-11-18-hole-1-shot-view.png`). The course load shows no new frame for about 40 s while pipelines compile; it is not a hang.

- 2026-11-18, shots played: in Beginners' Cup No. 1 on Green C.C. hole 10 (378 y, par 4, `2026-11-18-green-cc-hole-10-tee.png`) three tee shots ran from swing to result. Two were mis-hits that ended "O.B." with a penalty stroke (`2026-11-18-first-shot-ob-sequence.png`). The third had 97% power and a perfect impact and flew 187.8 y with 163.2 y carry (`2026-11-18-clean-tee-shot-sequence.png`); the game still returned to "Set Up Tee Shot" with a further penalty. The cause was found afterwards: the lie data was never read back from the GPU (next entry).

- 2026-11-18, cause of every lie being judged O.B.: the game draws course terrain data (lie type, height) into linear render targets and reads it on the CPU. The runtime did not copy those targets back to guest memory, so the game saw stale data, judged every landing O.B. and drew no terrain curve under the power bar. With `RESOGUN_READBACK_LINEAR=1` the tee shot was judged "On the Fairway" (`2026-11-18-eagle-city-fairway-hit.png`). Runtime commit `aa61692` makes that the default; `RESOGUN_READBACK_LINEAR=0` turns it off. `RESOGUN_READBACKS=2` is not needed.
- 2026-11-18, first completed hole: Eagle City G.C. hole 1 (309 y, par 4) with the readback switch on: fairway, fairway, approach to 6.9 ft ("Nice Approach!", `2026-11-18-eagle-city-nice-approach.png`), one putt short, gimme, "BOGEY" with total score +1 (`2026-11-18-eagle-city-hole-1-holed-out-bogey.png`).
- 2026-11-18, same hole on the rebuilt default runtime with no environment switches: fairway, "Bunker" (`2026-11-18-default-build-bunker-lie.png`), sand shot to 5.0 ft, putt holed, "PAR", then the scorecard (`2026-11-18-default-build-hole-1-par-scorecard.png`). Cross on the scorecard loaded hole 2 (281 y, par 4, `2026-11-18-default-build-hole-2-tee.png`); the drive went 182.2 y to the fairway (`2026-11-18-default-build-hole-2-drive.png`) and the approach was judged "Rough". The run ended there on the 600 s watchdog.

Gameplay status: the swing, ball flight, lie judgment (fairway, rough, bunker, green), putting, gimme, hole-out, scorecard and the move to the next hole work on screen. "First playable hole" and one completed hole are done; a full round is NOT_RUN. Open fault seen on the course: the hole map is black on hole 1 and drawn in color on hole 2. Auto-Impact was on for the completed holes; a three-press swing through to hole-out is NOT_RUN.

Swing input: `work/test-scripts/shot.py 1.1 1.15` sends Cross, waits 1.1 s, Cross for power, waits 1.15 s, Cross for impact. Pad-file polling adds about 0.1 s of jitter, so impact timing is not repeatable; "Toggle Auto-Impact" (Square on the pre-round screen) is untested.

Stepwise driver: `work/test-scripts/step.py TOKEN[:ms] ...` plays pad tokens against a running hidden boot (`boot-seq.ps1 -Warm 66 -Seq '-wait'` in the background), dumps one frame and writes `last.png`. Talking to a character needs the player turned toward them before Cross. A copy of the post-tutorial save is in `work/saves/after-tutorial` (untracked).

Fixed 2026-11-18, auto-save wrote nothing: the game opens `/app0//savedata0/DATAn.BIN` before `/savedata0/DATAn.BIN` and goes on only after ENOENT. The runtime answered EROFS for every write under `/app0`. A write to a directory that is missing from the game image now fails with ENOENT (runtime `aa82402`).

Test driver: copies of the boot scripts are in `work/test-scripts` (untracked). `boot-seq.ps1 -Until 'ImeDialog text' -Pulse 4000` taps Cross until the nickname dialog returns (about 120 s), then plays a comma list of pad tokens. A token takes `:ms` to hold and `@ms` for its gap. The creator needs 3000 ms gaps, because inputs get dropped during its transitions.

Fixed 2026-11-18, the hang after "Finish editing" (and an intermittent stall during boot): the game rebuilds its compute command buffers in place as soon as `sceGnmDingDong` returns. When the GPU thread was still running the previous buffer, the label releases in it were overwritten and the graphics queue waited forever on a label holding 0. `sceGnmDingDong` now waits up to 2 s for the compute queue to drain (`Liverpool::WaitAsc`). `RESOGUN_TRACE_DINGDONG=1` prints the compute submits and label traffic that showed this.

Color correction, 2026-11-18: the "blue skin", teal grass and orange sky recorded earlier were never drawn by the game. The screenshots were wrong. The frame dump (`output_*.raw`) holds the presenter frame in the swapchain format, which is BGRA on this PC, and the conversion scripts read it as RGBA, so every screenshot had red and blue swapped. Read as BGRA the home island shows a blue sky, skin tones and a brick plaza. A frame capture confirmed it from the other side: the game's 16-bit float copy of the final image has natural colors with no channel remapping. All screenshots in `docs/media` were re-saved with red and blue restored, and `step.py`, `burst.py` and `conv.py` now read BGRA. Still open: the creator avatar's skin draws white (`2026-11-17-character-creator.png`); whether that is a fault or the creator's default is NOT_VERIFIED. The sky bands noted on the course have not been re-checked on a corrected frame (NOT_RUN).

Other open items: no sound (the Ngs2 port renders silence), `IT_SET_PREDICATION` is not implemented (warned once), `sceGnmDebugHardwareStatus` is stubbed, `data_EU_18_ENG/sound/bgm/generic_menu.sxd1` and `NMG_OP_71.sxd1` are asked for and absent from the dump.

### What fixed what (2026-11-17, second half)

- Base package extraction was corrupt. LibOrbisPkg left zero-filled holes in 805 of 1,091 base files (found when `courseeffect.xb` entries failed zlib and the course load faulted at `0xeaddb4`). The base is now extracted with the Orbis CLI to `work/base-orbis` (1,114 files; only `sce_sys/license.info` skipped) and `work/game-1.17` links to it; `stage-manifest.json` names the new base. `work/base/uroot` is the old damaged copy: do not use it.
- Scattered-triangle geometry: a draw-preparation worker read the vertex buffer table before the game rewrote it for the frame. The draw now compares each vertex buffer descriptor before using prepared inputs (`vk_rasterizer.cpp`). Found by switching the renderer's optimizations off one at a time with `RESOGUN_TOGGLE_FILE`.
- Black faces: `v_writelane` was emitted as 0. Fixed by porting two hunks of the golf-fix v41 shadPS4 patch (`tools/golf-fix-pro-v41/source/golf-fix-v41.patch`, GPL-2.0-or-later).
- PM4 type 0 packets are skipped with one warning per register instead of asserting.
- Shader resource lists hold 128 images and 64 samplers; a draw with more bindings than the old limit threw.
- A local PSN account answers sign-in and NpWebApi locally (`src/runtime_golf.c`). 31 add-on labels from the game's own entitlement table are reported installed. Whether the game shows those items is NOT_VERIFIED.

### Switches

- `GOLF_NP=offline`: signed-out console instead of the local account. `GOLF_ONLINE_ID=<name>`: the local online id (default `Golfer`).
- `GOLF_ENTITLEMENTS=original`: report no add-ons.
- `RESOGUN_IME_TEXT=<text>`: answer every keyboard dialog with this text (needed for unattended boots: the on-screen dialog waits for a real controller or keyboard).
- `RESOGUN_FILE_TRACE_MATCH=<text>`: log every open whose path contains the text, found or not.
- `RESOGUN_FAULT_PEEK=<reg><+|->0x<offset>`: print the string at that address in a fault report.
- `RESOGUN_VERIFY_PREPARED=1`: compare what the draw-preparation workers read with a fresh read and log differences.
- `RESOGUN_TOGGLE_FILE=<file>`: a number in the file switches renderer optimizations off while the game runs (bits in `gpu/shim/resogun_toggles.h`).

### Network contract seen so far

The game opens `https://ssps4.scej-network.jp:443/nmg-us/ss.info` (GET, five times in a boot). Nothing is sent. No NpWebApi entitlement request has been observed yet, so the S Ticket grant is not built.

## Earlier findings (2026-11-17, first half)

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

1. Find why character skin draws blue or white.
2. Walk through the home island tutorial and reach the first hole.
3. Sound: an Ngs2 mixer.
4. Watch for the NpWebApi entitlement request (S Tickets), then build the grant list and check the items in the game.
5. Capture the game server's request contracts for the community server.

## Verification commands

Run from `F:/everybodys golf ps4` with `MSYS2_ROOT=F:\everybodys golf ps4\tools\msys2\msys64`:

```bash
python external/resogun-recomp/run.py check --game work/game-1.17 --out work/game-1.17-prepared --any-build
python external/resogun-recomp/run.py play --game work/game-1.17 --out work/game-1.17-prepared --any-build --timeout 20
```

Build through `tools/msys2/msys64/msys2_shell.cmd -defterm -clang64 -no-start`, then run `bash build.sh` in `external/resogun-recomp`.

## Evidence boundaries

Rendering is shown for the title screen, menu dialogs, course 00 behind the loading text, the opening event and the character creator. No playable hole, multiplayer session, visible DLC item or event reward has been demonstrated. The golf-fix shadPS4 binary has not been run; only its source patch was read and two hunks ported. REA cannot currently analyze this ELF on Windows: Ghidra P0 accepts PE/raw targets only there, and REA's ELF-layout provider is Linux-only. Use the existing standalone Ghidra project until a supported REA route is configured.
