# Everybody's Golf PS4 — recompilation research

Research checked 2026-11-17. Star counts are same-day GitHub snapshots. Compatibility and performance statements are maintainer-reported unless this project directly verified them.

Target: Everybody's Golf, `CUSA04687`. The folder contains a base 1.00 PKG, update 1.17 split archives, DLC, and an incomplete `.crdownload`. Do not assume the update is complete until every required part is present and verified.

## Recommendation for this Windows x86-64 project

Use a **direct x86-64 guest-code loader with native PS4 HLE and Vulkan**, following Resogun and DriveClub, as the first route. The PS4 and this PC share the same CPU architecture, so translating the executable to C or ARM64 would add a large verification burden without helping the Windows target.

Keep a separate future track for generated-C or ARM64 support using Bloodborne and PS4Recomp. That track needs its own instruction, control-flow, memory-ordering, and replay tests. Do not make it a prerequisite for the first Windows playable hole.

The project will still be a native port: original game machine code runs directly, while PS4 system libraries and GPU behavior are supplied by native host code. Describe it precisely rather than calling every x86-64 loader a source-level static recompilation.

## PS4 repositories ranked by usefulness and popularity

| Repository | Stars | Architecture and reported state | Value here |
|---|---:|---|---|
| [`OverkillLabs3/driveclub-recomp`](https://github.com/OverkillLabs3/driveclub-recomp) | 1053 | Original x86-64 code, native HLE and Vulkan on Windows/Linux; maintainer reports races, saves, DLC and multiplayer | Most popular direct-code PS4 port found. Strong benchmark, diagnostics, update/base separation, PGO and renderer work. GPL-2.0-or-later. |
| [`rcostanza/resogun-recomp`](https://github.com/rcostanza/resogun-recomp) | 57 | Original x86-64 code on Windows/Linux, HLE and Vulkan; playable port | Clearest small-runtime development loop, NID linking, tests, import traps and preparation pipeline. GPL-2.0-or-later. |
| [`wie-project/PS4Recomp`](https://github.com/wie-project/PS4Recomp) | 48 | Actual AMD64→ARM64 AOT assembly translation for Apple Silicon; several titles reported playable/in-game | Best general PS4 lifter architecture found: CFG analysis, multi-module linking, TSO, Metal, patch reports and differential tooling. Supports Apple Silicon rather than Windows. GPL-2.0. |
| [`rcostanza/dead-nation-ps4-recomp`](https://github.com/rcostanza/dead-nation-ps4-recomp) | 46 | Related direct-code Windows/Linux port | Useful comparison for how the Resogun runtime generalizes to another title. GPL-2.0. |
| [`bloodborne-native/bloodborne-recomp`](https://github.com/bloodborne-native/bloodborne-recomp) | 44 | x86-64→C static recompiler, arm64/x86-64 output, interpreter fallback | Best incremental lifter process: instruction fuzzing, recorded-call replay, annotations and per-function disable/bisection. GPL-2.0-or-later. |
| [`saulob/alienation-pc`](https://github.com/saulob/alienation-pc) | 20 | Native Windows/Linux port with Vulkan and co-op | Another Housemarque-era runtime reference; not needed while Resogun is clearer and more directly documented. GPL-2.0. |
| [`danilenko22/shadPS4-EverybodysGolf-fix`](https://github.com/danilenko22/shadPS4-EverybodysGolf-fix) | 0 | Modified shadPS4 specifically for `CUSA04687` 1.17 | Highest title-specific value despite zero stars: documented fixes and a complete patch against a named shadPS4 commit. GPL-2.0-or-later. |
| [`shadps4-emu/shadPS4`](https://github.com/shadps4-emu/shadPS4) | — | PS4 emulator for desktop hosts | Reference execution, PS4 HLE/GPU behavior, logging, patches and captures. It is not the standalone static-port deliverable. GPL-2.0. |

## Game-specific evidence

The [Everybody's Golf fix README](https://github.com/danilenko22/shadPS4-EverybodysGolf-fix) targets the same `CUSA04687` update 1.17 and describes fixes for black scenes, shot behavior, character faces, grass, shadows, text, cache reopening, offline dialogs and PS4 Pro rendering. Its performance work includes asynchronous image readback, batched command submission, background pipeline compilation and a crash-safe shader cache.

The supplied source patch names shadPS4 base commit `e0a466753a1aacbc8db8253be685bf7ab4d9daae`. Treat those changes as hypotheses and specifications to test in the native port, not as proof that every modification is necessary or correct. The modified emulator remains a reference runtime, not code to mix into an incompatible-license project.

The downloaded configuration explicitly enables direct memory access, linear-image readback, PS4 Pro mode and offline behavior. Those settings identify subsystems that need early attention.

## What the leading projects teach

### Resogun: the cleanest Windows bring-up loop

The [development guide](https://github.com/rcostanza/resogun-recomp/blob/main/docs/development.md) says the original x86-64 image is mapped and run directly. Preparation strips the SELF wrapper, links the EBOOT with shipped PRX modules by NID/library identity, and records analysis output. Unsupported imports become traps with an explicit first failure instead of a fake successful return.

Reusable process:

1. Prepare and link the image reproducibly.
2. Run `check` before execution and list missing imports.
3. Fix the first `STOP:` or guest fault, then rerun.
4. Keep a runtime implementation only for imports the target actually uses.
5. Preserve input recording/replay and thread hang reports from the start.

Its [build guide](https://github.com/rcostanza/resogun-recomp/blob/main/docs/building.md) includes Python and native tests, CI packaging and smoke tests. Windows builds require MSYS2 CLANG64; that prerequisite is not yet installed.

### DriveClub: measurement and update-aware packaging

The [build and diagnostics guide](https://github.com/OverkillLabs3/driveclub-recomp/blob/main/BUILDING.md) provides repeatable benchmark modes, frame logs, readback attribution, shader regression tests and PGO. The launcher keeps base and update folders separate and can prepare modified copies without changing the dumps.

Adopt its benchmark and diagnostic model after basic correctness. Do not import its performance defaults before measuring them on Everybody's Golf.

### PS4Recomp: actual AOT translation and patch provenance

[PS4Recomp](https://github.com/wie-project/PS4Recomp) translates AMD64 to ARM64 assembly, preserves x86 TSO with acquire/release operations, links multiple PRX modules and translates GCN shaders to Metal. Its patch system applies shadPS4-format patches before analysis and records old/new bytes, guest addresses and file offsets in `patch_report.txt`.

Its contribution gates require `go test -count=1 ./...` and `go vet ./...`, and reject artificial zero-return stubs. This is the better reference if an Apple Silicon target becomes necessary. It is not installed because the current host is unsupported.

### Bloodborne: incremental static translation with proof

The [recompilation guide](https://github.com/bloodborne-native/bloodborne-recomp/blob/main/docs/RECOMPILATION.md) keeps the game playable by leaving uncompiled code in the translator, checking generated code against recorded calls, and allowing individual generated functions to be disabled for bisection. It also preserves LP64 data layouts and treats x86 memory ordering as a separate measured layer.

Use this design if a generated-C route is later required:

- instruction-form fuzzing against an independent interpreter;
- recorded-call replay comparing results, writes and calls;
- per-function switches and bisection;
- published annotations rather than generated game code;
- explicit coverage of what still executes through the fallback.

### N64Recomp, XenonRecomp and ReXGlue

The strongest general recompilers remain useful as design references:

- [`N64Recomp/N64Recomp`](https://github.com/N64Recomp/N64Recomp) (8420 stars, MIT) uses declarative TOML metadata, literal instruction translation, runtime lookups for indirect calls, relocatable overlays and a single-file mode that lets linker order select replacement functions.
- [`hedge-dev/XenonRecomp`](https://github.com/hedge-dev/XenonRecomp) (6726 stars, MIT) documents explicit function bounds, jump-table analysis, weak function overrides and mid-instruction hooks. It recommends enabling register optimizations only after a working recompilation and includes CPU instruction tests.
- [`rexglue/rexglue-sdk`](https://github.com/rexglue/rexglue-sdk) (1293 stars) is another active Xbox 360 toolkit, but its README calls it early development with unstable APIs. Use it as a secondary reference rather than another dependency.

None supplies the PS4 runtime. Their reusable value is function metadata, controlled overrides, test strategy and update handling.

## Download and adoption decisions

| Capability | Decision | Result |
|---|---|---|
| LibOrbisPkg | **ADOPT** | Pinned and built. `PkgTool.Core` successfully listed the real base PKG. |
| Ghidra 12.2 | **ADOPT** | Hash-verified, extracted and headless launcher verified with project-local JDK 25. REA currently exposes no native Ghidra provider in this session; integration remains a later configuration step. |
| Temurin JDK 25.0.5+8 | **ADOPT** | Hash-verified and used for the Ghidra check. System Java was not changed. |
| shadPS4 0.21.0 | **ADOPT as reference runtime** | Hash-verified and extracted. Not launched with game data in this pass. |
| shadPS4 QtLauncher | **ADOPT as reference UI** | Hash-verified and extracted. No global user directories were populated by this setup. |
| Everybody's Golf fix v41 | **ADOPT as title-specific reference** | Hash-verified and extracted, including source patch, config and 1.17 patch. Not installed globally or launched. |
| Resogun and DriveClub source | **ADAPT candidate** | Exact commits cloned for inspection. No build attempted; MSYS2 CLANG64 remains required. |
| PS4Recomp / Bloodborne | **REFERENCE** | Read primary documentation, but do not install an incompatible macOS-oriented stack on this Windows host. |
| OpenOrbis SDK, RenderDoc, MSYS2 packages | **DEFER** | Add only when the selected runtime or a concrete test requires them. |

Exact paths, versions, hashes, verification and rollback instructions are in `tools/manifest.json`. The concrete implementation sequence is in `docs/recomp-process.md`.
