const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
async function fixture(authenticated=false, deletionAvailable=false, overrides={}, reply) {
  const elements={}, calls=[], bodies=[], clock=[1000];
  let poll;
  const el=id=>elements[id] ||= {hidden:false,disabled:false,checked:false,textContent:'',value:'15',
    addEventListener(type,handler){this[type]=handler;},removeAttribute(){},showModal(){this.open=true;},close(){this.open=false;}};
  const state={authenticated,ready:false,has_connection_key:authenticated,deletion_available:deletionAvailable,
    settings:{announce_now:true,reply_position:true,periodic:false,interval_minutes:15},...overrides};
  class TestDate extends Date { static now(){return clock[0];} }
  const context={document:{getElementById:el},window:{},URL,AbortSignal,Date:TestDate,setInterval(handler){poll=handler;},
    fetch:async(path,options)=>{
      calls.push(path);
      if(options.method) {
        bodies.push(JSON.parse(options.body));
        if (reply) return reply(JSON.parse(options.body));
        return {ok:false,json:async()=>({detail:'接続できませんでした'})};
      }
      return {ok:true,json:async()=>state};
    }};
  vm.runInNewContext(fs.readFileSync('static/bot.js','utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  return {el,calls,bodies,context,state,poll:()=>poll(),advance:ms=>{clock[0]+=ms;}};
}
test('position reply guidance has no question keyword requirement and explains per-user cooldown',()=>{
  const html=fs.readFileSync('static/bot.html','utf8');
  assert.match(html, /@JoinQueueBotへのリプライに、本人の待機順・グループを返信する（同じユーザーは3分に1回）/);
  assert.doesNotMatch(html, /「順番」が含まれる場合/);
});

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

test('server erasure needs supported authenticated connection, two actions and exact confirmation text',async()=>{
  for(const [authenticated,available] of [[false,false],[true,false],[false,true]]) {
    const f=await fixture(authenticated,available);
    assert.equal(f.el('bot-erase-open').disabled,true);
    f.el('bot-erase-open').onclick();
    assert.notEqual(f.el('bot-erase-dialog').open,true);
    assert.deepEqual(f.calls,['/api/bot']);
  }
  const f=await fixture(true,true);
  assert.equal(f.el('bot-erase-open').disabled,false);
  f.el('bot-erase-open').onclick();
  assert.equal(f.el('bot-erase-dialog').open,true);
  assert.equal(f.el('bot-erase-confirm').disabled,true);
  f.el('bot-erase-text').value='削除'; f.el('bot-erase-text').input();
  await f.el('bot-erase-confirm').onclick();
  assert.deepEqual(f.calls,['/api/bot']);
  f.el('bot-erase-text').value='サーバー記録を削除'; f.el('bot-erase-text').input();
  assert.equal(f.el('bot-erase-confirm').disabled,false);
  await f.el('bot-erase-confirm').onclick();
  assert.deepEqual(f.calls,['/api/bot','/api/bot/erase']);
  assert.equal(f.bodies[0].confirmation,'サーバー記録を削除');
  assert.equal(f.el('bot-erase-dialog').open,false);
  assert.match(f.el('bot-start-result').textContent,/接続キーは保持/);
  const html=fs.readFileSync('static/bot.html','utf8');
  assert.match(html,/id="bot-erase-open"[^>]*disabled/);
  assert.match(html,/id="bot-erase-cancel"[^>]*autofocus/);
});

test('a stored device never hides recovery while authentication is incomplete',async()=>{
  for(const authState of ['unverified','pending','expired']) {
    const f=await fixture(false,false,{has_connection_key:true,auth_state:authState});
    assert.equal(f.el('bot-connect').hidden,false);
    assert.equal(f.el('bot-connect').disabled,false);
    assert.equal(f.el('bot-connect').textContent,'認証を再開・やり直す');
    assert.equal(f.el('bot-status-check').hidden,false);
    assert.equal(f.el('bot-start').hidden,true);
    // On reopening the page the server is queried once, never every UI poll.
    assert.deepEqual(f.calls,['/api/bot','/api/bot/connection']);
    await f.el('bot-connect').click();
    assert.equal(f.el('bot-connect').hidden,false);
    assert.equal(f.el('bot-auth-result').textContent,'接続できませんでした');
  }
  assert.equal((await fixture(true)).el('bot-connect').hidden,true);
});

test('restored pending link and confirmation are displayed and recovery respects actual response',async()=>{
  const link='https://joinqueue-bot-backend.joinqueue.workers.dev/connect?id=1234abcd-1111-4111-8111-111111111111&key='+'k'.repeat(43);
  const pending={authenticated:false,ready:false,has_connection_key:true,auth_state:'pending',login_pending:true,
    authorization_url:link,confirmation:'1234abcd'};
  const f=await fixture(false,false,pending,async()=>({ok:true,json:async()=>pending}));
  assert.equal(f.el('bot-login-link').hidden,false);
  assert.equal(f.el('bot-login-link').href,link);
  assert.equal(f.el('bot-confirmation').textContent,'照合番号：1234abcd');
  await f.el('bot-connect').click();
  assert.match(f.el('bot-auth-result').textContent,/認証リンクを開いて/);
  await f.el('bot-start').click();
  assert.match(f.el('bot-start-result').textContent,/起動していません/);
  assert.doesNotMatch(f.el('bot-start-result').textContent,/Botを起動しました/);
});

test('checking a restored authenticated device never asks for unnecessary Google authentication',async()=>{
  const f=await fixture(false,false,{has_connection_key:true,auth_state:'unverified'},
    async()=>({ok:true,json:async()=>({authenticated:true,ready:false,has_connection_key:true,auth_state:'authenticated'})}));
  assert.equal(f.el('bot-connect').hidden,true);
  assert.equal(f.el('bot-start').hidden,false);
  assert.equal(f.el('bot-running-status').textContent,'チャンネル接続済み／停止中');
  assert.deepEqual(f.bodies,[{action:'status'}]);
});

test('normal connection guide has three steps, with check optional and reauthentication explicit',()=>{
  const html=fs.readFileSync('static/bot.html','utf8');
  assert.deepEqual([...html.matchAll(/<h2>([123])\. /g)].map(m=>m[1]),['1','2','3']);
  assert.doesNotMatch(html,/<h2>[45]\. /);
  assert.match(html,/結果を自動で確認/);
  assert.match(html,/起動せずに接続だけ確認する/);
  assert.match(html,/id="bot-reauth-cancel"[^>]*autofocus/);
  assert.match(html,/同じGoogleアカウントで接続した他のチャンネル・端末にも影響/);
});

test('reauthentication is available after failure, expiry and even successful authentication',async()=>{
  for(const auth of [false,true]) {
    const f=await fixture(auth,false,{has_connection_key:true,auth_state:auth?'authenticated':'expired'});
    assert.equal(f.el('bot-reauth-open').hidden,false);
    const count=f.bodies.length;
    await f.el('bot-reauth-confirm').onclick();
    assert.equal(f.bodies.length,count); // Cannot bypass opening the confirmation.
    f.el('bot-reauth-open').onclick();
    assert.equal(f.el('bot-reauth-dialog').open,true);
    f.el('bot-reauth-cancel').onclick();
    assert.equal(f.el('bot-reauth-dialog').open,false);
    assert.equal(f.bodies.length,count); // Opening and cancelling never disconnects.
  }
  assert.equal((await fixture(false)).el('bot-reauth-open').hidden,true);
});

test('confirmed reauthentication disconnects first, issues a fresh link and never starts or erases data',async()=>{
  let f;
  const pending={authenticated:false,ready:false,has_connection_key:true,auth_state:'pending',login_pending:true,
    authorization_url:'https://joinqueue-bot-backend.joinqueue.workers.dev/connect?id=1234abcd&key=test',confirmation:'1234abcd'};
  f=await fixture(true,false,{},async body=>({ok:true,json:async()=>body.confirmation
    ? {...f.state,authenticated:false,ready:false,has_connection_key:false,auth_state:'disconnected'}
    : {...f.state,...pending}}));
  f.el('bot-reauth-open').onclick();
  await f.el('bot-reauth-confirm').onclick();
  assert.deepEqual(f.calls,['/api/bot','/api/bot/disconnect','/api/bot/connection']);
  assert.deepEqual(f.bodies,[{confirmation:'接続を解除'},{action:'connect'}]);
  assert.equal(f.el('bot-login-link').hidden,false);
  assert.equal(f.el('bot-start').hidden,true);
  assert.match(f.el('bot-auth-result').textContent,/新しい認証リンク/);
  assert.equal(f.el('bot-reauth-dialog').open,false);
});

test('failed or unconfirmed disconnection never proceeds to issuing another credential',async()=>{
  for(const response of [
    {ok:false,json:async()=>({detail:'サーバーに接続できません'})},
    {ok:true,json:async()=>({authenticated:true,ready:false,has_connection_key:true})}
  ]) {
    const f=await fixture(true,false,{},async()=>response);
    f.el('bot-reauth-open').onclick();
    await f.el('bot-reauth-confirm').onclick();
    assert.deepEqual(f.calls,['/api/bot','/api/bot/disconnect']);
    assert.match(f.el('bot-auth-result').textContent,/接続状態を確認/);
    assert.equal(f.el('bot-reauth-open').hidden,false);
  }
});

test('failure to issue a new link after confirmed disconnection leaves the normal retry available',async()=>{
  let f;
  f=await fixture(true,false,{},async body=>body.confirmation
    ? {ok:true,json:async()=>({...f.state,authenticated:false,has_connection_key:false,auth_state:'disconnected'})}
    : {ok:false,json:async()=>({detail:'認証開始に失敗しました'})});
  f.el('bot-reauth-open').onclick();
  await f.el('bot-reauth-confirm').onclick();
  assert.equal(f.el('bot-connect').hidden,false);
  assert.equal(f.el('bot-start').hidden,true);
  assert.match(f.el('bot-auth-result').textContent,/認証開始に失敗/);
});

test('visible pending authentication is automatically checked, throttled and never starts the Bot',async()=>{
  let authenticated=false;
  const f=await fixture(false,false,{has_connection_key:true,auth_state:'pending'},async()=>({ok:true,json:async()=>({
    authenticated,ready:false,has_connection_key:true,auth_state:authenticated?'authenticated':'pending'})}));
  assert.equal(f.bodies.length,1);
  f.advance(9000); await f.poll(); assert.equal(f.bodies.length,1);
  f.context.document.hidden=true;
  f.advance(3000); await f.poll(); assert.equal(f.bodies.length,1);
  f.context.document.hidden=false;
  authenticated=true; await f.poll();
  assert.deepEqual(f.bodies,[{action:'status'},{action:'status'}]);
  assert.match(f.el('bot-auth-result').textContent,/認証が完了/);
  assert.equal(f.el('bot-start').disabled,false);
  assert.equal(f.el('bot-running-status').textContent,'チャンネル接続済み／停止中');
});

test('automatic authentication checks back off on failure and stop after ten minutes',async()=>{
  const f=await fixture(false,false,{has_connection_key:true,auth_state:'pending'});
  assert.equal(f.bodies.length,1);
  f.advance(10000); await f.poll(); assert.equal(f.bodies.length,1);
  f.advance(50000); await f.poll(); assert.equal(f.bodies.length,2);
  f.advance(600000); await f.poll(); assert.equal(f.bodies.length,2);
  // The user can always request another status check explicitly.
  await f.el('bot-status-check').click(); assert.equal(f.bodies.length,3);
});

test('start saves changed notification settings then checks and starts in one operation',async()=>{
  let f;
  f=await fixture(true,false,{},async body=>({ok:true,json:async()=>body.action
    ? {...f.state,ready:true} : {...f.state,settings:body}}));
  f.el('bot-now').checked=false;
  f.el('bot-periodic').checked=true;
  f.el('bot-initial-delay').value='45';
  await f.el('bot-start').click();
  assert.deepEqual(f.calls,['/api/bot','/api/bot/settings','/api/bot/connection']);
  assert.equal(f.bodies[0].announce_now,false);
  assert.equal(f.bodies[0].initial_delay_minutes,45);
  assert.equal(f.bodies[0].enabled,false);
  assert.deepEqual(f.bodies[1],{action:'start'});
  assert.match(f.el('bot-start-result').textContent,/Botを起動しました/);
  await f.el('bot-start').click(); assert.equal(f.bodies.length,2);
});

test('unchanged settings need no redundant save and failed save never starts the Bot',async()=>{
  const unchanged=await fixture(true);
  await unchanged.el('bot-start').click();
  assert.deepEqual(unchanged.bodies,[{action:'start'}]);
  const changed=await fixture(true);
  changed.el('bot-now').checked=false;
  await changed.el('bot-start').click();
  assert.deepEqual(changed.calls,['/api/bot','/api/bot/settings']);
  assert.match(changed.el('bot-start-result').textContent,/接続できませんでした/);
});

test('stop during settings save cancels the following start request',async()=>{
  let f;
  f=await fixture(true,false,{},async body=>{
    if (!body.action) await f.el('bot-stop').click();
    return {ok:true,json:async()=>({...f.state,settings:body.action?f.state.settings:body})};
  });
  f.el('bot-now').checked=false;
  await f.el('bot-start').click();
  assert.deepEqual(f.calls,['/api/bot','/api/bot/settings','/api/bot/connection']);
  assert.deepEqual(f.bodies[1],{action:'stop'});
  assert.match(f.el('bot-start-result').textContent,/起動を取り消し/);
});
