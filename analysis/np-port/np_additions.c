/* Draft additions for the PSN libraries (offline console, one signed-out user).
 * PART A pastes into src/runtime_np.c (helpers reused by name: signed_out, ok, object,
 * community_no_id, new_object, matching2_no_context, webapi_callback_a, invitation_*, dialog_*).
 * PART B pastes into src/runtime_services.c (needs np_create, np_complete, np_availability,
 * logged_in, lock, trophy_* and trp_* helpers, ime/ime_complete, NP_* macros).
 * Contract sources: S = runtime_np.c / runtime_services.c, D = driveclub-recomp (none of these
 * names exist there), P = shadPS4 src/core/libraries/np (+ np_error.h), R = RPCS3 cellRudp.h,
 * C = eboot call site. Anything marked NOT_VERIFIED could not be checked against firmware.
 * Functions whose arguments never change the offline result take (void) like the existing
 * community_no_id families (SysV ABI ignores extra arguments); the real list is in the comment. */

/* ======================================================================================= */
/* PART A: runtime_np.c                                                                    */
/* ======================================================================================= */

/* ---- New error codes (np_error.h) ---- */
#define NP_INVALID_ARGUMENT ((int32_t)0x80550003)
#define NP_CALLBACK_ALREADY_REGISTERED ((int32_t)0x80550008)
#define NP_CALLBACK_NOT_REGISTERED ((int32_t)0x80550009)
#define UTIL_NOT_MATCH ((int32_t)0x80550609)
#define AUTH_INVALID_SIZE ((int32_t)0x80550302)
#define AUTH_INVALID_ID ((int32_t)0x80550307)
#define COMMUNITY_INSUFFICIENT_ARGUMENT ((int32_t)0x8055070C)
#define WEBAPI_REQUEST_NOT_FOUND ((int32_t)0x80552906)
#define SIGNALING_NOT_INITIALIZED ((int32_t)0x80552701)
#define SIGNALING_ALREADY_INITIALIZED ((int32_t)0x80552702)
#define SIGNALING_CTX_NOT_FOUND ((int32_t)0x80552705)
#define SIGNALING_INVALID_ARGUMENT ((int32_t)0x80552715)
#define NET_CTL_INVALID_ADDR ((int32_t)0x80412107)
#define RUDP_NOT_INITIALIZED ((int32_t)0x80770001) /* R: PS3 header; PS4 values NOT_VERIFIED */
#define RUDP_ALREADY_INITIALIZED ((int32_t)0x80770002)
#define RUDP_INVALID_CONTEXT_ID ((int32_t)0x80770003)
#define RUDP_INVALID_ARGUMENT ((int32_t)0x80770004)
#define RUDP_NOT_BOUND ((int32_t)0x80770013)
#define RUDP_INVALID_SOCKET ((int32_t)0x80770019)
#define RUDP_TOO_MANY_CONTEXTS ((int32_t)0x80770020)

/* ---- NpTus (P np_tus.cpp, S) ----
 * sceNpTusCreateNpTitleCtx(serviceLabel, NpId *self): P checks npId (INSUFFICIENT_ARGUMENT) and
 * the label (INVALID_ARGUMENT), then creates the context; here the context needs the user's
 * NpId: SIGNED_OUT, as sceNpTusCreateNpTitleCtxA. Every request call (Get/Set/AddAndGet/
 * TryAndSet/DeleteMultiSlot, plain, A, VUser, AVUser, ForCrossSave and Friends forms, and
 * sceNpTssGetData) takes the reqId of sceNpTusCreateRequest, which cannot exist: community
 * INVALID_ID (community_no_id, as the *Async forms in the existing table). Real argument lists:
 *   (int reqId, <target>, s32 slotId | s32 *slotIds, ..., void *option)  [P signatures]. */
static ABI int32_t tus_ctx(uint32_t label,const void *np_id) {
    if (!np_id) return COMMUNITY_INSUFFICIENT_ARGUMENT;
    return label==INVALID_SERVICE_LABEL ? COMMUNITY_INVALID_ARGUMENT : NP_SIGNED_OUT;
}

/* ---- NpScore (P np_score.cpp, S) ----
 * sceNpScoreCreateNpTitleCtx(label, NpId *self): same checks and result as tus_ctx (P order:
 * label INVALID_ARGUMENT before the null NpId INSUFFICIENT_ARGUMENT).
 * sceNpScoreGet(Friends)Ranking*, GetGameData*, GetBoardInfo, RecordScore, RecordGameData
 * (sync, non-A, ForCrossSave, PcId forms): the request fails its transfer: SIGNED_OUT (signed_out),
 * as the *Async forms already do. Argument lists: (s32 reqId, boardId, ..., void *option).
 * sceNpScoreSetPlayerCharacterId(ctxId, pcId): pcId < 0 INVALID_ARGUMENT, else the ctx/req id
 * cannot exist: INVALID_ID (P). */
static ABI int32_t score_ctx(uint32_t label,const void *np_id) {
    if (label==INVALID_SERVICE_LABEL) return COMMUNITY_INVALID_ARGUMENT;
    return np_id ? NP_SIGNED_OUT : COMMUNITY_INSUFFICIENT_ARGUMENT;
}
static ABI int32_t score_pc_id(int32_t ctx,int32_t pc_id) {
    (void)ctx; return pc_id<0 ? COMMUNITY_INVALID_ARGUMENT : COMMUNITY_INVALID_ID;
}

/* ---- NpUtility (P np_utility.cpp, S; C: eboot calls CreateTitleCtxA at 0xa8b263 with the user
 * id from a global (0x2ccbdb4), stores the id only if >= 0, and guards every Delete with id >= 0,
 * so a failed create is harmless) ----
 * sceNpLookupCreateTitleCtx(NpId *self) (null: INSUFFICIENT_
 * ARGUMENT as P), sceNpWordFilterCreateTitleCtx(NpId *self): SIGNED_OUT as WordFilterCreateTitleCtxA
 * (CreateTitleCtxA(user) is in runtime_np.c already).
 * sceNpLookupCreateRequest(titleCtx), sceNpLookupDeleteTitleCtx(titleCtx), sceNpLookupDeleteRequest
 * (req), sceNpLookupNpId(req, onlineId, npId, option), sceNpLookupPollAsync(req, *result),
 * sceNpWordFilterCreateRequest(titleCtx), sceNpWordFilterSanitizeComment(req, comment, out,
 * option): the id cannot exist: INVALID_ID. sceNpBandwidthTestInitStart / GetStatus /
 * Shutdown: SIGNED_OUT (runtime_np.c header); P returns OK from logging stubs, not copied.
 * sceNpBandwidthTestAbort: OK (nothing running). Real arguments of InitStart/GetStatus
 * NOT_VERIFIED (P has none). */
static ABI int32_t utility_ctx(const void *np_id) { return np_id ? NP_SIGNED_OUT : COMMUNITY_INSUFFICIENT_ARGUMENT; }

/* ---- NpManager, library side (P np_manager.cpp) ----
 * sceNpInGameMessagePrepare(ctx, handle, ...) / SendData(ctx, handle, ...): like the A forms,
 * SIGNED_OUT. sceNpInGameMessageGetMemoryPoolStatistics(ctx, stat *): statistics of a pool the
 * library holds: OK (as the existing Terminate; struct layout NOT_VERIFIED, nothing written).
 * sceNpRegisterNpReachabilityStateCallback(cb, arg) (P): null callback INVALID_ARGUMENT, a second
 * registration CALLBACK_ALREADY_REGISTERED, else OK (state is signed out, no event follows).
 * C: eboot 0xb9af0b ignores the result. ForToolkit: sceNpRegisterStateCallbackForToolkit(cb, arg)
 * OK (P), sceNpUnregisterStateCallbackForToolkit() CALLBACK_NOT_REGISTERED unless registered
 * (P), sceNpCheckCallbackForLib() OK, nothing pending. */
static _Atomic int reachability_cb, toolkit_cb;
static ABI int32_t reachability_register(void *cb,void *arg) {
    (void)arg;
    if (!cb) return NP_INVALID_ARGUMENT;
    int none=0;
    return atomic_compare_exchange_strong(&reachability_cb,&none,1) ? 0 : NP_CALLBACK_ALREADY_REGISTERED;
}
static ABI int32_t toolkit_register(void *cb,void *arg) { (void)cb; (void)arg; atomic_store(&toolkit_cb,1); return 0; }
static ABI int32_t toolkit_unregister(void) {
    int one=1;
    return atomic_compare_exchange_strong(&toolkit_cb,&one,0) ? 0 : NP_CALLBACK_NOT_REGISTERED;
}

/* ---- NpCommon: sceNpCmpNpId(NpId *a, NpId *b) (P np_common.cpp): null INVALID_ARGUMENT; NpId is
 * handle{data[16], term, dummy[3]}, opt[8], reserved[8]: the data (strncmp 16), opt and reserved
 * must match, else UTIL NOT_MATCH. ---- */
static ABI int32_t np_cmp_id(const uint8_t *a,const uint8_t *b) {
    if (!a || !b) return NP_INVALID_ARGUMENT;
    if (strncmp((const char *)a,(const char *)b,16)) return UTIL_NOT_MATCH;
    return memcmp(a+20,b+20,16) ? UTIL_NOT_MATCH : 0;
}

/* ---- NpAuth (P np_auth.cpp, S; C: eboot 0xa60ca9 creates an async request with
 * {size=0x18, mask, priority=700}, tests < 0, then calls GetAuthorizationCodeA(req, param{size
 * 0x20, user..}, code, issuer) and goes on only if that is >= 0; on failure it deletes the
 * request. Poll (0xb97f4c): 0 finished or < 0 deletes it, > 0 keeps polling.) ----
 * sceNpAuthCreateAsyncRequest(param{u64 size=0x18, mask, s32 priority}): null INVALID_ARGUMENT,
 * wrong size INVALID_SIZE, else an id (shared with the sync ids). sceNpAuthGetAuthorizationCode
 * (req, param, code, issuer) is the existing auth_code_a. sceNpAuthGetIdTokenA(req, param, token):
 * pointers checked, then SIGNED_OUT at once, returned directly even on an async id (as the
 * existing auth_code_a; the game's fail path never polls). sceNpAuthPollAsync(req, *result): no
 * operation is ever left running, so the async request has none to report: INVALID_ID (P
 * returns it for an async request whose operation never started). */
static ABI int32_t auth_async_request(const uint64_t *param) {
    if (!param) return AUTH_INVALID_ARGUMENT;
    return param[0]!=24 ? AUTH_INVALID_SIZE : auth_request();
}
static ABI int32_t auth_token_a(int32_t req,const void *param,void *token) {
    (void)req; return !param || !token ? AUTH_INVALID_ARGUMENT : NP_SIGNED_OUT;
}
static ABI int32_t auth_poll(int32_t req,int32_t *result) {
    (void)req; return result ? AUTH_INVALID_ID : AUTH_INVALID_ARGUMENT;
}

/* ---- NpWebApi (P np_web_api.cpp / np_web_api_internal.cpp, S) ----
 * sceNpWebApiCreateContext(lib, OrbisNpOnlineId *): lib >= 0x8000 INVALID_LIB_CONTEXT_ID, null
 * INVALID_ARGUMENT, else a user context needs PSN: SIGNED_OUT (as ...ContextA).
 * sceNpWebApiCreatePushEventFilter(lib, params, count): null/0 INVALID_ARGUMENT, bad lib, else
 * created (a library-level object). sceNpWebApiCreateServicePushEventFilter(lib, handle, service,
 * label, params, count): also needs the service name and a label != INVALID. DeletePush/
 * DeleteServicePush filter: OK as DeleteExtd. Register[Service]PushEventCallback(userCtx, filter,
 * cb, arg) is webapi_callback_a; Unregister[Service]PushEventCallback(userCtx, id): OK as
 * UnregisterExtd (P: USER_CONTEXT_NOT_FOUND, kept consistent with the Extd sibling).
 * Request header calls take a request id from CreateRequest, which fails: REQUEST_NOT_FOUND (P
 * finds no request) after the null checks. GetMemoryPoolStats(lib, stats{u64 pool, max, cur; s32}):
 * a library pool with nothing in use; the pool size is NOT_VERIFIED, zero is written. */
static ABI int32_t webapi_context(int32_t lib,const void *online_id) {
    if (lib>=0x8000) return WEBAPI_INVALID_LIB_CONTEXT_ID;
    return online_id ? NP_SIGNED_OUT : WEBAPI_INVALID_ARGUMENT;
}
static ABI int32_t webapi_plain_filter(int32_t lib,const void *params,uint64_t count) {
    if (!params || !count) return WEBAPI_INVALID_ARGUMENT;
    return lib>=0x8000 ? WEBAPI_INVALID_LIB_CONTEXT_ID : new_object();
}
static ABI int32_t webapi_service_filter(int32_t lib,int32_t handle,const char *service,uint32_t label,const void *params,uint64_t count) {
    (void)handle;
    if (!service || !params || !count || label==INVALID_SERVICE_LABEL) return WEBAPI_INVALID_ARGUMENT;
    return lib>=0x8000 ? WEBAPI_INVALID_LIB_CONTEXT_ID : new_object();
}
static ABI int32_t webapi_add_header(int64_t req,const char *name,const char *value) {
    (void)req; return !name || !value ? WEBAPI_INVALID_ARGUMENT : WEBAPI_REQUEST_NOT_FOUND;
}
static ABI int32_t webapi_header_length(int64_t req,const char *name,uint64_t *length) {
    (void)req; return !name || !length ? WEBAPI_INVALID_ARGUMENT : WEBAPI_REQUEST_NOT_FOUND;
}
static ABI int32_t webapi_header_value(int64_t req,const char *name,char *value,uint64_t size) {
    (void)req; return !name || !value || !size ? WEBAPI_INVALID_ARGUMENT : WEBAPI_REQUEST_NOT_FOUND;
}
static ABI int32_t webapi_pool_stats(int32_t lib,uint64_t *stats) {
    if (!stats) return WEBAPI_INVALID_ARGUMENT;
    if (lib>=0x8000) return WEBAPI_INVALID_LIB_CONTEXT_ID;
    memset(stats,0,24); return 0;
}

/* ---- NpMatching2 (P np_matching2.cpp, S) ----
 * sceNpMatching2CreateContext(param{NpId *, commId *, passphrase *, u32 label, u64 size=0x28},
 * ctxId *): null/size/ctxId INVALID_ARGUMENT, else SIGNED_OUT (A form: size 0x10 at +8).
 * Every call that names a context (ctxId first, u16): CreateJoinRoom, JoinRoom, KickoutRoomMember,
 * SendRoomMessage, SendRoomChatMessage, SetUserInfo, GetUserInfoList[A], GetRoomDataInternal,
 * GetRoomMemberDataInternal, SetRoomMemberDataInternal, JoinLobby, LeaveLobby, GetLobbyInfoList,
 * GetLobbyMemberDataInternalList, Register Lobby{Event,Message}Callback, SetSignalingOptParam,
 * SignalingGet/Cancel PeerNetInfo[Result], SignalingGetConnectionInfo[A],
 * GetRoomMemberIdListLocal, GetRoomPasswordLocal, GetSignalingOptParamLocal:
 * INVALID_CONTEXT_ID (matching2_no_context). Argument lists: see P (ctx, request, optParam,
 * *requestId) for the request calls; the Local and PeerNetInfo lists are NOT_VERIFIED (P has none).
 * sceNpMatching2GetMemoryInfo(info *) / GetSslMemoryInfo(info *): library memory statistics: OK as
 * P, nothing written (struct layout NOT_VERIFIED).
 * C: eboot 0xa7e1e1 creates the context (CreateContextA) right after Signaling and Rudp init and
 * jumps to cleanup on any non-zero result, so every call above is unreachable offline. */
static ABI int32_t matching2_context(const uint8_t *param,uint16_t *ctx) {
    if (!param || !ctx) return MATCHING2_INVALID_ARGUMENT;
    uint64_t size; memcpy(&size,param+32,8);
    return size!=0x28 ? MATCHING2_INVALID_ARGUMENT : NP_SIGNED_OUT;
}

/* ---- NpSignaling (P np_signaling.cpp; C: eboot 0xa7e0c2 Initialize(0x20000, 0x100, 0x3f,
 * 0x4000) must return 0 or the setup is dropped; CreateContextA (0xa7e4f0) non-zero also drops) ----
 * sceNpSignalingInitialize(memSize, priority, affinity, stackSize): the library starts local
 * threads and needs no PSN: OK; again ALREADY_INITIALIZED. sceNpSignalingTerminate(): OK, else
 * NOT_INITIALIZED. sceNpSignalingCreateContextA(user, callback, arg, ctxId *): NOT_INITIALIZED,
 * then user -1 or null ctxId INVALID_ARGUMENT, then the user's NpId: SIGNED_OUT (P order).
 * Every other call (GetConnectionStatus, Activate/Deactivate/TerminateConnection, GetConnection
 * FromPeerAddressA: ctxId first) names a context that cannot exist: NOT_INITIALIZED first, then
 * CTX_NOT_FOUND. DeleteContext(ctx): CTX_NOT_FOUND (P erases silently and returns OK; an id never
 * issued is not OK here).
 * Argument lists: P. */
static _Atomic int signaling_up;
static ABI int32_t signaling_init(int64_t mem,int32_t priority,int32_t affinity,int64_t stack) {
    (void)mem; (void)priority; (void)affinity; (void)stack;
    int none=0;
    return atomic_compare_exchange_strong(&signaling_up,&none,1) ? 0 : SIGNALING_ALREADY_INITIALIZED;
}
static ABI int32_t signaling_term(void) {
    int one=1;
    return atomic_compare_exchange_strong(&signaling_up,&one,0) ? 0 : SIGNALING_NOT_INITIALIZED;
}
static ABI int32_t signaling_context_a(int32_t user,void *cb,void *arg,int32_t *ctx) {
    (void)cb; (void)arg;
    if (!atomic_load(&signaling_up)) return SIGNALING_NOT_INITIALIZED;
    return user==USER_INVALID || !ctx ? SIGNALING_INVALID_ARGUMENT : NP_SIGNED_OUT;
}
static ABI int32_t signaling_no_context(void) { return atomic_load(&signaling_up) ? SIGNALING_CTX_NOT_FOUND : SIGNALING_NOT_INITIALIZED; }

/* ---- Rudp (R cellRudp.h error codes; arguments from the PS3/PS4 SDK API, C: eboot 0xa7e1a3
 * Init(pool, size) after SignalingInitialize, result tested < 0). P only has logging stubs
 * (OK), not copied. All contracts NOT_VERIFIED for PS4; local-only state follows the
 * Signaling model: no socket can exist (sceNetSocket fails), so nothing binds.
 * sceRudpInit(memPool, int memSize): null/<=0 INVALID_ARGUMENT, again ALREADY_INITIALIZED, else OK.
 * sceRudpEnd(): OK, else NOT_INITIALIZED. sceRudpEnableInternalIOThread(stack, priority) and
 * sceRudpSetEventHandler(handler, arg): NOT_INITIALIZED, else OK (local). sceRudpCreateContext(
 * handler, arg, int *ctxId): NOT_INITIALIZED, null ctxId INVALID_ARGUMENT, else a local id (16
 * at most, TOO_MANY_CONTEXTS). sceRudpBind(ctx, sockId, vport, muxMode): INVALID_CONTEXT_ID, else
 * INVALID_SOCKET. sceRudpTerminate(ctx): frees it, else INVALID_CONTEXT_ID. Initiate(ctx, addr,
 * len, vport), Write(ctx, data, len, flags), Read(ctx, buf, len, flags, ...), SetOption(ctx,
 * option, value, len), GetContextStatus(ctx, status *), GetSizeReadable(ctx),
 * GetNumberOfPacketsToRead(ctx): INVALID_CONTEXT_ID, else NOT_BOUND. */
#define RUDP_CONTEXTS 16
static _Atomic int rudp_up;
static _Atomic int32_t rudp_ctx[RUDP_CONTEXTS]; /* 0 free, else id */
static _Atomic int32_t rudp_next=1;
static ABI int32_t rudp_init(const void *pool,int32_t size) {
    if (!pool || size<=0) return RUDP_INVALID_ARGUMENT;
    int none=0;
    return atomic_compare_exchange_strong(&rudp_up,&none,1) ? 0 : RUDP_ALREADY_INITIALIZED;
}
static ABI int32_t rudp_end(void) {
    int one=1;
    if (!atomic_compare_exchange_strong(&rudp_up,&one,0)) return RUDP_NOT_INITIALIZED;
    for (int i=0;i<RUDP_CONTEXTS;i++) atomic_store(&rudp_ctx[i],0);
    return 0;
}
static ABI int32_t rudp_local(void) { return atomic_load(&rudp_up) ? 0 : RUDP_NOT_INITIALIZED; }
static ABI int32_t rudp_create(void *handler,void *arg,int32_t *ctx) {
    (void)handler; (void)arg;
    if (!atomic_load(&rudp_up)) return RUDP_NOT_INITIALIZED;
    if (!ctx) return RUDP_INVALID_ARGUMENT;
    for (int i=0;i<RUDP_CONTEXTS;i++) {
        int32_t none=0, id=atomic_fetch_add(&rudp_next,1);
        if (atomic_compare_exchange_strong(&rudp_ctx[i],&none,id)) { *ctx=id; return 0; }
    }
    return RUDP_TOO_MANY_CONTEXTS;
}
static int rudp_known(int32_t id) {
    for (int i=0;i<RUDP_CONTEXTS;i++) if (id && atomic_load(&rudp_ctx[i])==id) return 1;
    return 0;
}
static ABI int32_t rudp_bind(int32_t ctx,int32_t sock,uint8_t vport,uint8_t mux) {
    (void)sock; (void)vport; (void)mux;
    if (!atomic_load(&rudp_up)) return RUDP_NOT_INITIALIZED;
    return rudp_known(ctx) ? RUDP_INVALID_SOCKET : RUDP_INVALID_CONTEXT_ID;
}
static ABI int32_t rudp_terminate(int32_t ctx) {
    if (!atomic_load(&rudp_up)) return RUDP_NOT_INITIALIZED;
    for (int i=0;i<RUDP_CONTEXTS;i++) {
        int32_t id=ctx;
        if (id && atomic_compare_exchange_strong(&rudp_ctx[i],&id,0)) return 0;
    }
    return RUDP_INVALID_CONTEXT_ID;
}
static ABI int32_t rudp_unbound(int32_t ctx) {
    if (!atomic_load(&rudp_up)) return RUDP_NOT_INITIALIZED;
    return rudp_known(ctx) ? RUDP_NOT_BOUND : RUDP_INVALID_CONTEXT_ID;
}

/* ---- NetCtlForNpToolkit (P netctl.cpp; same offline state as sceNetCtl*) ----
 * RegisterCallbackForNpToolkit(cb, arg, int *cid): null cb or cid INVALID_ADDR, else an id; no
 * state change ever follows. Unregister(cid) and CheckCallback(): OK. */
static ABI int32_t netctl_toolkit_register(void *cb,void *arg,int32_t *cid) {
    (void)arg;
    if (!cb || !cid) return NET_CTL_INVALID_ADDR;
    *cid=new_object(); return 0;
}

/* ---- Dialogs. Replace the enum and name table at the top of the dialog block with (SigninDialog
 * is already in runtime_np.c, added while this draft was written, so it is not repeated):
 *   enum { SIGNIN, INVITATION, ERROR_DIALOG, SOCIAL_SCREEN, FRIEND_LIST, PROFILE, GAME_CUSTOM, DIALOGS };
 *   ... dialog_names[DIALOGS]={"SigninDialog","InvitationDialog","ErrorDialog","SocialScreenDialog",
 *                              "NpFriendListDialog","NpProfileDialog","GameCustomDataDialog"};
 * ----
 * sceNpProfileDialog* (P np_profile_dialog.cpp): Initialize, OpenA(param), UpdateStatus, Close,
 * Terminate follow the friend-list dialog; GetResult(result{s32 result, s32 userAction, void *userData, reserved[32]}):
 * result SIGNED_OUT, userAction USER_CANCELED, userData kept (as invitation_result). C: eboot
 * 0xef6aca..0xef6be0: status 3 then GetResult (result only tested < 0), 0 clears its flag.
 * sceGameCustomDataDialog* (P game_custom_data_dialog.cpp): Initialize, Open(A)(param),
 * UpdateStatus, Terminate (no Close in the import list); GetResult(A)(result{callbackArg,
 * errorCode, result, sentUsers *, reserved[32]}) exactly as invitation_result (SIGNED_OUT,
 * USER_CANCELED, no users). sceInvitationDialogOpen / GetResult (non-A) are invitation_open /
 * invitation_result: the sentOnlineIds pointer at +16 is zeroed like sentUsers. */
static ABI int32_t profile_init(void) { return dialog_init(PROFILE); }
static ABI int32_t profile_open(const void *param) { (void)param; return dialog_open(PROFILE,""); }
static ABI int32_t profile_status(void) { return atomic_load(&dialog_status[PROFILE]); }
static ABI int32_t profile_result(uint8_t *result) {
    int32_t r=dialog_result(PROFILE,result);
    if (!r) { int32_t codes[2]={NP_SIGNED_OUT,RESULT_USER_CANCELED}; memcpy(result,codes,8); }
    return r;
}
static ABI int32_t profile_close(void) { return atomic_load(&dialog_status[PROFILE]) ? 0 : DIALOG_NOT_INITIALIZED; }
static ABI int32_t profile_term(void) { return dialog_term(PROFILE); }
static ABI int32_t custom_init(void) { return dialog_init(GAME_CUSTOM); }
static ABI int32_t custom_open(const void *param) { (void)param; return dialog_open(GAME_CUSTOM,""); }
static ABI int32_t custom_status(void) { return atomic_load(&dialog_status[GAME_CUSTOM]); }
static ABI int32_t custom_result(uint8_t *result) {
    int32_t r=dialog_result(GAME_CUSTOM,result);
    if (r) return r;
    int32_t codes[2]={NP_SIGNED_OUT,RESULT_USER_CANCELED};
    memcpy(result+8,codes,8); memset(result+16,0,40);
    return 0;
}
static ABI int32_t custom_term(void) { return dialog_term(GAME_CUSTOM); }

/* ---- Export table lines for PART A: see exports.txt ---- */

/* ======================================================================================= */
/* PART B: runtime_services.c (after trophy_release / np_account_id; uses its helpers)    */
/* ======================================================================================= */

/* ---- NpManager requests (P np_manager.cpp, S np_create/np_complete) ----
 * sceNpCreateRequest(): a synchronous request id, as sceNpCreateAsyncRequest without the async
 * flag. sceNpCheckNpReachability(req, user) is np_availability (user -1 INVALID_ARGUMENT, then
 * the request completes with SIGNED_OUT). sceNpCheckNpAvailability(req, OrbisNpOnlineId *): null
 * INVALID_ARGUMENT, then no user has an online id while signed out: USER_NOT_FOUND (P).
 * C: eboot 0xb9aa2d/0xb9ae2a: CreateRequest > 0 is used as the id, CheckNpReachability == 0 means
 * reachable (state 2), anything else state 0; a request id <= 0 skips to the failure path. */
static ABI int32_t np_create_sync(void) { return np_create(0); }
static ABI int32_t np_availability_id(int32_t id,const void *online_id) {
    (void)id; return !online_id ? NP_INVALID_ARGUMENT : NP_USER_NOT_FOUND;
}
/* ---- sceNpGetUserIdByAccountId(u64 account, int32 *user): 0/null INVALID_ARGUMENT; the account
 * of np_account_id gives its user, else USER_NOT_FOUND (S comment above np_account_id; P returns
 * SIGNED_OUT without a shadnet session). sceNpGetAccountCountryA and sceNpGetOnlineId are in
 * runtime_golf.c already (not repeated). ---- */
static ABI int32_t np_user_by_account(uint64_t account,int32_t *user) {
    if (!account || !user) return NP_INVALID_ARGUMENT;
    uint64_t index=account-NP_ACCOUNT_ID;
    if (account<NP_ACCOUNT_ID || index>1 || !logged_in(USER_ID+(int32_t)index)) return NP_USER_NOT_FOUND;
    *user=USER_ID+(int32_t)index; return 0;
}

/* ---- Trophies (S trophy section; P np_trophy.cpp for the checks) ----
 * sceNpTrophyAbortHandle(handle): nothing is in flight on a local trophy set: OK; handle <= 0
 * INVALID_HANDLE. C: the eboot wrapper at 0xef78b0 passes *handlePtr and returns the result.
 * sceNpTrophyShowTrophyList(ctx, handle): the system list is not drawn: OK after the id checks.
 * sceNpTrophyCaptureScreenshot(): no capture facility: SCREENSHOT_DISABLED (P returns OK from a
 * stub, not copied). GetGameIcon(ctx, handle, buffer, *size) / GetGroupIcon(ctx, handle, group,
 * buffer, *size) / GetTrophyIcon(ctx, handle, id, buffer, *size): *size null INVALID_ARGUMENT,
 * ctx/handle <= 0 INVALID_CONTEXT / INVALID_HANDLE, the PNG from the TRP (ICON0.PNG, GR%03d.PNG,
 * TROP%03d.PNG) else ICON_FILE_NOT_FOUND; no buffer: *size = file size; smaller buffer:
 * INSUFFICIENT_BUFFER; else the file is copied and *size set. A trophy icon needs the trophy
 * unlocked (P): TROPHY_NOT_UNLOCKED; id outside 0..TROPHY_MAX INVALID_TROPHY_ID; group outside
 * 0..TROPHY_MAX INVALID_GROUP_ID (the base-game group id NOT_VERIFIED). */
#define TROPHY_INVALID_TROPHY_ID ((int32_t)0x8055160A)
#define TROPHY_INVALID_GROUP_ID ((int32_t)0x8055160B)
#define TROPHY_NOT_UNLOCKED ((int32_t)0x8055161A)
#define TROPHY_SCREENSHOT_DISABLED ((int32_t)0x8055162B)
static ABI int32_t trophy_abort(int32_t handle) { return handle>0 ? 0 : TROPHY_INVALID_HANDLE; }
static ABI int32_t trophy_show_list(int32_t ctx,int32_t handle) {
    if (ctx<=0) return TROPHY_INVALID_CONTEXT;
    return handle>0 ? 0 : TROPHY_INVALID_HANDLE;
}
static ABI int32_t trophy_screenshot(void) { return TROPHY_SCREENSHOT_DISABLED; }
static int32_t trophy_send_png(const unsigned char *png,uint64_t len,void *buffer,uint64_t *size) {
    if (!png) return TROPHY_ICON_NOT_FOUND;
    if (!buffer) { *size=len; return 0; }
    if (*size<len) return TROPHY_INSUFFICIENT_BUFFER;
    memcpy(buffer,png,len); *size=len; return 0;
}
static int32_t trophy_icon_checks(int32_t ctx,int32_t handle,uint64_t *size) {
    if (!size) return TROPHY_INVALID;
    if (ctx<=0) return TROPHY_INVALID_CONTEXT;
    return handle>0 ? 0 : TROPHY_INVALID_HANDLE;
}
static ABI int32_t trophy_game_icon(int32_t ctx,int32_t handle,void *buffer,uint64_t *size) {
    int32_t r=trophy_icon_checks(ctx,handle,size);
    if (r) return r;
    const unsigned char *png=0; uint64_t len=0;
    pthread_mutex_lock(&lock); trophy_load_once();
    r=trophy_send_png(trp_file("ICON0.PNG",&png,&len) ? png : 0,len,buffer,size);
    pthread_mutex_unlock(&lock);
    return r;
}
static ABI int32_t trophy_group_icon(int32_t ctx,int32_t handle,int32_t group,void *buffer,uint64_t *size) {
    int32_t r=trophy_icon_checks(ctx,handle,size);
    if (r) return r;
    if (group<0 || group>=TROPHY_MAX) return TROPHY_INVALID_GROUP_ID;
    char want[16]; snprintf(want,sizeof(want),"GR%03d.PNG",group);
    const unsigned char *png=0; uint64_t len=0;
    pthread_mutex_lock(&lock); trophy_load_once();
    r=trophy_send_png(trp_file(want,&png,&len) ? png : 0,len,buffer,size);
    pthread_mutex_unlock(&lock);
    return r;
}
static ABI int32_t trophy_trophy_icon(int32_t ctx,int32_t handle,int32_t id,void *buffer,uint64_t *size) {
    int32_t r=trophy_icon_checks(ctx,handle,size);
    if (r) return r;
    if (id<0 || id>=TROPHY_MAX) return TROPHY_INVALID_TROPHY_ID;
    const unsigned char *png=0; uint64_t len=0;
    pthread_mutex_lock(&lock); trophy_load_once();
    if (!(trophy_flags[id/32]>>(id%32)&1u)) r=TROPHY_NOT_UNLOCKED;
    else r=trophy_send_png(trophy_icon(id,&png,&len) ? png : 0,len,buffer,size);
    pthread_mutex_unlock(&lock);
    return r;
}

/* ---- sceImeDialogAbort() (P ime_dialog.cpp): no dialog ever opened IME DIALOG NOT_IN_USE
 * (0x80BC0107), one that already finished NOT_RUNNING (0x80BC0105), a running one ends as
 * aborted (end status 2) and returns OK. C: eboot 0xef5aa4 returns (result == 0).
 * NOTE: ime_result above returns 0x80BC0101 for "not finished"; P's DIALOG_NOT_FINISHED is
 * 0x80BC0106 (0x80BC0101 is INVALID_TITLE). ---- */
static ABI int32_t ime_abort(void) {
    if (!ime.running && !ime.finished) return (int32_t)0x80BC0107;
    if (!ime.running) return (int32_t)0x80BC0105;
    ime_complete(2,"");
    return 0;
}
