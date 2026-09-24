import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { randomBytes } from 'node:crypto';
import { ChannelConnections, channelBoundary, CHANNEL_SCOPE, CONNECT_CALLBACK, type ChannelEnv } from '../backend/cloudflare/channel-connect';
import { AUTH_ORIGIN } from '../backend/cloudflare/bot-auth';
import { SqlBotStore, type SqlDriver } from '../backend/sql-store';
import { applyPostingApproval } from '../backend/cloudflare/posting-approval';

function fixture() {
  const db = new DatabaseSync(':memory:'); let now = 1_000_000;
  const driver: SqlDriver = { exec: sql => { db.exec(sql); }, prepare: sql => db.prepare(sql), transaction: fn => {
    db.exec('BEGIN'); try { const result = fn(); db.exec('COMMIT'); return result; } catch (e) { db.exec('ROLLBACK'); throw e; }
  } };
  const env: ChannelEnv = { BOT_CHANNEL_ID: 'UC' + 'b'.repeat(22), GOOGLE_CLIENT_ID: 'fake-client', GOOGLE_CLIENT_SECRET: 'fake-secret',
    BOT_VAULT_KEY: randomBytes(32).toString('base64url'), CHANNEL_CONNECT_ENABLED: 'true', BOT_POSTING_ENABLED: 'false' };
  const token = randomBytes(32).toString('base64url'), channelId = 'UC' + 'a'.repeat(22);
  let lookups = 0, checks = 0, exchanges = 0, bad = '', pause: (() => Promise<void>) | undefined;
  const request: typeof fetch = async (url, init) => {
    assert.equal(init?.redirect, 'manual'); assert.ok(init?.signal);
    if (url === 'https://oauth2.googleapis.com/token') {
      exchanges++; await pause?.();
      const body = new URLSearchParams(String(init?.body));
      assert.equal(body.get('redirect_uri'), AUTH_ORIGIN + CONNECT_CALLBACK);
      assert.match(body.get('code_verifier')!, /^[\w-]{43}$/);
      return Response.json({ access_token: 'private-access', token_type: 'Bearer', scope: bad === 'scope' ? 'bad' : CHANNEL_SCOPE });
    }
    assert.equal(url, 'https://www.googleapis.com/youtube/v3/channels?part=id&mine=true');
    lookups++; return Response.json({ items: bad === 'empty' ? [] : [{ id: bad === 'bot' ? env.BOT_CHANNEL_ID : channelId }] });
  };
  const auth = () => new ChannelConnections(driver, env, { async resolveChat(_video, owner) { checks++; assert.equal(owner, channelId); return 'chat'; }, async post() { assert.fail('No posting from connection endpoints'); } }, request, () => now);
  const api = (path: string, body = {}, credential = token, source = 'a'.repeat(64)) => auth().handle(new Request(AUTH_ORIGIN + '/v1/connections/' + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + credential, 'X-JoinQueue-Source': source }, body: JSON.stringify(body),
  }));
  const start = async () => {
    const res = await api('start'); assert.equal(res.status, 200); const data = await res.json() as any;
    const landing = await auth().handle(new Request(data.authorizationUrl));
    const html = await landing.text(); const cookie = landing.headers.get('set-cookie')!.split(';')[0]!;
    const csrf = /name="csrf" value="([^"]+)"/.exec(html)![1]!;
    const begin = await auth().handle(new Request(data.authorizationUrl, { method: 'POST', headers: { Origin: AUTH_ORIGIN, Cookie: cookie, 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ csrf }) }));
    assert.equal(begin.status, 303);
    const google = new URL(begin.headers.get('location')!);
    assert.equal(google.origin, 'https://accounts.google.com'); assert.equal(google.searchParams.get('scope'), CHANNEL_SCOPE);
    assert.equal(google.searchParams.get('access_type'), 'online'); assert.equal(google.searchParams.has('include_granted_scopes'), false);
    return { cookie, state: google.searchParams.get('state')!, link: data.authorizationUrl };
  };
  const callback = (state: string, cookie: string) => auth().handle(new Request(AUTH_ORIGIN + CONNECT_CALLBACK + '?state=' + state + '&code=fake-code', { headers: { Cookie: cookie } }));
  return { db, driver, env, token, channelId, auth, api, start, callback, counts: () => ({ lookups, checks, exchanges }),
    bad: (value: string) => { bad = value; }, pause: (fn: () => Promise<void>) => { pause = fn; }, advance: (ms: number) => { now += ms; } };
}

test('operator posting approval: explicit configuration only, a restart or replay never reopens tripped breaker', () => {
  const f = fixture(); try {
    const store = new SqlBotStore(f.driver), id = '12345678-1111-4111-8111-111111111111';
    applyPostingApproval(f.driver, 'false', id, true); assert.throws(() => store.assertEnabled());
    applyPostingApproval(f.driver, 'true', id, false); assert.throws(() => store.assertEnabled());
    applyPostingApproval(f.driver, 'true', id, true); store.assertEnabled(); store.setEnabled(false);
    applyPostingApproval(f.driver, 'true', id, true); assert.throws(() => store.assertEnabled());
    applyPostingApproval(f.driver, 'true', '87654321-1111-4111-8111-111111111111', true); store.assertEnabled();
  } finally { f.db.close(); }
});

test('channel pairing: proof creates scoped hashed device; status/check never expose secrets or post', async () => {
  const f = fixture(); try {
    const b = await f.start(); assert.equal((await f.api('status')).status, 200);
    const [first, duplicate] = await Promise.all([f.callback(b.state, b.cookie), f.callback(b.state, b.cookie)]);
    assert.equal(first.status, 200); assert.equal(duplicate.status, 403);
    assert.deepEqual(f.counts(), { exchanges: 1, lookups: 1, checks: 0 });
    const status = await (await f.api('status')).json() as any;
    assert.equal(status.channelId, f.channelId); assert.equal(status.serviceEnabled, false);
    assert.equal((await f.api('check', { videoId: 'abcdefghijk' })).status, 503);
    new SqlBotStore(f.driver).setEnabled(true); f.env.BOT_POSTING_ENABLED = 'true';
    assert.equal((await f.api('check', { videoId: 'abcdefghijk' })).status, 200);
    assert.equal((await f.api('check', { videoId: 'abcdefghijk' })).status, 429);
    const devices = f.db.prepare('SELECT * FROM devices').all();
    assert.equal(devices.length, 1); assert.equal(devices[0]!.userId, 'youtube:' + f.channelId);
    const dump = JSON.stringify([status, devices, f.db.prepare('SELECT * FROM channel_pairings').all()]);
    for (const secret of [f.token, 'private-access', 'fake-secret']) assert.ok(!dump.includes(secret));
    assert.equal((await f.api('disconnect')).status, 200);
    assert.equal((await f.api('status')).status, 403);
  } finally { f.db.close(); }
});

test('channel pairing: no OAuth without cookie/state, expiry; owner missing/wrong scope/Bot channel rejected', async () => {
  for (const invalid of ['bot', 'empty', 'scope']) {
    const f = fixture(); try {
      f.bad(invalid); const b = await f.start();
      assert.equal((await f.callback(b.state, '')).status, 403);
      assert.equal((await f.callback('a'.repeat(43), b.cookie)).status, 403);
      assert.equal(f.counts().exchanges, 0);
      assert.equal((await f.callback(b.state, b.cookie)).status, 400);
      assert.equal(f.db.prepare('SELECT count(*) AS n FROM devices').get()!.n, 0);
    } finally { f.db.close(); }
  }
  const f = fixture(); try { const b = await f.start(); f.advance(600001); assert.equal((await f.callback(b.state, b.cookie)).status, 403); assert.equal(f.counts().exchanges, 0); } finally { f.db.close(); }
});

test('channel pairing: cancellation during OAuth awaits cannot issue a device', async () => {
  const f = fixture(); try {
    const b = await f.start(); let release!: () => void, reached!: () => void;
    const entered = new Promise<void>(r => { reached = r; });
    f.pause(() => new Promise<void>(r => { release = r; reached(); }));
    const pending = f.callback(b.state, b.cookie); await entered;
    assert.equal((await f.api('disconnect')).status, 200); release();
    assert.equal((await pending).status, 400);
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM devices').get()!.n, 0);
  } finally { f.db.close(); }
});

test('channel pairing: boundary, issuance caps and browser CSRF fail closed', async () => {
  const f = fixture(); try {
    const valid = new Request(AUTH_ORIGIN + '/v1/connections/start', { method: 'POST', headers: { Authorization: 'Bearer ' + f.token, 'Content-Type': 'application/json' } });
    assert.equal(channelBoundary(valid, f.env), true);
    for (const req of [new Request(valid, { headers: { Authorization: 'Bearer ' + f.token, 'Content-Type': 'application/json', Origin: AUTH_ORIGIN } }), new Request(AUTH_ORIGIN + '/v1/connections/start?x=y'), new Request('https://evil.invalid/connect')]) assert.equal(channelBoundary(req, f.env), false);
    f.env.CHANNEL_CONNECT_ENABLED = 'false'; assert.equal((await f.api('start')).status, 503); f.env.CHANNEL_CONNECT_ENABLED = 'true';
    const data = await (await f.api('start')).json() as any;
    const bad = await f.auth().handle(new Request(data.authorizationUrl, { method: 'POST', headers: { Origin: AUTH_ORIGIN, 'Content-Type': 'application/x-www-form-urlencoded' }, body: 'csrf=bad' }));
    assert.equal(bad.status, 403);
    for (let i = 1; i < 20; i++) assert.equal((await f.api('start', {}, randomBytes(32).toString('base64url'))).status, 200);
    assert.equal((await f.api('start', {}, randomBytes(32).toString('base64url'))).status, 429);
    assert.equal((await f.api('start', {}, randomBytes(32).toString('base64url'), 'b'.repeat(64))).status, 200);
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM channel_oauth_budget').get()!.n, 0);
    assert.equal((await f.api('start', {}, randomBytes(32).toString('base64url'), '')).status, 403);
    assert.equal(f.counts().exchanges, 0);
  } finally { f.db.close(); }
});
