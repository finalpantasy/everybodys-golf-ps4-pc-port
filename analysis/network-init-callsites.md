# Network / HTTP init call sites (static disassembly)

Imports are resolved with `analysis/plt-import-map.json` (PLT stub -> import). Stub = `call 0x10fXXXX`. Argument registers are read from the instructions just before the call. "Result" = what the code does with eax. Names for libc NIDs not in `import-names.json` are shown as NID only. Everything below was read statically; nothing was run.

Mapping validated: 0x10fdb90 = idx 252 sceNetCtlInit, 0x10fe210 = idx 356 sceHttpsEnableOption, 0x10fe220 = idx 357 sceHttpCreateConnectionWithURL, 0x10fe2e0 = idx 369 sceHttpsSetSslCallback (all four match).

Note: the huge guest functions near 0xc0f00 and 0xf6b94 have no frame-pointer prologue nearby (switch-heavy, thousands of bytes). The true function starts were not found; the windows below begin at the first cleanly decoded instruction.

## 1. Window 0xc0f00-0xc1100 (net bring-up, runs once at startup)

| call addr | import | args | result |
|---|---|---|---|
| c0f2d | libc NID tcVi5SivF7Q (idx 26, sprintf-style) | rdi=stack buf (rsp+0x260), rsi="%s_00" (0x120b815), rdx="CUSA04687" | ignored |
| c0f3c | sceNetInit (242) | none | tested < 0 (js -> 0xc7add) |
| c0f59 | sceNetPoolCreate (248) | rdi="LIBNET_POOL", esi=0x30000, edx=0 | stored at 0x2c905f4 (net pool id), tested < 0 -> 0xc7add |
| c0f6c | sceNetCtlInit (252) MISSING | none | tested < 0 (js -> 0xc7ad6); not stored |
| c0f7e | sceSslInit (250) | edi=0x80000 | stored at 0x13643a4 (ssl ctx id), tested < 0 -> 0xc7ad1 |
| c0f9e | sceHttpInit (254) | edi=[0x2c905f4] (net pool id), esi=eax from SslInit (ssl ctx id), edx=0x80000 | stored at 0x13643a0 (http ctx id), tested < 0 -> 0xc7ac6 |
| c0fc0 | sceNpSetNpTitleId (239) | rdi=rsp+0x260 (title id struct from the sprintf), rsi=0x1361f30 (binary title secret) | ignored |
| c100a, c1025 | malloc / memset (0x85cc10 bytes) | | not network |
| c105d | sceKernelDeleteEventFlag (694) | rdi=[r15+0x98] | ignored |
| c1095 | scePthreadJoin (335) | rdi=[r15+0xb0], rsi=0 | ignored |

## 2. Function 0xec87e0 (0xec87e0-0xec8eef): HTTP object ctor/reset

Called from 0xf6b81 with rdi=[r13+0xe8], rsi=0x1361ec0 ("bo%Vu&%W"). Starts with memcpy (rdi=this+0x48, rsi=0x1238960, edx=0x1000), then a string/vector cleanup tail. Network imports it calls (all implemented): sceHttpDeleteRequest (ec8a22, edi=[this+8]), sceHttpDeleteConnection (ec8a37, edi=[this+0x10]), sceHttpDeleteTemplate (ec8a4c, edi=[this+0xc]), each only if the id is > 0 and the field is zeroed after. Also scePthreadCondDestroy (ec8a6a, rdi=this+0xc8) and scePthreadMutexDestroy (ec8a8c, rdi=this+0xb8), results tested. The rest is libc-style free/memset (idx 350 NID NDcSfcYZRC8, memset, free). No missing imports.

## 3. Function 0xec8ef0 (0xec8ef0-0xec9200): create template and connection

Signature seen at the call at 0xf6b63: rdi=this (r13), rsi=0x120b831 user agent "PS4Application nolib/0.0 (U-UP9000-CUSA04687_00-EVERYBODYSGOLF07/2017022700/1170...", rdx=0x1361e40 url "https://ssps4.scej-network.jp:443/nmg-us/ss.info". Inside: r12=this, r15=user agent, r14=url.

| call addr | import | args | result |
|---|---|---|---|
| ec8f0d / ec8f24 / ec8f3b | sceHttpDeleteRequest / DeleteConnection / DeleteTemplate | edi=[this+8], [this+0x10], [this+0xc], each only if > 0 | ignored, field zeroed |
| ec8f5c | sceHttpCreateTemplate (251) | edi=[0x13643a0] (http ctx), rsi=user agent, edx=2, ecx=1 | tested < 0 (js -> fail 0xec8fa8); eax kept in ebx |
| ec8f7f / ec8f8f / ec8f9f | sceHttpSetConnectTimeOut / SetSendTimeOut / SetRecvTimeOut (362/361/365) | edi=template id, esi=0xe4e1c0 (15,000,000 us) | nonzero -> fail; zero continues |
| ec9007 | sceHttpsSetSslCallback (369) MISSING | edi=[this+0xc] (template), rsi=callback 0xec9070, rdx=this (user arg) | tested < 0 -> fail path 0xec8fa8 |
| ec901d | sceHttpCreateConnectionWithURL (357) MISSING | edi=[this+0xc] (template), rsi=url, edx=1 (keep-alive) | stored at [this+0x10], tested < 0 -> fail |
| ec9034 / ec9048 / ec905c | Set Connect/Send/Recv timeouts | edi=connection id, esi=0xe4e1c0 | nonzero -> fail; success sets al=1 |

SSL callback body at 0xec9070 is `negl esi; sbbl eax,eax; ret`: it returns -1 if its 2nd arg (esi, the verify result) is nonzero, else 0. It never reads the cert array. A stub that never calls it, or calls it with 0, is enough.

A second entry, 0xec9080, re-creates only the connection: ec90be sceHttpCreateConnectionWithURL (rdi=[this+0xc], rsi=url, edx=1), stored to [this+0x10], tested < 0, then the three timeouts (ec90e1, ec90f2, ec9103).

Function 0xec9120 (request): ec9174 sceHttpCreateRequestWithURL (366) MISSING: edi=[this+0x10] (connection id), esi=method from table 0x123999c indexed by [this+0x20] (0 if index > 2), rdx=[this+0x18] (url), rcx=[this+0x40] (content length). Stored at [this+8], tested < 0 -> 0xec9290. Beyond the requested window, same function: ec921b sceHttpAddRequestHeader (implemented); ec92ca sceHttpsDisableOption (370) MISSING (edi=[this+8], esi=0 or [this+0xa0] at ec930a); ec92d5 and ec932d sceHttpsEnableOption (356) MISSING (edi=request id, esi=0 or [this+0xa4]); ec9351 sceHttpSendRequest (rsi=[this+0x38], rdx=[this+0x40]); ec9360 sceHttpGetStatusCode (compared with 0xc8); ec937f sceHttpGetResponseContentLength; ec9393 sceHttpReadData loop; ec93d4 sceHttpsGetSslError (355) MISSING, only when SendRequest returned 0x80431075 (edi=request id, rsi=rsp-0x38, rdx=rsp-0x3c).

## 4. Window around 0xf6b94 (0xf6a46-0xf7194)

Calls in order (function start not located; r13 = the HTTP/session object):

| call addr | import / callee | args | result |
|---|---|---|---|
| f6a77, f6ab1 | libc NID Ovb2dSJOAuE (idx 24, strcmp-style) | string compare in a map lookup | tested sign |
| f6b63 | guest 0xec8ef0 | rdi=r13, rsi=0x120b831 (user agent), rdx=0x1361e40 (ss.info url) | ignored (rax not read) |
| f6b81 | guest 0xec87e0 | rdi=[r13+0xe8] (after `[rdi+0x1048]=0`), rsi=0x1361ec0 | ignored |
| f6b8f | sceHttpsEnableOption (356) MISSING | edi=[r13+0x10] (connection id set by ec901d), esi=0x18 | ignored (next instr is a memset) |
| f6ba2..f6bdb | memset x4 | r13+0x120 size 0x5f150, r13+0x5f274 size 0x20000, r13+0x7f280 size 0xa2800, r13+0x121a98 size 0x3e9 | ignored |
| f6c96..f6d55 | malloc/memset/guest 0xec87e0 | allocations 0x1050 | not network |
| f6d85 | sceNpRegisterStateCallbackA (260) | rdi=0xb97260 (callback fn), rsi=0x2c8f338 (user arg) | ignored |
| f6daf onward | malloc 0x58, 0x90, 0x5870, 0x10, 0x8, 0x38; guest 0xaa6980, 0xf8d860 | | not network |

The ec8ef0 result at f6b63 is ignored. If sceHttpsSetSslCallback or CreateConnectionWithURL fails (< 0), [r13+0x10] stays 0 and sceHttpsEnableOption at f6b8f is called with edi=0 anyway.

## Missing on this path (call order)

1. c0f6c sceNetCtlInit (idx 252, stub 0x10fdb90): no args; result tested < 0 (js to 0xc7ad6), not stored.
2. ec9007 sceHttpsSetSslCallback (idx 369, stub 0x10fe2e0): edi=template id ([this+0xc]), rsi=0xec9070 (returns -1 if esi != 0 else 0), rdx=this; result tested < 0 -> failure path.
3. ec901d sceHttpCreateConnectionWithURL (idx 357, stub 0x10fe220): edi=template id, rsi=url "https://ssps4.scej-network.jp:443/nmg-us/ss.info", edx=1; result stored as connection id at [this+0x10], tested < 0 -> failure. Also at ec90be.
4. f6b8f sceHttpsEnableOption (idx 356, stub 0x10fe210): edi=[r13+0x10] (connection id), esi=0x18; result ignored. Same stub later (ec92d5, ec932d: edi=request id, esi=0 or [this+0xa4]).
5. ec9174 sceHttpCreateRequestWithURL (idx 366, stub 0x10fe2b0): edi=connection id, esi=method enum from table (0 default), rdx=url, rcx=content length; result stored at [this+8], tested < 0.
6. ec92ca sceHttpsDisableOption (idx 370, stub 0x10fe2f0): edi=request id, esi=0 or [this+0xa0]; result tested nonzero -> bail.
7. ec93d4 sceHttpsGetSslError (idx 355, stub 0x10fe200): edi=request id, rsi/rdx=out pointers on the stack; only if SendRequest returned 0x80431075; result stored at [this+0x58].
