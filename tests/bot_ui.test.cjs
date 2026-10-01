const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
async function fixture(authenticated=false) {
  const elements={}, calls=[], bodies=[];
  const el=id=>elements[id] ||= {hidden:false,disabled:false,checked:false,textContent:'',value:'15',
    addEventListener(type,handler){this[type]=handler;},removeAttribute(){},showModal(){},close(){}};
  const state={authenticated,ready:false,has_connection_key:authenticated,
    settings:{announce_now:true,reply_position:true,periodic:false,interval_minutes:15}};
  const context={document:{getElementById:el},window:{},URL,AbortSignal,setInterval(){},
    fetch:async(path,options)=>{
      calls.push(path);
      if(options.method) {
        bodies.push(JSON.parse(options.body));
        return {ok:false,json:async()=>({detail:'接続できませんでした'})};
      }
      return {ok:true,json:async()=>state};
    }};
  vm.runInNewContext(fs.readFileSync('static/bot.js','utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  return {el,calls,bodies,context};
}
test('notification guide stays visible but controls and start require authentication',async()=>{
  for(const auth of [false,true]) {
    const f=await fixture(auth);
    assert.equal(f.el('bot-notifications').hidden,false);
    assert.equal(f.el('bot-notification-fields').disabled,!auth);
    assert.equal(f.el('bot-notifications-hint').hidden,auth);
    assert.equal(f.el('bot-start').hidden,!auth);
    assert.equal(f.el('bot-running-status').textContent,f.el('bot-status').textContent);
    assert.deepEqual(f.calls,['/api/bot']);
  }
});

test('first announcement defaults to 30, follows periodic switch and is included in save',async()=>{
  const f=await fixture(true);
  assert.equal(f.el('bot-initial-delay').value,'30');
  assert.equal(f.el('bot-initial-delay').disabled,true);
  f.el('bot-periodic').checked=true;
  f.el('bot-periodic').change();
  assert.equal(f.el('bot-initial-delay').disabled,false);
  f.el('bot-initial-delay').value='45';
  await f.context.window.saveBotSettings();
  assert.equal(f.bodies[0].initial_delay_minutes,45);
  assert.equal(f.bodies[0].interval_minutes,15);
});

test('Bot copy and timing selector match the setup request',()=>{
  const html=fs.readFileSync('static/bot.html','utf8');
  assert.match(html, /id="bot-check"[^>]*>接続を確認</);
  assert.match(html, /初回の定期案内は今から/);
  const select=html.match(/<select id="bot-initial-delay"[^>]*>(.*?)<\/select>/)[1];
  assert.deepEqual([...select.matchAll(/value="(\d+)"/g)].map(m=>m[1]),['15','30','45','60']);
  assert.doesNotMatch(html, /bot-next|bot-test-availability|接続確認（投稿なし）/);
});
test('errors are shown next to the corresponding authentication, check or start action',async()=>{
  for(const [button,result] of [['bot-connect','bot-auth-result'],['bot-status-check','bot-auth-result'],['bot-check','bot-login-result'],['bot-start','bot-start-result']]) {
    const f=await fixture(true);
    await f.el(button).click();
    assert.equal(f.el(result).textContent,'接続できませんでした');
    assert.equal(f.el('bot-running-status').textContent,'チャンネル接続済み／停止中');
  }
});
