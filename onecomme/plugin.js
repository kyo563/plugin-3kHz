'use strict';
const {spawn} = require('node:child_process');
const path = require('node:path');

function youtubeVideo(url) {
    try {
        const u = new URL(url);
        if (u.protocol !== 'https:' || u.username || u.password || u.port) return '';
        let id = '';
        if (u.hostname === 'youtu.be') id = u.pathname.slice(1);
        if (['youtube.com', 'www.youtube.com', 'm.youtube.com'].includes(u.hostname)) {
            id = u.pathname === '/watch' ? u.searchParams.get('v') : /^\/(?:live|embed)\/([^/]+)\/?$/.exec(u.pathname)?.[1];
        }
        return /^[A-Za-z0-9_-]{11}$/.test(id || '') ? id : '';
    } catch (_) { return ''; }
}

// Only public Service fields leave OneComme, and only for our local worker.
function serviceFrame(s, receivedYoutube = false) {
    if (!s || typeof s.id !== 'string' || !s.id || s.id.length > 200 || typeof s.enabled !== 'boolean') return null;
    const meta = s.meta || {};
    const id = youtubeVideo(s.url) || youtubeVideo(meta.url);
    let youtube = !!id;
    try { youtube ||= ['youtube.com','www.youtube.com','m.youtube.com','youtu.be'].includes(new URL(s.url).hostname); } catch (_) {}
    // filterComment already identifies the platform. Missing/private video
    // metadata must not prevent forwarding its official YouTube comments.
    if (!youtube && !receivedYoutube) return null;
    const name = [meta.title, s.name].find(v => typeof v === 'string' && v.trim()) || 'YouTube';
    const start = typeof meta.startTime === 'number' && Number.isFinite(meta.startTime) && meta.startTime > 0 ? meta.startTime : null;
    const ended = [meta.actualEndTime, meta.endTimestamp].some(v => typeof v === 'number' && v > 0);
    return {service_id:s.id, service_name:typeof s.name === 'string' ? s.name.slice(0,200) : '', id, name:name.slice(0,200), enabled:s.enabled,
        url:id ? `https://www.youtube.com/watch?v=${id}` : '', start_time:start,
        state:ended ? 'ended' : meta.isLive === true ? 'live' : start && (start < 1e12 ? start * 1000 : start) > Date.now() ? 'upcoming' : 'unknown'};
}

function convert(comment, userData) {
    const d = comment?.data;
    if (comment?.service !== 'youtube' || !d || d.meta?.type === 'system' || d.meta?.anonymity || d.autoModerated) return null;
    // OneComme owns identity. Preserve opaque IDs exactly, including existing UC IDs.
    if (typeof d.userId !== 'string' || !d.userId.trim() || d.userId.length > 512 || /[\p{Cc}\p{Cf}]/u.test(d.userId)) return null;
    if (![d.id, d.liveId, d.name, d.timestamp].every(v => typeof v === 'string' && v.length > 0)) return null;
    if (typeof d.comment !== 'string' || d.comment.length > 4096 || d.name.length > 200 || d.id.length > 512 || d.liveId.length > 200) return null;
    if (!d.liveId.trim() || /[\p{Cc}\p{Cf}\p{Cs}]/u.test(d.liveId)) return null;
    const handle = [d.screenName, d.name].find(v => typeof v === 'string' && /^@[^\s]{1,199}$/.test(v));
    const memo = userData?.id === d.userId && (userData.service === undefined || userData.service === 'youtube') && typeof userData.memo === 'string'
        ? userData.memo.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '').slice(0, 4000) : null;
    return {
        frame_id: d.liveId, frame_name: `${String(comment.name || 'YouTube').slice(0, 150)} (${d.liveId})`.slice(0, 200),
        comment: {source: 'youtube', externalMessageId: d.id, receivedAt: d.timestamp,
            userKey: d.userId, displayName: d.name, youtubeNickname: d.name,
            youtubeHandle: handle || null, avatarUrl: typeof d.profileImage === 'string' ? d.profileImage : null,
            oneCommeMemo: memo, message: d.comment}
    };
}

function createPlugin({spawnWorker = spawn, http = fetch} = {}) {
    let worker = null, ready = null, timer = null, buffer = '', generation = 0;
    let queue = [], draining = false, dropped = 0, services = null, revision = 0, sentRevision = 0, heartbeatDue = false;
    let receiptSince = new Map(), serviceURLs = new Map(), receiptHistory = new Map(), removedServices = new Set(), startedAt = 0;
    function resetReceipt(id) {
        receiptSince.set(id, Date.now());
        receiptHistory.delete(id);
    }
    function preserveReceipt(frame, old) {
        // Resolution of a channel URL is not a different stream. Explicit video
        // changes, disconnects and meta.clear must invalidate the old receipt.
        if (old?.receive_id && frame.enabled && old.enabled && frame.state !== 'ended' &&
            (!frame.id || !old.id || frame.id === old.id)) frame.receive_id = old.receive_id;
        return frame;
    }
    function updateServices(items) {
        if (!Array.isArray(items)) return;
        const next = new Map();
        for (const item of items.length > 32 ? [] : items) {
            const previous = typeof item?.id === 'string' ? services?.get(item.id) : null;
            const frame = serviceFrame(item, !!previous?.receive_id && serviceURLs.get(item.id) === item.url);
            if (!frame) continue;
            const old = services?.get(frame.service_id);
            const sameURL = serviceURLs.get(frame.service_id) === item.url;
            if (sameURL) preserveReceipt(frame, old);
            if (!old || !sameURL || !frame.enabled || (old.id && frame.id && old.id !== frame.id) || frame.state === 'ended')
                resetReceipt(frame.service_id);
            serviceURLs.set(frame.service_id, item.url);
            next.set(frame.service_id, frame);
        }
        for (const id of services?.keys() || []) if (!items.some(s => s?.id === id)) removedServices.add(id);
        for (const item of items) if (typeof item?.id === 'string') removedServices.delete(item.id);
        // Bound memory without resurrecting removed rows in this plugin session.
        if (removedServices.size > 128) removedServices = new Set([...removedServices].slice(-128));
        services = next;
        receiptSince = new Map([...receiptSince].filter(([id]) => next.has(id)));
        serviceURLs = new Map([...serviceURLs].filter(([id]) => next.has(id)));
        receiptHistory = new Map([...receiptHistory].filter(([id]) => next.has(id)));
        revision++;
        void drain();
    }
    let error = '準備中です';
    async function post(endpoint, data, connection) {
        return http(connection.base + endpoint, {method: 'POST',
            headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + connection.ingest},
            body: JSON.stringify(data), signal: AbortSignal.timeout(3000)});
    }
    async function drain() {
        if (draining || !ready) return;
        draining = true;
        const current = generation;
        try {
            while ((queue.length || sentRevision !== revision || heartbeatDue) && ready && current === generation) {
                if (sentRevision !== revision || heartbeatDue) {
                    const sendingRevision = revision;
                    const data = {dropped, ...(services === null ? {} : {services:[...services.values()]})};
                    try {
                        const r = await post('/api/onecomme/heartbeat', data, ready);
                        if (current !== generation || !r.ok) break;
                        sentRevision = sendingRevision; heartbeatDue = false;
                    } catch (_) { break; }
                    continue;
                }
                const event = queue[0];
                try {
                    const r = await post('/api/onecomme/comment', event, ready);
                    if (current !== generation) break;
                    if (!r.ok && r.status >= 500) break;
                    if (!r.ok) dropped++;
                    queue.shift();
                } catch (_) { break; }
            }
        } finally { draining = false; }
    }
    return {
        name: '待機列整理アプリ',
        uid: 'jp.kyo563.sankagata-seiretsu', version: '0.1.5', author: 'kyo563',
        url: 'http://localhost:11180/plugins/jp.kyo563.sankagata-seiretsu/index.html',
        permissions: ['filter.comment', 'services', 'meta', 'meta.clear'],
        init({dir}, initialData) {
            if (worker) return;
            generation++; ready = null; queue = []; buffer = ''; dropped = 0; error = '起動中です';
            services = null; revision = sentRevision = 0; heartbeatDue = false;
            receiptSince = new Map(); serviceURLs = new Map(); receiptHistory = new Map(); removedServices = new Set(); startedAt = Date.now();
            updateServices(initialData?.services);
            const mine = generation;
            worker = spawnWorker(path.join(dir, 'runtime', 'QueueWorker.exe'), [], {
                cwd: dir, windowsHide: true, shell: false, stdio: ['pipe', 'pipe', 'pipe']
            });
            worker.stdout.on('data', chunk => {
                if (mine !== generation) return;
                buffer += chunk.toString('utf8');
                if (buffer.length > 8192) { buffer = ''; error = '起動応答が不正です'; return; }
                let nl;
                while ((nl = buffer.indexOf('\n')) >= 0) {
                    const line = buffer.slice(0, nl); buffer = buffer.slice(nl + 1);
                    try {
                        const msg = JSON.parse(line);
                        if (msg.base === 'http://127.0.0.1:18765' && /^http:\/\/127\.0\.0\.1:18765\/control#key=[A-Za-z0-9_-]{40,128}$/.test(msg.control) && /^[A-Za-z0-9_-]{40,128}$/.test(msg.ingest)) {
                            ready = msg; error = '';
                            void drain();
                        } else error = '処理を起動できませんでした。重複起動やポート18765を確認してください';
                    } catch (_) { error = '起動応答を読み取れませんでした'; }
                }
            });
            // Drain diagnostics without retaining or exposing their contents.
            worker.stderr.on('data', () => {});
            worker.stdin.on('error', () => {});
            worker.on('error', () => { if (mine === generation) { ready = null; error = '同梱のruntimeを起動できません。ZIPの展開状態を確認してください'; } });
            worker.on('exit', () => { if (mine === generation) { ready = null; worker = null; queue = []; error = '処理が終了しました。プラグインを無効にしてから有効にしてください'; } });
            timer = setInterval(() => {
                heartbeatDue = true;
                void drain();
            }, 1500);
            timer.unref?.();
        },
        subscribe(type, data, service, meta) {
            if (!worker) return;
            if (type === 'services') updateServices(data);
            if (type === 'meta') {
                // Public event payload; older plugin dispatchers supply positional arguments.
                const s = data?.service || service;
                const m = data?.data || meta;
                const frame = serviceFrame(s && {...s, meta:{...s.meta, ...m}});
                if (frame && services?.has(frame.service_id)) {
                    const old = services.get(frame.service_id);
                    preserveReceipt(frame, old);
                    if ((old.id && frame.id && old.id !== frame.id) || !frame.enabled || frame.state === 'ended')
                        resetReceipt(frame.service_id);
                    services.set(frame.service_id,frame); revision++; void drain();
                }
            }
            if (type === 'meta.clear' && services?.has(data)) {
                // Do not retain a resolved old video while a channel URL reconnects.
                const old = services.get(data);
                services.set(data,{...old,id:'',url:'',state:'unknown',start_time:null,receive_id:''});
                resetReceipt(data);
                revision++; void drain();
            }
        },
        filterComment(comment, service, userData) {
            // Never change, suppress, or wait for processing of OneComme comments.
            if (ready) {
                const event = convert(comment, userData);
                if (event) {
                    // Use the official callback's Service, not names or Google
                    // metadata, to bind comments from restricted rooms locally.
                    let frame = serviceFrame(service, true);
                    const old = frame && services?.get(frame.service_id);
                    if (frame) event.service_id = frame.service_id;
                    if (frame && frame.enabled && !removedServices.has(frame.service_id) && (old || !services || services.size < 32)) {
                        if (!services) services = new Map();
                        if (old) frame = {...old};
                        else serviceURLs.set(frame.service_id, service.url);
                        const at = Date.parse(comment.data.timestamp);
                        const floor = Math.max(startedAt, receiptSince.get(frame.service_id) || startedAt);
                        if (frame.enabled && frame.state !== 'ended' && Number.isFinite(at) && at + 20 >= floor && at <= Date.now() + 60000) {
                            {
                                const history = receiptHistory.get(frame.service_id) || {at:0, retired:new Set()};
                                if (frame.receive_id && frame.receive_id !== event.frame_id) {
                                    // Fresh official events can move an unresolved channel
                                    // row to its next stream, but cannot switch back to an
                                    // old room because of delayed/history comments.
                                    if (at <= history.at || history.retired.has(event.frame_id) || history.retired.size >= 32) {
                                        dropped++; return comment;
                                    }
                                    history.retired.add(frame.receive_id);
                                }
                                frame.receive_id = event.frame_id;
                                history.at = Math.max(history.at, at);
                                receiptHistory.set(frame.service_id, history);
                            }
                            if (JSON.stringify(frame) !== JSON.stringify(old)) {
                                services.set(frame.service_id, frame); revision++;
                            }
                        }
                    }
                    if (queue.length >= 500) dropped++;
                    else { queue.push(event); void drain(); }
                } else if (comment?.service === 'youtube' && comment.data && !comment.data.autoModerated && comment.data.meta?.type !== 'system') {
                    dropped++;
                }
            }
            return comment;
        },
        async request(req) {
            if (req.method !== 'GET') return {code: 405, response: {error: 'GET only'}};
            return {code: 200, response: ready ? {ready: true, control: ready.control} : {ready: false, message: error}};
        },
        destroy() {
            generation++; clearInterval(timer); timer = null; ready = null; queue = []; services = null;
            const owned = worker; worker = null;
            // EOF closes only this worker. No process-name kills, no OneComme changes.
            if (owned) {
                owned.stdin.end();
                const timeout = setTimeout(() => { if (owned.exitCode === null) owned.kill(); }, 12000);
                timeout.unref?.(); owned.once('exit', () => clearTimeout(timeout));
            }
        }
    };
}
module.exports = createPlugin();
// Non-enumerable exports used by the contract tests, not OneComme permissions.
Object.defineProperties(module.exports, {convert: {value: convert}, createPlugin: {value: createPlugin}, serviceFrame:{value:serviceFrame}});
