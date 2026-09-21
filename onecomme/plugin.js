'use strict';
const {spawn} = require('node:child_process');
const path = require('node:path');

function convert(comment) {
    const d = comment?.data;
    if (comment?.service !== 'youtube' || !d || d.meta?.type === 'system' || d.meta?.anonymity || d.autoModerated) return null;
    if (typeof d.userId !== 'string' || !/^UC[A-Za-z0-9_-]{22}$/.test(d.userId)) return null;
    if (![d.id, d.liveId, d.name, d.timestamp].every(v => typeof v === 'string' && v.length > 0)) return null;
    if (typeof d.comment !== 'string' || d.comment.length > 4096 || d.name.length > 200 || d.id.length > 512 || d.liveId.length > 200) return null;
    const handle = [d.screenName, d.name].find(v => typeof v === 'string' && /^@[^\s]{1,199}$/.test(v));
    return {
        frame_id: d.liveId, frame_name: `${String(comment.name || 'YouTube').slice(0, 150)} (${d.liveId})`.slice(0, 200),
        comment: {source: 'youtube', externalMessageId: d.id, receivedAt: d.timestamp,
            userKey: d.userId, displayName: d.name, youtubeNickname: d.name,
            youtubeHandle: handle || null, avatarUrl: typeof d.profileImage === 'string' ? d.profileImage : null,
            message: d.comment}
    };
}

function createPlugin({spawnWorker = spawn, http = fetch} = {}) {
    let worker = null, ready = null, timer = null, buffer = '', generation = 0;
    let queue = [], draining = false, heartbeatBusy = false, dropped = 0;
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
            while (queue.length && ready && current === generation) {
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
        uid: 'jp.kyo563.sankagata-seiretsu', version: '1.1.0', author: 'kyo563',
        url: 'http://localhost:11180/plugins/jp.kyo563.sankagata-seiretsu/index.html',
        permissions: ['filter.comment'],
        init({dir}) {
            if (worker) return;
            generation++; ready = null; queue = []; buffer = ''; dropped = 0; error = '起動中です';
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
                        } else error = '処理を起動できませんでした。重複起動やポート18765を確認してください';
                    } catch (_) { error = '起動応答を読み取れませんでした'; }
                }
            });
            // Drain diagnostics without retaining or exposing their contents.
            worker.stderr.on('data', () => {});
            worker.stdin.on('error', () => {});
            worker.on('error', () => { if (mine === generation) { ready = null; error = '同梱のruntimeを起動できません。ZIPの展開状態を確認してください'; } });
            worker.on('exit', () => { if (mine === generation) { ready = null; worker = null; queue = []; error = '処理が終了しました。プラグインを無効にしてから有効にしてください'; } });
            timer = setInterval(async () => {
                if (!ready || heartbeatBusy) return;
                heartbeatBusy = true;
                try { await post('/api/onecomme/heartbeat', {dropped}, ready); } catch (_) {}
                finally { heartbeatBusy = false; }
                await drain();
            }, 1500);
            timer.unref?.();
        },
        filterComment(comment) {
            // Never change, suppress, or wait for processing of OneComme comments.
            if (ready) {
                const event = convert(comment);
                if (event) {
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
            generation++; clearInterval(timer); timer = null; ready = null; queue = [];
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
Object.defineProperties(module.exports, {convert: {value: convert}, createPlugin: {value: createPlugin}});
