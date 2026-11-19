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
   - With `--esrgan path/to/realesrgan-ncnn-vulkan.exe`, Real-ESRGAN upscales the color
     textures. Without it, the tool uses Lanczos with light sharpening, which adds little detail.
   - Normal maps and channel masks always get plain Lanczos. About half of this game's textures
     hold data, not pictures: 297 normal maps and 286 masks with an empty blue channel, against
     632 color textures. Real-ESRGAN shifted their values by up to 10 levels out of 255, which
     would change shading.
   - Real-ESRGAN (`realesrgan-x4plus`) sharpens woven and printed detail well, but it smooths
     noise-like detail such as grass blades into flat color and darkens some textures. So only
     its brightness detail is used, moved to the texture's own brightness mean and spread, and
     color comes from Lanczos. Matching each color channel instead turned gray atlases lavender.
     A result that keeps less than 75% of the edge detail (`--min-detail`) falls back to
     Lanczos, and so does one that sharpens unevenly: on blurry noise it sharpened some patches
     and invented lichen in others. `--max-uneven` (0.25) caps the spread of its detail gain
     over an 8x8 grid; good results scored under 0.1.
   - Real-ESRGAN runs in 528-pixel tiles (`--tile`), which hold a whole padded 512 texture. Its
     default tiles on an RTX 4090 are about 200 pixels, and each tile was sharpened
     differently. Tiles above about 540 pixels crashed the driver.
   - Real-ESRGAN results are cached in `PACK_DIR-esrgan`, so a rerun with other settings skips
     the GPU work.
   - `--limit N` stops after N textures; the next run skips the ones already in the pack.
   - Outputs are capped at 4096 px per side (`--max-side`). Textures under 128 px (`--min`)
     and screen-sized frame captures are skipped.
   - `--format dds` writes block-compressed DDS files with full mip chains: BC1 for opaque
     textures, BC3 for ones with alpha, BC7 where the game used BC7. A PNG pack is uploaded as
     uncompressed RGBA8, so the 2x PNG pack already used 9.9 GB of video memory. BC1 takes an
     eighth of that per pixel. The 4K pack is `--scale 4 --format dds`; it needs the `etcpak`
     Python module, and `--jobs N` encodes N textures at a time.
   - Real-ESRGAN gets each texture padded by 8 pixels: wrapped around when its opposite edges
     match (a tiling texture), mirrored otherwise, so a tiling texture gets no seam where it
     repeats.
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
- A DDS replacement is uploaded as it is, in BC1, BC3 or BC7, and wins over a PNG with the
  same key. A PNG becomes an RGBA8 image.
- The replacement is sampled in place of the original view, with the original
  view's swizzle and sRGB setting. A texture the GPU later renders into goes back to the
  original.

## Measured (2026-11-19, RTX 4090, free roam)

- Dump on: 59.2-59.8 FPS while writing 1,273 textures.
- 2x pack (1,148 PNGs, 2.0 GB on disk): free roam at 58.8-59.4 FPS with GPU idle about 69%,
  the same as without a pack. Over 1,024 textures replaced, using 9.9 GB of video memory;
  the process commit peaked at 17.9 GB. A tinted test pack confirmed the swap in game.
- The scene between the title and free roam stalls for up to 7 s on a cold shader cache, with
  or without a pack.

## Measured (2026-11-19, RTX 4090, 4K pack)

- `--scale 4 --format dds`: 1,215 textures, 4.4 GB on disk, built in about 14 minutes in two runs
  (Real-ESRGAN kept for 431 color textures, Lanczos for 201). 256 becomes 1024, 512 becomes
  2048, 1024 and 2048 become 4096.
- In game: over 1,024 textures replaced using 3.9 GB of video memory, against 9.9 GB for the
  uncompressed 2x PNG pack. The island and Eagle City load and render normally.
- At 1080p from the normal camera the GPU samples smaller mip levels, so the gain is small:
  paving and pebbles look a little cleaner. The extra detail shows up close.

## Limits

- Video memory: every replacement is uncompressed RGBA8, 8x the size of a BC1 original (4x a
  BC3 or BC7 one) at the same resolution, and 2x scale multiplies that by 4. A full 2x pack
  needs about 12 GB.
- Shaders that read a texture's size or fetch exact texels see the larger image. None was
  seen in this game yet. If one breaks, delete that PNG from the pack.
- The hidden test launcher caps a run's job memory at 14 GB (`GHOST_MEM_GB`). Video memory
  counts toward that cap, so pack tests set `GHOST_MEM_GB=48`. Normal play has no such cap.
