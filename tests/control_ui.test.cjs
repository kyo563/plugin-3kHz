const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const state = revision => ({revision, undo_available:true, is_open:true, priority_mode:true,
    current:[], waiting:[], now_view:[], next_view:[], queue_view:[], logs:[]});
function harness(fetcher) {
    const elements = new Map(), handlers = {};
    let modal = false, created = 0;
    const element = key => {
        if (!elements.has(key)) elements.set(key, {textContent:'', value:'', dataset:{}, style:{},
            children:[],appendChild(child){this.children.push(child);},attributes:{},setAttribute(name,value){this.attributes[name]=value;},disabled:false, checked:false, hidden:false, addEventListener(){}, append(){},
            replaceChildren(){}, closest(){return {open:false};}, focus(){}, files:[]});
        return elements.get(key);
    };
    const sandbox = {console:{error(){}}, AbortSignal, setTimeout(){}, URL,
        document:{hidden:false, hasFocus:()=>true,
            querySelector:s => s === 'dialog[open]' ? (modal ? {} : null) : element(s),
            querySelectorAll:()=>[], createElement:()=>element('created-'+(++created)),
            addEventListener:(name, fn)=>handlers[name]=fn},
        window:{location:{origin:'http://127.0.0.1'},confirm:()=>true},
        fetch:(url, options) => url === '/api/capabilities' ? Promise.resolve({ok:true,json:async()=>({development:false})}) : fetcher(url, options)};
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync('static/control.js','utf8').replace('poll();','/* polling tested separately */'), sandbox);
    return {sandbox,element,handlers,modal:()=>{modal=true;}};
}
const reply = data => ({ok:true,json:async()=>data});

test('OneComme memo is rendered as text, never HTML', () => {
    const h = harness(()=>Promise.resolve(reply(state(1))));
    const row = h.sandbox.participantItem({user_id:'id',display_name:'Name',onecomme_memo:'<img src=x onerror=alert(1)>'});
    const memo = row.children.find(child=>child.className==='participant-memo');
    assert.equal(memo.textContent, ' / <img src=x onerror=alert(1)>');
    assert.equal(memo.innerHTML, undefined);
});
test('rapid next clicks send only one mutation', async()=>{
    let calls=0, release;
    const h=harness((url, options)=>{
        if(options?.method==='POST') {calls++;return new Promise(resolve=>release=resolve);}
        return Promise.resolve(reply(state(1)));
    });
    const first=h.sandbox.post('/api/control/move-next');
    const second=h.sandbox.post('/api/control/move-next');
    assert.equal(calls,1);
    release(reply(state(1))); await Promise.all([first,second]);
});
test('older polling response cannot overwrite a newer display', async()=>{
    const replies=[];
    const h=harness(()=>new Promise(resolve=>replies.push(resolve)));
    const older=h.sandbox.refresh(), newer=h.sandbox.refresh();
    replies[1](reply({...state(2),is_open:false})); await newer;
    replies[0](reply(state(1))); await older;
    assert.equal(h.element('#open').textContent,'受付状態: 受付終了');
});
test('shortcuts cannot mutate while a modal dialog is open', ()=>{
    let mutations=0;
    const h=harness(()=>{mutations++;return Promise.resolve(reply(state(1)));});
    h.element('#shortcuts-enabled').checked=true; h.modal();
    h.handlers.keydown({altKey:true,key:'n',target:{closest:()=>null},preventDefault(){}});
    assert.equal(mutations,0);
});

test('network failure releases mutation guard and allows retry', async()=>{
    let attempts=0;
    const h=harness((url,options)=>{
        if(options?.method==='POST' && ++attempts===1) return Promise.reject(new TypeError('network disconnected'));
        return Promise.resolve(reply(state(2)));
    });
    assert.equal(await h.sandbox.post('/api/control/move-next'),false);
    assert.equal(await h.sandbox.post('/api/control/move-next'),true);
    assert.equal(attempts,2);
});
test('failed state fetch preserves last rendered state', async()=>{
    let attempts=0;
    const h=harness(()=>++attempts===1?Promise.resolve(reply(state(1))):Promise.reject(new Error('offline')));
    await h.sandbox.refresh(); await h.sandbox.refresh();
    assert.equal(h.element('#open').textContent,'受付状態: 受付中');
    assert.match(h.element('#conn').textContent,/失敗/);
});
test('mutation requests have a bounded network wait', async()=>{
    let signal;
    const h=harness((url,options)=>{if(options?.method==='POST') signal=options.signal; return Promise.resolve(reply(state(1)));});
    await h.sandbox.post('/api/control/move-next');
    assert.ok(signal instanceof AbortSignal);
});

function desktopHarness(settings, {pending=false, failComplete=false}={}) {
    const elements=new Map(); const sent=[];
    const el=id=>{
        if(!elements.has(id)) elements.set(id,{hidden:false,disabled:false,open:false,textContent:'',
            addEventListener(){},showModal(){this.open=true;},close(){this.open=false;}});
        return elements.get(id);
    };
    const scope={window:{},document:{hidden:true,getElementById:el,querySelector:()=>null},
        mutationPending:pending,AbortSignal,setTimeout(){},location:{origin:'http://127.0.0.1'},
        navigator:{clipboard:{writeText:async()=>{}}},
        fetch:async(url)=>{sent.push(url);return {ok:!(failComplete && url.endsWith('onboarding-complete')),json:async()=>settings};}};
    vm.createContext(scope); vm.runInContext(fs.readFileSync('static/desktop-flow.js','utf8'),scope);
    return {scope,el,sent};
}
test('first run guide can be deferred and is recorded',async()=>{
    const h=desktopHarness({available:true,onboarding_completed:false});
    await new Promise(setImmediate);
    assert.equal(h.el('welcome-dialog').open,true);
    await h.el('welcome-later').onclick();
    assert.equal(h.el('welcome-dialog').open,false);
    assert.ok(h.sent.includes('/api/desktop/onboarding-complete'));
});
test('later startups skip guide',async()=>{
    const h=desktopHarness({available:true,onboarding_completed:true}); await new Promise(setImmediate);
    assert.equal(h.el('welcome-dialog').open,false);
});
test('failed onboarding save keeps a retryable guide',async()=>{
    const h=desktopHarness({available:true,onboarding_completed:false},{failComplete:true}); await new Promise(setImmediate);
    await h.el('welcome-done').onclick();
    assert.equal(h.el('welcome-dialog').open,true);
    assert.equal(h.el('welcome-done').disabled,false);
});
test('exit waits for mutation and requires one confirmation',async()=>{
    const h=desktopHarness({available:true,onboarding_completed:true},{pending:true}); await new Promise(setImmediate);
    h.scope.window.showExitDialog(); assert.equal(h.el('exit-dialog').open,false);
    h.scope.mutationPending=false;
    h.scope.window.showExitDialog(); assert.equal(h.el('exit-dialog').open,true);
    h.el('exit-cancel').onclick(); assert.ok(!h.sent.includes('/api/desktop/exit'));
    h.scope.window.showExitDialog(); await h.el('exit-confirm').onclick();
    assert.equal(h.sent.filter(x=>x==='/api/desktop/exit').length,1);
});


test('priority mode exposes ON and OFF visually and to assistive technology',()=>{
 const h=harness(()=>Promise.resolve(reply(state(1))));
 h.sandbox.renderState(state(1));
 assert.match(h.element('#toggle-priority').textContent,/初回参加優先モード：ON/);
 assert.equal(h.element('#toggle-priority').attributes['aria-pressed'],'true');
 assert.equal(h.element('#toggle-priority').className,'priority-on');
 h.sandbox.renderState({...state(2),priority_mode:false});
 assert.equal(h.element('#toggle-priority').attributes['aria-pressed'],'false');
 assert.equal(h.element('#toggle-priority').className,'priority-off');
});


test('total matches is rendered as rounds and follows undo state',()=>{
 const h=harness(()=>Promise.resolve(reply(state(1))));
 h.sandbox.renderState({...state(1),total_match_count:12});
 assert.equal(h.element('#total-matches').textContent,'総対戦回数：12回');
 h.sandbox.renderState({...state(2),total_match_count:11});
 assert.equal(h.element('#total-matches').textContent,'総対戦回数：11回');
});


test('waiting list includes everyone and shows account name before alias', ()=>{
    const h=harness(()=>Promise.resolve(reply(state(1))));
    const waiting=Array.from({length:7},(_,i)=>({user_id:`u${i}`,display_name:`Account${i}`,declared_player_name:i===0?'Edited':null,participation_count:0}));
    h.sandbox.renderState({...state(1),waiting});
    assert.equal(h.element('#waiting').children.length,7);
    assert.equal(h.element('#waiting-count').textContent,'7人');
    assert.equal(h.element('#waiting').children[0].children[0].textContent,'1 次');
    assert.equal(h.element('#waiting').children[3].children[0].textContent,'4');
    assert.equal(h.element('#waiting').children[0].children[2].textContent,'Account0（Edited）');
});

test('drag reorder supports first and last positions across the NEXT boundary', async()=>{
    const bodies=[];
    const h=harness((url,options)=>{
        if(options?.method==='POST') bodies.push(JSON.parse(options.body));
        return Promise.resolve(reply(state(2)));
    });
    const waiting=Array.from({length:7},(_,i)=>({user_id:`u${i}`,display_name:`Account${i}`}));
    h.sandbox.renderState({...state(1),waiting});
    await h.sandbox.reorderWaitingWithDrag('u0','u6',true);
    assert.deepEqual(bodies[0].ordered_user_ids,['u1','u2','u3','u4','u5','u6','u0']);
    h.sandbox.renderState({...state(3),waiting});
    await h.sandbox.reorderWaitingWithDrag('u6','u0',false);
    assert.deepEqual(bodies[1].ordered_user_ids,['u6','u0','u1','u2','u3','u4','u5']);
});


test('sixty waiting participants render without truncation and can move last to first', async () => {
    const bodies = [];
    const h = harness(async (url, options) => {
        if (options?.method === 'POST') bodies.push(JSON.parse(options.body));
        return reply(state(2));
    });
    h.sandbox.window.controlListDisplay = {values: {avatar:true, username:true, alias:true, memo:true, count:true, order:true}};
    const waiting = Array.from({length:60}, (_, i) => ({user_id:`u${i}`, display_name:`User${i}`, participation_count:0}));
    h.sandbox.renderState({...state(1), waiting});
    assert.equal(h.element('#waiting').children.length, 60);
    assert.equal(h.element('#waiting-count').textContent, '60人');
    assert.equal(h.element('#waiting').children.at(-1).dataset.userId, 'u59');
    assert.equal(h.element('#waiting').children.at(-1).draggable, true);
    await h.sandbox.reorderWaitingWithDrag('u59', 'u0');
    assert.deepEqual(bodies[0].ordered_user_ids, ['u59', ...waiting.slice(0, 59).map(u => u.user_id)]);
});

test('waiting avatars are lazy, private and reject foreign URLs', () => {
    const h = harness(async()=>reply(state(1)));
    const user = {user_id:'u1',display_name:'Alice',avatar_url:'https://yt3.ggpht.com/example=s32'};
    const row = h.sandbox.participantItem(user,{listType:'waiting'});
    const avatar = row.children.find(c=>c.className==='participant-avatar');
    const img = avatar.children[0];
    assert.equal(img.src,user.avatar_url);
    assert.equal(img.loading,'lazy');
    assert.equal(img.referrerPolicy,'no-referrer');
    const bad = h.sandbox.participantItem({...user,avatar_url:'https://localhost/private'},{listType:'waiting'});
    assert.equal(bad.children.find(c=>c.className==='participant-avatar').children.length,0);
});

test('OneComme rows split ordered fields and hide only selected information', () => {
    const h = harness(async()=>reply(state(1)));
    const values = {avatar:true, username:true, alias:true, memo:true, count:true, order:true};
    h.sandbox.window.controlListDisplay = {values};
    const user = {user_id:'alice', display_name:'Alice', youtube_handle:'@alice', youtube_nickname:'Nickname',
        declared_player_name:'Declared', onecomme_memo:'<img src=x>\n長いメモ', participation_count:7};
    const row = h.sandbox.participantItem(user, {listType:'waiting', position:0});
    assert.deepEqual(row.children.slice(0,6).map(c=>c.className),
        ['participant-order','participant-avatar','participant-label','participant-alias','participant-memo','participant-count']);
    assert.equal(row.children[2].textContent, '@alice');
    assert.equal(row.children[3].textContent, 'Declared');
    assert.equal(row.children[4].textContent, user.onecomme_memo);
    assert.equal(row.children[4].innerHTML, undefined);
    assert.ok(row.children[4].title.includes(user.onecomme_memo));
    const fallback = h.sandbox.participantItem({...user, declared_player_name:null}, {listType:'now'});
    assert.equal(fallback.children.find(c=>c.className==='participant-alias').textContent, 'Nickname');
    assert.ok(fallback.children.some(c=>c.className==='participant-avatar'));
    for (const key of ['avatar','alias','memo','count','order']) values[key] = false;
    const minimal = h.sandbox.participantItem(user, {listType:'waiting',position:0});
    assert.deepEqual(minimal.children.slice(0,-2).map(c=>c.className), ['participant-label']);
    assert.equal(minimal.children.at(-1).className, 'remove-participant');
    values.username = false;
    const empty = h.sandbox.participantItem(user, {listType:'waiting'});
    assert.equal(empty.children[0].className, 'participant-spacer');
    const placeholder = h.sandbox.participantItem({display_name:'参加者募集中', is_placeholder:true}, {listType:'now'});
    assert.equal(placeholder.children[0].textContent, '参加者募集中');
});

test('visibility change invalidates cached rows but keeps identities and dragging', () => {
    const h = harness(async()=>reply(state(1)));
    const values = {avatar:true, username:true, alias:true, memo:true, count:true, order:true};
    h.sandbox.window.controlListDisplay = {values};
    const waiting = [{user_id:'opaque-user',display_name:'Name',onecomme_memo:'note'}];
    h.sandbox.renderState({...state(1),waiting});
    const before = h.element('#waiting').dataset.signature;
    values.memo = false;
    h.sandbox.window.refreshControlDisplay();
    assert.notEqual(h.element('#waiting').dataset.signature, before);
    const row = h.element('#waiting').children.at(-1);
    assert.equal(row.dataset.userId, 'opaque-user');
    assert.equal(row.draggable, true);
    assert.ok(!row.children.some(c=>c.className==='participant-memo'));
});


test('participant counts show current stream separately and refresh at a new stream', () => {
    const h=harness(async()=>reply(state(1)));
    const user={user_id:'alice',display_name:'Alice',participation_count:7};
    h.sandbox.renderState({...state(1),current:[user],now_view:[user],session_participation_counts:{alice:2}});
    const row=h.element('#now').children.at(-1);
    assert.equal(row.children.find(c=>c.className==='participant-count').textContent,'今回2回／累計7回');
    h.sandbox.renderState({...state(2),current:[user],now_view:[user],session_participation_counts:{}});
    assert.equal(h.element('#now').children.at(-1).children.find(c=>c.className==='participant-count').textContent,'今回0回／累計7回');
});


test('priority toggle appears once in the top status block below reception', () => {
    const html=fs.readFileSync('static/control.html','utf8');
    assert.equal((html.match(/id="toggle-priority"/g)||[]).length,1);
    const status=html.slice(html.indexOf('<div class="status">'),html.indexOf('<details id="youtube-panel"'));
    assert.ok(status.indexOf('id="toggle-priority"') > status.indexOf('id="open"'));
    assert.match(status,/<button[^>]+id="toggle-priority"[^>]+data-api="\/api\/control\/toggle-priority"/);
});
