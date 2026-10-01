const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const tick = () => new Promise(resolve => setImmediate(resolve));
async function fixture(saved={}, search='?setup=1') {
  const elements = {}, posts = [];
  const el = id => elements[id] ||= {hidden:false,disabled:false,checked:false,value:'参加希望',textContent:'',classList:{add(){}},focus(){},closest(){return {classList:{add(){}}};}};
  let prefs = {completed:false,deferred:false,step:0,use_bot:false,use_obs:true,...saved};
  const state = {connected:false,authenticated:false,fail:false,obsSave:true,botSave:true};
  const location = {href:'http://localhost/settings'+search,search,assign(url){state.navigation=url;}};
  const context = {document:{getElementById:el,querySelectorAll:()=>[],body:{dataset:{},classList:{add(){},remove(){}}}},location,
    history:{replaceState(){}},URL,URLSearchParams,AbortSignal,Event,
    window:{dispatchEvent(){},selectSettingsTab(name){state.tab=name;},saveOverlaySettings:async()=>state.obsSave,saveBotSettings:async()=>state.botSave},
    fetch:async (path, options) => {
      if (options.method) {
        const value=JSON.parse(options.body); posts.push({path,value});
        if(state.fail) return {ok:false};
        if(path==='/api/setup') prefs=value;
        return {ok:true,json:async()=>path==='/api/setup'?prefs:{}};
      }
      const data=path==='/api/setup'?prefs:path==='/api/onecomme/status'?{connected:state.connected,selected:state.connected?'live':''}:path==='/api/bot'?{authenticated:state.authenticated}: {last_access_seconds:null};
      return {ok:true,json:async()=>data};
    }};
  vm.runInNewContext(fs.readFileSync('static/setup-wizard.js','utf8'),context);
  await tick();
  return {el,state,posts,prefs:()=>prefs,async click(id){await el(id).onclick(); await tick();}};
}
test('setup checks connection, permits skipping, saves keywords, and finishes without Bot or OBS',async()=>{
  const f=await fixture();
  await f.click('setup-next'); assert.equal(f.prefs().step,0); assert.match(f.el('setup-result').textContent,/配信を選んで/);
  await f.click('setup-skip'); assert.equal(f.prefs().step,1);
  f.el('join-commands').value='参加希望\n参加する';
  await f.click('setup-next'); assert.equal(f.prefs().step,2);
  assert.deepEqual(f.posts.find(p=>p.path==='/api/settings/commands').value.join,['参加希望','参加する']);
  assert.equal(f.el('settings-bot-panel').hidden,true);
  await f.click('setup-skip'); assert.equal(f.prefs().step,3);
  assert.equal(f.posts.find(p=>p.path==='/api/bot/connection').value.action,'stop');
  await f.click('setup-skip'); assert.equal(f.prefs().step,4);
  await f.click('setup-next'); assert.equal(f.prefs().completed,true); assert.equal(f.state.navigation,'/control');
});
test('setup resumes saved step, supports defer, and never advances after failed save',async()=>{
  const f=await fixture({step:1});
  f.state.fail=true; await f.click('setup-next'); assert.equal(f.prefs().step,1); assert.match(f.el('setup-result').textContent,/保存/);
  f.state.fail=false; await f.click('setup-later'); assert.equal(f.prefs().deferred,true); assert.equal(f.el('setup-wizard').hidden,true);
  await f.click('setup-restart'); assert.equal(f.prefs().step,0); assert.equal(f.el('setup-wizard').hidden,false);
});
test('setup requires authenticated channel and saved notifications when opting into Bot',async()=>{
  const f=await fixture({step:2,use_bot:true});
  await f.click('setup-next'); assert.equal(f.prefs().step,2);
  f.state.authenticated=true; f.state.botSave=false;
  await f.click('setup-next'); assert.equal(f.prefs().step,2);
  f.state.botSave=true; await f.click('setup-next'); assert.equal(f.prefs().step,3);
  f.state.obsSave=false; await f.click('setup-next'); assert.equal(f.prefs().step,3);
  f.state.obsSave=true; await f.click('setup-next'); assert.equal(f.prefs().step,4);
});
test('completed setup does not reopen automatically in normal settings',async()=>{
  const f=await fixture({completed:true},'');
  assert.equal(f.state.tab,undefined); assert.equal(f.posts.length,0);
});
