const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const defaults = {avatar:true, username:true, alias:true, memo:true, count:true, order:true};
const reply = data => ({ok:true, json:async()=>data});
const settle = () => new Promise(setImmediate);
function setup(fetch) {
    const inputs = Object.keys(defaults).map(key => ({dataset:{display:key}, disabled:true, checked:true,
        addEventListener(type, fn) { this[type] = fn; }}));
    const status = {textContent:''};
    const retry = {hidden:true, addEventListener(type, fn) { this[type] = fn; }};
    const window = {refreshControlDisplay() { this.rendered = {...this.controlListDisplay.values}; }};
    vm.runInNewContext(fs.readFileSync('static/control-display.js','utf8'), {window,fetch,AbortSignal,
        document:{querySelectorAll:()=>inputs,querySelector:s=>s==='#control-display-status'?status:retry}});
    return {inputs,status,retry,window};
}
test('visibility restores booleans and saves a complete snapshot immediately', async()=>{
    const sent=[];
    const saved={...defaults,memo:false};
    const h=setup(async(url,options)=>{
        sent.push([url,options]);
        return reply(options.method==='POST'?JSON.parse(options.body):saved);
    });
    await settle();
    assert.equal(h.inputs[3].checked,false);
    assert.ok(h.inputs.every(i=>!i.disabled));
    h.inputs[0].checked=false;
    await h.inputs[0].change();
    assert.deepEqual(JSON.parse(sent[1][1].body),{...saved,avatar:false});
    assert.ok(sent[1][1].signal instanceof AbortSignal);
    assert.equal(h.window.rendered.avatar,false);
    assert.match(h.status.textContent,/保存しました/);
});
test('failed load never overwrites existing preferences and can be retried', async()=>{
    let attempts=0;
    const h=setup(async()=>{if(++attempts===1) throw new Error('offline'); return reply({...defaults,count:false});});
    await settle();
    assert.ok(h.inputs.every(i=>i.disabled));
    assert.equal(h.retry.hidden,false);
    await h.retry.click();
    assert.equal(h.inputs[4].checked,false);
    assert.ok(h.inputs.every(i=>!i.disabled));
});
test('ambiguous save rolls back UI and requires readback instead of blind retry', async()=>{
    const saved={...defaults};
    const h=setup(async(url,options)=>{
        if(options.method==='POST') {saved.memo=false; throw new Error('lost response');}
        return reply(saved);
    });
    await settle();
    h.inputs[3].checked=false;
    await h.inputs[3].change();
    assert.equal(h.window.rendered.memo,true);
    assert.ok(h.inputs.every(i=>i.disabled));
    assert.equal(h.retry.hidden,false);
    await h.retry.click();
    assert.equal(h.window.rendered.memo,false);
});
test('unexpected response is rejected rather than coercing strings into booleans', async()=>{
    const h=setup(async()=>reply({...defaults,memo:'false'}));
    await settle();
    assert.ok(h.inputs.every(i=>i.disabled));
    assert.equal(h.retry.hidden,false);
});
