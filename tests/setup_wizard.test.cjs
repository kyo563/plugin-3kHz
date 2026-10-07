const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const tick = () => new Promise(resolve => setImmediate(resolve));
async function fixture(saved={}, search='?setup=1') {
  const elements = {}, posts = [];
  const el = id => elements[id] ||= {hidden:false,disabled:false,checked:false,value:'参加希望',textContent:'',dataset:{},append(child){child.parent=this;},prepend(child){child.parent=this;},dispatchEvent(){},classList:{add(){}},focus(){},closest(){return {classList:{add(){}}};}};
  el('setup-reset-commands').dataset.defaults=JSON.stringify({'join-commands':'参加希望','cancel-commands':'参加辞退\n参加を辞退'});
  el('setup-reset-labels').dataset.defaults=JSON.stringify({'setup-label-open_label':'受付中','setup-label-now_label':'現在の対戦','setup-label-next_label':'次回','setup-label-queue_label':'待機人数'});
  let prefs = {completed:false,deferred:false,step:0,use_bot:false,use_obs:true,...saved};
  const state = {connected:false,authenticated:false,fail:false,obsSave:true,botSave:true,unresolved:false,ready:false};
  const location = {href:'http://localhost/settings'+search,search,assign(url){state.navigation=url;}};
  const context = {document:{getElementById:el,querySelectorAll:()=>[],body:{dataset:{},classList:{add(){},remove(){}}}},location,
    history:{replaceState(){}},URL,URLSearchParams,AbortSignal,Event,
    window:{dispatchEvent(){},selectSettingsTab(name){state.tab=name;},saveOverlaySettings:async()=>{state.obsSaveCalls=(state.obsSaveCalls||0)+1;return state.obsSave;},saveBotSettings:async()=>state.botSave},
    fetch:async (path, options) => {
      if (options.method) {
        const value=JSON.parse(options.body); posts.push({path,value});
        if(state.fail) return {ok:false};
        if(path==='/api/setup') prefs=value;
        return {ok:true,json:async()=>path==='/api/setup'?prefs:{}};
      }
      const data=path==='/api/setup'?prefs:path==='/api/onecomme/status'?{connected:state.connected,selected:state.connected&&!state.unresolved?'live':'',ready_to_receive:state.ready}:path==='/api/bot'?{authenticated:state.authenticated}: {last_access_seconds:null};
      return {ok:true,json:async()=>data};
    }};
  vm.runInNewContext(fs.readFileSync('static/setup-wizard.js','utf8'),context);
  await tick();
  return {el,state,posts,prefs:()=>prefs,async click(id){await el(id).onclick(); await tick();}};
}
test('first setup explains the automatic connection, success state, and manual reconnection',async()=>{
  const f=await fixture();
  assert.equal(f.el('setup-instruction').textContent,
    'このプラグインでは、わんコメがコメントを受信している配信に自動で接続します。\n下記の「接続先の配信」に、利用する配信が表示されていれば接続完了です。「次へ」で進んでください。\n未接続、または別の配信が表示されている場合は、「別の配信に連携し直す」から接続先を選び直してください。');
  assert.match(fs.readFileSync('static/setup.css','utf8'), /#setup-instruction, #setup-summary\s*\{\s*white-space:pre-line;/);
  assert.equal(f.posts.length,0);
});

test('final setup step explains that setup can be repeated from settings',async()=>{
  const f=await fixture({step:4});
  assert.equal(f.el('setup-instruction').textContent,
    '設定内容を確認し、「次へ」でセットアップを完了してください。\nこの初回セットアップは設定から再度行うことができます。');
  assert.equal(f.posts.length,0);
});

test('setup checks connection, saves keywords, and finishes using only Next without Bot or OBS',async()=>{
  const f=await fixture();
  await f.click('setup-next'); assert.equal(f.prefs().step,0); assert.match(f.el('setup-result').textContent,/わんコメのプラグインを有効/);
  f.state.connected=true;
  await f.click('setup-next'); assert.equal(f.prefs().step,1);
  f.el('join-commands').value='参加希望\n参加する';
  await f.click('setup-next'); assert.equal(f.prefs().step,2);
  assert.deepEqual(f.posts.find(p=>p.path==='/api/settings/commands').value.join,['参加希望','参加する']);
  assert.equal(f.state.obsSaveCalls,1);
  assert.equal(f.el('settings-bot-panel').hidden,true);
  await f.click('setup-next'); assert.equal(f.prefs().step,3);
  assert.equal(f.posts.find(p=>p.path==='/api/bot/connection').value.action,'stop');
  f.el('setup-use-obs').checked=false;
  await f.click('setup-next'); assert.equal(f.prefs().step,4);
  await f.click('setup-next'); assert.equal(f.prefs().completed,true); assert.equal(f.state.navigation,'/control');
});

test('restricted room setup advances on a linked receiving row without video metadata or Bot',async()=>{
  const f=await fixture();
  Object.assign(f.state,{connected:true,unresolved:true,ready:true});
  await f.click('setup-next');
  assert.equal(f.prefs().step,1);
  assert.equal(f.prefs().use_bot,false);
  assert.equal(f.posts.some(p=>p.path.startsWith('/api/bot')),false);
});

test('setup requires only the OneComme plugin link, not any URL or resolved stream',async()=>{
  const f=await fixture();
  Object.assign(f.state,{connected:true,unresolved:true,ready:false});
  await f.click('setup-next');assert.equal(f.prefs().step,1);
  assert.equal(f.posts.some(p=>p.path.includes('select-url')),false);
});
test('setup resumes saved step and never advances after failed save',async()=>{
  const f=await fixture({step:1});
  f.state.fail=true; await f.click('setup-next'); assert.equal(f.prefs().step,1); assert.match(f.el('setup-result').textContent,/保存/);
  f.state.fail=false; await f.click('setup-back');
  assert.equal(f.prefs().step,0);
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

test('OBS setup shows adjustment controls expanded with concise guidance',async()=>{
  const f=await fixture({step:3});
  assert.equal(f.el('setup-obs-details').open,true);
  assert.equal(f.el('setup-instruction').textContent,'OBS表示用の設定を編集します。');
  await f.click('setup-back');
  await f.click('setup-next');
  assert.equal(f.el('setup-obs-details').open,true);
});

test('step 2 saves shared OBS labels and stays on the page if saving fails',async()=>{
  const f=await fixture({step:1});
  f.state.obsSave=false;
  await f.click('setup-next');
  assert.equal(f.prefs().step,1);
  assert.match(f.el('setup-result').textContent,/表示文言を保存できません/);
  f.state.obsSave=true;
  await f.click('setup-next');
  assert.equal(f.prefs().step,2);
});

test('all five steps expose only Back and Next navigation with no skip/defer handlers',async()=>{
  const html=fs.readFileSync('static/setup-wizard.html','utf8');
  assert.doesNotMatch(html,/setup-skip|setup-later|スキップ|あとで設定する/);
  assert.equal((html.match(/<button /g)||[]).length,2);
  for (const step of [0,1,2,3,4]) {
    const f=await fixture({step});
    assert.equal(f.el('setup-next').textContent,'次へ');
    assert.equal(f.el('setup-back').disabled,step===0);
    assert.equal(f.el('setup-skip').onclick,undefined);
    assert.equal(f.el('setup-later').onclick,undefined);
    assert.doesNotMatch(f.el('setup-instruction').textContent,/スキップ/);
  }
});

test('section resets only change their own drafts and Next saves them',async()=>{
  const f=await fixture({step:1});
  f.el('join-commands').value='参加する';
  f.el('cancel-commands').value='辞退する';
  f.el('setup-label-now_label').value='対戦中';
  await f.click('setup-reset-commands');
  assert.equal(f.el('join-commands').value,'参加希望');
  assert.equal(f.el('cancel-commands').value,'参加辞退\n参加を辞退');
  assert.equal(f.el('setup-label-now_label').value,'対戦中');
  f.el('join-commands').value='参加する';
  await f.click('setup-reset-labels');
  assert.equal(f.el('join-commands').value,'参加する');
  for(const [key,value] of Object.entries({open_label:'受付中',now_label:'現在の対戦',next_label:'次回',queue_label:'待機人数'})) assert.equal(f.el('setup-label-'+key).value,value);
  assert.equal(f.posts.length,0);
  await f.click('setup-next');
  assert.equal(f.prefs().step,2);
  assert.deepEqual(f.posts.find(p=>p.path==='/api/settings/commands').value.join,['参加する']);
  assert.equal(f.state.obsSaveCalls,1);
});

test('reset does not overwrite drafts during loading or outside step 2',async()=>{
  const f=await fixture({step:1});
  f.el('save-commands').disabled=true;
  f.el('cancel-commands').value='変更前';
  await f.click('setup-reset-commands');
  assert.equal(f.el('cancel-commands').value,'変更前');
  f.el('save-display-labels').disabled=true;
  f.el('setup-label-now_label').value='変更前';
  await f.click('setup-reset-labels');
  assert.equal(f.el('setup-label-now_label').value,'変更前');
  await f.click('setup-back');
  f.el('save-commands').disabled=false;
  await f.click('setup-reset-commands');
  assert.equal(f.el('cancel-commands').value,'変更前');
});

test('Bot setup reuses the stream picker and restores it when leaving step 3',async()=>{
  const f=await fixture({step:2});
  const picker=f.el('setup-connection');
  assert.equal(picker.parent,f.el('bot-stream-picker'));
  assert.equal(f.el('bot-stream-settings-link').hidden,true);
  assert.match(f.el('setup-instruction').textContent,/Botを標準モデレーターに設定し/);
  await f.click('setup-back');
  assert.equal(picker.parent,f.el('settings-general-panel'));
  await f.click('setup-next');
  assert.equal(picker.parent,f.el('bot-stream-picker'));
  await f.click('setup-next');
  assert.equal(picker.parent,f.el('settings-general-panel'));
  assert.equal(f.el('bot-stream-settings-link').hidden,false);
});
