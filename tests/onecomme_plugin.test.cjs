const test = require('node:test');
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const {PassThrough} = require('node:stream');
const {convert, createPlugin, serviceFrame} = require('../onecomme/plugin.js');
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
test('membership flag does not exclude ordinary participation comments', () => {
    const c = comment();
    c.data.isMember = true;
    assert.equal(convert(c).comment.message, c.data.comment);
    assert.equal(convert(c).comment.userKey, c.data.userId);
});

async function receivingFixture(initial) {
    const worker=new EventEmitter();
    worker.stdin=new PassThrough(); worker.stdout=new PassThrough(); worker.stderr=new PassThrough(); worker.exitCode=null;
    const calls=[];
    const p=createPlugin({spawnWorker:()=>worker,http:async(url,options)=>{
        calls.push({url,body:JSON.parse(options.body)}); return {ok:true};
    }});
    p.init({dir:'C:/plugin'}, initial);
    worker.stdout.write(JSON.stringify({base:'http://127.0.0.1:18765',control:'http://127.0.0.1:18765/control#key='+'a'.repeat(43),ingest:'b'.repeat(43)})+'\n');
    await new Promise(r=>setImmediate(r));
    return {p,calls,async flush(){await new Promise(r=>setImmediate(r));},close(){p.destroy();worker.exitCode=0;worker.emit('exit',0);}};
}
const restrictedService = () => ({id:'restricted-row',name:'限定配信',enabled:true,url:'https://www.youtube.com/@channel/live',meta:{}});

test('restricted receipt uses official Service and liveId before forwarding; repeated snapshots retain it',async()=>{
    const s=restrictedService(), f=await receivingFixture({services:[s]});
    try {
        const c=comment(); c.data.liveId='restricted-room'; c.data.isMember=true;
        f.p.filterComment(c,s); await f.flush();
        const heartbeat=f.calls.filter(c=>c.url.endsWith('/heartbeat')).at(-1);
        assert.equal(heartbeat.body.services[0].receive_id,'restricted-room');
        assert.equal(heartbeat.body.services[0].id,'');
        const forwarded=f.calls.filter(c=>c.url.endsWith('/comment')).at(-1);
        assert.equal(forwarded.body.service_id,s.id);
        assert.ok(f.calls.indexOf(heartbeat)<f.calls.indexOf(forwarded));
        f.p.subscribe('services',[s]); await f.flush();
        assert.equal(f.calls.at(-1).body.services[0].receive_id,'restricted-room');
        f.p.subscribe('meta.clear',s.id); await f.flush();
        assert.equal(f.calls.at(-1).body.services[0].receive_id,'');
    } finally {f.close();}
});

test('official receiving callback supplies a source when initial metadata is absent; old history never learns a target',async()=>{
    const s=restrictedService(), f=await receivingFixture();
    try {
        const old=comment(); old.data.timestamp=new Date(Date.now()-60000).toISOString();
        f.p.filterComment(old,s); await f.flush();
        assert.equal(f.calls.filter(c=>c.url.endsWith('/heartbeat')).length,0);
        f.p.filterComment(comment(),s); await f.flush();
        assert.equal(f.calls.filter(c=>c.url.endsWith('/heartbeat')).at(-1).body.services[0].receive_id,'stream');
    } finally {f.close();}
});

test('unresolved receiving row follows a fresh next stream but never switches back to delayed old rooms',async()=>{
    const s=restrictedService(), f=await receivingFixture({services:[s]});
    try {
        const a=comment(); a.data.liveId='room-a';
        f.p.filterComment(a,s); await f.flush();
        const b=comment(); b.data.liveId='room-b'; b.data.timestamp=new Date(Date.parse(a.data.timestamp)+100).toISOString();
        f.p.filterComment(b,s); await f.flush();
        assert.equal(f.calls.filter(c=>c.url.endsWith('/heartbeat')).at(-1).body.services[0].receive_id,'room-b');
        const count=f.calls.filter(c=>c.url.endsWith('/comment')).length;
        for (const at of [a.data.timestamp,new Date(Date.parse(b.data.timestamp)+100).toISOString()]) {
            a.data.timestamp=at; f.p.filterComment(a,s); await f.flush();
        }
        assert.equal(f.calls.filter(c=>c.url.endsWith('/comment')).length,count);
        assert.equal(f.calls.filter(c=>c.url.endsWith('/heartbeat')).at(-1).body.services[0].receive_id,'room-b');
    } finally {f.close();}
});

test('changed URL, explicit video, disconnect and removal invalidate restricted receipt; old resolved comments do not redirect',async()=>{
    for (const replacement of [null,{...restrictedService(),enabled:false},{...restrictedService(),url:'https://www.youtube.com/@other/live'},
        {...restrictedService(),url:'https://www.youtube.com/watch?v=lmnopqrstuv'}]) {
        const s=restrictedService(), f=await receivingFixture({services:[s]});
        try {
            f.p.filterComment(comment(),s); await f.flush();
            f.p.subscribe('services',replacement?[replacement]:[]); await f.flush();
            assert.ok(!f.calls.at(-1).body.services[0]?.receive_id);
            if(replacement?.url.includes('watch')) {
                const stale=comment(); stale.data.liveId='abcdefghijk';
                stale.data.timestamp=new Date(Date.now()-60000).toISOString();
                f.p.filterComment(stale,replacement); await f.flush();
                assert.ok(!f.calls.filter(c=>c.url.endsWith('/heartbeat')).at(-1).body.services[0]?.receive_id);
            }
        } finally {f.close();}
    }
});

test('displayed YouTube comments supply the source without URL, service list or video metadata',async()=>{
    const s={id:'private-row',name:'Restricted',enabled:true};
    const f=await receivingFixture({services:[s]});
    try {
        const c=comment();c.data.liveId='private-room';c.data.isMember=true;
        assert.equal(f.p.filterComment(c,s),c);await f.flush();
        const hb=f.calls.filter(c=>c.url.endsWith('/heartbeat')).at(-1).body.services[0];
        assert.equal(hb.id,'');assert.equal(hb.url,'');assert.equal(hb.receive_id,'private-room');
        assert.equal(f.calls.at(-1).body.comment.message,c.data.comment);
        f.p.subscribe('services',[s]);await f.flush();
        assert.equal(f.calls.at(-1).body.services[0].receive_id,'private-room');
        f.p.subscribe('services',[]);await f.flush();
        f.p.filterComment(comment(),s);await f.flush();
        assert.deepEqual(f.calls.filter(c=>c.url.endsWith('/heartbeat')).at(-1).body.services,[]);
    } finally {f.close();}
});

test('official opaque liveId binds even when public video metadata is already present',async()=>{
    for(const url of ['https://www.youtube.com/watch?v=abcdefghijk','https://www.youtube.com/@channel/live']) {
        const s={...restrictedService(),url,meta:{url:'https://www.youtube.com/watch?v=abcdefghijk'}};
        const f=await receivingFixture({services:[s]});
        try {
            f.p.filterComment(comment(),s); await f.flush();
            const source=f.calls.filter(c=>c.url.endsWith('/heartbeat')).at(-1).body.services[0];
            assert.equal(source.receive_id,'stream'); assert.equal(source.id,'abcdefghijk');
            assert.equal(f.calls.at(-1).body.service_id,s.id);
        } finally {f.close();}
    }
});

test('public service metadata resolves scheduled videos without leaking account fields', () => {
    const s={id:'row',name:'枠',enabled:true,url:'https://www.youtube.com/@channel/live',meta:{url:'https://www.youtube.com/watch?v=abcdefghijk',title:'開始前',startTime:Date.now()+60000,loggedName:'private',loggedIn:true}};
    const f=serviceFrame(s);
    assert.equal(f.id,'abcdefghijk'); assert.equal(f.state,'upcoming'); assert.equal(f.name,'開始前');
    assert.equal(JSON.stringify(f).includes('private'),false);
    assert.equal(serviceFrame({...s,url:'https://youtu.be/lmnopqrstuv'}).id,'lmnopqrstuv');
    assert.equal(serviceFrame({...s,url:'https://youtube.com.evil.test/watch?v=abcdefghijk',meta:{}}),null);
    assert.equal(serviceFrame({...s,meta:{}}).id,'');
    assert.equal(serviceFrame({...s,enabled:'true'}),null);
});

test('initial services and updates arrive before comments; service removal clears snapshot', async () => {
    const worker=new EventEmitter();
    worker.stdin=new PassThrough(); worker.stdout=new PassThrough(); worker.stderr=new PassThrough(); worker.exitCode=null;
    const calls=[];
    const p=createPlugin({spawnWorker:()=>worker,http:async(url,opts)=>{calls.push([url,JSON.parse(opts.body)]);return {ok:true};}});
    const s={id:'row',name:'枠',enabled:true,url:'https://www.youtube.com/watch?v=abcdefghijk'};
    p.init({dir:'C:/plugin'},{services:[s]});
    assert.ok(p.permissions.includes('services')); assert.ok(p.permissions.includes('meta'));
    worker.stdout.write(JSON.stringify({base:'http://127.0.0.1:18765',control:'http://127.0.0.1:18765/control#key='+'a'.repeat(43),ingest:'b'.repeat(43)})+'\n');
    p.filterComment(comment());
    await new Promise(r=>setImmediate(r));
    assert.ok(calls[0][0].endsWith('/heartbeat')); assert.equal(calls[0][1].services[0].id,'abcdefghijk');
    assert.ok(calls[1][0].endsWith('/comment'));
    p.subscribe('meta',{type:'youtube',service:s,data:{title:'新タイトル',isLive:true}});
    await new Promise(r=>setImmediate(r));
    assert.equal(calls.at(-1)[1].services[0].name,'新タイトル');
    assert.equal(calls.at(-1)[1].services[0].state,'live');
    p.subscribe('services',[]);
    await new Promise(r=>setImmediate(r));
    assert.deepEqual(calls.at(-1)[1].services,[]);
    p.destroy(); worker.exitCode=0; worker.emit('exit',0);
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
