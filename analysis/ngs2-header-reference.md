# libSceNgs2 struct and constant reference

Sources fetched 2026-11-18 from shadps4-emu/shadPS4 `main`, `src/core/libraries/ngs2/`: ngs2.h, ngs2_sampler.h, ngs2_submixer.h, ngs2_mastering.h, ngs2_pan.h, ngs2_geom.h, ngs2_custom.h (only grepped), ngs2_eq.h, ngs2_reverb.h, ngs2_impl.h, ngs2_error.h, ngs2_report.h, plus ngs2.cpp, ngs2_impl.cpp, ngs2_sampler.cpp. Also FFmpeg `libavcodec/atrac9dec.c` and `atrac9tab.h`, vgmstream `src/meta/sndx.c`.

Offsets below are computed by hand with x86-64 rules (u16/s16 2, u32/float 4, pointer/size_t/uintptr_t/u64 8, struct align = max member). Sizes marked "(SDK-observed)" match a size the game passes in `sceNgs2VoiceControl`, taken from `analysis/ngs2-contracts.md` (disassembly of the game, not shadPS4).

## 0. Main finding: shadPS4 has NO numeric ids for voice params, events, waveform types or state bits

The shadPS4 headers define struct layouts only. They contain none of: voice param id constants, voice event ids, waveform type constants (PCM/VAG/ATRAC9), voice state flag bits (except `StateFlagInUse = 1` in ngs2_impl.cpp), envelope curve constants, filter type constants. `sceNgs2VoiceControl` is a stub in shadPS4 (logs, returns 0). A web search for the public Sony names found nothing. Do not invent them; the only ids available are the ones observed in the game (section 1.2), marked as observed, and the 4 render waveform types (section 3.3).

## 1. Voice param header and ids

```
OrbisNgs2VoiceParamHeader   size 8, align 4
  +0  u16 size        total byte size of this param struct (including header)
  +2  s16 next        byte offset from this header to the next param in the list, 0 = last
  +4  u32 id
```

### 1.1 Id composition (observed, not from a header)

Observed ids in the game: common params have small ids (2, 5, 6), rack-specific params carry the rack family in the top byte: `0x1000xxxx` sampler, `0x2000xxxx` submixer, `0x3000xxxx` mastering, `0x4000xxxx` custom racks. So id = (rack family << 24 or rack id base) + index, with index 0 = setup param. (Pattern inferred from 3 families; (not verified) against any header.)

Rack ids (ngs2_impl.cpp, `RackId`): Sampler 0x1000, Submixer 0x2000, Reverb 0x2001, Mastering 0x3000, CustomSampler 0x4001, CustomSubmixer 0x4002, CustomMastering 0x4003.
Rack type (`RackType`): Sampler 0, Effect 1, Mastering 2.

### 1.2 Ids seen in the game (SDK-observed; struct name is inferred from size and header order)

| id | size | meaning |
|---|---|---|
| 0x10000000 | 0x28 | sampler setup (size matches OrbisNgs2SamplerVoiceSetupParam) |
| 0x10000001 | 0x20 | sampler waveform blocks (size matches; game code at 0x109b70e treats it as {data*, flags, numBlocks, aBlock*}) |
| 0x10000005 | 0x10 | sampler pitch (size matches; game writes a float ratio) |
| 0x10000006 | 0x18 | sampler, size matches WaveformAddressParam or Envelope (not verified which) |
| 0x10000008 | 0x28 | sampler, size matches Distortion or UserFx (not verified) |
| 0x1000000a | 0x30 | sampler, size matches FilterParam (not verified) |
| 0x20000000 | 0x10 | submixer setup {numIoChannels, flags} |
| 0x20000004 | 0x28 | submixer, size matches Compressor or Distortion (not verified) |
| 0x30000000 | 0x10 | mastering setup {numInputChannels, flags} |
| 0x30000005 | 0x10 | mastering, {u32 index, u32 0}, size matches OutputParam {outputId} or Gain (not verified) |
| 5 | 0x18 | common patch {port, destInputId, destHandle} |
| 6 | 0xc | common event {eventId}; eventId 0 used at voice setup, 1 used elsewhere |
| 2 | 0x10 | common, unknown |
| 0x40020000, 0x40001f00 | 0x18 | custom rack module params |

No other numeric ids are known. The remaining names (matrix levels, port volume, port matrix, port delay, callback, exit loop, frame offset, peak meter, num filters, limiter, LFE, matrix, output) have NO known numeric id (not verified).

### 1.3 Common param structs (ngs2.h)

| struct | fields (offset) | size |
|---|---|---|
| OrbisNgs2VoiceMatrixLevelsParam | header 0, u32 matrixId 8, u32 numLevels 12, const float* aLevel 16 | 24 |
| OrbisNgs2VoicePortMatrixParam | header 0, u32 port 8, s32 matrixId 12 | 16 |
| OrbisNgs2VoicePortVolumeParam | header 0, u32 port 8, float level 12 | 16 |
| OrbisNgs2VoicePortDelayParam | header 0, u32 port 8, u32 numSamples 12 | 16 |
| OrbisNgs2VoicePatchParam | header 0, u32 port 8, u32 destInputId 12, Handle destHandle 16 | 24 |
| OrbisNgs2VoiceEventParam | header 0, u32 eventId 8 | 12 (align 4) |
| OrbisNgs2VoiceCallbackParam | header 0, handler ptr 8, uintptr_t callbackData 16, u32 flags 24, u32 reserved 28 | 32 |
| OrbisNgs2VoiceCallbackInfo | uintptr_t callbackData 0, Handle voiceHandle 8, u32 flag 16, u32 reserved 20, union param 24 | 56 |

`OrbisNgs2VoiceCallbackInfo.param.waveformBlock` (at 24): uintptr_t userData 24, const void* data 32, u32 dataSize 40, u32 repeatedCount 44, u32 attributeFlags 48, u32 reserved2 52.
Callback handler: `void PS4_SYSV_ABI (*)(const OrbisNgs2VoiceCallbackInfo*)`.

Query structs: `OrbisNgs2VoicePortInfo` {s32 matrixId 0, float volume 4, u32 numDelaySamples 8, u32 destInputId 12, Handle destHandle 16} = 24. `OrbisNgs2VoiceMatrixInfo` {u32 numLevels 0, float aLevel[64] 4} = 260.

### 1.4 Sampler param structs (ngs2_sampler.h)

| struct | fields (offset) | size |
|---|---|---|
| SamplerVoiceSetupParam | header 0, WaveformFormat format 8 (24 B), u32 flags 32, u32 reserved 36 | 40 |
| SamplerVoiceWaveformBlocksParam | header 0, const void* data 8, u32 flags 16, u32 numBlocks 20, const WaveformBlock* aBlock 24 | 32 |
| SamplerVoiceWaveformAddressParam | header 0, const void* from 8, const void* to 16 | 24 |
| SamplerVoiceWaveformFrameOffsetParam | header 0, u32 frameOffset 8, u32 reserved 12 | 16 |
| SamplerVoiceExitLoopParam | header 0 only | 8 |
| SamplerVoicePitchParam | header 0, float ratio 8, u32 reserved 12 | 16 |
| SamplerVoiceEnvelopeParam | header 0, u32 numForwardPoints 8, u32 numReleasePoints 12, const EnvelopePoint* aPoint 16 | 24 |
| SamplerVoiceDistortionParam | header 0, u32 flags 8, float a 12, b 16, clip 20, gate 24, wetLevel 28, dryLevel 32, u32 reserved 36 | 40 |
| SamplerVoiceUserFxParam | header 0, handler ptr 8, userData0 16, userData1 24, userData2 32 | 40 |
| SamplerVoicePeakMeterParam | header 0, u32 enableFlag 8, u32 reserved 12 | 16 |
| SamplerVoiceFilterParam | header 0, u32 index 8, u32 location 12, u32 type 16, u32 channelMask 20, union param 24 (20 B), u32 reserved3 44 | 48 |
| SamplerVoiceNumFilters | header 0, u32 numFilters 8, u32 reserved 12 | 16 |

Filter union (20 bytes, at 24): `direct` {float i0, i1, i2, o1, o2} (biquad coefficients) or `fcq` {float fc, q, level, u32 reserved, reserved2}. Filter type and location constants are not in the headers (not verified).
Sampler has no compressor, LFE filter or gain param in the shadPS4 header. Upstream names such as "LFE filter" do not appear (not verified).

Envelope (OrbisNgs2EnvelopePoint, 12 bytes): u32 curve 0, u32 duration 4, float height 8. `aPoint` holds numForwardPoints points followed by numReleasePoints points (order is an assumption from field order, not stated in the header). Rack limit: `maxEnvelopePoints` in the rack option. `curve` constants not in the header (not verified).

### 1.5 Submixer param structs (ngs2_submixer.h)

| struct | fields (offset) | size |
|---|---|---|
| SubmixerVoiceSetupParam | header 0, u32 numIoChannels 8, u32 flags 12 | 16 |
| SubmixerVoiceEnvelopeParam | header 0, u32 numForwardPoints 8, u32 numReleasePoints 12, const EnvelopePoint* aPoint 16 | 24 |
| SubmixerVoiceCompressorParam | header 0, u32 flags 8, float threshold 12, ratio 16, knee 20, attackTime 24, releaseTime 28, level 32, u32 reserved 36 | 40 |
| SubmixerVoiceDistortionParam | same layout as sampler distortion | 40 |
| SubmixerVoiceUserFxParam | same layout as sampler user fx | 40 |
| SubmixerVoicePeakMeterParam | header 0, u32 enableFlag 8, u32 reserved 12 | 16 |
| SubmixerVoiceFilterParam | same layout as sampler filter | 48 |
| SubmixerVoiceNumFilters | header 0, u32 numFilters 8, u32 reserved 12 | 16 |

### 1.6 Mastering param structs (ngs2_mastering.h)

| struct | fields (offset) | size |
|---|---|---|
| MasteringVoiceSetupParam | header 0, u32 numInputChannels 8, u32 flags 12 | 16 |
| MasteringVoiceMatrixParam | header 0, u32 type 8, u32 numLevels 12, const float* aLevel 16 | 24 |
| MasteringVoiceLfeParam | header 0, u32 enableFlag 8, u32 fc 12 | 16 |
| MasteringVoiceLimiterParam | header 0, u32 enableFlag 8, float threshold 12 | 16 |
| MasteringVoiceGainParam | header 0, float fbwLevel 8, float lfeLevel 12 | 16 |
| MasteringVoiceOutputParam | header 0, u32 outputId 8, u32 reserved 12 | 16 |
| MasteringVoicePeakMeterParam | header 0, u32 enableFlag 8, u32 reserved 12 | 16 |

### 1.7 Reverb (ngs2_reverb.h) for completeness

ReverbVoiceSetupParam: header 0, numInputChannels 8, numOutputChannels 12, flags 16, reserved 20 = 24. ReverbVoiceI3DL2Param: header 0, I3DL2Param 8 = 96. I3DL2Param (88 B): float wet 0, float dry 4, s32 room 8, s32 roomHF 12, u32 reflectionPattern 16, float decayTime 20, float decayHFRatio 24, s32 reflections 28, float reflectionsDelay 32, s32 reverb 36, float reverbDelay 40, float diffusion 44, float density 48, float HFReference 52, u32 reserve[8] 56.

### 1.8 Rack options (sizes match what the game passes to RackCreate)

OrbisNgs2RackOption (128 B): size_t size 0, char name[16] 8, u32 flags 24, maxGrainSamples 28, maxVoices 32, maxInputDelayBlocks 36, maxMatrices 40, maxPorts 44, aReserved[20] 48.
Sampler rack option = base 128 + u32 maxChannelWorks, maxCodecCaches, maxWaveformBlocks, maxEnvelopePoints, maxFilters, maxAtrac9Decoders, maxAtrac9ChannelWorks, maxAjmAtrac9Decoders, numPeakMeterBlocks at 128..160 = 168 (0xa8) with padding.
Submixer = base + maxChannels, maxEnvelopePoints, maxFilters, maxInputs, numPeakMeterBlocks = 152 (0x98). Mastering = base + maxChannels, numPeakMeterBlocks = 136 (0x88). Reverb = base + maxChannels, reverbSize = 136 (game passes 0x98).
Limits in shadPS4 impl: MinGrainSamples 64, MaxGrainSamples 1024, `FirmwareRackOptionFlags = 0xc0000000`.

## 2. Max-channel constants (ngs2.h)

- `ORBIS_NGS2_MAX_VOICE_CHANNELS = 8`
- `ORBIS_NGS2_MAX_MATRIX_LEVELS = 8 * 8 = 64`
- `ORBIS_NGS2_WAVEFORM_INFO_MAX_BLOCKS = 4`
- `ORBIS_NGS2_SYSTEM_NAME_LENGTH = 16`, `ORBIS_NGS2_RACK_NAME_LENGTH = 16`

Matrix levels param: `aLevel` is a pointer to numLevels floats (max 64); `matrixId` selects the matrix slot. Layout of the 8x8 matrix (row = input, column = output or the reverse) is not stated in the header (not verified). Port matrix: `matrixId` is signed s32 (-1 probably means none; not verified). Port volume: single float `level` per port. Port delay: `numSamples` per port. Patch: connects `port` of this voice to `destInputId` of `destHandle` (game passes a rack handle for a pre-master to master patch).

## 3. Waveform structs

### 3.1 OrbisNgs2WaveformFormat (24 B)
u32 waveformType 0, u32 numChannels 4, u32 sampleRate 8, u32 configData 12, u32 frameOffset 16, u32 frameMargin 20.

### 3.2 OrbisNgs2WaveformBlock (32 B)
u32 dataOffset 0, u32 dataSize 4, u32 numRepeats 8, u32 numSkipSamples 12, u32 numSamples 16, u32 reserved 20, uintptr_t userData 24.

### 3.3 OrbisNgs2WaveformInfo (200 B)
format 0 (24), u32 dataOffset 24, dataSize 28, loopBeginPosition 32, loopEndPosition 36, numSamples 40, audioUnitSize 44, numAudioUnitSamples 48, numAudioUnitPerFrame 52, audioFrameSize 56, numAudioFrameSamples 60, numDelaySamples 64, numBlocks 68, aBlock[4] 72 (4 x 32 = 128).

### 3.4 Waveform type constants
The headers define NO waveform type constants for PCM/VAG/ATRAC9. The only values in shadPS4 are the render-buffer types accepted by `sceNgs2SystemRender` (ngs2_impl.cpp `RenderWaveformType`):

| value | name |
|---|---|
| 0x12 | PcmI16LittleEndian |
| 0x13 | PcmI16BigEndian |
| 0x18 | PcmF32LittleEndian |
| 0x19 | PcmF32BigEndian |

Render channels accepted: 1, 2, 6, 8. Values for VAG, ATRAC9, other PCM (u8, etc.): not in any fetched file (not verified). Note render type 0x12 and 0x18 suggest that sampler input PCM types share the same numbering (inference only).

Related structs: OrbisNgs2RenderBufferInfo {void* buffer 0, size_t bufferSize 8, u32 waveformType 16, u32 numChannels 20} = 24.

## 4. Voice events and state flags

Event ids (play, stop, kill, pause, resume, ...): NOT in any fetched file (not verified). Game-observed: eventId 0 at voice setup, 1 elsewhere, via common param id 6.

State flag bits (in use, playing, paused, stopped, error, empty): NOT in the headers. Only `StateFlagInUse = 1` (ngs2_impl.cpp, used for system/rack stateFlags). From game disassembly (inferred, not authoritative): the game tests `stateFlags & 0x22 == 2`, and treats "bit 0 clear" as a voice that has ended.

## 5. Voice state structs

| struct | fields (offset) | size |
|---|---|---|
| OrbisNgs2VoiceState | u32 stateFlags 0 | 4 |
| SamplerVoiceState | VoiceState 0, float envelopeHeight 4, float peakHeight 8, u32 reserved 12, u64 numDecodedSamples 16, u64 decodedDataSize 24, u64 userData 32, const void* waveformData 40 | 48 |
| SubmixerVoiceState | VoiceState 0, float envelopeHeight 4, float peakHeight 8, float compressorHeight 12 | 16 |
| MasteringVoiceState | VoiceState 0, float limiterPeakLevel 4, float limiterPressLevel 8, float aInputPeakHeight[8] 12, float aOutputPeakHeight[8] 44 | 76 |
| ReverbVoiceState | VoiceState 0 | 4 |

`sceNgs2VoiceGetState(voice, out, stateSize)`: the game passes 0x30 (sampler) and 0x10 (submixer), matching the sizes above.
Handle types (`OrbisNgs2HandleType`): Invalid 0, System 1, Rack 2, Voice 4, VoiceControl 6.

## 6. Other structs (for reference)

OrbisNgs2SystemOption (0x40 B): size_t size 0, char name[16] 8, u32 flags 24, maxGrainSamples 28, numGrainSamples 32, sampleRate 36, aReserved[6] 40. ContextBufferInfo (64 B): void* hostBuffer 0, size_t hostBufferSize 8, uintptr_t reserved[5] 16, uintptr_t userData 56. BufferAllocator (24 B): allocHandler 0, freeHandler 8, userData 16.
Pan: OrbisNgs2PanParam {float angle, distance, fbwLevel, lfeLevel} = 16. Eq/geom/custom structs exist but are not needed for sampler/submixer/mastering racks.

## 7. ATRAC9 configData in shadPS4

shadPS4 has no notes on ATRAC9 `configData`. The field is only the u32 at +12 of OrbisNgs2WaveformFormat; the sampler rack option has `maxAtrac9Decoders`, `maxAtrac9ChannelWorks`, `maxAjmAtrac9Decoders` (ngs2_impl.cpp validates maxAtrac9ChannelWorks in [maxAtrac9Decoders, 8*maxAtrac9Decoders] and maxAjmAtrac9Decoders <= min(32, maxVoices)). Nothing in shadPS4 decodes ATRAC9. Meaning of configData: per vgmstream (below) the same u32 is the SCE ATRAC9 config word, read little-endian, first byte 0xFE.

## 8. ATRAC9 with FFmpeg

libavcodec/atrac9dec.c, `atrac9_decode_init`:

```c
if (avctx->block_align <= 0) -> error "Invalid block align"
if (avctx->extradata_size != 12) -> error "Invalid extradata length!"
version = AV_RL32(avctx->extradata);            // must be <= 2
init_get_bits8(&gb, avctx->extradata + 4, avctx->extradata_size);
if (get_bits(&gb, 8) != 0xFE) -> error "Incorrect magic byte!"
s->samplerate_idx = get_bits(&gb, 4);           // avctx->sample_rate = at9_tab_samplerates[idx]
block_config_idx = get_bits(&gb, 3);            // 0..5, else error
if (get_bits1(&gb)) -> error "Incorrect verification bit!"
s->avg_frame_size = get_bits(&gb, 11) + 1;      // bytes per frame
superframe_idx = get_bits(&gb, 2);              // must be even
s->frame_count = 1 << superframe_idx;
s->frame_log2 = at9_tab_sri_frame_log2[s->samplerate_idx];
```

Layout of the 12-byte extradata:
- bytes 0..3: u32 LE version (0, 1 or 2).
- bytes 4..7: the 4-byte ATRAC9 config word (the sxd/NGS2 `configData`, byte 4 = 0xFE). Bits MSB first: magic 8, sample rate index 4, block config 3, verification bit 1 (must be 0), frame size minus 1: 11, superframe index 2, remaining 3 bits unused by this decoder.
- bytes 8..11: not read by the decoder (extradata_size only has to be 12); zero them.
- `avctx->block_align` must be > 0; it is only used as the return value for a full packet. Set it to `(frameSizeField + 1) << superframeIdx` = avg_frame_size * frame_count (one superframe packet).

Block config: 0 mono (1 ch), 1 dual mono (2), 2 stereo (2), 3 5.1 (6), 4 7.1 (8), 5 quad (4). Channel count comes from the config, not from the container.
Sample rate table (index 0..15): 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000, 44100, 48000, 64000, 88200, 96000, 128000, 176400, 192000.
`at9_tab_sri_frame_log2` by index: 6 6 7 7 7 8 8 8 6 6 7 7 7 8 8 8.
Samples per frame per channel = `1 << frame_log2` (64, 128 or 256; 256 for idx 5..7, e.g. 48 kHz). Decode (`atrac9_decode_frame`): `frames = min(pkt_size / avg_frame_size, frame_count)`, `nb_samples = (1 << frame_log2) * frames`; a full packet = `frame_count` frames = `frame_count << frame_log2` samples (1024 at 48 kHz with superframe index 2). Output format is planar float (FLTP).
Feed packets of `avg_frame_size * frame_count` bytes starting at the stream data offset.

### vgmstream SXD (SNDX) layout

There is no `src/meta/sxd.c` (404). The `.sxd` format is `src/meta/sndx.c` (SXDF/SXDS "SNDX", Sony SCE lib, cousin of SGXD). Fetched and read. In the WAVE chunk (found by `find_chunk_le` from 0x60 in the SXDF header file):
- WAVE+0x04: s32 total subsongs; then at +0x08 a table of s32 relative offsets (4 B each, relative to the entry's own table slot) to each stream header.
- Stream header (header_offset): +0x00 u32 flags (bit0 = has TLV extra data/tags, bit1 = data is external in the SXDS/.sxd2 file); +0x04 u8 codec; +0x05 u8 channels; +0x08 s32 sample rate; +0x14 s32 num_samples; +0x18 s32 loop start (-1 = none); +0x1c s32 loop end (-1 = none); +0x20 u32 stream size; +0x24 u32 stream offset (absolute in the data file if external, else relative to header_offset + 0x24).
- Codec ids: 0x20 PS-ADPCM, 0x21 HEVAG, 0x42 ATRAC9. (0x28 appears as a dummy codec with 0 samples.)
- ATRAC9 config: the TLV area starts at header_offset + 0x28 (needs flags bit0). vgmstream scans in 4-byte steps for the big-endian tag 0x0A010000 or 0x0A010600, then reads the config as `read_u32le(tag_offset + 4)` ("yes, LE"). That u32 is the same word as the NGS2 `configData`. Channels come from the header byte; samples counts from the header.
- Some PS4 files are `.sxd3` (sxd1 + sxd2 concatenated).
