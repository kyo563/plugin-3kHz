import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { randomBytes } from 'node:crypto';
import { SqlBotStore, DEFAULT_LIMITS, CONNECTION_RETENTION_MS, type SqlDriver } from '../backend/sql-store';
import { ChannelConnections, type ChannelEnv } from '../backend/cloudflare/channel-connect';
import { PrivacyRecords } from '../backend/cloudflare/privacy';
import { AUTH_ORIGIN } from '../backend/cloudflare/bot-auth';
import { digest } from '../backend/policy';
import { BotService } from '../backend/service';
import { publicInfo } from '../backend/cloudflare/public-info';

function fixture() {
  const db = new DatabaseSync(':memory:'); let now = Date.parse('2026-10-01T00:00:00Z');
  const driver: SqlDriver = {exec:s=>db.exec(s), prepare:s=>db.prepare(s), transaction:fn=>{
    db.exec('BEGIN'); try {const v=fn();db.exec('COMMIT');return v;} catch(e){db.exec('ROLLBACK');throw e;}
  }};
  const env: ChannelEnv={BOT_CHANNEL_ID:'UC'+'b'.repeat(22), BOT_DATA_LIFECYCLE_ENABLED:'true', BOT_POSTING_ENABLED:'true',
    CHANNEL_CONNECT_ENABLED:'true',GOOGLE_CLIENT_ID:'fake',GOOGLE_CLIENT_SECRET:'fake',BOT_VAULT_KEY:randomBytes(32).toString('base64url')};
  let lookups=0;
  const channels=new ChannelConnections(driver,env,{async resolveChat(){lookups++;return 'chat';},async post(){assert.fail('No post from privacy API');}},fetch,()=>now);
  const store=new SqlBotStore(driver,true), privacy=new PrivacyRecords(driver); store.setEnabled(true);
  function seed(n:string, age=0) {
    const channel='UC'+n.repeat(22), user='youtube:'+channel, device='device-'+n, token=randomBytes(32).toString('base64url'), connection='connection-'+n;
    store.provisionDevice(token,{userId:user,deviceId:device},now+30*86_400_000);
    store.provisionVerifiedConnection({id:connection,userId:user,channelId:channel,verifiedAt:now-age});
    db.prepare('INSERT INTO channel_pairings (id,tokenHash,browserKey,createdAt,expiresAt,status,channelId,connectionId,deviceId) VALUES (?,?,?,?,?,?,?,?,?)')
      .run('pair-'+n,digest(token),'browser',now-age,now+600000,'connected',channel,connection,device);
    db.prepare('INSERT INTO channel_checks VALUES (?,?)').run(device,now);
    const data={requestId:'post-'+n,userId:user,channelId:channel,eventHash:'event-'+n,fingerprint:'fingerprint',contentHash:'body-'+n};
    store.reserve(data,now-age,{...DEFAULT_LIMITS,channelGapMs:0,globalGapMs:0});
    return {channel,user,device,token,connection,data};
  }
  const api=(token:string,body:unknown={},path='erase')=>channels.handle(new Request(AUTH_ORIGIN+'/v1/connections/'+path,{method:'POST',
    headers:{Authorization:'Bearer '+token,'Content-Type':'application/json','X-JoinQueue-Source':'a'.repeat(64)},body:JSON.stringify(body)}));
  return {db,driver,store,privacy,env,seed,api,now:()=>now,advance:(ms:number)=>{now+=ms;},lookups:()=>lookups};
}

test('privacy erasure requires authenticated owner, explicit channel confirmation, feature flag and strict boundary',async()=>{
  const f=fixture();try{
    const a=f.seed('a');
    for(const body of [{},{confirmation:a.channel,extra:true},{confirmation:'wrong'}]) assert.equal((await f.api(a.token,body)).status,400);
    assert.equal((await f.api('z'.repeat(43),{confirmation:a.channel})).status,401);
    assert.equal((await f.api(a.token,{confirmation:'UC'+'c'.repeat(22)})).status,403);
    f.env.BOT_DATA_LIFECYCLE_ENABLED='false';assert.equal((await f.api(a.token,{confirmation:a.channel})).status,503);
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM posts').get()!.n,1);
    assert.equal(f.lookups(),0);
  }finally{f.db.close();}
});

test('public ownership page contains no credentials and never changes protected API/OAuth boundaries',async()=>{
  const page=publicInfo(new Request(AUTH_ORIGIN+'/'))!;
  assert.equal(page.status,200);assert.match(await page.text(),/google-site-verification/);
  assert.equal(page.headers.get('referrer-policy'),'no-referrer');
  for(const request of [new Request(AUTH_ORIGIN+'/?token=private'),new Request(AUTH_ORIGIN+'/connect'),
    new Request(AUTH_ORIGIN+'/',{method:'POST'}),new Request('https://evil.invalid/')]) assert.equal(publicInfo(request),undefined);
});

test('privacy erasure removes all own devices and ledger, preserves other creator and Bot vault, and is retry-safe',async()=>{
  const f=fixture();try{
    const a=f.seed('a'),c=f.seed('c');
    f.db.exec("CREATE TABLE local_queue (name TEXT); INSERT INTO local_queue VALUES ('keep-me');");
    f.db.prepare('INSERT INTO devices VALUES (?,?,?,?,0)').run(digest('s'.repeat(43)),a.user,'second-device',f.now()+100000);
    const response=await f.api(a.token,{confirmation:a.channel});assert.equal(response.status,200);
    assert.deepEqual(await response.json(),{status:'deleted',securityRetentionHours:25});
    for(const table of ['connections','devices','channel_pairings','channel_checks','posts']) assert.equal(f.db.prepare('SELECT count(*) AS n FROM '+table).get()!.n,1);
    assert.equal(f.store.connection(c.connection,c.user,f.now()).channelId,c.channel);
    assert.throws(()=>f.store.authenticate('Bearer '+a.token,f.now()));
    f.store.assertEnabled();assert.equal(f.db.prepare('SELECT name FROM local_queue').get()!.name,'keep-me');
    const dump=JSON.stringify(f.db.prepare('SELECT * FROM posts').all());assert.ok(!dump.includes(a.channel));
    assert.equal((await f.api(a.token,{confirmation:a.channel})).status,200);
    assert.equal((await f.api(a.token,{},'start')).status,403);
    assert.equal((await f.api(a.token,{confirmation:c.channel})).status,401);
    f.advance(86_400_000);f.privacy.prune(f.now());
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM erasure_receipts').get()!.n,0);
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM erasure_barriers').get()!.n,0);
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM rate_reservations').get()!.n,0);
  }finally{f.db.close();}
});

test('erasure never resets rate limits or daily quota, including migration from the legacy posting ledger',async()=>{
  const f=fixture();try{
    const a=f.seed('a');f.db.exec('DELETE FROM rate_reservations'); // Simulate existing production rows.
    await f.api(a.token,{confirmation:a.channel});
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM rate_reservations').get()!.n,1);
    assert.throws(()=>f.store.reserve({...a.data,requestId:'new',eventHash:'new',contentHash:'new'},f.now(),DEFAULT_LIMITS),/投稿間隔/);
    f.advance(60001);
    assert.throws(()=>f.store.reserve({...a.data,requestId:'new',eventHash:'new'},f.now(),{...DEFAULT_LIMITS,dailyUnits:52}),/利用上限/);
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM posts').get()!.n,0);
  }finally{f.db.close();}
});

test('29-day connection expiry stops API use and cleanup preserves fresh creators and Bot credentials',()=>{
  const f=fixture();try{
    const old=f.seed('a',CONNECTION_RETENTION_MS),fresh=f.seed('c');
    assert.throws(()=>f.store.connection(old.connection,old.user,f.now()),/チャンネル接続/);
    // Actual credential table, with a harmless synthetic encrypted fixture.
    f.db.prepare('INSERT INTO bot_credentials VALUES (1,?,?,?,?,?)').run('encrypted-fixture',f.env.BOT_CHANNEL_ID,'fake-client-hash',f.now(),f.now()+3600000);
    f.privacy.prune(f.now());
    for(const table of ['connections','devices','channel_pairings','channel_checks','posts']) assert.equal(f.db.prepare('SELECT count(*) AS n FROM '+table).get()!.n,1);
    assert.equal(f.store.connection(fresh.connection,fresh.user,f.now()).channelId,fresh.channel);
    assert.equal(f.db.prepare('SELECT encrypted FROM bot_credentials').get()!.encrypted,'encrypted-fixture');
    f.store.assertEnabled();
  }finally{f.db.close();}
});

test('deletion barriers reject older in-flight OAuth but allow a new explicit connection',async()=>{
  const f=fixture();try{
    const a=f.seed('a');await f.api(a.token,{confirmation:a.channel});
    assert.throws(()=>f.privacy.assertFreshPairing(a.channel,f.now()),/認証/);
    f.privacy.assertFreshPairing(a.channel,f.now()+1);
    f.privacy.assertFreshPairing('UC'+'d'.repeat(22),f.now()-1000);
  }finally{f.db.close();}
});

test('erasure during destination validation prevents a pending YouTube post, without resurrecting ledger rows',async()=>{
  const f=fixture();try{
    const a=f.seed('a');f.advance(70000);let entered!:()=>void,release!:()=>void,posts=0;
    const gate=new Promise<void>(r=>entered=r),pause=new Promise<void>(r=>release=r);
    const service=new BotService(f.store,{async resolveChat(){entered();await pause;return 'chat';},async post(){posts++;}},()=>{},f.now);
    const pending=service.submit('Bearer '+a.token,{channelConnectionId:a.connection,videoId:'abcdefghijk',eventId:'in-flight',createdAt:f.now(),templateId:'connection-test',variables:{}});
    await gate;await f.api(a.token,{confirmation:a.channel});release();await pending;
    assert.equal(posts,0);assert.equal(f.db.prepare('SELECT count(*) AS n FROM posts').get()!.n,0);
  }finally{f.db.close();}
});
