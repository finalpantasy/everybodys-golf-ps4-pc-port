# libSceFont port notes (Everybody's Golf CUSA04687 1.17)

Files here: `runtime_font.c` (drop-in for `external/resogun-recomp/src/`), `import_names.txt` (22 lines for
`src/import_names.inc`). `runtime_font.c` passes `clang -std=c11 -Wall -Wextra -Werror -fsyntax-only` with
`-Iexternal/resogun-recomp/src` (syntax check only; not linked, not run).

## 1. The 5 unknown NIDs (SHA1 of name + suffix, first 8 bytes reversed, base64; matched against ps4libdoc-known_names.txt)

| NID | Name |
|---|---|
| cKYtVmeSTcw | sceFontOpenFontSet |
| IQtleGLL5pQ | sceFontGetRenderCharGlyphMetrics |
| TMtqoFQjjbA | sceFontSetEffectSlant |
| h6hIgxXEiEc | sceFontMemoryTerm |
| v0phZwa4R5o | sceFontSetEffectWeight |

All 17 DriveClub names re-hashed and matched (17 of 17 OK). Argument shapes below confirm each name.

## 2. Call sites (eboot image base 0; stub addresses 0x10fe950..0x10feaa0)

Startup, one function around 0xc1a6d..0xc1c40 (runs only when the byte at 0x2ccb9d8 is set; the game object is `r13`, global at 0x2ccb9b8):

1. `0xc1ab0` sceFontMemoryInit(mem=0x2ccba50, 0, 0, iface=0x133add8, 0, destroyCb=0xf19de0 (a bare `ret`), 0). Return ignored.
2. `0xc1abb` sceFontSelectLibraryFt(0) -> rax passed straight on, untested.
3. `0xc1ad0` sceFontCreateLibraryWithEdition(mem, sel, edition=0x0500807100000000, &lib=0x2ccba90). Return ignored. The lib global is re-read as the handle.
4. `0xc1adc` sceFontSupportSystemFonts(lib).
5. `0xc1af2` sceFontSupportExternalFonts(lib, 16, 0x52).
6. Loop `0xc1b10..0xc1be8`, 6 iterations (fonts at obj+0x40..+0x68, renderers at obj+0x70..+0x98, layouts at 0x2ccbaa0, 12 bytes each):
   - `0xc1b37` sceFontOpenFontSet(lib, type=[0x123f2f0+4i], mode=3, params=NULL, &font[i]). All six types are 0x1808a444 (read from the ELF). Return ignored.
   - `0xc1b4d` sceFontSetScalePixel(font, 36.0, 36.0) (constant at 0x115eeb0).
   - `0xc1b6b` sceFontSetEffectWeight(font, mode=0, w, w): w = 1.04, 1.04, 0.96, 1.04, 1.04, 0.96 (0x123f310).
   - `0xc1b83` sceFontSetEffectSlant(font, s): s = 0, 0, 0, 0.15, 0.15, 0.15 (0x123f330).
   - `0xc1b90` sceFontGetHorizontalLayout(font, &layout[i]) (3 floats; baselineOffset is read back later).
   - `0xc1b97` sceFontSelectRendererFt(0), `0xc1baf` sceFontCreateRendererWithEdition(mem, sel, edition, &renderer[i]).
   - `0xc1bc1` sceFontBindRenderer(font, renderer), `0xc1bd7` sceFontSetupRenderScalePixel(font, 36.0, 36.0).

Per glyph (glyph-cache loader around 0xf1a980..0xf1ad1e, plus atlas setup at 0xc2845..0xc286b):
7. `0xc286b` sceFontRenderSurfaceInit(&surface[i] (0x80 stride), buffer, widthByte=atlasW, pixelSize=1, width=atlasW, height=atlasH), six of them. 8-bit coverage atlases. Void.
8. `0xf1abb3` sceFontGetRenderCharGlyphMetrics(font, code (u16), &metrics 0x20 bytes). Tested: 0 -> continue; 0x80460042 (NO_SUPPORT_GLYPH) or anything else -> function returns false, no cache entry. After success the game copies width, height, bearingX, bearingY, advance (first 0x14 bytes) into the cache entry and uses them to size the cell.
9. `0xf1ad19` sceFontRenderCharGlyphImage(font, code, &surface[i], x, y, &metrics, &result). x = cellX - bearingX + 2.0, y = cellY + bearingY - layout[i].baselineOffset + 2.0 (2.0 is the constant at 0x1169fc8). Return value and `result` are not read: only the pixels written into the atlas matter.

Shutdown: `0xc1387..0xc1430` per font: sceFontUnbindRenderer(font), sceFontDestroyRenderer(&renderer), sceFontCloseFont(font) (stubs 0x10fea80, 0x10fea40, 0x10fea60); `0xc184e` sceFontDestroyLibrary(&lib); `0xc185a` sceFontMemoryTerm(mem).

All 22 stubs have at least one call site (the call-site scan covered 0x0..0x10fcbd0).

Why this differs from DriveClub: DriveClub feeds TrueType fonts from memory (sceFontOpenFontMemory). This game opens the firmware font sets only (OpenFontSet), and uses neither OpenFontMemory, GetCharGlyphMetrics, GetKerning, AttachDeviceCacheBuffer nor RenderCharGlyphImageHorizontal. Those are dropped.

## 3. DriveClub `runtime_font.c` versus shadPS4, where this game cares

| Function | DriveClub | shadPS4 (`src/core/libraries/font/font.cpp`) |
|---|---|---|
| OpenFontSet | prints "not provided", `*out=NULL`, returns FATAL. Nothing renders. | Implemented: decodes the set type (0x1808a444 -> tag 0xA4, style 0x44: SST-Roman.otf, SSTJpPro-Regular.otf, DFHEI5-SONY.ttf, SCEPS4Yoongd-Medium.otf), loads font files from the host, bundled Noto fallback, modes 1..3 only. Needs firmware font files. |
| Render metrics and image | stb_truetype, real 8-bit coverage, metrics only after a font handle exists. Same function for ...Image and ...ImageHorizontal. | Image: adds baseline offset to y. ...ImageHorizontal: does not. The game relies on the add (see item 9), so the shared DriveClub function would put glyphs one ascent too high. Fixed here. |
| Layout | baselineOffset = ascent*scale. Real result for this game's purpose. | baselineOffset from its layout blocks. |
| Mem/Library/Renderer | accept-and-ignore, calloc'd handles | Magic-checked blocks (0x0F00/0x0F01/0x0F07), allocate through the game's memory interface. |
| Error codes | HANDLE = 0x80460001 and FATAL = 0x80460009 | The table gives 0x80460005 for an invalid font handle, 0x80460009 is INVALID_STRING. Corrected here. |
| Host deps | `imstb_truetype.h` (resogun has it, same path), `runtime_font_fallback.inc` (CJK fallback via `runtime_file_translate`, pthread). | Host font files. |

This port: stb_truetype from `gpu/third_party/imgui/imstb_truetype.h` (present in resogun-recomp), no fallback include.

## 4. What the first version renders

Text will render if a host face loads, with these limits. Every system font set maps to one host face: `GOLF_FONT_FILE`, else `C:/Windows/Fonts/segoeui.ttf` or `arial.ttf` (Linux: DejaVuSans). Glyph shapes and widths differ from the PS4 SST font. Weight (1.04/0.96) and italic slant (0.15) are stored and not applied, so the three "italic" sets look upright. CJK and other codes the face lacks return NO_SUPPORT_GLYPH and are skipped (the game tolerates this, per item 8): Japanese text will be missing unless `GOLF_FONT_FILE` points to a CJK face. If no face loads at all, OpenFontSet returns FONT_OPEN_FAILED and every glyph call afterwards fails with INVALID_FONT_HANDLE: the atlas stays blank. Nothing has been run, so "renders" is untested; coverage is stored into the atlas exactly where the game's cell math expects.

## 5. Integration steps (lead)

1. Copy `analysis/font-port/runtime_font.c` to `external/resogun-recomp/src/runtime_font.c`. The gpu CMake globs `../src/runtime*.c` (gpu/CMakeLists.txt line 177), reconfigure to pick it up.
2. Append the 22 lines of `import_names.txt` to `src/import_names.inc` (no libSceFont entries exist there yet).
3. `src/runtime.h`, next to `runtime_rtc_resolve`: `uintptr_t runtime_font_resolve(const char *name);`
4. `src/runtime.c`, in `runtime_resolve` before `return resogun_gpu_resolve(name);`: `uintptr_t font = runtime_font_resolve(name); if (font) return font;`
5. Boot with `python run.py --timeout 20` and read the next `STOP:`. Optional: set `GOLF_FONT_FILE`.

Helpers the file calls: `runtime_low_alloc`, `runtime_low_free` (runtime.h lines 159-160, runtime_memory.c), `RUNTIME_LOOKUP`, `RuntimeExport`, `ABI`. All exist; none missing. The earlier DriveClub dependencies `runtime_file_translate`, `bb_scale` and `bb_glyph_choose` are not used.

## 6. Inferred (no direct evidence in the call sites)

- The u16 at offset 0 of mem/library/renderer is the tag (0x0F00/0x0F01/0x0F07, from shadPS4); the game never reads them.
- sceFontSetEffectSlant takes one float; sceFontSetEffectWeight is (font, mode, x, y). From the register loads (rsi=0, xmm0, xmm1; xmm0 only).
- baselineOffset equals the ascent in pixels at 36 px, and the Image variant adds the ascent at the render scale. Consistent with the game's y math, but the PS4 value could be a different font metric. If glyphs sit too high or low, adjust here.
- Set scale values are pixels per em (stb `ScaleForMappingEmToPixels`), as DriveClub does.
- UnbindRenderer returning NOT_BOUND_RENDERER when unbound: from the error table; the game always binds first.
- Whether `0x80460042` at 0xf1abbc leads to a different path than other errors: both return false at the end of the function (asserts are spin loops guarded by a flag at 0x2ccb9d8).
- The game's glyph cache feeds a quad renderer; correct on-screen placement of glyphs was not checked.
