# Codex goal: launcher, release packaging and online groundwork

You are the second agent on a native Windows PC port of Everybody's Golf for PS4 (CUSA04687, update 1.17). Work without check-ins until a stop condition below is met.

## Read first

`AGENTS.md`, `docs/STATE.md`, `docs/recomp-process.md`, `docs/online-and-dlc.md`, `docs/research/release-standards-gap.md`, `external/resogun-recomp/CLAUDE.md`.

## Who owns what

A Claude session is the orchestrator and sole integration owner. It owns the boot path: `external/resogun-recomp` on branch `everybodys-golf`, every `src/runtime*.c`, `src/import_names.inc`, the `gpu/` renderer, `docs/STATE.md`, `README.md`, all game boots and the shared `out/` build folder.

You own the opposite side. Never edit the files above, never run the game or `run.py play`, and never push to `everybodys-golf` or `main`.

Your workspace:

- A separate git worktree of the runtime: `git -C external/resogun-recomp worktree add ../resogun-recomp-launcher -b golf-launcher everybodys-golf`. Build there with `bash build.sh`; its `out/` is yours.
- New top-level folders in the main repo: `server/` and `analysis/online/`. The main checkout is shared with the orchestrator, so do not switch branches, commit, stash or reset there. Leave your files uncommitted; the orchestrator commits them after review.

## Track 1: one executable, portable, flags (in the `golf-launcher` worktree)

Follow the 8-step order in `docs/research/release-standards-gap.md`. Target state:

1. One executable. It prepares the game image itself (port `prepare/` Python logic to C), detects an already prepared folder and goes straight into the game. No setup exe, no Python needed by the player.
2. Portable by default. Config, saves, caches, logs and the prepared image live beside the executable, or under `--data-dir`. Nothing is written to `%APPDATA%`, `%LOCALAPPDATA%`, the home folder or the current directory.
3. A flag for everything: `--game`, `--dlc`, `--data-dir`, `--config`, `--fullscreen`, `--windowed`, `--resolution`, `--monitor`, `--prepare-only`, `--reprepare`, `--timeout`, `--help`, `--version`, plus one flag per existing `RESOGUN_*` setting.
4. Linux packaging: a plain tarball next to any AppImage, and the AppImage takes one directory argument that holds everything.
5. Rename user-facing names from Resogun to Everybody's Golf only in files you own; leave `runtime*.c` identifiers alone.

Touch only launcher, loader argument parsing, setup, prepare, packaging and build files. If a change needs a `src/runtime*.c` or `gpu/` edit, write the exact patch to `docs/MAILBOX.md` and move on.

## Track 2: online and DLC groundwork (analysis and a server skeleton)

1. From `work/game-1.17-prepared/eboot.elf` (disassemble with `tools/msys2/msys64/clang64/bin/llvm-objdump.exe`; stub map in `analysis/plt-import-map.json`) document every network call path: hosts, URLs, HTTP methods, headers, request and response formats, the NP/matching/signaling imports used and their call order. Known start: `https://ssps4.scej-network.jp:443/nmg-us/ss.info` at guest `0xec901d`. Write `analysis/online/protocol.md` with an address for every claim and mark guesses as guesses.
2. Document the AppContent entitlement path: which calls list or check add-ons, the labels for the 24 DLC packages in `analysis/dlc-content-inventory.json`, and what the runtime must report to unlock them. Write `analysis/online/entitlements.md`.
3. Build `server/`: a small local service that answers the documented endpoints with the documented formats, with tests that replay the request shapes from `protocol.md`. No real PSN credentials, no contact with Sony hosts, no traffic to anything but localhost.

## Rules

- Evidence first: no blanket success stubs, no claims about rendering, menus or playability.
- No game files, keys, decompiled game code or build output in commits. Respect `.gitignore`.
- Commit as `finalpantasy <289411238+finalpantasy@users.noreply.github.com>`. No personal names, emails or `C:\Users\...` paths in files or commit messages. Commit only in your `golf-launcher` worktree. Do not push; leave that branch local for the orchestrator to review.
- One heavy process at a time (a build counts), at BelowNormal priority, nothing over 10 minutes. Kill only processes you started, by PID.
- American English.

## Mailbox

`docs/MAILBOX.md` is shared with the orchestrator. Read it at the start of each work block and before you stop. Append only, newest at the bottom, one entry per message: `### <date time> <from> -> <to>: <subject>`, then the message. Use it for patches you need in the boot path, questions, and findings the orchestrator should act on. It is the one shared file you may edit outside your own folders; never rewrite or delete another entry.

## Stop and report

Stop when both tracks are done, or when blocked on something only the owner can decide. Report once: branches and commits, what was built and which tests ran with their real output, what is unverified, and the patches waiting in `docs/MAILBOX.md`. Mark anything not executed as NOT_RUN.
