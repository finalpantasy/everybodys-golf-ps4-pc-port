# Everybody's Golf PS4 native-port process

This process applies the repository research in `docs/research/ps4-recomp-repository-survey.md`. It favors a Windows x86-64 direct-code runtime and leaves ARM/generated-C support as a separately verified option.

## 1. Complete and pin the input set

Record every base, update, DLC and license input with its content ID, version, role, size and SHA-256. Preserve the originals.

- Base: `CUSA04687` 1.00 PKG.
- Update: 1.17 split RAR parts; verify the full set and reject incomplete `.crdownload` data.
- DLC: identify whether each package contains data, entitlement declarations, or both.

Extract base, update and DLC into separate staging trees. Do not flatten them before recording replacements. Use LibOrbisPkg for PKG inventory/validation/extraction, then verify the SELF/ELF state of `eboot.bin` rather than assuming package extraction decrypted it.

## 2. Establish the title-specific reference

Run the user's copy in the reference environment only when the complete update and any required system modules are available:

- stable shadPS4 for upstream comparison;
- the Golf fix build and patch for the known 1.17 behavior;
- identical game version, settings, save and scene where comparisons are made.

Record loaded modules, missing imports, GPU readbacks, game timing and the expected boot/menu/gameplay sequence. Treat the custom build as an unofficial reference, not upstream shadPS4 evidence.

## 3. Analyze the executable with REA/Ghidra

After obtaining the decrypted ELF:

- pin its SHA-256 and update version;
- record loadable segments, entry point, imports, exports and linked PRX modules;
- resolve imports by NID and library identity;
- map game-specific functions, strings and engine evidence;
- preserve REA Evidence IDs or Ghidra project notes for each conclusion.

Use the downloaded Ghidra 12.2 with local JDK 25 for standalone analysis. REA did not expose a Ghidra provider during setup, so do not claim REA decompilation until that provider is configured and verified on the actual ELF.

## 4. Build the Windows direct-code scaffold

Start from the smallest suitable Resogun/DriveClub-style architecture, retaining GPL notices and reviewing third-party components:

1. Prepare the EBOOT and shipped PRX modules reproducibly.
2. Map original x86-64 code and guest memory.
3. Link modules and resolve every imported NID intentionally.
4. Supply native kernel, threading, filesystem, input, audio, save and system-dialog behavior.
5. Translate GNM/GCN GPU work through the selected Vulkan core.
6. Enter the game's own code and record the first unsupported import or fault.

Unknown imports must trap or return a documented unsupported-service result. Do not silently return success for behavior that has not been established.

The pinned source candidates are references, not evidence that they already support this game. Before building them locally, install and audit the required MSYS2 CLANG64 toolchain and fetch pinned submodules.

## 5. Keep preparation and updates reproducible

Use a declarative pipeline with input hashes, commands and output receipts:

```text
inventory → extract → decrypt/unwrap → analyze → link
→ prepare-runtime → build → smoke
```

Separate base/update/DLC overlays in the virtual filesystem. Keep generated game images and build products local. Record source and runtime patches separately, and preserve old/new bytes and addresses for every executable patch.

A rerun should skip valid completed work. A changed EBOOT invalidates dependent analysis, linked images and runtime patches.

## 6. Verify in layers

### Loader and HLE

- The input executable hash and ELF layout match the target profile.
- Every linked module and import is accounted for.
- No unknown import silently succeeds.
- Base and update paths resolve to the intended content.

### Runtime and rendering

- Use a lightweight milestone stream for initialization, imports, file access, frames and saves.
- Compare the same scene against the reference runtime.
- Capture rendering evidence with guest and host overlays clearly distinguished.
- Pay early attention to linear-image readback, shader cache behavior, text, faces, shadows and PS4 Pro mode because the title-specific fix identifies them.

### Performance

- Use a repeatable hole or scene with recorded input.
- Warm up shader caches and the process before measurement.
- Alternate A/B runs and report average FPS, 1% lows and frame-time spread.
- Attribute stalls to GPU readback, command submission, shader compilation or game threads before optimizing.
- Record no-gain results and measurement corrections.

### Gameplay

Use these labels:

- **Prepared:** the executable and assets produce a reproducible local image.
- **Boots:** original game code enters and initializes without an unresolved blocker.
- **Renders:** the guest produces verified game pixels.
- **Menu:** the actual game menu accepts input.
- **First playable hole:** one hole can be started, played, scored and exited with working input, audio and saves.
- **Playable:** a person completes a representative playthrough with no known progression blocker and all remaining issues documented.

A launcher, host overlay or prepared image is not guest gameplay evidence.

## 7. Optional ARM/generated-C track

Do this only after the Windows route is understood or when an ARM target is explicitly required.

- Evaluate PS4Recomp's AMD64→ARM64 assembly path and its TSO/differential tests.
- Evaluate Bloodborne's generated-C path with interpreter fallback, instruction fuzzing, call replay and per-function bisection.
- Measure interpreted/translated coverage separately from static coverage.
- Do not claim cross-platform portability from a successful lifter build alone; the PS4 HLE/GPU runtime must also run on that host.

## 8. Diagnostic and release discipline

A diagnostic bundle may include build/input hashes, hardware, settings, milestone logs, frame timings and crash details. Scrub usernames and paths. Never include game files, generated game images, licenses, keys or other people's saves.

A preview requires a reproducible build, documented known issues and verified source/tool hashes. A playable release requires the gameplay gate above, reference scene comparisons, save/reload checks and a dated human playthrough log.

## Immediate sequence

1. Preserve and verify the complete base/update/DLC set.
2. Inventory and stage the packages with LibOrbisPkg.
3. Validate and analyze the updated decrypted EBOOT with REA/Ghidra.
4. Establish stable and Golf-fixed reference runs.
5. Select the smallest runtime candidate and install its audited build prerequisites.
6. Reach the first intentional loader/HLE failure, then advance by measured milestones.
