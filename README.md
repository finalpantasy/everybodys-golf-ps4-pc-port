# Everybody's Golf PS4 PC Port

A work-in-progress native Windows x86-64 port of Everybody's Golf for PS4 (CUSA04687, update 1.17; sold as "Hot Shots Golf" in earlier US releases).

The port runs the game's original x86-64 code directly on Windows. The PS4 system libraries it calls are reimplemented in a runtime, and GPU commands are meant to be drawn with Vulkan. The runtime is a fork of [resogun-recomp](https://github.com/rcostanza/resogun-recomp). It lives in `external/resogun-recomp` as a git submodule, on the `everybodys-golf` branch of [finalpantasy/resogun-recomp](https://github.com/finalpantasy/resogun-recomp).

**No game files are included in this repository.**

## Current status

This is not playable yet.

- The original game code starts and runs initialization.
- The runner creates 56 game threads.
- The runner registers two display buffers.
- Network, HTTP and mouse startup calls are handled.
- Audio startup runs against a silent `libSceNgs2` (no mixing yet) and fonts are served from a host font.
- The game draws its first frames: the "NOW LOADING" screen below, captured from a 90-second run.
- It stays on that screen for the rest of the run. There is no menu and no gameplay yet.

![The game's own NOW LOADING screen, drawn by the port](docs/media/2026-11-17-first-frame-now-loading.png)

Progress is measured by these steps: prepared image, boot, guest rendering, real menu, first playable hole, representative playthrough. The first three are reached; guest rendering so far means the loading screen only.

## Goals

- Built-in DLC unlocked by default, with an original-entitlement test mode.
- Online multiplayer through a community server and a compatible peer transport.
- Restored limited-event gear, based on evidence of the original event, redemption and shop behavior.

None of these is implemented yet.

## What you need

- Your own legally dumped base game (CUSA04687).
- The 1.17 update.
- Your own DLC packages.

Packages, keys, licenses and game data stay out of the repository. See `.gitignore`.

## Build

Clone with the runtime submodule:

```bash
git clone --recurse-submodules https://github.com/finalpantasy/everybodys-golf-ps4-pc-port.git
```

Requires Windows and MSYS2 with the CLANG64 environment. From `external/resogun-recomp`, in a CLANG64 shell:

```bash
bash build.sh
```

## Run

Set `MSYS2_ROOT` to your MSYS2 install first. Without it, the runner exits with 0xC0000135 (DLL not found). Run from the repository root.

Check the prepared game files:

```bash
python external/resogun-recomp/run.py check --game work/game-1.17 --out work/game-1.17-prepared --any-build
```

Stage your dump into `work/game-1.17` first with `tools/stage_game.py`. Then start a bounded boot (20 second limit):

```bash
python external/resogun-recomp/run.py play --game work/game-1.17 --out work/game-1.17-prepared --any-build --timeout 20
```

The runner opens a borderless window that covers the screen. Set `RESOGUN_DISPLAY_MODE=windowed` for a normal window. The boot is sensitive to CPU load, so a timeout on a busy machine does not mean the game hung.

Current state, evidence and the next step are in [docs/STATE.md](docs/STATE.md).

## Release standards

Releases will follow these rules. The current tree does not meet them yet; the gap list is in [docs/research/release-standards-gap.md](docs/research/release-standards-gap.md).

- One executable.
- Portable by default.
- A tarball next to any AppImage.
- A command-line flag for every option.

## Credits and license

Licensed under the GNU General Public License, version 2, the same license as the upstream project. The upstream `LICENSE` is kept unchanged.

- [resogun-recomp](https://github.com/rcostanza/resogun-recomp) by rcostanza: the runtime this port is forked from.
- driveclub-recomp: a reference for the same approach.
- shadPS4: a reference for PS4 system behavior.

This is an unofficial project and is not affiliated with Sony or the game's developers.
