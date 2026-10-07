const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const tick = () => new Promise(resolve=>setImmediate(resolve));
async function fixture(pending=null) {
  const elements={}, posts=[], timers=[];
  const el=id=>elements[id] ||= {value:'',textContent:'',hidden:false,disabled:false,listeners:{},options:[],
    addEventListener(type,handler){this.listeners[type]=handler;},
    replaceChildren(...children){this.options=children;},add(option){this.options.push(option);}};
  const state={connected:true,frames:[{id:'abcdefghijk',name:'開始前'}],selected:'abcdefghijk',
    selected_name:'開始前',services:[{service_id:'row',service_name:'麻雀',id:'abcdefghijk',name:'開始前',state:'upcoming'}],
    pinned_service:'row',selection_mode:'auto',commands:0,received:0,pending};
  const context={document:{getElementById:el},AbortSignal,Option:function(text,value){this.text=text;this.value=value;},
    setTimeout(fn){timers.push(fn);},fetch:async(path,options={})=>{
      if(options.method){posts.push({path,body:JSON.parse(options.body)});return {ok:true,json:async()=>({})};}
      return {ok:true,json:async()=>state};
    }};
  vm.runInNewContext(fs.readFileSync('static/onecomme.js','utf8'),context);
  await tick();
  return {el,state,posts,async click(id){el(id).listeners.click();await tick();},async refresh(){await timers.pop()();}};
}
test('remembered row and stream title are distinct; remember API uses service ID',async()=>{
  const f=await fixture();
  assert.match(f.el('onecomme-remembered').textContent,/麻雀/);
  assert.match(f.el('onecomme-target').textContent,/開始前/);
  assert.equal(f.el('onecomme-transition').hidden,true);
  await f.click('onecomme-select');
  assert.deepEqual(f.posts[0],{path:'/api/onecomme/remember',body:{service_id:'row'}});
});

test('manual choice persists through polling and reconnects using the chosen service',async()=>{
  const f=await fixture();
  f.state.services.push({service_id:'other',service_name:'別の接続欄',id:'lmnopqrstuv',name:'次の配信',state:'live'});
  await f.refresh();
  const select=f.el('onecomme-stream');
  select.value='service:other'; select.listeners.change();
  f.state.services[1].name='更新されたタイトル';
  await f.refresh();
  assert.equal(select.value,'service:other');
  assert.match(select.options[2].text,/更新されたタイトル.*別の接続欄/);
  await f.click('onecomme-select');
  assert.deepEqual(f.posts[0],{path:'/api/onecomme/remember',body:{service_id:'other'}});
});

test('unavailable choices cannot reconnect; disappearing edited choice is not silently replaced',async()=>{
  const f=await fixture();
  for (const change of [{connected:false},{connected:true,services:[{id:'',name:'未解決'}]},
    {services:[{service_id:'row',id:'abcdefghijk',enabled:false}]},{services:[{service_id:'row',id:'abcdefghijk',state:'ended'}]}]) {
    Object.assign(f.state,change); await f.refresh();
    assert.equal(f.el('onecomme-select').disabled,true);
    await f.click('onecomme-select');
  }
  assert.equal(f.posts.length,0);
  f.el('onecomme-stream').listeners.change();
  f.state.services=[{service_id:'different',id:'lmnopqrstuv',name:'別の配信'}];
  await f.refresh();
  assert.equal(f.el('onecomme-stream').value,'');
  assert.equal(f.el('onecomme-select').disabled,true);
});

test('unresolved OneComme row can be chosen without Google video metadata',async()=>{
  const f=await fixture();
  Object.assign(f.state,{selected:'',selected_name:'限定配信',ready_to_receive:true,
    services:[{service_id:'row',id:'',enabled:true,state:'unknown',name:'限定配信'}]});
  await f.refresh();
  assert.equal(f.el('onecomme-select').disabled,false);
  assert.match(f.el('onecomme-target').textContent,/限定配信.*連動中/);
  await f.click('onecomme-select');
  assert.deepEqual(f.posts[0],{path:'/api/onecomme/remember',body:{service_id:'row'}});
});

test('stop preserves explicit manual stop and legacy frames can still be selected',async()=>{
  const f=await fixture();
  await f.click('onecomme-stop');
  assert.deepEqual(f.posts[0],{path:'/api/onecomme/select',body:{frame_id:'',mode:'manual'}});
  f.state.services=[]; await f.refresh();
  assert.equal(f.el('onecomme-stream').value,'video:abcdefghijk');
  await f.click('onecomme-select');
  assert.deepEqual(f.posts[1],{path:'/api/onecomme/select',body:{frame_id:'abcdefghijk',mode:'manual'}});
});
test('transition buttons send explicit choice with displayed video and revision',async()=>{
  const f=await fixture({video_id:'lmnopqrstuv',name:'次回',current_count:3,waiting_count:37,revision:9,saved:false});
  assert.equal(f.el('onecomme-transition').hidden,false);
  assert.match(f.el('onecomme-transition-summary').textContent,/NOW 3人・待機 37人/);
  await f.click('onecomme-carry-session');
  assert.deepEqual(f.posts[0].body,{video_id:'lmnopqrstuv',revision:9,carry:true});
  f.state.pending.saved=true; await f.refresh();
  assert.equal(f.el('onecomme-carry-session').hidden,true);
  assert.equal(f.el('onecomme-new-session').textContent,'保存済みの状態に戻る');
  await f.click('onecomme-new-session');
  assert.equal(f.posts[1].body.carry,false);
});

test('manual URL guide uses the concise fallback wording',()=>{
  const html=fs.readFileSync('static/onecomme-panel.html','utf8');
  assert.match(html, /<p id="onecomme-url-guide">自動で連携されない場合はURLを直接貼り付けて読み込ませてください<\/p>/);
  assert.doesNotMatch(html, /限定公開・メンバー限定配信のURLも指定できます。/);
  assert.match(html, /aria-describedby="onecomme-url-guide"/);
});

test('manual URL input preserves drafts, saves resolved URLs, and binds unresolved chosen sources',async()=>{
  const f=await fixture();
  const input=f.el('onecomme-url');
  input.value='https://youtu.be/abcdefghijk';input.listeners.input();
  await f.refresh();
  assert.equal(input.value,'https://youtu.be/abcdefghijk');
  assert.equal(f.el('onecomme-url-select').disabled,false);
  await f.click('onecomme-url-select');
  assert.deepEqual(f.posts[0],{path:'/api/onecomme/select-url',body:{url:'https://youtu.be/abcdefghijk'}});
  f.state.services=[{service_id:'row',id:'',name:'限定配信',enabled:true,state:'unknown'}];
  f.state.selected='';f.state.manual_url='https://www.youtube.com/watch?v=abcdefghijk';
  f.state.url_service_id='row';f.state.ready_to_receive=true;
  await f.refresh();
  assert.equal(input.value,f.state.manual_url);
  assert.match(f.el('onecomme-url-status').textContent,/連携中/);
  await f.click('onecomme-url-select');
  assert.equal(f.posts[1].body.service_id,'row');
  input.value=' ';input.listeners.input();
  assert.equal(f.el('onecomme-url-select').disabled,true);
  await f.click('onecomme-url-select');assert.equal(f.posts.length,2);
});
