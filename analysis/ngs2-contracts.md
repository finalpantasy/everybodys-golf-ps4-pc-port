# libSceNgs2 contracts for Everybody's Golf (CUSA04687 1.17)

Scope: the 11 libSceNgs2 imports the eboot uses, their guest call sites, the public contract, and the smallest faithful implementation. Analysis only; nothing under `external/` was touched.

Evidence key:
- `0xADDR` = guest address in `work/game-1.17-prepared/eboot.elf` (image base 0), disassembled with llvm-objdump. Constant tables were read straight from the ELF program headers.
- `shadPS4 file:line` = upstream `src/core/libraries/ngs2/` on `main`, fetched 2026-11-17 from raw.githubusercontent.com (no shadPS4 source is bundled in `tools/shadps4-*`, only `shadPS4.exe`). Line numbers refer to that fetch and may drift.
- "(inferred)" marks anything not read directly from code or a header.

## 1. NID resolution (all 11 matched, none left over)

Method: SHA1(name + 518D64A635DED8C1E6B039B1C3E55230), first 8 bytes reversed, base64, `/` to `-`, no padding, over every `sceNgs2*` line of `analysis/reference/ps4libdoc-known_names.txt`.

| NID | Name | PLT stub | Call sites |
|---|---|---|---|
| cLV4aiT9JpA | sceNgs2RackCreate | 0x10ff630 | 15 |
| U546k6orxQo | sceNgs2RackCreateWithAllocator | 0x10ff640 | 5 |
| lCqD7oycmIM | sceNgs2RackDestroy | 0x10ff650 | 11 |
| MwmHz8pAdAo | sceNgs2RackGetVoiceHandle | 0x10ff660 | 107 |
| 0eFLVCfWVds | sceNgs2RackQueryBufferSize | 0x10ff670 | 15 |
| mPYgU4oYpuY | sceNgs2SystemCreateWithAllocator | 0x10ff680 | 1 |
| u-WrYDaJA3k | sceNgs2SystemDestroy | 0x10ff690 | 2 |
| i0VnXM-C9fc | sceNgs2SystemRender | 0x10ff6a0 | 1 |
| uu94irFOGpA | sceNgs2VoiceControl | 0x10ff6b0 | 126 |
| -TOuuAQ-buE | sceNgs2VoiceGetState | 0x10ff6c0 | 2 |
| rEh728kXk3w | sceNgs2VoiceGetStateFlags | 0x10ff6d0 | 0 (imported, never called) |

Stub addresses: `analysis/plt-import-map.json:4074-4134`. Call counts: every `callq 0x10ff6X0` in 0x1000000-0x10fcbd0.

## 2. Boot path

The first stop (return offset 0x10967a6) is inside the audio-system init function starting at `0x1095870` (prologue 0x1095870-0x1095881). Args: `rdi` = r13 (game memory arena context), `rsi` = r15 (config object).

### 2.1 Config read (0x1095993-0x1095be2, helper 0x10b0a10(config, key, default, &out))

| Local | Key | Default / clamp |
|---|---|---|
| 0x54(rsp) | loadAudio3d | 0 |
| 0x58 | noLoadNgs2 | 0. If 0, init calls `0x10fd2f0(0xb)` (0x1095b68-0x1095b70; inferred sceSysmoduleLoadModule(SCE_SYSMODULE_NGS2 = 0xb)). `0xa7` at 0x1095945 is Audio3d (inferred). |
| 0x50 | enableAmbisonicsPan | 0 |
| 0x7c | numGrains | 0x100, rounded up to a multiple of 0x100, range 0x100..0x400 (0x10959ae-0x10959e3) |
| 0x78 | enableACP | 0 |
| 0x6c | numDecoderMemoryBlocks | 0, max 0x10 |
| 0x74 | maxAtrac9Decoders | 0x100, values >= 0x400 become 0x400 |
| 0x70 | maxVoiceChannels | 0x100, range 1..0x400 |
| 0x4c | maxSubmixers | 0, max 0x400 |
| 0x68 | numControllerSpeakers / maxControllerSpeakers | 0, must be < 5 (0x1095ac7) |
| 0x64 | numHeadsetSpeakers / maxHeadsetSpeakers | 0, must be < 5 (0x1095b22) |
| 0x60 | enableRestricted | 1 |
| 0x5c | enableAUX | 0 |

Master rack maxVoices (0x1095bf0-0x1095c0a, inferred arithmetic) = controllerSpeakers + headsetSpeakers + 1 + (enableRestricted != 0) + (enableAUX != 0). Default = 2.

### 2.2 Call order with default config

1. `0x10967a1` **SystemCreateWithAllocator**(rdi=&option@rsp+0x220, rsi=&allocator@0x13655e8, rdx=&outHandle@rsp+0xa8). Result: `movl %eax,%r13d; testl; js 0x109723e` (0x10967a6-0x10967af). Out handle read back as first arg of every later call (0x10967d8).
2. `0x109688f` **RackCreateWithAllocator** "Master", rack id 0x3000 (`movl $0x3000,%esi` at 0x10967f7), out rsp+0xa0. Tested `js 0x109723e`.
3. `0x1096950` RackCreateWithAllocator "Pre Master", id 0x2000, out rsp+0x98. Tested.
4. `0x1096a32` RackCreateWithAllocator "Sampler", id 0x1000, out rsp+0x90. Tested.
5. `0x1096b3d` RackCreateWithAllocator "Dynamic SubMixer" (name truncated to 15 chars), id 0x2000, out rsp+0x88, only if maxSubmixers != 0 (0x1096a43-0x1096a49). Tested.
6. `0x1096c2c` RackCreateWithAllocator "Ambisonics Mast" (15 chars, string at 0x11b2160), id 0x2000, out global 0x2d54668, only if enableAmbisonicsPan != 0 and global 0x13655e0 != -1 (0x1096b4e-0x1096b6b); followed by sceAudio3dObjectReserve calls (0x10ff7a0). Failure here is tolerated (`js 0x1096e8c`).
7. `0x1096ea4` RackGetVoiceHandle(master rack, 0, &rsp+0x80). Not tested.
8. `0x1096eea` VoiceControl(master voice 0, {size 0x10, next 0, id 0x30000000, u32 8, u32 0}). Not tested.
9. `0x1096f1f` VoiceControl(master voice 0, {size 0xc, next 0, id 6, u32 0}).
10. `0x1096f31` RackGetVoiceHandle(Pre Master, 0); `0x1096f77` VoiceControl {size 0x10, id 0x20000000, u32 8, u32 0}; `0x1096fac` VoiceControl {size 0xc, id 6, u32 0}.
11. `0x1097006` VoiceControl(pre-master voice 0, {size 0x18, id 5, u32 port 0, u32 destInputId 0, u64 destHandle = the Master RACK handle from rsp+0xa0}). The game passes a rack handle here, not a voice handle (observed).
12. `0x1097034`-`0x10970e6` loop, voice index 1..controllerSpeakers: RackGetVoiceHandle(master, i); VoiceControl id 0x30000000; VoiceControl {size 0x10, id 0x30000005, u32 i, u32 0}; VoiceControl id 6.
13. `0x109712a`-`0x10971e5` same triple for headset voices; `0x1097434`-`0x10975d0` for the remaining master voices (sites 0x1097470, 0x10974b6, 0x10974eb, 0x1097519, 0x1097555, 0x109759b, 0x10975d0).
14. `0x1097934`, `0x1097a64`, `0x109862a`... more RackGetVoiceHandle/VoiceControl for sampler and sub-mixer voice setup (all 107 RackGetVoiceHandle addresses in 3.7).

Failure/shutdown path `0x1095d1a-0x1095d79`: RackDestroy(rack, esi=0, so outBufferInfo = NULL) for each non-null rack at rsp+0x88/0x90/0x98/0xa0, then SystemDestroy(system, NULL). Results ignored. Destroy must tolerate a NULL out pointer.

### 2.3 System option, struct SceNgs2SystemOption, 0x40 bytes (built at rsp+0x220 from constants at 0x124c2d8 / 0x124c2f8)

| Offset | Field | Value |
|---|---|---|
| +0x00 | size | 0x40 |
| +0x08 | name[16] | "NGS2" (0x3253474e at 0x1096780) |
| +0x18 | flags | 0 |
| +0x1c | maxGrainSamples | numGrains, default 0x100 (0x1096793) |
| +0x20 | numGrainSamples | numGrains (0x109679a) |
| +0x24 | sampleRate | 0xbb80 = 48000 |
| +0x28..0x3f | reserved[6] | 0 |

Matches `OrbisNgs2SystemOption` (shadPS4 ngs2.h:24-31).

### 2.4 Rack options (SceNgs2RackOption = 0x80 bytes, then a rack-specific tail)

Layout (shadPS4 ngs2.h, OrbisNgs2RackOption): `size_t size` +0, `char name[16]` +8, `u32 flags` +0x18, `maxGrainSamples` +0x1c, `maxVoices` +0x20, `maxInputDelayBlocks` +0x24, `maxMatrices` +0x28, `maxPorts` +0x2c, `aReserved[20]` +0x30..0x7f. Full struct sizes: Sampler 0xa8, Submixer 0x98, Mastering 0x88 (the three sizes the game writes, confirming the layout).

| Rack (id) | Site | size | maxGrain | maxVoices | maxInDelay | maxMatr | maxPorts | Tail from +0x80 |
|---|---|---|---|---|---|---|---|---|
| Master (0x3000) | 0x109688f | 0x88 | numGrains | 2 (2.1) | 1 | 0 | 0 | maxChannels 8, numPeakMeterBlocks 8 |
| Pre Master (0x2000) | 0x1096950 | 0x98 | numGrains | 1 | 1 | 1 | 8 | maxChannels 8, maxEnvelopePoints 4, maxFilters 8, maxInputs 1, numPeakMeterBlocks 8 |
| Sampler (0x1000) | 0x1096a32 | 0xa8 | numGrains | 0x100 | 0 | 1 | 8 | maxChannelWorks 0x100, maxCodecCaches 0x20, maxWaveformBlocks 0x10, maxEnvelopePoints 4, maxFilters 8, maxAtrac9Decoders 0x100, maxAtrac9ChannelWorks 0x100, maxAjmAtrac9Decoders 0, numPeakMeterBlocks 8 |
| Dynamic SubMixer (0x2000) | 0x1096b3d | 0x98 | numGrains | maxSubmixers | 1 | 1 | 8 | as Pre Master except maxPorts 8 at +0x2c, maxFilters 8, maxInputs 1 |
| Ambisonics Mast (0x2000) | 0x1096c2c | 0x98 | template | see 0x1096b71-0x1096c23 | | | | Audio3d-only, gated |

Evidence: templates at 0x124c318/0x124c338 (Master), 0x12501f0/0x1250210/0x1250230-0x1250268 (submixers), 0x124c3a0-0x124c440 (Sampler); patches at 0x1096881/0x1096888 (Master voices/grain), 0x10969ca-0x10969e2 (Sampler maxWaveformBlocks 0x10; if enableACP, maxCodecCaches and maxAjmAtrac9Decoders = maxAtrac9Decoders config), 0x1096ac8-0x1096ae9 (Dynamic SubMixer voices).

With default config these pass shadPS4's validators (ngs2_impl.cpp:204-380). Hazard: with enableACP != 0 the game sets maxAjmAtrac9Decoders up to 0x400, which shadPS4 rejects (it caps at min(32, maxVoices)).

### 2.5 Allocator, struct SceNgs2BufferAllocator { alloc, free, userData } at 0x13655e8 = { 0x1097b30, 0x1097b90, 0 }

- alloc `0x1097b30`: `rdi` = `SceNgs2ContextBufferInfo*`; reads `hostBufferSize` (+8); calls malloc (GOT 0x1367708 -> 0x10dfaf0 -> PLT 0x10fccf0 = `malloc`); stores the pointer at `hostBuffer` (+0); returns 0, or 0x804a020c if malloc returned NULL (0x1097b74). Ignores `userData`, leaves `reserved[]` untouched.
- free `0x1097b90`: if `*(void**)rdi != NULL`, free (0x1367710 -> 0x10dfb00 -> PLT 0x10fcc70 = `free`); returns 0.
- Both are guest functions; calling them from HLE needs a guest-call. v1 can skip them (section 5).

### 2.6 Other

- Global audio manager pointer 0x2d44490 holds the system handle at +0x60 (SystemRender at 0x10ace79-0x10ace8e) and rack handles at +0x68/+0x70/+0x78/+0x80 (0x10917eb-0x1091811, 0x10dff17, 0x10e00b3) (inferred from loads).
- A negative result from any of the 5 create calls on the boot path goes to `0x109723e` (log + unwind); it aborts audio init, not the process.

## 3. Per-function contract

Signatures follow shadPS4 (ngs2.cpp / ngs2.h) and agree with the call sites. `OrbisNgs2Handle` = u64.

### 3.1 sceNgs2SystemCreateWithAllocator(const SystemOption*, const BufferAllocator*, Handle* out) -> s32
- Game: 1 call, 0x10967a1 (2.2, 2.3, 2.5). Result tested `< 0`.
- Contract: validates option (size 0x40; grains multiple of 64 up to 1024; sample rate 11025..192000), runs allocHandler to get the system buffer, writes `*out`.
- shadPS4: real (ngs2_impl.cpp:579-615; option checks 178-202; calls the allocator handlers).

### 3.2 sceNgs2SystemDestroy(Handle, ContextBufferInfo* outBufferInfo) -> s32
- Game: 0x1095d79 (error path, out NULL), 0x1097c9c (shutdown, out NULL). Results ignored.
- shadPS4: real (ngs2_impl.cpp:617-645), runs freeHandler.

### 3.3 sceNgs2RackQueryBufferSize(u32 rackId, const RackOption*, ContextBufferInfo* out) -> s32 (15 sites 0x109e83f..0x109f83a)
- Game: effect-rack factory around 0x109e7a0 (switch table 0x11d4e4c, 15 cases). Rack ids at the sites: 0x2000 (ten), 0x2001 reverb (0x109ecd8), 0x4002 custom submixer (0x109efca, 0x109f102, 0x109f317, 0x109f83a). Args: `rsi` = option (rsp+0xfc0, size 0x98) or 0x4d8-byte custom option, `rdx` = &bufferInfo (rsp+0xee0). Result tested `testl; js 0x10a1ec2`.
- The game then reads `bufferInfo.hostBufferSize` (rsp+0xee8), carves that many bytes (rounded to 8) from its own arena, memsets them to 0 (0x10ff830), stores the pointer in `hostBuffer` (rsp+0xee0) and passes the struct to RackCreate (0x109e84c-0x109ea05). The game never reads the buffer back (inferred). The size must be nonzero and sane because the game's arena is consumed.
- shadPS4: real; byte sizes are its own invention, not Sony's (ngs2_impl.cpp:647-661; `RackBufferSize` 394).

### 3.4 sceNgs2RackCreate(Handle system, u32 rackId, const RackOption*, const ContextBufferInfo*, Handle* out) -> s32 (15 sites)
- Sites: 0x109eaaf, 0x109fc3f, 0x109fe1f, 0x10a038f, 0x10a052f, 0x10a06cf, 0x10a096f, 0x10a0af2, 0x10a0caf, 0x10a0e3f, 0x10a0fef, 0x10a118f, 0x10a150f, 0x10a175f, 0x10a1a3f.
- Args at 0x109ea92-0x109eaa7: `esi` = 0x2000, `rdx` = option rsp+0xfc0, `rcx` = &bufferInfo rsp+0xee0, `r8` = &out rsp+0xb0. Result `testl; js 0x10a1ec2`. The out handle is used at once for RackGetVoiceHandle(…,0) (0x109ead3) and VoiceControl.
- Custom submixer (id 0x4002) option: 0x4d8 bytes copied from the template at 0x1250288 (0x109ef4e-0x109ef5d), then numBuffers=1 (+0x84), numModules=1 (+0x88), aModule[0] at +0x90 {option = NULL or a user-FX struct at rsp+0x1060, moduleId 0x1c, sourceBufferId 0, destBufferId 0}, aPort[0].sourceBufferId = 0 (+0x450). `0x4d8 = 0x80 + 16 + 24*40 + 16*8 + 8` matches shadPS4 ngs2_custom.h:95-120 (MAX_MODULES 24, MAX_PORTS 16). moduleId 0x1c is probably a user-FX module (inferred).
- shadPS4: real for 0x1000/0x2000/0x2001/0x3000 (ngs2_impl.cpp:663-685). **Rack ids 0x4001-0x4003 return ORBIS_NGS2_ERROR_FAIL** (ngs2_impl.cpp:230-234), which would fail the four custom sites.

### 3.5 sceNgs2RackCreateWithAllocator(Handle, u32 rackId, const RackOption*, const BufferAllocator*, Handle* out) -> s32 (5 sites: 0x109688f, 0x1096950, 0x1096a32, 0x1096b3d, 0x1096c2c)
- See 2.2 and 2.4; every result is tested `< 0`.
- shadPS4: real (ngs2_impl.cpp:687-726).

### 3.6 sceNgs2RackDestroy(Handle, ContextBufferInfo* outBufferInfo) -> s32 (11 sites)
- Game: 0x1095d29, 0x1095d3d, 0x1095d51, 0x1095d65 (out NULL, ignored); 0x1091354 and 0x10913f4 (`testl; js`); 0x1097c2f and 0x1097c54 (shutdown routine at 0x1097bb0) and others. NULL out must be accepted.
- shadPS4: real (ngs2_impl.cpp:728-738).

### 3.7 sceNgs2RackGetVoiceHandle(Handle rack, u32 index, Handle* out) -> s32 (107 sites)
- Index: constant 0 at 67 sites (`xorl %esi,%esi`, singleton voices of Master / Pre Master / sub-mixer racks); u16 loaded from `0x8(record)` at about 38 sites (sampler slot ids); loop counters at 0x1097034 and 0x109712a. `rdx` is a stack slot read immediately as the first arg of VoiceControl or VoiceGetState. The result is mostly not tested (heuristic).
- Sites: 0x10917c5 0x1091803 0x1091811 0x1091924 0x1091fa8 0x1092345 0x1092356 0x10924c3 0x109269c 0x10926ad 0x1092824 0x109288c 0x109289d 0x109294f 0x1092963 0x1092a2d 0x1092a4b 0x1092ae2 0x1092aff 0x1092f28 0x1092f39 0x1092f86 0x1093077 0x1093088 0x10930f0 0x1093101 0x1093155 0x10932f4 0x1093320 0x1093517 0x109361e 0x1094300 0x1096c4a 0x1096ea4 0x1096f31 0x1097034 0x109712a 0x1097434 0x1097519 0x1097934 0x1097a64 0x109862a 0x109875a 0x109886a 0x109897a 0x1098a8a 0x1098b8a 0x1098e36 0x1099054 0x10994f1 0x1099e74 0x109a150 0x109a51f 0x109a802 0x109b0f0 0x109b324 0x109b493 0x109b62b 0x109b8a3 0x109bd8a 0x109be44 0x109c115 0x109c190 0x109d148 0x109d483 0x109d623 0x109ead3 0x109fc63 0x109fe3e 0x10a03b3 0x10a0553 0x10a06ee 0x10a098e 0x10a0b11 0x10a0cd3 0x10a0e5e 0x10a1013 0x10a11ae 0x10a152e 0x10a177e 0x10a1a5a 0x10a1bc2 0x10a1c0f 0x10a1c5c 0x10a1ca9 0x10a1cf6 0x10a1d43 0x10a1d90 0x10a1dda 0x10abd04 0x10abe06 0x10abe75 0x10abf56 0x10ac06b 0x10ac15c 0x10ac40a 0x10ac8e4 0x10aca47 0x10acbbd 0x10acc7d 0x10c3abd 0x10c3b21 0x10c3b4b 0x10c3f21 0x10c4336 0x10dff2c 0x10e00c3.
- Contract: stable handle per (rack, index); index >= maxVoices gives INVALID_VOICE_INDEX (0x804A0302).
- shadPS4: real (ngs2_impl.cpp:740-758).

### 3.8 sceNgs2VoiceControl(Handle voice, const VoiceParamHeader* list) -> s32 (126 sites)
- `SceNgs2VoiceParamHeader { u16 size; s16 next; u32 id; }` (shadPS4 ngs2.h). `next` = byte offset to the next param; every site read writes `next = 0` (one param per call).
- Resolved (size, id) pairs; names are inferred from struct sizes and shadPS4 header order:

| id | size | struct (inferred) | site |
|---|---|---|---|
| 0x10000000 | 0x28 | Sampler setup {WaveformFormat 24B, flags, reserved} | 0x10995f9 |
| 0x10000001 | 0x20 | Sampler waveform blocks {data*, flags, numBlocks, aBlock*} | 0x109b70e |
| 0x10000005 | 0x10 | Sampler pitch {float ratio, reserved} | 0x1099690 |
| 0x10000006 | 0x18 | Sampler | 0x109b378 |
| 0x10000008 | 0x28 | Sampler | 0x109b5aa |
| 0x1000000a | 0x30 | Sampler | 0x109915f |
| 0x20000000 | 0x10 | Submixer setup {numIoChannels 8, flags 0} | 0x1096f77 |
| 0x20000004 | 0x28 | Submixer | 0x1096e81, 0x10a1e48 |
| 0x30000000 | 0x10 | Mastering setup {numInputChannels 8, flags 0} | 0x1096eea |
| 0x30000005 | 0x10 | Mastering, {u32 index, u32 0} | 0x10974b6, 0x109759b |
| 5 | 0x18 | Patch {port, destInputId, destHandle} (OrbisNgs2VoicePatchParam) | 0x1097006, 0x1091847 |
| 6 | 0xc | Event {eventId} (OrbisNgs2VoiceEventParam); eventId 0 at setup (0x1096f1f), 1 elsewhere (0x10917e1, 0x10acca4) | many |
| 2 | 0x10 | common | 0x10ac702 |
| 0x40020000, 0x40001f00 | 0x18 | custom-rack module params | 0x10abedf, 0x10ac371 |

  About 87 sites (the rbp-framed code at 0x1091354-0x1094300) and 20 more (register/ymm-built headers) were not resolved by a constant scan; patch (5) and event (6) dominate there (e.g. 0x10917e1 id 6 / eventId 1, 0x1091847 id 5).
- Results: not tested at the boot sites (0x1096eea-0x10975d0). A simple "next instruction uses eax" scan flags 54 of 126; that is unreliable, so treat as unverified.
- shadPS4: **stub**, logs and returns 0 (ngs2.cpp:192-195).

### 3.9 sceNgs2VoiceGetState(Handle voice, VoiceState* out, size_t stateSize) -> s32 (2 sites)
- 0x10dff3d: `edx` = 0x30 = sizeof SceNgs2SamplerVoiceState {stateFlags u32, envelopeHeight f32, peakHeight f32, reserved u32, numDecodedSamples u64, decodedDataSize u64, userData u64, waveformData ptr} (shadPS4 ngs2_sampler.h). Result ignored. Reads `-0x68(rbp)` stateFlags, `-0x64` envelopeHeight, `-0x60` peakHeight, and 16 bytes at `-0x58` copied into the voice record (+0x38; +0x98, +0x9c).
- 0x10e00d4: `edx` = 0x10 = sizeof SceNgs2SubmixerVoiceState {state, envelopeHeight, peakHeight, compressorHeight}. Result ignored. Reads stateFlags, `-0x64`, `-0x60`.
- Flag meaning from the game's tests (inferred): bit 0 = voice running; the game tests `flags & 0x22 == 2` (0x10dff62-0x10dff65). If its record says active and bit 0 is clear, it marks the voice ended (`orl $0x100`, 0x10dff95). Zero flags therefore retire every started sound at the next poll.
- shadPS4: partial. Real handle lookup and zero-fill of the full per-rack state, but `stateFlags` comes from a field never updated (always 0) (ngs2_impl.cpp:959-986).

### 3.10 sceNgs2VoiceGetStateFlags(Handle voice, u32* out) -> s32
- Imported, no guest call site. shadPS4: partial (ngs2_impl.cpp:949-957, returns the stored flag, 0).

### 3.11 sceNgs2SystemRender(Handle system, const RenderBufferInfo* aBufferInfo, u32 numBufferInfo) -> s32 (1 site, 0x10ace8e)
- Caller `0x10acce0` (returns early if `esi` = numBuffers is 0 or the format code at descriptor+4 is outside 4..0x11). It builds an array of `SceNgs2RenderBufferInfo` (0x18 bytes: `void* buffer` +0, `size_t bufferSize` +8, `u32 waveformType` +0x10, `u32 numChannels` +0x14) at rbp-0x140 from game descriptors (stride 0x20, 0x10ace40-0x10ace67). bufferSize = numChannels * a grain-sample count * bytes per sample (`r13d` = 2 or 4). waveformType (`r15d`) is 0x12 (i16 LE, default), 0x13 (i16 BE), 0x18 (f32 LE) or 0x19 (f32 BE) chosen via a jump table at 0x11d5334 (0x10acd11-0x10acd5a).
- `rdi` = system handle from 0x2d44490+0x60. Result in `ebx`, tested `js` (0x10aceac); on negative the game skips its timing and counter updates and returns.
- Contract: fills each buffer with one grain of the mix; the game submits them to audio out afterward (outside Ngs2).
- shadPS4: real shape, silent. Validates channels (1, 2, 6, 8), waveform type (0x12, 0x13, 0x18, 0x19), size >= bytes*channels*numGrainSamples, then memsets 0 (ngs2_impl.cpp:988-1052). No mixing.

## 4. Error codes (shadPS4 ngs2_error.h:6-117, all `0x804A....`)

FAIL 0x0001; INVALID_MAX_GRAIN_SAMPLES 0x50; INVALID_NUM_GRAIN_SAMPLES 0x51; INVALID_NUM_CHANNELS 0x52; INVALID_OUT_ADDRESS 0x53; INVALID_OUT_SIZE 0x54; INVALID_OPTION_ADDRESS 0x80; INVALID_OPTION_SIZE 0x81; INVALID_OPTION_FLAG 0x82; INVALID_MAX_VOICES 0x103; INVALID_HANDLE 0x200; INVALID_SAMPLE_RATE 0x201; INVALID_BUFFER_INFO 0x206; INVALID_BUFFER_ADDRESS 0x207; INVALID_BUFFER_SIZE 0x209; INVALID_BUFFER_ALLOCATOR 0x20a; EMPTY_BUFFER 0x20c; INVALID_SYSTEM_HANDLE 0x230; INVALID_RACK_ID 0x260; INVALID_RACK_HANDLE 0x261; INVALID_VOICE_HANDLE 0x300; INVALID_VOICE_INDEX 0x302; INVALID_VOICE_CONTROL_ID 0x308; INVALID_WAVEFORM_TYPE 0x402. The game's own allocator returns 0x804a020c (0x1097b74).

## 5. Recommended smallest faithful implementation

Principle: every handle call succeeds with real handles and real out-fields; only the audio content is silent.

1. Host-side tables for system, rack and voice. Handles are unique non-zero u64s across all three types (the game passes a rack handle as a patch destination, 0x1097006).
2. `SystemCreateWithAllocator`: check option size 0x40; keep grain/sampleRate; write `*out`. Calling the guest alloc/free is optional: the game never reads the buffer, so v1 can skip the callbacks (no leak, since the free handler is only invoked by Ngs2).
3. `RackQueryBufferSize`: accept 0x1000, 0x2000, 0x2001, 0x3000, and 0x4001-0x4003 (option size 0x4d8 for 0x4002); write `hostBuffer = 0`, `hostBufferSize` = a small nonzero size (for example shadPS4's formula or 0x1000), zero `reserved[5]`. Nonzero matters: the game carves and zeroes that many bytes from its arena (0x109e84c-0x109ea05).
4. `RackCreate` / `RackCreateWithAllocator`: check option size by id (0xa8, 0x98, 0x88; 0x4d8 for 0x4002), read maxVoices at option+0x20, build the voice-handle table, write `*out`. Never return FAIL for 0x4002 (four game sites).
5. `RackGetVoiceHandle`: write `*out` for index < maxVoices, else return 0x804A0302.
6. `VoiceControl`: return 0. Cheap tracking worth adding: remember patches (id 5) and events (id 6, eventId 0 = play at setup) per voice; nothing else for silent v1.
7. `VoiceGetState`: zero `stateSize` bytes (0x30 sampler or 0x10 submixer) so `stateFlags` = 0; `VoiceGetStateFlags`: write 0.
8. `SystemRender`: validate like shadPS4 (channels 1/2/6/8, waveformType 0x12/0x13/0x18/0x19, size) and zero `bufferSize` bytes of each buffer; return 0.
9. `RackDestroy` / `SystemDestroy`: accept NULL `outBufferInfo`, drop the handles, return 0.
10. Port shadPS4's `ngs2_impl.cpp` logic for 1-5, 7-9 (it already matches these contracts, including its zeroing render), and add custom-rack acceptance.

Full audio later needs: a mixing graph (sampler voices with waveform blocks, pitch, envelope and loops; PCM and ATRAC9 decode), submixer and mastering racks with patch routing (master voices map to output speakers), per-voice state flags and decoded-sample counters in VoiceGetState, voice callbacks, custom racks with the user-FX module, and a render pacing path into sceAudioOut. Audio3d (sceAudio3dObjectReserve, 0x10ff7a0) is a separate library gated by `loadAudio3d` / `enableAmbisonicsPan` and is not on the default boot path above.

## 6. Unverified or inferred

- Voice-control id names and struct shapes beyond ids 5 and 6 are inferred from sizes and shadPS4 header order; no public header with the numeric ids was found (web search returned nothing).
- Default config values come from the init code; the real config contents were not read.
- Ignored-vs-tested counts for RackGetVoiceHandle and VoiceControl come from a heuristic scan of the next two instructions. Confirmed `testl; js` sites: SystemCreateWithAllocator, all 5 RackCreateWithAllocator, all RackQueryBufferSize and RackCreate sites, RackDestroy at 0x1091354 and 0x10913f4, SystemRender.
- shadPS4 line numbers refer to the 2026-11-17 `main` fetch.
