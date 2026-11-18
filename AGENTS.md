# Everybody's Golf PS4 native recompilation

- Target: `CUSA04687`, base 1.00 with update 1.17 and DLC supplied by the user.
- Goals include restored online multiplayer and limited-event gear. Unlock content shipped with the installed game by default in the native runtime, with an optional original-entitlement test mode. The online/DLC findings and acceptance milestones are in `docs/online-and-dlc.md`.
- Inventory confirmed 24 DLC packages, all metadata/entitlement-only with no filesystem payloads. Do not assume they represent every historical item or that files alone restore online features.
- Base 1.00 and update 1.17 are staged in `work/game-1.17`; the prepared runner enters original game code but has not demonstrated guest rendering or gameplay. Current status and ownership are in `docs/STATE.md`.
- Primary Windows route: run original x86-64 code with a native PS4 HLE/Vulkan runtime, following Resogun and DriveClub. Treat generated-C/ARM64 as a separate optional track using Bloodborne and PS4Recomp.
- Research: `docs/research/ps4-recomp-repository-survey.md`.
- Project process: `docs/recomp-process.md`.
- Tool versions, hashes, verification and rollback: `tools/manifest.json`.
- Use REA/Ghidra for claims about decrypted game binaries. Ghidra 12.2 and JDK 25 are project-local; REA's Ghidra provider is not configured yet.
- Keep packages, game data, keys, licenses, generated game images, shaders and build output out of source control. Preserve third-party licenses and do not commit generated game code.
- Measure progress by prepared image, boot, guest rendering, real menu, first playable hole and representative playthrough. Do not equate a launcher or lifted-function count with playability.
