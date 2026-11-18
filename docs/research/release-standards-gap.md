# Release standards gap: resogun-recomp tree

Scope: `external/resogun-recomp` as it is on disk (2026-11-17). Read-only audit; nothing was built or run.
Paths are relative to that folder unless they start with `docs/`. Line numbers are from the files as read.

Note: the tree is still Resogun. No file mentions Everybody's Golf or CUSA04687, so every
"Resogun" name (exe names, `RESOGUN_*` env vars, `resogun.log`, window title, shortcut name) is
still to be renamed when the port is adapted. LostOdysseyRecomp was not fetched for this audit; step 1
below is written from the owner's description of it, not from its source.

## Current layout in one paragraph

`build.sh:204` builds two targets, `resogun` and `resogun-setup`, copied to `out/` (`build.sh:229`).
`run.py` is the dev driver: it runs `scripts/prepare.py` and `scripts/link.py` (Python) to turn a
decrypted dump into `out/game/boot-linked.bin` + `content.bin`, then starts `out/resogun.exe` with
explicit flags. A release (`tools/package.py`) holds `resogun[.exe]`, `resogun-setup[.exe]`,
`prepare/` (run.py, scripts, and an embedded Python on Windows), `release.txt`. The player runs
`resogun-setup`, which calls Python to prepare `game/`, writes `paths.ini` and `settings.ini`, then
`resogun` reads `paths.ini` (`src/launcher.c`) and starts the game. If the image is stale or missing,
`resogun` runs `resogun-setup --update` and waits (`src/launcher.c:508-516`).

---

## Standard 1: one executable

**Current behavior**
- `build.sh:204` `targets=(resogun resogun-setup)`; `recomplauncher.json:16-21` names the setup as the
  `prepare` program and `resogun` as `start`; `tools/package.py:51` `EXES = ('resogun', 'resogun-setup')`.
- The runner already does the "detect prepared folder, go straight to game" half: `src/loader.c:596`
  calls `launch_from_paths_ini` when argv has no boot file; it checks `game/boot-linked.bin`,
  `content.bin`, `release.txt` and `source.txt` (`src/launcher.c:236-247`) and starts the game with no UI.
- The other half is a second binary: `open_setup` (`src/launcher.c:223-231`) and `run_setup`
  (`src/launcher.c:185-219`) spawn `resogun-setup` and wait for it. The setup (`setup/main.cpp` 876 lines,
  `setup/main_linux.cpp` 574, `setup/setup.cpp` 840) is a separate Win32/Linux GUI + CLI.
- Preparing needs Python: `setup/setup.cpp:197-207` (Windows: `prepare/python/python.exe`, else `py.exe -3`,
  else `python.exe`) and `:267-276` (Linux: bundled or system `python3`); it runs `prepare/run.py prepare`
  (`setup/setup.cpp:655-656`) and `scripts/isa_rewrite.py` (`:699-700`). The Python is
  926 lines in `scripts/prepare.py` (359), `link.py` (366), `isa_rewrite.py` (201). `link.py` and
  `isa_rewrite.py` import `prepare`; `isa_rewrite.py` also needs the pip package `iced-x86`
  (`setup/setup.cpp:~702-705` error text).
- `run.py` is a third entry point (dev only; not in the release, but `prepare/run.py` is).

**What breaks it**
1. Two exes ship and the main exe depends on the second to ever reach a playable state.
2. First-run preparation needs Python (shipped on Windows, system python on Linux) plus `iced-x86` on some CPUs.
3. The setup window is the only place to pick the dump folder; the main exe has no UI of its own
   (`complain()` only shows message boxes, `src/launcher.c:54-61`).
4. `paths.ini` stores the dump path; with no `paths.ini` the exe cannot be told the path on its command line.

**Minimal change list, ordered by effort**
1. (small) Stop building and shipping the second binary as a requirement: delete `resogun-setup` from
   `build.sh:204`, `tools/package.py:51`, `recomplauncher.json:16-21` once item 4 lands. Keep it until then.
2. (small) New flags on the main exe, parsed in `launch_from_paths_ini` (`src/launcher.c:455`) before
   `read_paths`: `--game <dir>`, `--save <dir>`, `--dlc <dir>`, `--prepare-only`, `--reprepare`.
   `--game` writes `paths.ini` when given (today only setup does, `setup/setup.cpp:748`). With `--game`
   given and `game/` current, go straight to the game; no `paths.ini` needed on later runs.
3. (small) Replace `open_setup` with a minimal in-process prompt: on Windows `IFileOpenDialog` folder
   picker; on Linux `SDL_ShowOpenFolderDialog` (SDL3 is already linked, `src/launcher.c:39`). If the
   player cancels, exit with a clear message that names `--game`. This is the "simple Play button not
   tied to another binary" fallback; a progress window can reuse the SDL window.
4. (medium) Move preparation into the main exe. Two options:
   a. Port `prepare.py`, `link.py`, `isa_rewrite.py` (926 lines) to C inside `src/` as
      `src/prepare.c` with entry `int prepare_image(const char* game, const char* out, int any_build)`;
      `isa_rewrite` needs an x86 decoder, and `src/isa_rewrite.c` / `src/isa_emulate.c` already exist
      for the runtime, so check first whether they can replace `iced-x86`. Removes Python entirely.
   b. Embed CPython in the exe (large, not recommended; adds a runtime and still two moving parts).
   Pick (a). Call it from `launch_from_paths_ini` in place of `run_setup("--update")`
   (`src/launcher.c:508-516`), and from a new `--prepare-only` flag.
5. (small, after 4) Delete `setup/`, `setup.manifest/rc` and the setup targets from `gpu/CMakeLists.txt`;
   move the settings-seeding (`setup/setup.cpp:~740-750`, copy `settings.example.ini` to `settings.ini`)
   and `--skip-intro/--play-intro` into the launcher flags; drop `prepare/` from the package.
6. (small) Drop `run.py` as the way to run; keep it as a dev wrapper that only forwards flags.

---

## Standard 2: portable by default

**Current behavior (what already stays in the exe folder)**
- Prepared image: `game/` next to the exe (`src/launcher.c:486-488`).
- Shader cache: `shaders/` next to the exe (`src/launcher.c:552-555`; `gpu/shadps4/common/path_util.cpp:293-306`,
  `GetShaderCachePath`, takes `RESOGUN_SHADER_DIR`).
- GPU logs, screenshots, frame captures: `gpu/` next to the exe by default (`src/launcher.c:87-91`, `:163`;
  `run.py:53-58`). `UserPaths()` honors `RESOGUN_GPU_USER_DIR` (`gpu/shadps4/common/path_util.cpp:162`).
- `settings.ini`: first `<save>/settings.ini`, else `<exe>/settings.ini` (`src/launcher.c:541-545`;
  `gpu/shim/resogun_settings.cpp:22-36`).
- Saves, trophies, `addcont`, `temp0`: under `--user` (`src/loader.c:664`, `src/runtime_savedata.c:87`,
  `src/runtime_content.c:123,154`, `src/runtime_services.c:694`), default `save/` from the setup
  (`setup/main.cpp:89`).
- Log: `<save>/log/resogun.log` only when started from a file manager (`src/launcher.c:518-537`), crash copies in `<save>/log/`.
- Release scripts already move old per-user data in and delete it: `adopt_user_paths` (`src/launcher.c:126-139`),
  `MoveOldSharedFolder` (`gpu/shadps4/common/path_util.cpp:91-155`).

**What breaks the standard**
1. `src/loader.c:664` and `:883`: with no `--user`, the runtime uses `"user"` relative to the **current
   directory**, not the exe folder. `gpu/shadps4/common/path_util.cpp:162` does the same
   (`current_path() / PORTABLE_DIR`) when `RESOGUN_GPU_USER_DIR` is unset. Running the exe from another
   working directory (a shortcut without "Start in", a terminal) scatters files.
2. `gpu/shadps4/common/path_util.cpp:168-179`: when `RESOGUN_GPU_USER_DIR` is unset on Linux, falls back to
   `~/.local/share/shadPS4` (`XDG_DATA_HOME`, `HOME`). Launcher normally sets the variable, direct runs do not.
3. `paths.ini` stores `save=` as an absolute path (`setup/setup.cpp:303-305`, `narrow(text(save))`), so
   moving or copying the folder keeps pointing at the old save folder. Deleting the folder removes
   `paths.ini` too, but a moved folder silently shares saves with the old location.
4. Writes outside the exe folder by design (see the table at the end): per-user `paths.ini` handling
   (`src/launcher.c:95-105,126-139`), desktop/menu shortcuts (`setup/setup.cpp:758-840`), a Linux
   `~/.local/share/applications` entry, and GPU driver shader caches (not controlled by the port).
5. `src/launcher.c:282` uses `readlink("/proc/self/exe")`. In an AppImage that is the read-only
   squashfs mount (`/tmp/.mount_*`), so `game/`, `shaders/`, `gpu/`, `paths.ini` cannot be written there.
   There is no AppImage in the tree (`grep` for AppImage finds nothing outside docs text).
6. Setup writes only `root` = its own exe folder, but `settings.ini` is first looked up in the save folder,
   which can be anywhere the player chose in the setup.
7. `RESOGUN_SHADER_DIR` / `RESOGUN_GPU_USER_DIR` are env-only; no flag moves them.

**Minimal change list, ordered by effort**
1. (tiny) `src/loader.c:664,883`: replace the `"user"` default with `<exe_dir>/save`. Export the exe dir
   from `src/launcher.c` (`find_exe_dir`, `:276`) as `const char* launcher_exe_dir(void)` in `src/launcher.h`.
2. (tiny) `gpu/shadps4/common/path_util.cpp:162-179`: delete the XDG/HOME/`Library` fallback; when the env var is
   unset use `<exe_dir>/gpu`. Same file `:253-262` and `:91-155`: delete `MoveOldSharedFolder` and the
   `XDG_DATA_HOME` adoption once nobody has an old install to migrate (this is a new port: no old installs).
3. (small) `src/launcher.c`: delete `user_paths_ini`, `copy_file`, `adopt_user_paths` (`:93-139`) and the call
   at `:478`. A new port has no per-user `paths.ini` to adopt. Same for `setup/setup.cpp:503-508`.
4. (small) Write `paths.ini` values relative to the exe folder when the target is inside it
   (`setup/setup.cpp:303-305`, and the launcher's `set_path` already resolves relative values, `src/launcher.c:82-85`).
   Better: stop needing `paths.ini` for save/cache at all; only `game=` stays (the dump is external and read-only).
5. (small) Add one portable-root flag `--data-dir <dir>` (env `EG_DATA_DIR`) that sets the base for
   `game/`, `save/`, `shaders/`, `gpu/`, `log/`, `settings.ini`. Default: the exe's folder. This is the
   AppImage hook: the AppImage wrapper passes the directory argument, and `launcher_exe_dir()` becomes
   `launcher_data_dir()` everywhere (`src/launcher.c:186-188,238-243,477,486-488,553`).
6. (small) Shortcuts: make `--shortcut` the only way to create one (already CLI,
   `setup/main.cpp:150-153`), drop the post-install "Add a shortcut?" prompt (`setup/main.cpp:502-506`),
   and write nothing outside the folder by default.
7. (small) Redirect driver caches into the folder through env vars set before Vulkan loads, in
   `launch_from_paths_ini` (`src/launcher.c:544-555`): `MESA_SHADER_CACHE_DIR`, `__GL_SHADER_DISK_CACHE_PATH`
   (+ `__GL_SHADER_DISK_CACHE_SKIP_CLEANUP=1`) on Linux. Windows NVIDIA `DXCache` has no documented
   redirect; list it as a known exception in the README. This list was not verified on a machine.

---

## Standard 3: plain tarball next to any AppImage

**Current behavior**
- Linux release is already a tarball: `tools/package.py:10` ("--zip writes <release>-linux.tar.gz"),
  `docs/building.md:145`, `README.md:65` (`tar -xzf resogun-pc-<version>-linux.tar.gz`).
- No AppImage exists: no `appimagetool` call, no AppRun, no `.desktop` template in `packaging/` (only
  `packaging/diagnose/*.bat`) or in `tools/package.py`.
- CI publishes the Windows zip and the Linux tarball (`docs/building.md:180`).

**What breaks it**
- Nothing yet. The standard becomes a gap the moment an AppImage is added: the tarball must stay,
  and the AppImage needs the directory-argument design from standard 2 item 5.

**Minimal change list**
1. (nothing now) Keep the existing `--zip` tarball in `tools/package.py`; make the release job fail if a
   `.AppImage` is uploaded without the matching `-linux.tar.gz` (one line in the CI workflow under `.github/workflows/`).
2. (medium, only if an AppImage is wanted) New `packaging/appimage/`: `AppRun` that reads a data
   directory (first CLI argument, else `$APPIMAGE_DATA_DIR`, else `<dir of $APPIMAGE>/<name>-data`),
   `exec`s the binary with `--data-dir "$DIR"`; `.desktop` + icon; `tools/package.py --appimage`.
   Requires standard 2 item 5 first. AppImage must not use `/proc/self/exe` for the data location.

---

## Standard 4: a CLI flag for everything

**Current behavior**
- The runtime parses a fixed flag list in a plain loop (`src/loader.c:610-632`), starting at `argv[2]`
  (argv[1] is the boot file). Any other flag aborts: `Unknown option` (`src/loader.c:631`).
- The launcher path (`src/loader.c:596`) only runs when argv[1] is absent or starts with `--`; it prepends
  the boot, profile, app0, user, dlc, timeout, isa args (`src/launcher.c:557-565`) and forwards the rest
  (`:566-567`), so every user flag still passes through the runtime loop above, which rejects unknown ones.
- Display, audio, frame rate etc. exist only as `settings.ini` keys and as env vars read by
  `gpu/shim/resogun_settings.cpp:219-229`; no flags (`RESOGUN_DISPLAY_MODE`, `RESOGUN_MONITOR`, `RESOGUN_VSYNC`...).
- `run.py` has its own flag set for dev use (`run.py:143-152`).

**What breaks it**
- No `--fullscreen`, no `--windowed`, no `--monitor`, no `--resolution`, no `--vsync`, no `--frame-rate`,
  no `--config <file>`, no `--shader-dir`, no `--log`, no `--help`/`--version`.
- Paths (`game`, `save`, `shader`, `gpu`, `config`) have env or `paths.ini` routes but no flags on the main exe.
- Unknown flags exit with a one-line error; the usage string (`src/loader.c:634`) omits the launcher-mode flags.

**Minimal change list, ordered by effort**
1. (tiny) Add `--help`/`-h` and `--version` to the launcher before parsing (`src/launcher.c:455`), print the
   table below, exit 0.
2. (small) New helper in `src/launcher.c`: for each settings-flag below, call `set_env("RESOGUN_<KEY>", value)`
   (already `src/launcher.c:290-297`, and unlike `setenv` it does not overwrite an existing env; change
   to overwrite for CLI flags so flags beat env). The shim already maps those env names to settings keys
   (`gpu/shim/resogun_settings.cpp:219-229`), so no GPU change is needed. Remove each consumed flag from the
   forwarded list (`src/launcher.c:566-567`) so the runtime loop never sees them.
3. (small) Exact flag names to add (same on `resogun` and the future single exe):

   | Flag | Sets |
   |---|---|
   | `--fullscreen` / `--windowed` / `--borderless` | `RESOGUN_DISPLAY_MODE` = fullscreen/windowed/borderless |
   | `--resolution WxH` | `RESOGUN_OUTPUT_RESOLUTION` |
   | `--render-resolution 4k\|1080p` | `RESOGUN_RENDER_RESOLUTION` |
   | `--aspect-ratio 16:9\|...` | `RESOGUN_ASPECT_RATIO` |
   | `--monitor N` | `RESOGUN_MONITOR` |
   | `--vsync 0\|1`, `--tearing 0\|1` | `RESOGUN_VSYNC`, `RESOGUN_TEARING` |
   | `--frame-rate N` | `RESOGUN_FRAME_RATE` |
   | `--hdr 0\|1`, `--sharpening 0\|1` | `RESOGUN_HDR`, `RESOGUN_SHARPENING` |
   | `--audio-channels auto\|stereo\|5.1\|7.1` | `RESOGUN_AUDIO_CHANNELS` |
   | `--skip-intro` / `--play-intro` | `RESOGUN_SKIP_INTRO` 1/0 (same names as setup, `setup/main.cpp:118`) |
   | `--game DIR`, `--save DIR`, `--dlc DIR` | launcher paths (same names as setup) |
   | `--data-dir DIR` | portable root (standard 2) |
   | `--config FILE` | `RESOGUN_CONFIG` |
   | `--shader-dir DIR`, `--gpu-dir DIR` | `RESOGUN_SHADER_DIR`, `RESOGUN_GPU_USER_DIR` |
   | `--log FILE`, `--verbose` | log path (`src/launcher.c:521`), `RESOGUN_VERBOSE` |
   | `--prepare-only`, `--reprepare` | prepare and exit; force rebuild of `game/` |
   | `--no-crash-watch` | `RESOGUN_CRASH_WATCH=0` |
4. (small) Fix the runtime's unknown-option message to point at `--help`; make `--timeout` default `0` in
   `src/loader.c:604` for launcher starts (the runtime default is 10 s, `src/loader.c:604`; only the launcher
   passes `--timeout 0`, `src/launcher.c:564`, so a direct start of `resogun.exe boot.bin` exits after 10 s).
5. (medium) Replace the hand-written loop in `src/loader.c:610-632` and the setup parsers
   (`setup/main.cpp:104-127`, `setup/main_linux.cpp:~85-110`) with one table-driven parser in
   `src/cli.c` so flag docs and `--help` are generated from one list.

---

## Every existing CLI flag

| Binary | Flag | Meaning |
|---|---|---|
| resogun | `--vulkan-only` (alone, `src/loader.c:582`) | Vulkan smoke test |
| resogun | `--cpu-features` (alone, `:584`) | print `CPU: missing ...` or `CPU: complete`; exit 20 if unsupported |
| resogun | `--gamepad` (alone, `:590`) | list gamepads and exit |
| resogun | `<boot-linked.bin>` (argv[1], `:605`) | the linked game image to run |
| resogun | `--cpu-only` (`:612`) | run without the GPU |
| resogun | `--strict-imports` (`:613`) | fail on a missing PS4 import |
| resogun | `--check-imports` (`:614`) | print `MISSING:` imports and exit |
| resogun | `--content-profile FILE` (`:615`) | `content.bin` |
| resogun | `--app0 DIR` (`:616`) | the decrypted dump mounted as /app0 |
| resogun | `--user DIR` (`:617`) | saves, trophies, addcont, temp0 (default `user` in CWD) |
| resogun | `--dlc DIR` (`:618`) | one more DLC folder |
| resogun | `--isa-rewrite FILE` (`:619`) | ISA rewrite table for CPUs lacking instruction sets |
| resogun | `--mount GUEST=HOST` (`:620`) | mount one host file/folder into the guest (max 24) |
| resogun | `--guest-arg ARG` (`:626`) | argument for the game's own argv (max 16) |
| resogun | `--timeout SECONDS` (`:630`) | stop after N seconds (default 10, 0 = no limit) |
| resogun | `--console` (`src/launcher.c:457`) | launcher only: attach a console / do not redirect to the log |
| resogun-setup | `--game PATH` (`setup/main.cpp:109`) | the dump or its eboot.bin; required in CLI mode |
| resogun-setup | `--save DIR` (`:110`) | save folder |
| resogun-setup | `--dlc DIR` (`:112`), `--no-dlc` (`:120`) | extra DLC folder / none |
| resogun-setup | `--copy-saves` (`:116`) | copy saves when `--save` changes |
| resogun-setup | `--skip-intro`, `--play-intro` (`:118`) | settings.ini `skip_intro` 1/0 |
| resogun-setup | `--progress` (`:122`) | print `progress <0..1> <step>` lines (RecompLauncher) |
| resogun-setup | `--shortcut FOLDER\|desktop` (`:111`) | write a shortcut |
| resogun-setup | `--update` (alone, `:868`) | re-prepare from paths.ini in a small window |
| resogun-setup | `--help`, `-h` (`:125`) | usage |
| run.py | `play\|check\|prepare` (`run.py:144`) | command (default play) |
| run.py | `--game DIR` (`:145`; env `RESOGUN_GAME_DIR`) | dump |
| run.py | `--timeout N` (`:146`) | play seconds |
| run.py | `--user DIR` (`:147`) | save folder (default `user/` beside run.py) |
| run.py | `--out DIR` (`:148`) | game image (default `out/game`) |
| run.py | `--dlc DIR` (`:149`) | extra DLC |
| run.py | `--any-build` (`:151`) | prepare an unverified eboot |
| run.py | anything else | passed to resogun (`parse_known_args`, `:153`) |
| scripts/*.py | `--out`, `--any-build` (`prepare.py`, `link.py`, `isa_rewrite.py`) | image folder, unverified build |
| tools/package.py | `--out`, `--python`, `--zip`, `--debug` (`tools/package.py:289-291`) | package options |
| build_windows.ps1 | `-Test -Run -Game -Timeout -Package -PythonEmbed -Clean` | build wrapper |
| build_linux.sh | `--test --run --game --timeout --package --clean` | build wrapper |
| build.sh | `--test` | also run tests |

Environment variables read (not flags): `RESOGUN_SAVE_DIR`, `RESOGUN_DLC_DIR`, `RESOGUN_CONFIG`,
`RESOGUN_CONFIG_DEFAULT`, `RESOGUN_GPU_USER_DIR`, `RESOGUN_SHADER_DIR`, `RESOGUN_CRASH_WATCH`,
`RESOGUN_VERBOSE`, `RESOGUN_ISA_REWRITE`, plus the display keys (`RESOGUN_DISPLAY_MODE`, `_VSYNC`,
`_TEARING`, `_MONITOR`, `_OUTPUT_RESOLUTION`, `_ASPECT_RATIO`, `_AUDIO_CHANNELS`, `_SKIP_INTRO`,
`_FRAME_RATE`, `_TITLE_BACK_EXITS`, `_RENDER_RESOLUTION`, `_HDR`, `_SHARPENING`;
`gpu/shim/resogun_settings.cpp:219-229`) and many debug switches (`RESOGUN_PAD_*`, `_FILE_TRACE`,
`_HANG_DUMP`, `_DMEM_MB`, ...).

## Every location outside the exe folder that gets written

| Writer | Location | When | Evidence |
|---|---|---|---|
| Runtime, no `--user` | `./user/` (current directory) | direct run without `--user` | `src/loader.c:664,883` |
| GPU lib, no env var | `./user/`; Linux fallback `$XDG_DATA_HOME/shadPS4` or `~/.local/share/shadPS4` | `RESOGUN_GPU_USER_DIR` unset | `gpu/shadps4/common/path_util.cpp:162-179` |
| GPU lib | `~/.local/share/shadPS4/cache/<serial>` read, moved, then removed | adoption on Linux | `path_util.cpp:253-262` |
| Launcher/GPU lib | `%LOCALAPPDATA%\Resogun`, `~/.cache/resogun` (moved in, then deleted) | `RESOGUN_GPU_ADOPT_SHARED=1` | `src/launcher.c:550`, `path_util.cpp:91-155` |
| Launcher | `%APPDATA%\Resogun\paths.ini`, `$XDG_CONFIG_HOME/resogun/paths.ini` or `~/.config/resogun/paths.ini` (moved in, then deleted) | every start | `src/launcher.c:95-105,126-139` |
| Setup | `%USERPROFILE%\Desktop\*.lnk` (`SHGetKnownFolderPath`) | shortcut prompt or `--shortcut desktop` | `setup/setup.cpp:785-793`, `setup/main.cpp:502-506` |
| Setup (Linux) | `~/Desktop` or `XDG_DESKTOP_DIR`; `$XDG_DATA_HOME/applications` (`~/.local/share/applications`) | shortcut | `setup/setup.cpp:817-837` |
| Setup | `--save` folder anywhere the player picks | install | `setup/main.cpp:110`, `paths.ini` |
| Setup | `--dlc` read-only; `game=` dump is read only | install | `setup/setup.cpp:289-300` |
| Setup (Windows, if prompted) | per-user Python bytecode in `prepare/scripts/__pycache__` (inside folder) | prepare | inside folder, noted for completeness |
| Setup | `--game` dump folder is never written | | `setup/setup.cpp:~290` comment |
| GPU driver | NVIDIA `%LOCALAPPDATA%\NVIDIA\DXCache`, AMD `%LOCALAPPDATA%\AMD\*`, Mesa `~/.cache/mesa_shader_cache`, NVIDIA `~/.nv`/`~/.cache/nvidia` | Vulkan pipeline creation | not in the repo, driver behavior, unverified here |
| Crash dumps | Windows WER `%LOCALAPPDATA%\CrashDumps` if enabled by the OS | crash | OS behavior, not the port |
| `packaging/diagnose/start.bat` | stays in `diagnose\` | debug kit only | `packaging/diagnose/start.bat` |

## Recommended implementation order

1. Anchor every path to one data root: add `launcher_data_dir()`, make the `user`, `gpu` and `shaders` defaults
   use it (`src/loader.c:664,883`, `path_util.cpp:162-179`), add `--data-dir`. Delete the per-user `paths.ini`,
   `~/.local/share/shadPS4` and `%LOCALAPPDATA%` adoption code (new port, no old installs).
2. Add the flag layer to the launcher: `--help`, `--version`, `--game/--save/--dlc/--data-dir/--config`, then
   the display and audio flags that set the existing `RESOGUN_*` env vars; consume them before the runtime loop.
3. Make the launcher self-sufficient without `paths.ini`: `--game DIR` writes/remembers it, a folder
   picker replaces `open_setup` when nothing is configured.
4. Port `prepare.py`, `link.py`, `isa_rewrite.py` into `src/prepare.c` (check `src/isa_rewrite.c` first for the
   decoder); call it from the launcher; add `--prepare-only` and `--reprepare`.
5. Delete the setup target, `setup/`, `prepare/` and the bundled Python from `build.sh`, `gpu/CMakeLists.txt`,
   `tools/package.py`, `recomplauncher.json`; make shortcut creation an explicit `--shortcut` only.
6. Rename for Everybody's Golf in one pass (exe name, `EG_*` env prefix, log/shortcut names, `release.txt`,
   `recomplauncher.json` game check and label), then retest the flags and paths.
7. Redirect driver shader caches into the folder where the driver allows it, and document the Windows exception.
8. Only then add the AppImage (`packaging/appimage/`, `AppRun` passing the directory argument) and keep the
   `-linux.tar.gz` published beside it, with a CI check that both exist.

## Three largest gaps

1. Two executables plus Python at first run (standard 1): the main exe cannot prepare a game; it needs
   `resogun-setup` and a Python interpreter, and the setup is the only folder picker.
2. No flags for display, paths or config (standard 4): the only route is `settings.ini` or `RESOGUN_*` env
   vars, and the runtime rejects unknown flags.
3. Paths not anchored to the exe folder (standard 2): defaults depend on the current directory
   (`src/loader.c:664,883`, `path_util.cpp:162`), the setup writes shortcuts and per-user files outside the folder,
   absolute `save=` in `paths.ini`, and `/proc/self/exe` breaks AppImage.
