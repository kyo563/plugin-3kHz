'use strict';
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const assert = require('node:assert/strict');
const {createPlugin} = require('../onecomme/plugin.js');

let stage = 'start';
async function main() {
    const dir = path.resolve(process.argv[2] || 'dist/onecomme-prototype/sankagata-seiretsu');
    const local = fs.mkdtempSync(path.join(os.tmpdir(), 'queue-onecomme-smoke-'));
    const old = path.join(local, 'WaitingListApp'); fs.mkdirSync(old);
    const sentinel = path.join(old, 'preserve.txt'); fs.writeFileSync(sentinel, 'unchanged');
    let child;
    const plugin = createPlugin({http: async (url, options) => { const r = await fetch(url, options); if (url.endsWith('/comment')) { const v = await r.clone().json(); if (v.status !== 'accepted' && v.status !== 'unselected') console.log(JSON.stringify({comment_status: v.status, http_status: r.status})); } return r; }, spawnWorker: (exe, args, options) => {
        child = spawn(exe, args, {...options, env: {...process.env, LOCALAPPDATA: local,
            WAITING_LIST_DATA_DIR: old, WAITING_LIST_DB_PATH: path.join(old, 'must-not-exist.sqlite3')}});
        return child;
    }});
    const delay = ms => new Promise(r => setTimeout(r, ms));
    async function until(fn, timeout = 15000) {
        const end = Date.now() + timeout;
        while (Date.now() < end) { const value = await fn(); if (value) return value; await delay(100); }
        throw new Error('smoke timeout');
    }
    try {
        plugin.init({dir});
        stage = 'worker-ready';
        const ready = await until(async () => { const r = await plugin.request({method: 'GET'}); return r.response.ready && r.response; }, 30000);
        const key = new URL(ready.control).hash.slice(5);
        async function api(endpoint, body) {
            const r = await fetch('http://127.0.0.1:18765' + endpoint, {headers: {Authorization: 'Bearer ' + key, 'Content-Type': 'application/json'},
                method: body ? 'POST' : 'GET', body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(5000)});
            assert.equal(r.status, 200); return r.json();
        }
        stage = 'management-page';
        const html = await (await fetch('http://127.0.0.1:18765/control')).text();
        assert.ok(html.includes('onecomme-stream')); assert.ok(!html.includes('youtube-key'));
        function event(id, message) { return {service: 'youtube', name: '試験配信', data: {id, liveId: 'test-stream', userId: 'UC' + 'a'.repeat(22), name: '試験参加者', timestamp: new Date().toISOString(), comment: message}}; }
        stage = 'discover-stream';
        plugin.filterComment(event('before', '参加希望'));
        await until(async () => (await api('/api/onecomme/status')).frames.length === 1);
        assert.equal((await api('/api/state')).current.length, 0);
        await api('/api/onecomme/select', {frame_id: 'test-stream'});
        stage = 'join';
        plugin.filterComment(event('after', '参加希望 『Test』'));
        await until(async () => (await api('/api/state')).current.length === 1);
        assert.equal((await api('/api/state')).current[0].declared_player_name, 'Test');
        stage = 'heartbeat';
        await until(async () => (await api('/api/onecomme/status')).connected);
        stage = 'overlay';
        assert.equal((await api('/api/overlay-state')).now_view[0].display_name, '試験参加者');
        assert.equal(fs.readFileSync(sentinel, 'utf8'), 'unchanged');
        assert.equal(fs.existsSync(path.join(old, 'must-not-exist.sqlite3')), false);
        assert.ok(fs.existsSync(path.join(local, 'WaitingListAppOneComme', 'waiting_list.sqlite3')));
    } finally {
        plugin.destroy();
        if (child) await until(() => child.exitCode !== null, 15000);
    }
    let listening = false;
    try { await fetch('http://127.0.0.1:18765/control', {signal: AbortSignal.timeout(1000)}); listening = true; } catch (_) {}
    assert.equal(listening, false);
    console.log(JSON.stringify({ok: true, packaged_worker: true, plugin_lifecycle: true, management_page: true, join: true, isolated_data: true, stopped: true}));
}
main().catch(() => { console.error('OneComme prototype smoke failed at ' + stage); process.exitCode = 1; });
