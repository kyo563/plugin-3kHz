const test = require('node:test');
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const {PassThrough} = require('node:stream');
const {convert, createPlugin} = require('../onecomme/plugin.js');
function comment() {
    return {service: 'youtube', name: '配信', data: {id: 'message', liveId: 'stream', userId: 'UC' + 'a'.repeat(22), name: 'User', screenName: '@handle', comment: '参加希望 『Name』', timestamp: new Date().toISOString()}};
}
test('maps documented fields and never uses display names as identity', () => {
    const c = comment();
    assert.equal(convert(c).comment.userKey, c.data.userId);
    assert.equal(convert(c).comment.youtubeHandle, '@handle');
    assert.equal(convert({...c, service: 'twitch'}), null);
    c.data.userId = '@handle'; assert.equal(convert(c).comment.userKey, '@handle');
    c.data.userId = 'opaque-onecomme-id'; assert.equal(convert(c).comment.userKey, 'opaque-onecomme-id');
    for (const id of ['', '   ', 'x\n', 'a'.repeat(513)]) {
        c.data.userId = id; assert.equal(convert(c), null);
    }
    c.data.userId = 'UC' + 'a'.repeat(22); c.data.comment = 'a'.repeat(4097);
    assert.equal(convert(c), null);
});
test('memo uses matching official UserNameData, retaining absent vs explicit empty', () => {
    const c = comment(), data = {id:c.data.userId, service:'youtube', memo:'<b>private</b>'};
    assert.equal(convert(c, data).comment.oneCommeMemo, data.memo);
    assert.equal(convert(c, {...data, id:'other'}).comment.oneCommeMemo, null);
    assert.equal(convert(c, {...data, service:'twitch'}).comment.oneCommeMemo, null);
    assert.equal(convert(c).comment.oneCommeMemo, null);
    assert.equal(convert(c, {...data, memo:''}).comment.oneCommeMemo, '');
    assert.equal(convert(c, {...data, memo:'a'.repeat(5000)}).comment.oneCommeMemo.length, 4000);
});
test('worker ownership, exact pass-through, bounded forwarding and no secrets in plugin response', async () => {
    const worker = new EventEmitter();
    worker.stdin = new PassThrough(); worker.stdout = new PassThrough(); worker.stderr = new PassThrough();
    worker.exitCode = null; worker.kill = () => assert.fail('unexpected kill');
    let options, resolveRequest;
    const calls = [];
    const p = createPlugin({spawnWorker: (exe, args, opts) => { options = opts; return worker; },
        http: async (url, opts) => { calls.push([url, opts]); await new Promise(r => resolveRequest = r); return {ok: true}; }});
    p.init({dir: 'C:/plugin'});
    const original = comment();
    assert.equal(p.filterComment(original), original);
    assert.equal(calls.length, 0);
    assert.equal(options.windowsHide, true); assert.equal(options.shell, false);
    worker.stdout.write(JSON.stringify({base: 'http://127.0.0.1:18765', control: 'http://127.0.0.1:18765/control#key=' + 'a'.repeat(43), ingest: 'b'.repeat(43)}) + '\n');
    const response = await p.request({method: 'GET'});
    assert.equal(response.response.ready, true);
    assert.equal(JSON.stringify(response).includes('b'.repeat(43)), false);
    assert.equal(p.filterComment(original), original);
    assert.equal(calls.length, 1);
    assert.equal(JSON.parse(calls[0][1].body).comment.message, original.data.comment);
    for (let i = 0; i < 700; i++) p.filterComment(comment());
    assert.equal(calls.length, 1); // serial, not 700 concurrent HTTP requests
    p.destroy(); resolveRequest();
    worker.exitCode = 0; worker.emit('exit', 0);
    assert.equal(worker.stdin.writableEnded, true);
    assert.equal((await p.request({method: 'GET'})).response.ready, false);
});
