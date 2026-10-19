const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'), vm=require('node:vm');

function harness({state={revision:12},result=true,download=true}={}) {
    const elements=new Map(), requests=[], downloads=[];
    const el=id=>{
        if(!elements.has(id)) elements.set(id,{listeners:{},disabled:false,open:false,textContent:'',
            addEventListener(name,fn){this.listeners[name]=fn;},
            showModal(){this.open=true;},close(){this.open=false;}});
        return elements.get(id);
    };
    const scope={mutationPending:false,AbortSignal,setTimeout(){},
        document:{getElementById:el,body:{append(){}},createElement:()=>({click(){downloads.push(this.download);},remove(){}})},
        URL:{createObjectURL:()=> 'blob:download',revokeObjectURL(){}},
        fetchState:async()=>state,
        post:async(api,payload)=>{requests.push([api,payload]);return result;},
        fetch:async api=>{requests.push([api]);return {ok:download,blob:async()=>({})};}};
    vm.createContext(scope);vm.runInContext(fs.readFileSync('static/queue-diagnostics.js','utf8'),scope);
    return {scope,el,requests,downloads};
}

test('startup never resets or downloads, first click only opens confirmation',async()=>{
    const h=harness();
    assert.equal(h.requests.length,0);
    await h.el('session-count-reset').listeners.click();
    assert.equal(h.el('session-reset-dialog').open,true);
    assert.equal(h.requests.length,0);
    h.el('session-reset-cancel').listeners.click();
    assert.equal(h.el('session-reset-dialog').open,false);
    assert.equal(h.requests.length,0);
});
test('confirmation sends exact revision and affects only this stream count API',async()=>{
    const h=harness();
    await h.el('session-count-reset').listeners.click();
    await h.el('session-reset-confirm').listeners.click();
    assert.deepEqual(JSON.parse(JSON.stringify(h.requests)),[['/api/control/reset-session-counts',{confirmed:true,expected_revision:12}]]);
    assert.equal(h.el('session-reset-dialog').open,false);
    assert.match(h.el('diagnostic-tools-status').textContent,/累計参加回数と待機列はそのまま/);
});
test('state lookup failure and mutation guard never open confirmation or reset',async()=>{
    const h=harness({state:null});
    await h.el('session-count-reset').listeners.click();
    assert.equal(h.el('session-reset-dialog').open,false);
    assert.match(h.el('diagnostic-tools-status').textContent,/接続/);
    h.scope.mutationPending=true;
    await h.el('session-count-reset').listeners.click();
    await h.el('session-reset-confirm').listeners.click();
    assert.equal(h.requests.length,0);
});
test('failed reset is not reported as success and confirmation button recovers',async()=>{
    const h=harness({result:false});
    await h.el('session-count-reset').listeners.click();
    await h.el('session-reset-confirm').listeners.click();
    assert.match(h.el('diagnostic-tools-status').textContent,/確認できませんでした/);
    assert.equal(h.el('session-reset-confirm').disabled,false);
});
test('each download click makes a new read-only request and a text download',async()=>{
    const h=harness();
    await h.el('diagnostic-log-download').listeners.click();
    await h.el('diagnostic-log-download').listeners.click();
    assert.deepEqual(h.downloads,['JoinQueue-operation-log.txt','JoinQueue-operation-log.txt']);
    assert.equal(h.requests.length,2);
    assert.ok(h.requests.every(r=>r[0]==='/api/control/diagnostic-log'));
    assert.equal(h.el('diagnostic-log-download').disabled,false);
});
test('failed download creates no file and can be retried',async()=>{
    const h=harness({download:false});
    await h.el('diagnostic-log-download').listeners.click();
    assert.equal(h.downloads.length,0);
    assert.match(h.el('diagnostic-tools-status').textContent,/取得できません/);
    assert.equal(h.el('diagnostic-log-download').disabled,false);
});
