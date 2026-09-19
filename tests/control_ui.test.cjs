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
 assert.equal(h.element('#priority').className,'priority-on');
 h.sandbox.renderState({...state(2),priority_mode:false});
 assert.equal(h.element('#toggle-priority').attributes['aria-pressed'],'false');
 assert.equal(h.element('#priority').className,'priority-off');
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
