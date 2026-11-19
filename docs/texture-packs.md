# Texture packs

The runtime can swap the game's textures for higher-resolution PNGs. You make a pack from a
dump of your own copy of the game. Packs contain game art, so they are never committed or
shared.

## Make a pack

1. Dump the textures. Set `texture_dump=F:/path/to/dump` in `settings.ini` (or
   `RESOGUN_TEXTURE_DUMP`) and play through the places you want covered. Each texture is
   written once, as `<key>_<width>x<height>_<format>.dds`. A boot to free roam writes about
   1,270 textures (350 MB).
2. Convert them to PNG:
   `python external/resogun-recomp/tools/texture_pack.py convert DUMP_DIR PNG_DIR`
3. Upscale them:
   `python external/resogun-recomp/tools/texture_pack.py upscale PNG_DIR PACK_DIR --scale 2`
   - With `--esrgan path/to/realesrgan-ncnn-vulkan.exe`, Real-ESRGAN does the upscale. Without
     it, the tool uses Lanczos with light sharpening, which adds little detail.
   - Outputs are capped at 4096 px per side (`--max-side`). Textures under 128 px (`--min`)
     and screen-sized frame captures are skipped.
4. Turn the pack on: `texture_pack=F:/path/to/pack` (or `RESOGUN_TEXTURE_PACK`).

You can also edit any PNG by hand. A pack file only has to start with the 16-digit key of
the texture it replaces. It can have any size, and subfolders are searched.

## How it works

- Key: XXH3 of the texture's guest bytes, seeded with its size and format family. sRGB and
  UNORM views share a key.
- Eligible textures: 2D, one layer, at least 16x16, never written by the GPU, in BC1, BC2,
  BC3, BC7 or 8-bit RGBA/BGRA. BC4, BC5 and BC6H (normal maps, HDR) are left alone.
- A low-priority worker thread decodes each PNG and builds a mip chain. The render thread
  uploads at most 16 MiB per submit. Until a texture's replacement is uploaded, the game's
  own texture shows. At most 256 MiB of decoded images wait for upload at a time.
- The replacement is an RGBA8 image sampled in place of the original view, with the original
  view's swizzle and sRGB setting. A texture the GPU later renders into goes back to the
  original.

## Measured (2026-11-19, RTX 4090, free roam)

- Dump on: 59.2-59.8 FPS while writing 1,273 textures.
- 2x pack (1,148 PNGs, 2.0 GB on disk): free roam at 58.8-59.4 FPS with GPU idle about 69%,
  the same as without a pack. Over 1,024 textures replaced, using 9.9 GB of video memory;
  the process commit peaked at 17.9 GB. A tinted test pack confirmed the swap in game.
- The scene between the title and free roam stalls for up to 7 s on a cold shader cache, with
  or without a pack.

## Limits

- Video memory: every replacement is uncompressed RGBA8, 8x the size of a BC1 original (4x a
  BC3 or BC7 one) at the same resolution, and 2x scale multiplies that by 4. A full 2x pack
  needs about 12 GB.
- Shaders that read a texture's size or fetch exact texels see the larger image. None was
  seen in this game yet. If one breaks, delete that PNG from the pack.
- The hidden test launcher caps a run's job memory at 14 GB (`GHOST_MEM_GB`). Video memory
  counts toward that cap, so pack tests set `GHOST_MEM_GB=48`. Normal play has no such cap.
