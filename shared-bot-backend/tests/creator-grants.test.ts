import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {randomBytes} from 'node:crypto';
import {CreatorGrants, creatorConfigured, CREATOR_CHECK_MS, CREATOR_SCOPE} from '../backend/cloudflare/creator-grants';
import {ChannelConnections, type ChannelEnv} from '../backend/cloudflare/channel-connect';
import {AUTH_ORIGIN} from '../backend/cloudflare/bot-auth';
import {SqlBotStore, type SqlDriver} from '../backend/sql-store';
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
    return Response.json({access_token:'PRIVATE-CREATOR-ACCESS',expires_in:3600,token_type:'Bearer',scope:mode==='scope'?CREATOR_SCOPE+' write-scope':CREATOR_SCOPE});
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
