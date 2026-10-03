import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {randomBytes} from 'node:crypto';
import {CreatorGrants, creatorConfigured, CREATOR_CHECK_MS, CREATOR_SCOPE} from '../backend/cloudflare/creator-grants';
import {ChannelConnections, type ChannelEnv} from '../backend/cloudflare/channel-connect';
import {AUTH_ORIGIN} from '../backend/cloudflare/bot-auth';
import {SqlBotStore, CONNECTION_IDLE_MS, CONNECTION_RETENTION_MS, type SqlDriver} from '../backend/sql-store';
import {PrivacyRecords} from '../backend/cloudflare/privacy';
import {BotFault, digest} from '../backend/policy';
import {BotService} from '../backend/service';

function fixture() {
  const db=new DatabaseSync(':memory:'); let now=Date.parse('2026-10-01T00:00:00Z'), mode='ok', refreshes=0, revokes=0;
  let pause:(()=>Promise<void>)|undefined;
  const driver:SqlDriver={exec:s=>db.exec(s),prepare:s=>db.prepare(s),transaction:fn=>{
    db.exec('BEGIN');try{const v=fn();db.exec('COMMIT');return v;}catch(e){db.exec('ROLLBACK');throw e;}}};
  const env:ChannelEnv={BOT_CHANNEL_ID:'UC'+'b'.repeat(22),BOT_VAULT_KEY:randomBytes(32).toString('base64url'),
    GOOGLE_CLIENT_ID:'bot-client',GOOGLE_CLIENT_SECRET:'BOT-SECRET-DO-NOT-USE',BOT_GOOGLE_PROJECT_ID:'joinqueue-bot-dev',
    CREATOR_GOOGLE_CLIENT_ID:'creator-client',CREATOR_GOOGLE_CLIENT_SECRET:'CREATOR-SECRET',CREATOR_GOOGLE_PROJECT_ID:'joinqueue-creators-test',
    CHANNEL_GRANTS_ENABLED:'true',CHANNEL_CONNECT_ENABLED:'true',BOT_POSTING_ENABLED:'true',BOT_DATA_LIFECYCLE_ENABLED:'false'};
  const request:typeof fetch=async(url,init)=>{
    assert.equal(init?.redirect,'manual');assert.ok(init?.signal);
    if(url==='https://www.googleapis.com/youtube/v3/channels?part=id&mine=true') {
      const suffix = new Headers(init?.headers).get('Authorization')!.slice(-1);
      if(mode==='owner-fail') return Response.json({error:'private diagnostic'},{status:503});
      return Response.json({items:[{id:'UC'+(mode==='owner-mismatch'?'z':suffix).repeat(22)}]});
    }
    assert.equal(init?.method,'POST');const body=new URLSearchParams(String(init?.body));
    if(url==='https://oauth2.googleapis.com/revoke'){
      revokes++;assert.match(body.get('token')!,/^creator-refresh-/);assert.equal(body.has('client_secret'),false);
      if(mode==='revoke-fail') return Response.json({error:'temporary private diagnostic'},{status:503});
      return mode==='invalid-token'?Response.json({error:'invalid_token'},{status:400}):new Response('',{status:200});
    }
    assert.equal(url,'https://oauth2.googleapis.com/token');refreshes++;
    assert.equal(body.get('client_id'),'creator-client');assert.equal(body.get('client_secret'),'CREATOR-SECRET');
    assert.equal(body.get('grant_type'),'refresh_token');assert.match(body.get('refresh_token')!,/^creator-refresh-/);
    await pause?.();
    if(mode==='invalid')return Response.json({error:'invalid_grant'},{status:400});
    if(mode==='transient')return Response.json({error:'private secret diagnostic'},{status:503});
    return Response.json({access_token:'PRIVATE-CREATOR-ACCESS-'+body.get('refresh_token')!.slice(-1),expires_in:3600,token_type:'Bearer',scope:mode==='scope'?CREATOR_SCOPE+' write-scope':CREATOR_SCOPE});
  };
  const youtube={async resolveChat(){return 'chat';},async post(){assert.fail('No live posting in grant tests');}};
  new ChannelConnections(driver,env,youtube,request,()=>now);
  const store=new SqlBotStore(driver);store.setEnabled(true);
  db.prepare('INSERT INTO bot_credentials VALUES (1,?,?,?,?,?)').run('PRESERVE-BOT-CIPHERTEXT',env.BOT_CHANNEL_ID,digest(env.GOOGLE_CLIENT_ID!),now,0);
  const grants=new CreatorGrants(driver,env,request,()=>now);
  const seed=async(n:string)=>{
    const channel='UC'+n.repeat(22),connection='connection-'+n,device='device-'+n,token=randomBytes(32).toString('base64url');
    const prepared=await grants.prepare(connection,channel,'creator-refresh-'+n);
    driver.transaction(()=>{
      store.provisionVerifiedConnection({id:connection,userId:'youtube:'+channel,channelId:channel,verifiedAt:now});
      store.provisionDevice(token,{userId:'youtube:'+channel,deviceId:device},now+30*86400_000);
      db.prepare('INSERT INTO channel_pairings (id,tokenHash,browserKey,createdAt,expiresAt,status,channelId,connectionId,deviceId) VALUES (?,?,?,?,?,?,?,?,?)')
        .run('pair-'+n,digest(token),'browser',now,now+600000,'connected',channel,connection,device);
      grants.save(prepared);
    });return{channel,connection,device,token};
  };
  return{db,driver,env,grants,store,request,youtube,seed,now:()=>now,advance:(ms:number)=>{now+=ms;},mode:(v:string)=>{mode=v;},pause:(v:()=>Promise<void>)=>{pause=v;},
    counts:()=>({refreshes,revokes}),assertBot:()=>assert.equal(db.prepare('SELECT encrypted FROM bot_credentials').get()!.encrypted,'PRESERVE-BOT-CIPHERTEXT')};
}
const code=(v:string)=>(e:unknown)=>e instanceof BotFault&&e.code===v;

test('creator grants require explicitly isolated project and client; disabled/misconfigured fails closed',async()=>{
  const f=fixture();try{
    assert.equal(creatorConfigured(f.env),true);
    for(const change of [{CHANNEL_GRANTS_ENABLED:'false'},{CREATOR_GOOGLE_PROJECT_ID:f.env.BOT_GOOGLE_PROJECT_ID},
      {CREATOR_GOOGLE_CLIENT_ID:f.env.GOOGLE_CLIENT_ID},{CREATOR_GOOGLE_CLIENT_SECRET:undefined}]){
      const env={...f.env,...change};assert.equal(creatorConfigured(env),false);
      await assert.rejects(new CreatorGrants(f.driver,env,f.request,f.now).prepare('x','UC'+'a'.repeat(22),'creator-refresh-a'),code('SERVICE_DISABLED'));
    }
    assert.deepEqual(f.counts(),{refreshes:0,revokes:0});f.assertBot();
  }finally{f.db.close();}
});
test('creator refresh is encrypted, purpose/channel-bound and survives server object reconstruction',async()=>{
  const f=fixture();try{
    const a=await f.seed('a');const c=await f.seed('c');
    const dump=JSON.stringify(f.db.prepare('SELECT * FROM creator_grants').all());
    for(const secret of ['creator-refresh-a','CREATOR-SECRET','PRIVATE-CREATOR-ACCESS'])assert.ok(!dump.includes(secret));
    f.advance(CREATOR_CHECK_MS);
    await new CreatorGrants(f.driver,f.env,f.request,f.now).ensure(a.connection);assert.equal(f.counts().refreshes,1);
    const cipher=f.db.prepare('SELECT encrypted FROM creator_grants WHERE connectionId=?').get(a.connection)!.encrypted;
    f.db.prepare('UPDATE creator_grants SET encrypted=? WHERE connectionId=?').run(String(cipher),c.connection);
    await assert.rejects(f.grants.ensure(c.connection),code('CHANNEL_AUTH_UNAVAILABLE'));
    assert.equal(f.counts().refreshes,1);f.assertBot();
  }finally{f.db.close();}
});
test('creator checks deduplicate and do not persist returned access token',async()=>{
  const f=fixture();try{
    const a=await f.seed('a');await f.grants.ensure(a.connection);assert.equal(f.counts().refreshes,0);
    f.advance(CREATOR_CHECK_MS);await Promise.all([f.grants.ensure(a.connection),f.grants.ensure(a.connection)]);
    assert.equal(f.counts().refreshes,1);
    assert.ok(!JSON.stringify(f.db.prepare('SELECT * FROM creator_grants').all()).includes('PRIVATE-CREATOR-ACCESS'));f.assertBot();
  }finally{f.db.close();}
});
test('invalid_grant stops only the affected connection; transport failure retains encrypted credentials and blocks posts without shared shutdown',async()=>{
  for(const mode of ['invalid','transient','scope']){
    const f=fixture();try{
      const a=await f.seed('a'),c=await f.seed('c');f.advance(CREATOR_CHECK_MS);f.mode(mode);
      await assert.rejects(f.grants.ensure(a.connection),code(mode==='invalid'?'CHANNEL_NOT_LINKED':'CHANNEL_AUTH_UNAVAILABLE'));
      assert.equal(Number(f.db.prepare('SELECT count(*) AS n FROM creator_grants WHERE connectionId=?').get(a.connection)!.n),mode==='invalid'?0:1);
      f.store.authenticate('Bearer '+c.token,f.now());f.assertBot();f.store.assertEnabled();
      if(mode!=='invalid'){
        const svc=new BotService(f.store,f.youtube,()=>{},f.now,{},conn=>f.grants.ensure(conn.id));
        const result=await svc.submit('Bearer '+a.token,{channelConnectionId:a.connection,videoId:'abcdefghijk',eventId:'event',createdAt:f.now(),
          templateId:'connection-test',variables:{}});
        assert.equal(result.body.error?.code,'CHANNEL_AUTH_UNAVAILABLE');assert.ok(!JSON.stringify(result).includes('PRIVATE'));f.store.assertEnabled();
        assert.equal(f.counts().refreshes,1);f.mode('ok');f.advance(900000);await f.grants.ensure(a.connection);
      }else assert.throws(()=>f.store.authenticate('Bearer '+a.token,f.now()));
    }finally{f.db.close();}
  }
});
test('Google revoke uses form POST and isolated creator grant, stops local channel immediately, retries failure without erasing operational records',async()=>{
  const f=fixture();try{
    const a=await f.seed('a'),c=await f.seed('c');f.mode('revoke-fail');
    await assert.rejects(f.grants.revoke(a.channel),code('CHANNEL_AUTH_UNAVAILABLE'));
    assert.throws(()=>f.store.authenticate('Bearer '+a.token,f.now()));
    assert.equal(f.db.prepare('SELECT status FROM creator_grants WHERE connectionId=?').get(a.connection)!.status,'revoking');
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM connections').get()!.n,2); // no production data lifecycle activation
    f.store.authenticate('Bearer '+c.token,f.now());f.assertBot();
    f.mode('invalid-token');f.advance(900000);await f.grants.sweep();
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM creator_grants').get()!.n,1);
    f.store.authenticate('Bearer '+c.token,f.now());f.assertBot();assert.equal(f.counts().revokes,2);
  }finally{f.db.close();}
});
test('revocation during refresh never resurrects a grant or a device',async()=>{
  const f=fixture();try{
    const a=await f.seed('a');f.advance(CREATOR_CHECK_MS);let release!:()=>void,reached!:()=>void;
    const entered=new Promise<void>(r=>{reached=r;});f.pause(()=>new Promise<void>(r=>{release=r;reached();}));
    const pending=f.grants.ensure(a.connection);const rejected=assert.rejects(pending,code('CHANNEL_NOT_LINKED'));
    await entered;await f.grants.revoke(a.channel);release();await rejected;
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM creator_grants').get()!.n,0);
    assert.throws(()=>f.store.authenticate('Bearer '+a.token,f.now()));f.assertBot();
  }finally{f.db.close();}
});
test('periodic sweep checks due creators without local retention deletion and preserves retry fairness',async()=>{
  const f=fixture();try{
    const a=await f.seed('a'),c=await f.seed('c');f.advance(CREATOR_CHECK_MS);f.mode('transient');await f.grants.sweep();
    assert.equal(f.counts().refreshes,2);assert.equal(f.db.prepare('SELECT count(*) AS n FROM creator_grants').get()!.n,2);
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM connections').get()!.n,2);
    f.mode('ok');f.advance(900000);await f.grants.sweep();assert.equal(f.counts().refreshes,4);
    await f.grants.ensure(a.connection);await f.grants.ensure(c.connection);f.assertBot();
  }finally{f.db.close();}
});
test('disconnect endpoint waits for Google revocation acknowledgement and never returns refresh/access tokens',async()=>{
  const f=fixture();try{
    const a=await f.seed('a');const api=()=>new ChannelConnections(f.driver,f.env,f.youtube,f.request,f.now).handle(new Request(AUTH_ORIGIN+'/v1/connections/disconnect',{
      method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+a.token},body:'{}'}));
    f.mode('revoke-fail');assert.equal((await api()).status,503);f.mode('ok');
    const r=await api();assert.equal(r.status,200);assert.deepEqual(await r.json(),{status:'disconnected'});
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM creator_grants').get()!.n,0);f.assertBot();
  }finally{f.db.close();}
});

test('old in-flight OAuth cannot recreate revoked channel even with data lifecycle disabled',async()=>{
  const f=fixture();try{
    const a=await f.seed('a');const old=await f.grants.prepare('stale-connection',a.channel,'creator-refresh-new');
    await f.grants.revoke(a.channel);assert.throws(()=>f.grants.save(old),code('CHANNEL_NOT_LINKED'));
    f.advance(1);const fresh=await f.grants.prepare('fresh-connection',a.channel,'creator-refresh-new');f.grants.save(fresh);
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM creator_grants').get()!.n,1);f.assertBot();
  }finally{f.db.close();}
});
test('erasure retry uses the same owner credential after failed Google revoke, not arbitrary channel claims',async()=>{
  const f=fixture();try{
    const a=await f.seed('a'),c=await f.seed('c');f.env.BOT_DATA_LIFECYCLE_ENABLED='true';
    const api=(channel:string)=>new ChannelConnections(f.driver,f.env,f.youtube,f.request,f.now).handle(new Request(AUTH_ORIGIN+'/v1/connections/erase',{
      method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+a.token},body:JSON.stringify({confirmation:channel})}));
    f.mode('revoke-fail');assert.equal((await api(a.channel)).status,503);
    assert.equal((await api(c.channel)).status,403);f.mode('ok');
    assert.equal((await api(a.channel)).status,200);assert.equal((await api(a.channel)).status,200);
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM connections').get()!.n,1);
    f.store.authenticate('Bearer '+c.token,f.now());f.assertBot();
  }finally{f.db.close();}
});

test('90-day inactivity slides only on authenticated plugin activity, not provider refresh or alarms',async()=>{
  const f=fixture();try{
    const a=await f.seed('a'), other=await f.seed('c');
    const store=new SqlBotStore(f.driver,true,true);
    f.db.prepare('UPDATE devices SET expiresAt=?').run(f.now()+CONNECTION_IDLE_MS);
    const initial=f.now();f.advance(28*86400_000);
    await f.grants.ensure(a.connection);
    assert.equal(f.db.prepare('SELECT verifiedAt,lastUsedAt FROM connections WHERE id=?').get(a.connection)!.lastUsedAt,initial);
    assert.equal(f.db.prepare('SELECT verifiedAt FROM connections WHERE id=?').get(a.connection)!.verifiedAt,f.now());
    const api=new ChannelConnections(f.driver,f.env,f.youtube,f.request,f.now);
    const r=await api.handle(new Request(AUTH_ORIGIN+'/v1/connections/status',{method:'POST',
      headers:{'Content-Type':'application/json',Authorization:'Bearer '+a.token},body:'{}'}));
    assert.equal(r.status,200);
    assert.equal(f.db.prepare('SELECT lastUsedAt FROM connections WHERE id=?').get(a.connection)!.lastUsedAt,f.now());
    assert.equal(f.db.prepare('SELECT lastUsedAt FROM connections WHERE id=?').get(other.connection)!.lastUsedAt,initial);
    f.advance(63*86400_000);
    // Active user survives day 91; never-used creator expires despite automatic checks.
    store.authenticate('Bearer '+a.token,f.now());store.connection(a.connection,'youtube:'+a.channel,f.now());
    assert.throws(()=>store.connection(other.connection,'youtube:'+other.channel,f.now()),code('CHANNEL_NOT_LINKED'));
    const before=f.counts().refreshes;
    await assert.rejects(f.grants.ensure(other.connection),code('CHANNEL_NOT_LINKED'));
    assert.equal(f.counts().refreshes,before);f.assertBot();
  }finally{f.db.close();}
});

test('idle expiry revokes then prunes only that creator; old posts expire independently after 29 days',async()=>{
  const f=fixture();try{
    const a=await f.seed('a'),c=await f.seed('c');f.env.BOT_DATA_LIFECYCLE_ENABLED='true';
    f.db.prepare('UPDATE devices SET expiresAt=?').run(f.now()+CONNECTION_IDLE_MS);
    f.advance(CONNECTION_IDLE_MS);
    f.db.prepare('UPDATE connections SET lastUsedAt=?,verifiedAt=? WHERE id=?').run(f.now(),f.now(),c.connection);
    f.db.prepare('UPDATE devices SET expiresAt=? WHERE deviceId=?').run(f.now()+CONNECTION_IDLE_MS,c.device);
    await f.grants.sweep();new PrivacyRecords(f.driver,true).prune(f.now());
    assert.equal(f.counts().revokes,1);
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM connections').get()!.n,1);
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM creator_grants').get()!.n,1);
    assert.throws(()=>f.store.authenticate('Bearer '+a.token,f.now()));
    f.store.authenticate('Bearer '+c.token,f.now());f.assertBot();
  }finally{f.db.close();}
});

test('channel-data refresh failure cannot retain stale API ownership beyond its separate 29-day deadline',async()=>{
  const f=fixture();try{
    const a=await f.seed('a');f.advance(CONNECTION_RETENTION_MS-900000);f.mode('owner-fail');
    await assert.rejects(f.grants.ensure(a.connection),code('CHANNEL_AUTH_UNAVAILABLE'));
    f.advance(900000);
    await assert.rejects(f.grants.ensure(a.connection),code('CHANNEL_NOT_LINKED'));
    new PrivacyRecords(f.driver,true).prune(f.now());
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM creator_grants').get()!.n,0);
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM connections').get()!.n,0);f.assertBot();
  }finally{f.db.close();}
});

test('ownership mismatch invalidates connection; forged status and ordinary Google refresh never extend usage',async()=>{
  const f=fixture();try{
    const a=await f.seed('a'),initial=f.now();f.advance(CREATOR_CHECK_MS);f.mode('owner-mismatch');
    await assert.rejects(f.grants.ensure(a.connection),code('CHANNEL_NOT_LINKED'));
    const store=new SqlBotStore(f.driver,true,true);
    assert.throws(()=>store.recordUse(a.connection,'youtube:'+a.channel,f.now()),code('CHANNEL_NOT_LINKED'));
    assert.equal(f.db.prepare('SELECT lastUsedAt FROM connections WHERE id=?').get(a.connection)!.lastUsedAt,initial);f.assertBot();
  }finally{f.db.close();}
});

test('migration initializes activity from original verification date, never resets it on server restart',()=>{
  const db=new DatabaseSync(':memory:');try{
    db.exec("CREATE TABLE connections (id TEXT PRIMARY KEY,userId TEXT,channelId TEXT,verifiedAt INTEGER,revoked INTEGER); INSERT INTO connections VALUES ('old','owner','UCaaaaaaaaaaaaaaaaaaaaaa',12345,0)");
    const driver:SqlDriver={exec:s=>db.exec(s),prepare:s=>db.prepare(s),transaction:fn=>fn()};
    new SqlBotStore(driver,true,true);new SqlBotStore(driver,true,true);
    assert.equal(db.prepare('SELECT lastUsedAt FROM connections').get()!.lastUsedAt,12345);
  }finally{db.close();}
});

test('one active device extends its own channel only, never revives expired or revoked device keys',async()=>{
  const f=fixture();try{
    const a=await f.seed('a'),c=await f.seed('c'),initial=f.now();
    const store=new SqlBotStore(f.driver,true,true);
    store.provisionVerifiedConnection({id:'second-a',userId:'youtube:'+a.channel,channelId:a.channel,verifiedAt:initial});
    store.provisionDevice('r'.repeat(43),{userId:'youtube:'+a.channel,deviceId:'revoked-a'},initial+CONNECTION_IDLE_MS);
    store.revokeDevice('revoked-a');
    store.provisionDevice('e'.repeat(43),{userId:'youtube:'+a.channel,deviceId:'expired-a'},initial+1);
    f.advance(1000);store.recordUse(a.connection,'youtube:'+a.channel,f.now());
    assert.equal(f.db.prepare('SELECT lastUsedAt FROM connections WHERE id=?').get('second-a')!.lastUsedAt,f.now());
    assert.equal(f.db.prepare('SELECT lastUsedAt FROM connections WHERE id=?').get(c.connection)!.lastUsedAt,initial);
    assert.throws(()=>store.authenticate('Bearer '+'r'.repeat(43),f.now()));
    assert.throws(()=>store.authenticate('Bearer '+'e'.repeat(43),f.now()));
    assert.throws(()=>store.recordUse(a.connection,'youtube:'+c.channel,f.now()),code('CHANNEL_NOT_LINKED'));f.assertBot();
  }finally{f.db.close();}
});

test('valid Bot requests count as channel use, invalid or foreign-destination requests do not',async()=>{
  const f=fixture();try{
    const a=await f.seed('a'),initial=f.now();f.advance(60001);
    const store=new SqlBotStore(f.driver,true,true);let posts=0;
    const youtube={async resolveChat(video:string){if(video==='wrong000000')throw new BotFault('CHANNEL_MISMATCH',403);return 'chat';},async post(){posts++;}};
    const svc=new BotService(store,youtube,()=>{},f.now,{},conn=>f.grants.ensure(conn.id));
    const input={channelConnectionId:a.connection,videoId:'wrong000000',eventId:'wrong-target',createdAt:f.now(),templateId:'connection-test',variables:{}};
    assert.equal((await svc.submit('Bearer '+a.token,input)).body.error?.code,'CHANNEL_MISMATCH');
    assert.equal(f.db.prepare('SELECT lastUsedAt FROM connections WHERE id=?').get(a.connection)!.lastUsedAt,initial);
    f.advance(60001);assert.equal((await svc.submit('Bearer '+a.token,{...input,videoId:'abcdefghijk',eventId:'valid',createdAt:f.now()})).body.status,'sent');
    assert.equal(posts,1);assert.equal(f.db.prepare('SELECT lastUsedAt FROM connections WHERE id=?').get(a.connection)!.lastUsedAt,f.now());f.assertBot();
  }finally{f.db.close();}
});

test('inactivity sweep with lifecycle disabled rejects stale use but does not erase production records',async()=>{
  const f=fixture();try{
    const a=await f.seed('a');f.advance(CONNECTION_IDLE_MS);
    await f.grants.sweep();
    assert.equal(f.counts().revokes,0);
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM connections').get()!.n,1);
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM creator_grants').get()!.n,1);
    await assert.rejects(f.grants.ensure(a.connection),code('CHANNEL_NOT_LINKED'));f.assertBot();
  }finally{f.db.close();}
});

test('posting ledger retention remains 29 days while an actively used connection survives',async()=>{
  const f=fixture();try{
    const a=await f.seed('a');
    f.store.reserve({requestId:'old-post',userId:'youtube:'+a.channel,channelId:a.channel,eventHash:'event',fingerprint:'fp',contentHash:'body'},f.now(),
      {userPerMinute:12,channelPerMinute:6,globalPerMinute:20,channelGapMs:0,globalGapMs:0,dailyUnits:8000});
    f.advance(CONNECTION_RETENTION_MS);await f.grants.ensure(a.connection);
    new SqlBotStore(f.driver,true,true).recordUse(a.connection,'youtube:'+a.channel,f.now());
    new PrivacyRecords(f.driver,true).prune(f.now());
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM posts').get()!.n,0);
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM connections').get()!.n,1);
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM creator_grants').get()!.n,1);f.assertBot();
  }finally{f.db.close();}
});
