'use strict';
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const assert = require('node:assert/strict');
const {inflateRawSync} = require('node:zlib');

function zipEntries(bytes) {
    const end = bytes.length - 22; // Our generated ZIPs have no archive comment.
    assert.equal(bytes.readUInt32LE(end), 0x06054b50);
    let offset = bytes.readUInt32LE(end + 16);
    const entries = new Map();
    for (let i = 0; i < bytes.readUInt16LE(end + 10); i++) {
        assert.equal(bytes.readUInt32LE(offset), 0x02014b50);
        const method = bytes.readUInt16LE(offset + 10);
        const size = bytes.readUInt32LE(offset + 20);
        const nameLength = bytes.readUInt16LE(offset + 28);
        const name = bytes.subarray(offset + 46, offset + 46 + nameLength).toString('utf8');
        const local = bytes.readUInt32LE(offset + 42);
        assert.equal(bytes.readUInt32LE(local), 0x04034b50);
        const start = local + 30 + bytes.readUInt16LE(local + 26) + bytes.readUInt16LE(local + 28);
        const data = bytes.subarray(start, start + size);
        assert.ok(method === 0 || method === 8);
        entries.set(name, method === 8 ? inflateRawSync(data) : data);
        offset += 46 + nameLength + bytes.readUInt16LE(offset + 30) + bytes.readUInt16LE(offset + 32);
    }
    return entries;
}

let stage = 'start';
async function main() {
    const dir = path.resolve(process.argv[2] || 'dist/onecomme-prototype/sankagata-seiretsu');
    const {createPlugin} = require(path.join(dir, 'plugin.js'));
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
        // Node fetch can replace Sec-Fetch-Mode with cors. Send the actual
        // browser navigation headers through HTTP for this boundary test.
        const html = await new Promise((resolve, reject) => {
            require('node:http').get('http://127.0.0.1:18765/control', {headers: {'Sec-Fetch-Site': 'cross-site', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document'}}, r => {
                if (r.statusCode !== 200) { r.resume(); reject(new Error('navigation rejected')); return; }
                let text = ''; r.setEncoding('utf8'); r.on('data', part => text += part); r.on('end', () => resolve(text));
            }).on('error', reject);
        });
        assert.ok(html.includes('onecomme-stream')); assert.ok(!html.includes('youtube-key'));
        stage = 'control-display';
        assert.ok(html.includes('id="control-display-options"'));
        for (const asset of ['control-display.js', 'control-display.css']) {
            assert.equal((await fetch('http://127.0.0.1:18765/static/' + asset)).status, 200);
        }
        const display = {avatar: true, username: true, alias: true, memo: false, count: false, order: true};
        assert.equal((await api('/api/settings/control-display')).memo, true);
        assert.deepEqual(await api('/api/settings/control-display', display), display);
        stage = 'obs-named-drag';
        const obsSetup = await fetch('http://127.0.0.1:18765/obs-setup').then(r => r.text());
        const obsLink = obsSetup.match(/id="obs-drag-source"[^>]*href="([^"]+)"/)[1].replaceAll('&amp;', '&');
        const obsUrl = new URL(obsLink);
        assert.equal(obsUrl.pathname, '/onecomme-overlay');
        assert.equal(obsUrl.searchParams.get('layer-name'), '待機列表示');
        assert.equal(obsUrl.searchParams.get('layer-width'), '1200');
        assert.equal(obsUrl.searchParams.get('layer-height'), '600');
        assert.equal(obsUrl.hash, '');
        assert.equal((await fetch(obsLink)).status, 200);
        assert.equal((await fetch('http://127.0.0.1:18765/static/onecomme-obs-setup.css')).status, 200);
        stage = 'template-download';
        const templateResponse = await fetch('http://127.0.0.1:18765/api/onecomme/template', {
            headers: {Authorization: 'Bearer ' + key}, signal: AbortSignal.timeout(5000)});
        assert.equal(templateResponse.status, 200);
        assert.ok(templateResponse.headers.get('content-type').includes('application/zip'));
        assert.ok(templateResponse.headers.get('content-disposition').includes('Taikiretsu-Template.zip'));
        const downloaded = zipEntries(Buffer.from(await templateResponse.arrayBuffer()));
        const packaged = zipEntries(fs.readFileSync(path.join(dir, 'Taikiretsu-Template.zip')));
        assert.equal(downloaded.size, 5);
        assert.deepEqual(downloaded, packaged);
        assert.equal(JSON.parse(downloaded.get('taikiretsu-display/template.json')).name, '待機列整理アプリ｜OBS表示');
        assert.deepEqual(downloaded.get('taikiretsu-display/thumb.png'),
            fs.readFileSync(path.join(__dirname, '../static/onecomme-template/thumb.png')));
        stage = 'bot-settings';
        const settingsPage = await fetch('http://127.0.0.1:18765/settings?tab=bot', {headers: {Authorization: 'Bearer ' + key}}).then(r => r.text());
        assert.ok(settingsPage.includes('id="settings-bot-panel"'));
        assert.ok(settingsPage.includes('<small>' + plugin.version + '</small>'));
        assert.ok(settingsPage.includes('<h2>通知選択</h2>'));
        assert.ok(settingsPage.includes('name="show_participation_number"'));
        for (const name of ['background_color','background_transparency','auto_fit_font','text_bold','text_shadow']) assert.ok(settingsPage.includes('name="' + name + '"'));
        assert.ok(!settingsPage.includes('Botを使わなくても'));
        let bot = await api('/api/bot');
        assert.equal(bot.settings.enabled, false);
        assert.equal(bot.settings.interval_minutes, 30);
        assert.equal(bot.authenticated, false);
        bot = await api('/api/bot/settings', {enabled: false, announce_now: false, reply_position: true, periodic: false, interval_minutes: 15});
        assert.equal(bot.settings.announce_now, false);
        assert.equal(bot.settings.interval_minutes, 15);
        function event(id, message) { return {service: 'youtube', name: '試験配信', data: {id, liveId: 'test-stream', userId: 'UC' + 'a'.repeat(22), name: '試験参加者', timestamp: new Date().toISOString(), comment: message}}; }
        stage = 'discover-stream';
        plugin.filterComment(event('before', '参加希望'));
        await until(async () => (await api('/api/onecomme/status')).frames.length === 1);
        assert.equal((await api('/api/state')).current.length, 0);
        await api('/api/onecomme/select', {frame_id: 'test-stream'});
        stage = 'join';
        plugin.filterComment(event('after', '参加希望 『Test』'), null, {id:'UC'+'a'.repeat(22), memo:'PRIVATE MEMO'});
        await until(async () => (await api('/api/state')).current.length === 1);
        assert.equal((await api('/api/state')).current[0].declared_player_name, 'Test');
        assert.equal((await api('/api/state')).current[0].onecomme_memo, 'PRIVATE MEMO');
        const opaque = event('opaque', '参加希望 名前採用しない');
        opaque.data.userId = 'onecomme-opaque-user';
        plugin.filterComment(opaque);
        await until(async () => (await api('/api/state')).current.length === 2);
        assert.equal((await api('/api/state')).current[1].declared_player_name, '試験参加者');
        stage = 'heartbeat';
        await until(async () => (await api('/api/onecomme/status')).connected);
        stage = 'overlay';
        assert.equal((await api('/api/overlay-state')).now_view[0].display_name, '試験参加者');
        assert.ok(!JSON.stringify(await api('/api/overlay-state')).includes('PRIVATE MEMO'));
        stage = 'overlay-number';
        assert.equal((await api('/api/settings/overlay')).show_participation_number, false);
        const systemFonts = await api('/api/fonts/system');
        assert.ok(systemFonts.length > 0 && systemFonts.every(f => f.id.startsWith('system:')));
        assert.ok(settingsPage.includes('id="obs-font-select"'));
        const fontSettings = {all:'default', ui_body:'meiryo', obs_all:systemFonts[0].id};
        await api('/api/settings/overlay', {name_mode:'declared', show_participation_number:true, background_color:'#123456', background_transparency:35, font_size:56, auto_fit_font:false, text_bold:false, text_shadow:false, fonts:fontSettings});
        assert.equal((await api('/api/overlay-state')).now_view[0].display_name, 'Test *1回目');
        assert.equal((await api('/api/overlay-state')).now_view[2].display_name, '参加者募集中');
        assert.equal(fs.readFileSync(sentinel, 'utf8'), 'unchanged');
        assert.equal(fs.existsSync(path.join(old, 'must-not-exist.sqlite3')), false);
        assert.ok(fs.existsSync(path.join(local, 'WaitingListAppOneComme', 'waiting_list.sqlite3')));
        stage = 'control-display-restart';
        plugin.destroy();
        await until(() => child.exitCode !== null, 15000);
        plugin.init({dir});
        await until(async () => (await plugin.request({method: 'GET'})).response.ready, 30000);
        assert.deepEqual(await api('/api/settings/control-display'), display);
        assert.equal((await api('/api/state')).current.length, 2);
        assert.equal((await api('/api/overlay-state')).now_view[0].display_name, 'Test *1回目');
        assert.equal((await api('/api/bot')).settings.enabled, false);
        const appearance = (await api('/api/overlay-state')).appearance;
        assert.equal(appearance.background_color, '#123456');
        assert.equal(appearance.background_transparency, 35);
        assert.equal(appearance.font_size, 56);
        assert.equal(appearance.auto_fit_font, false);
        assert.equal(appearance.text_bold, false);
        assert.equal(appearance.text_shadow, false);
        assert.equal(appearance.fonts.obs_all, fontSettings.obs_all);
        assert.equal(appearance.fonts.ui_body, 'meiryo');
        stage = 'protected-next';
        for (let i = 0; i < 7; i++) await api('/api/control/add-user', {user_id:'priority-smoke-' + i, display_name:'Priority ' + i});
        const beforePriority = await api('/api/state');
        if (!beforePriority.priority_mode) await api('/api/control/toggle-priority');
        for (const user of beforePriority.waiting) await api('/api/control/correct-count', {user_id:user.user_id, participation_count:9});
        await api('/api/control/add-user', {user_id:'priority-new', display_name:'New'});
        const afterPriority = await api('/api/state');
        assert.deepEqual(afterPriority.current.map(u=>u.user_id), beforePriority.current.map(u=>u.user_id));
        assert.deepEqual(afterPriority.waiting.slice(0,3).map(u=>u.user_id), beforePriority.waiting.slice(0,3).map(u=>u.user_id));
        assert.equal(afterPriority.waiting[3].user_id, 'priority-new');
    } finally {
        plugin.destroy();
        if (child) await until(() => child.exitCode !== null, 15000);
    }
    let listening = false;
    try { await fetch('http://127.0.0.1:18765/control', {signal: AbortSignal.timeout(1000)}); listening = true; } catch (_) {}
    assert.equal(listening, false);
    console.log(JSON.stringify({ok: true, packaged_worker: true, plugin_lifecycle: true, management_page: true, control_display_restart: true, protected_next: true, overlay_number: true, obs_named_drag: true, template_download: true, thumbnail: true, join: true, isolated_data: true, stopped: true}));
}
main().catch(() => { console.error('OneComme prototype smoke failed at ' + stage); process.exitCode = 1; });
