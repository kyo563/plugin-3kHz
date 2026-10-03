import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createHash, randomBytes } from 'node:crypto';
import { AUTH_ORIGIN, AUTH_PATH, CALLBACK_PATH, BOT_SCOPE, BotAuthorization, BotVault, authBoundary, type BotAuthEnv } from '../backend/cloudflare/bot-auth';
import { GoogleRefreshTokens } from '../backend/cloudflare/tokens';
import { BotFault } from '../backend/policy';
import type { SqlDriver } from '../backend/sql-store';

const hash = (v: string) => createHash('sha256').update(v).digest('hex');
function fixture() {
  const db = new DatabaseSync(':memory:'); let now = 1_000_000;
  const driver: SqlDriver = { exec: sql => { db.exec(sql); }, prepare: sql => db.prepare(sql), transaction: fn => {
    db.exec('BEGIN'); try { const result = fn(); db.exec('COMMIT'); return result; } catch (e) { db.exec('ROLLBACK'); throw e; }
  } };
  const setup = randomBytes(32).toString('base64url');
  const env: BotAuthEnv = { BOT_CHANNEL_ID: 'UC' + 'a'.repeat(22), GOOGLE_CLIENT_ID: 'fake-client', GOOGLE_CLIENT_SECRET: 'fake-secret',
    BOT_VAULT_KEY: randomBytes(32).toString('base64url'), BOT_AUTH_SETUP_HASH: hash(setup), BOT_AUTH_ENABLED: 'true', BOT_AUTH_EXPIRES_AT: String(now + 3600_000) };
  let exchanges = 0; let refreshes = 0; let lookups = 0; let wrongBot = false; let badRefresh = false; let deniedScope = false;
  let refreshLifetime: number | undefined = 604800;
  const request: typeof fetch = async (url, init) => {
    assert.equal(init?.redirect, 'manual'); assert.ok(init?.signal);
    if (url === 'https://oauth2.googleapis.com/token') {
      const fields = new URLSearchParams(String(init?.body));
      assert.equal(fields.get('client_secret'), env.GOOGLE_CLIENT_SECRET);
      if (fields.get('grant_type') === 'authorization_code') {
        exchanges++; assert.equal(fields.get('redirect_uri'), AUTH_ORIGIN + CALLBACK_PATH);
        assert.match(fields.get('code_verifier')!, /^[A-Za-z0-9_-]{43}$/);
        return Response.json({ access_token: 'fake-access', refresh_token: 'fake-refresh', expires_in: 3600, token_type: 'Bearer', scope: deniedScope ? 'unrelated' : BOT_SCOPE, refresh_token_expires_in: refreshLifetime });
      }
      refreshes++; assert.equal(fields.get('refresh_token'), 'fake-refresh');
      return badRefresh ? new Response('private-provider-error', { status: 400 }) : Response.json({ access_token: 'fake-refreshed', expires_in: 3600, token_type: 'Bearer' });
    }
    assert.equal(url, 'https://www.googleapis.com/youtube/v3/channels?part=id&mine=true');
    assert.equal(new Headers(init?.headers).get('Authorization'), 'Bearer fake-refreshed');
    lookups++; return Response.json({ items: [{ id: wrongBot ? 'UC' + 'b'.repeat(22) : env.BOT_CHANNEL_ID }] });
  };
  const auth = () => new BotAuthorization(driver, env, request, () => now);
  const landing = async () => {
    const page = await auth().handle(new Request(AUTH_ORIGIN + AUTH_PATH));
    const html = await page.text(); const cookie = page.headers.get('set-cookie')!.split(';')[0]!;
    assert.match(page.headers.get('set-cookie')!, /Secure; HttpOnly; SameSite=Lax/);
    return { cookie, csrf: /name="csrf" value="([^"]+)"/.exec(html)![1]! };
  };
  const start = async (browser: { cookie: string; csrf: string }, overrides: Record<string, string> = {}) => auth().handle(new Request(AUTH_ORIGIN + AUTH_PATH, {
    method: 'POST', headers: { Origin: AUTH_ORIGIN, Cookie: browser.cookie, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ setup, csrf: browser.csrf, ...overrides }),
  }));
  const callback = (state: string, cookie: string, query = '') => new Request(AUTH_ORIGIN + CALLBACK_PATH + '?state=' + state + '&code=fake-code' + query, { headers: { Cookie: cookie } });
  return { db, driver, env, setup, auth, landing, start, callback, request, clock: () => now,
    advance: (n: number) => { now += n; }, counts: () => ({ exchanges, refreshes, lookups }),
    setRefreshLifetime: (value: number | undefined) => { refreshLifetime = value; },
    setWrongBot: () => { wrongBot = true; }, setBadRefresh: () => { badRefresh = true; }, setDeniedScope: () => { deniedScope = true; } };
}

test('Bot OAuth: 停止/別ホスト/Origin/余分な経路は入口で拒否', () => {
  const f = fixture();
  try {
    const req = new Request(AUTH_ORIGIN + AUTH_PATH);
    assert.equal(authBoundary(req, f.env, f.clock()), true);
    for (const env of [{ ...f.env, BOT_AUTH_ENABLED: 'false' }, { ...f.env, BOT_AUTH_EXPIRES_AT: '0' },
      { ...f.env, BOT_AUTH_EXPIRES_AT: String(f.clock() + 86_400_001) }, { ...f.env, BOT_VAULT_KEY: '' }]) assert.equal(authBoundary(req, env, f.clock()), false);
    for (const request of [new Request('https://evil.invalid' + AUTH_PATH), new Request(AUTH_ORIGIN + AUTH_PATH + '?return=evil'),
      new Request(AUTH_ORIGIN + AUTH_PATH + '/secrets'), new Request(AUTH_ORIGIN + CALLBACK_PATH, { method: 'POST' }),
      new Request(AUTH_ORIGIN + AUTH_PATH, { method: 'POST', headers: { Origin: 'null', 'Content-Type': 'application/x-www-form-urlencoded' } })]) {
      assert.equal(authBoundary(request, f.env, f.clock()), false);
    }
  } finally { f.db.close(); }
});

test('Bot OAuth: setup/CSRF/cookieを検証し固定Google URLへPKCE付きで一度だけ開始', async () => {
  const f = fixture();
  try {
    const b = await f.landing();
    assert.equal((await f.start(b, { setup: 'a'.repeat(43) })).status, 403);
    assert.equal((await f.start(b, { csrf: 'a'.repeat(43) })).status, 403);
    const result = await f.start(b); assert.equal(result.status, 303);
    const url = new URL(result.headers.get('location')!);
    assert.equal(url.origin, 'https://accounts.google.com'); assert.equal(url.pathname, '/o/oauth2/v2/auth');
    assert.equal(url.searchParams.get('scope'), BOT_SCOPE); assert.equal(url.searchParams.get('code_challenge_method'), 'S256');
    assert.equal(url.searchParams.get('redirect_uri'), AUTH_ORIGIN + CALLBACK_PATH);
    assert.ok(!url.href.includes(f.env.GOOGLE_CLIENT_SECRET!)); assert.ok(!url.href.includes(f.setup));
    assert.equal((await f.start(b)).status, 403);
    assert.deepEqual(f.counts(), { exchanges: 0, refreshes: 0, lookups: 0 });
    const row = f.db.prepare('SELECT * FROM bot_auth_session').get()!;
    assert.ok(!JSON.stringify(row).includes(url.searchParams.get('state')!)); assert.ok(!JSON.stringify(row).includes(b.csrf));
  } finally { f.db.close(); }
});

test('Bot OAuth: 同時callbackは一度だけ交換・refresh・Bot照合し暗号化保存、復元後も秘密を外へ返さない', async () => {
  const f = fixture();
  try {
    const b = await f.landing(); const redirect = await f.start(b); const state = new URL(redirect.headers.get('location')!).searchParams.get('state')!;
    const callbacks = await Promise.all([f.auth().handle(f.callback(state, b.cookie)), f.auth().handle(f.callback(state, b.cookie))]);
    assert.deepEqual(callbacks.map(r => r.status).sort(), [303, 403]);
    assert.deepEqual(f.counts(), { exchanges: 1, refreshes: 1, lookups: 1 });
    const vault = new BotVault(f.driver, f.env); assert.equal(await vault.refreshToken(f.clock()), 'fake-refresh');
    assert.equal(JSON.stringify(vault), '{}'); assert.equal(JSON.stringify(f.auth()), '{}');
    const snapshot = JSON.stringify(f.db.prepare('SELECT * FROM bot_credentials').all());
    for (const secret of ['fake-refresh', 'fake-access', 'fake-secret', f.setup, f.env.BOT_VAULT_KEY!]) assert.ok(!snapshot.includes(secret));
    const result = await f.auth().handle(new Request(AUTH_ORIGIN + AUTH_PATH + '/result', { headers: { Cookie: b.cookie } }));
    assert.equal(result.status, 200); assert.match(await result.text(), /Botの認証が完了/);
    assert.equal((await f.auth().handle(new Request(AUTH_ORIGIN + AUTH_PATH + '/result'))).status, 403);
    assert.equal((await f.start(b)).status, 409);
    const provider = new GoogleRefreshTokens(f.env, f.request, f.clock, () => vault.refreshToken(f.clock()));
    assert.equal(await provider.accessToken(), 'fake-refreshed');
    await assert.rejects(new BotVault(f.driver, { ...f.env, BOT_VAULT_KEY: randomBytes(32).toString('base64url') }).refreshToken(f.clock()));
    f.advance(604800_000); await assert.rejects(vault.refreshToken(f.clock()));
  } finally { f.db.close(); }
});

test('Bot OAuth: state/cookie不一致・重複query・期限切れはGoogleへ送らない', async () => {
  const f = fixture();
  try {
    const b = await f.landing(); const redirect = await f.start(b); const state = new URL(redirect.headers.get('location')!).searchParams.get('state')!;
    for (const req of [f.callback('a'.repeat(43), b.cookie), f.callback(state, ''), f.callback(state, b.cookie, '&state=again'), f.callback(state, b.cookie, '&iss=https://evil.invalid')]) {
      assert.equal((await f.auth().handle(req)).status, 403);
    }
    f.advance(600_001); assert.equal((await f.auth().handle(f.callback(state, b.cookie))).status, 403);
    assert.deepEqual(f.counts(), { exchanges: 0, refreshes: 0, lookups: 0 });
  } finally { f.db.close(); }
});

test('Bot OAuth: 別Bot・refresh失敗・scope不足・拒否は保存せず同じ認可コードも再利用しない', async () => {
  for (const mode of ['wrongBot', 'refresh', 'scope', 'denied']) {
    const f = fixture();
    try {
      if (mode === 'wrongBot') f.setWrongBot(); if (mode === 'refresh') f.setBadRefresh(); if (mode === 'scope') f.setDeniedScope();
      const b = await f.landing(); const redirect = await f.start(b); const state = new URL(redirect.headers.get('location')!).searchParams.get('state')!;
      const result = await f.auth().handle(f.callback(state, b.cookie, mode === 'denied' ? '&error=access_denied' : ''));
      assert.equal(result.status, 303); assert.ok(!result.headers.get('location')!.includes('code='));
      assert.equal(new BotVault(f.driver, f.env).connected(), false);
      assert.equal((await f.auth().handle(f.callback(state, b.cookie))).status, 403);
      const page = await f.auth().handle(new Request(result.headers.get('location')!, { headers: { Cookie: b.cookie } }));
      assert.equal(page.status, 400); assert.ok(!(await page.text()).includes('private-provider-error'));
    } finally { f.db.close(); }
  }
});

async function expiredCredential(f: ReturnType<typeof fixture>) {
  const vault = new BotVault(f.driver, f.env);
  const encrypted = await vault.crypt('old-expired-refresh', 'refresh');
  f.db.prepare('INSERT INTO bot_credentials VALUES (1,?,?,?,?,?)').run(encrypted, f.env.BOT_CHANNEL_ID,
    hash(f.env.GOOGLE_CLIENT_ID!), f.clock() - 604800_000, f.clock());
  return vault;
}

test('Bot OAuth renewal: expired same-Bot grant is kept until verified replacement, callback remains single-use', async () => {
  const f = fixture();
  try {
    const vault = await expiredCredential(f);
    const original = JSON.stringify(f.db.prepare('SELECT * FROM bot_credentials').get());
    assert.equal(vault.canAuthorize(f.clock()), true);
    await assert.rejects(vault.refreshToken(f.clock()), (e: any) => e.code === 'BOT_AUTH_EXPIRED');
    const b = await f.landing(); const redirect = await f.start(b);
    assert.equal(redirect.status, 303);
    assert.equal(JSON.stringify(f.db.prepare('SELECT * FROM bot_credentials').get()), original);
    const state = new URL(redirect.headers.get('location')!).searchParams.get('state')!;
    const result = await Promise.all([f.auth().handle(f.callback(state, b.cookie)), f.auth().handle(f.callback(state, b.cookie))]);
    assert.deepEqual(result.map(r => r.status).sort(), [303, 403]);
    assert.deepEqual(f.counts(), {exchanges:1, refreshes:1, lookups:1});
    assert.equal(await vault.refreshToken(f.clock()), 'fake-refresh');
    assert.equal(vault.canAuthorize(f.clock()), false);
    assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM bot_credentials').get()!.n, 1);
    assert.equal((await f.auth().handle(new Request(AUTH_ORIGIN + AUTH_PATH))).status, 409);
  } finally { f.db.close(); }
});

test('Bot OAuth renewal: denial/wrong Bot/refresh failure/scope failure retain expired ciphertext unchanged', async () => {
  for (const mode of ['denied','wrongBot','refresh','scope']) {
    const f = fixture();
    try {
      await expiredCredential(f);
      const original = JSON.stringify(f.db.prepare('SELECT * FROM bot_credentials').get());
      if (mode === 'wrongBot') f.setWrongBot(); if (mode === 'refresh') f.setBadRefresh(); if (mode === 'scope') f.setDeniedScope();
      const b = await f.landing(); const redirect = await f.start(b);
      const state = new URL(redirect.headers.get('location')!).searchParams.get('state')!;
      await f.auth().handle(f.callback(state, b.cookie, mode === 'denied' ? '&error=access_denied' : ''));
      assert.equal(JSON.stringify(f.db.prepare('SELECT * FROM bot_credentials').get()), original);
      assert.equal(f.db.prepare('SELECT status FROM bot_auth_session').get()!.status, 'failed');
      assert.equal((await f.auth().handle(f.callback(state, b.cookie))).status, 403);
    } finally { f.db.close(); }
  }
});

test('Bot OAuth renewal: active/unknown expiry/foreign Bot or client grants cannot be overwritten', async () => {
  for (const mode of ['active','unknown','foreignBot','foreignClient']) {
    const f = fixture();
    try {
      const vault = await expiredCredential(f);
      if (mode === 'active') f.db.prepare('UPDATE bot_credentials SET expiresAt=?').run(f.clock()+1);
      if (mode === 'unknown') f.db.prepare('UPDATE bot_credentials SET expiresAt=0').run();
      if (mode === 'foreignBot') f.db.prepare('UPDATE bot_credentials SET channelId=?').run('UC'+'b'.repeat(22));
      if (mode === 'foreignClient') f.db.prepare('UPDATE bot_credentials SET clientIdHash=?').run(hash('other-client'));
      assert.equal(vault.canAuthorize(f.clock()), false);
      assert.equal((await f.auth().handle(new Request(AUTH_ORIGIN+AUTH_PATH))).status,409);
      assert.deepEqual(f.counts(), {exchanges:0,refreshes:0,lookups:0});
    } finally { f.db.close(); }
  }
});

test('Bot OAuth renewal: concurrent replacement during Google verification is not overwritten', async () => {
  const f = fixture();
  try {
    await expiredCredential(f);
    const b=await f.landing(); const redirect=await f.start(b);
    const state=new URL(redirect.headers.get('location')!).searchParams.get('state')!;
    const transport: typeof fetch = async (url,init) => {
      const response=await f.request(url,init);
      if (String(url).includes('/channels?')) f.db.prepare('UPDATE bot_credentials SET expiresAt=?').run(f.clock()+100000);
      return response;
    };
    const auth=new BotAuthorization(f.driver,f.env,transport,f.clock);
    await auth.handle(f.callback(state,b.cookie));
    assert.equal(f.db.prepare('SELECT status FROM bot_auth_session').get()!.status,'failed');
    assert.equal(f.db.prepare('SELECT expiresAt FROM bot_credentials').get()!.expiresAt,f.clock()+100000);
    assert.equal(await new BotVault(f.driver,f.env).refreshToken(f.clock()),'old-expired-refresh');
  } finally { f.db.close(); }
});

test('Bot OAuth renewal: known expiry survives provider cooldown without Google calls or secret leakage', async () => {
  const f=fixture();
  try {
    const vault=await expiredCredential(f);
    const provider=new GoogleRefreshTokens(f.env,f.request,f.clock,()=>vault.refreshToken(f.clock()));
    for (let i=0;i<2;i++) await assert.rejects(provider.accessToken(), (e:any) => {
      assert.ok(e instanceof BotFault); assert.equal(e.code,'BOT_AUTH_EXPIRED');
      assert.ok(!e.message.includes('old-expired-refresh')); return true;
    });
    assert.deepEqual(f.counts(),{exchanges:0,refreshes:0,lookups:0});
  } finally { f.db.close(); }
});

async function approvedShortGrant(f: ReturnType<typeof fixture>) {
  const vault = await expiredCredential(f);
  const connected = f.clock() - 1000, expiry = connected + 604740_000;
  f.db.prepare('UPDATE bot_credentials SET connectedAt=?,expiresAt=?').run(connected, expiry);
  f.env.BOT_AUTH_REPLACE_GRANT = `${connected}:${expiry}`;
  return vault;
}

test('Bot production migration: exact short-grant pin permits atomic replacement without a fixed Google deadline', async () => {
  const f = fixture();
  try {
    const vault = await approvedShortGrant(f); f.setRefreshLifetime(undefined);
    const original = JSON.stringify(f.db.prepare('SELECT * FROM bot_credentials').get());
    assert.equal(vault.canAuthorize(f.clock()), true);
    const b = await f.landing(), redirect = await f.start(b);
    assert.equal(redirect.status,303);
    assert.equal(JSON.stringify(f.db.prepare('SELECT * FROM bot_credentials').get()), original);
    const state = new URL(redirect.headers.get('location')!).searchParams.get('state')!;
    const replies = await Promise.all([f.auth().handle(f.callback(state,b.cookie)), f.auth().handle(f.callback(state,b.cookie))]);
    assert.deepEqual(replies.map(r=>r.status).sort(),[303,403]);
    assert.equal(f.db.prepare('SELECT status FROM bot_auth_session').get()!.status,'connected');
    assert.equal(f.db.prepare('SELECT expiresAt FROM bot_credentials').get()!.expiresAt,0);
    assert.equal(await vault.refreshToken(f.clock()),'fake-refresh');
    assert.equal(vault.canAuthorize(f.clock()),false);
    assert.deepEqual(f.counts(),{exchanges:1,refreshes:1,lookups:1});
  } finally { f.db.close(); }
});

test('Bot production migration: no/stale pin, long/unknown expiry, foreign identity and disabled window are denied', async () => {
  for (const mode of ['noPin','stalePin','long','unknown','foreignBot','foreignClient','disabled','elapsed']) {
    const f = fixture();
    try {
      const vault = await approvedShortGrant(f);
      if(mode==='noPin') delete f.env.BOT_AUTH_REPLACE_GRANT;
      if(mode==='stalePin') f.env.BOT_AUTH_REPLACE_GRANT='1:2';
      if(mode==='long') {
        const expiry = f.clock()+8*86400_000;
        f.db.prepare('UPDATE bot_credentials SET expiresAt=?').run(expiry);
        f.env.BOT_AUTH_REPLACE_GRANT=`${f.clock()-1000}:${expiry}`;
      }
      if(mode==='unknown') f.db.prepare('UPDATE bot_credentials SET expiresAt=0').run();
      if(mode==='foreignBot') f.db.prepare('UPDATE bot_credentials SET channelId=?').run('UC'+'b'.repeat(22));
      if(mode==='foreignClient') f.db.prepare('UPDATE bot_credentials SET clientIdHash=?').run(hash('other-client'));
      if(mode==='disabled') f.env.BOT_AUTH_ENABLED='false';
      if(mode==='elapsed') f.env.BOT_AUTH_EXPIRES_AT=String(f.clock());
      assert.equal(vault.canAuthorize(f.clock()),false);
      assert.ok([404,409].includes((await f.auth().handle(new Request(AUTH_ORIGIN+AUTH_PATH))).status));
      assert.deepEqual(f.counts(),{exchanges:0,refreshes:0,lookups:0});
    } finally { f.db.close(); }
  }
});

test('Bot production migration: failed/denied/wrong identity/another seven-day grant preserves current credentials', async () => {
  for(const mode of ['denied','wrongBot','refresh','scope','short']) {
    const f = fixture();
    try {
      await approvedShortGrant(f);
      if(mode!=='short') f.setRefreshLifetime(undefined);
      if(mode==='wrongBot') f.setWrongBot(); if(mode==='refresh') f.setBadRefresh(); if(mode==='scope') f.setDeniedScope();
      const original = JSON.stringify(f.db.prepare('SELECT * FROM bot_credentials').get());
      const b=await f.landing(), redirect=await f.start(b);
      const state=new URL(redirect.headers.get('location')!).searchParams.get('state')!;
      await f.auth().handle(f.callback(state,b.cookie,mode==='denied'?'&error=access_denied':''));
      assert.equal(f.db.prepare('SELECT status FROM bot_auth_session').get()!.status,'failed');
      assert.equal(JSON.stringify(f.db.prepare('SELECT * FROM bot_credentials').get()),original);
    } finally { f.db.close(); }
  }
});

test('Bot production migration: record replacement before OAuth exchange or during verification is not overwritten', async () => {
  for(const phase of ['before','during']) {
    const f=fixture();
    try {
      const vault=await approvedShortGrant(f); f.setRefreshLifetime(undefined);
      const b=await f.landing(),redirect=await f.start(b);
      const state=new URL(redirect.headers.get('location')!).searchParams.get('state')!;
      const changed=await vault.crypt('concurrent-private-refresh','refresh');
      const replace=()=>f.db.prepare('UPDATE bot_credentials SET encrypted=?').run(changed);
      if(phase==='before')replace();
      const transport:typeof fetch=async(url,init)=>{
        const res=await f.request(url,init); if(String(url).includes('/channels?'))replace(); return res;
      };
      await new BotAuthorization(f.driver,f.env,transport,f.clock).handle(f.callback(state,b.cookie));
      assert.equal(f.db.prepare('SELECT status FROM bot_auth_session').get()!.status,'failed');
      assert.equal(await vault.refreshToken(f.clock()),'concurrent-private-refresh');
      if(phase==='before') assert.deepEqual(f.counts(),{exchanges:0,refreshes:0,lookups:0});
    } finally { f.db.close(); }
  }
});

test('Bot production migration: removing operator approval during OAuth verification aborts the replacement', async () => {
  const f=fixture();
  try {
    await approvedShortGrant(f); f.setRefreshLifetime(undefined);
    const original=JSON.stringify(f.db.prepare('SELECT * FROM bot_credentials').get());
    const b=await f.landing(),redirect=await f.start(b);
    const state=new URL(redirect.headers.get('location')!).searchParams.get('state')!;
    const transport:typeof fetch=async(url,init)=>{
      const res=await f.request(url,init); if(String(url).includes('/channels?'))delete f.env.BOT_AUTH_REPLACE_GRANT; return res;
    };
    await new BotAuthorization(f.driver,f.env,transport,f.clock).handle(f.callback(state,b.cookie));
    assert.equal(f.db.prepare('SELECT status FROM bot_auth_session').get()!.status,'failed');
    assert.equal(JSON.stringify(f.db.prepare('SELECT * FROM bot_credentials').get()),original);
  } finally {f.db.close();}
});
