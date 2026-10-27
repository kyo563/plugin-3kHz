const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const flush = () => new Promise(resolve => setImmediate(resolve));
function harness() {
  const handlers = {}, posts = [];
  const input = {value:'', disabled:true, addEventListener:(k,f) => handlers[k]=f};
  const result = {textContent:''};
  let pending, poll, timer, fail = false;
  const reply = s => ({ok:true, json:async () => s});
  const context = {
    AbortSignal, document:{getElementById:id => id==='reception-time' ? input : result},
    clearTimeout(){}, setTimeout(f){timer=f;}, setInterval(f){poll=f;},
    fetch:async (_, options) => {
      if (!options.method) return reply({enabled:false});
      const body = JSON.parse(options.body); posts.push(body);
      if (fail) throw Error('offline');
      return new Promise(resolve => {pending=()=>resolve(reply({...body,due_at:'2026-10-28T23:30:00'}));});
    }
  };
  vm.runInNewContext(fs.readFileSync('static/reception-schedule.js','utf8'),context);
  return {input,result,posts,edit(value){input.value=value;handlers.input();},
    save:()=>timer(), release:()=>pending(), poll:()=>poll(), fail:()=>{fail=true;}};
}
test('time input automatically arms, and clearing cancels without a checkbox',async()=>{
  const h=harness(); await flush(); assert.equal(h.input.disabled,false);
  h.edit('23:30'); const saved=h.save(); h.release(); await saved;
  assert.deepEqual(h.posts[0],{enabled:true,time:'23:30'});
  assert.equal(h.result.textContent,'');
  h.edit(''); const cancelled=h.save(); h.release(); await cancelled;
  assert.equal(h.posts[1].enabled,false);
});
test('incomplete time is not saved and polling cannot discard an edit',async()=>{
  const h=harness(); await flush(); h.edit('23:'); await h.save(); h.poll(); await flush();
  assert.equal(h.posts.length,0); assert.equal(h.input.value,'23:');
  assert.match(h.result.textContent,/変更していません/);
});
test('rapid edits are saved in order without old responses replacing new input',async()=>{
  const h=harness(); await flush(); h.edit('22:00'); const first=h.save();
  h.edit('23:30'); await h.save(); assert.equal(h.posts.length,1);
  h.release(); await first; assert.equal(h.input.value,'23:30');
  assert.equal(h.posts[1].time,'23:30'); h.release(); await flush();
  assert.equal(h.result.textContent,'');
});
test('failed save stays visibly unsaved instead of claiming the deadline is armed',async()=>{
  const h=harness(); await flush(); h.fail(); h.edit('23:30'); await h.save();
  assert.match(h.result.textContent,/保存を確認できません/);
  h.poll(); await flush(); assert.equal(h.input.value,'23:30');
});
