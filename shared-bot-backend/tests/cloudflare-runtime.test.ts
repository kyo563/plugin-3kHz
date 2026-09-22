import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { Miniflare, Log, LogLevel, convertV4MiniflareOptions } from 'miniflare';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, dirname, basename, resolve } from 'node:path';
import { createHash, randomBytes } from 'node:crypto';
import { AUTH_ORIGIN, AUTH_PATH, CALLBACK_PATH, BOT_SCOPE } from '../backend/cloudflare/bot-auth';
import { CHANNEL_SCOPE, CONNECT_CALLBACK } from '../backend/cloudflare/channel-connect';

async function bundle(entry: string): Promise<string> {
  const result = await build({ entryPoints: [entry], bundle: true, write: false, platform: 'node', format: 'esm', target: 'es2022', external: ['node:crypto'], metafile: true });
  assert.ok(!Object.keys(result.metafile!.inputs).some(p => /backend\/store\.ts$/.test(p)));
  assert.ok(!result.outputFiles[0]!.text.includes('node:sqlite'));
  return result.outputFiles[0]!.text;
}
const base = { modules: true, compatibilityDate: '2026-09-18', compatibilityFlags: ['nodejs_compat'],
  host: '127.0.0.1', port: 0, log: new Log(LogLevel.ERROR),
  outboundService: async () => { throw new Error('External network is forbidden in tests'); },
} as const;

test('Cloudflare channel connection: actual Worker routing, OAuth proof and revocation without live posting', async () => {
  let exchanges = 0;
  const mf = new Miniflare(convertV4MiniflareOptions({ ...base, compatibilityFlags: [...base.compatibilityFlags], script: await bundle('backend/cloudflare/worker.ts'),
    durableObjects: { BOT_COORDINATOR: { className: 'BotCoordinator', useSQLite: true } },
    bindings: { BOT_POSTING_ENABLED: 'false', CHANNEL_CONNECT_ENABLED: 'true', BOT_CHANNEL_ID: 'UC' + 'b'.repeat(22),
      BOT_VAULT_KEY: randomBytes(32).toString('base64url'), GOOGLE_CLIENT_ID: 'fake-client', GOOGLE_CLIENT_SECRET: 'fake-secret' },
    outboundService: async request => {
      if (request.url === 'https://oauth2.googleapis.com/token') { exchanges++; return Response.json({ access_token: 'fake-channel-access', token_type: 'Bearer', scope: CHANNEL_SCOPE }); }
      assert.equal(request.url, 'https://www.googleapis.com/youtube/v3/channels?part=id&mine=true');
      return Response.json({ items: [{ id: 'UC' + 'a'.repeat(22) }] });
    },
  }));
  try {
    const api = (path: string) => mf.dispatchFetch(AUTH_ORIGIN + '/v1/connections/' + path, { method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + 'c'.repeat(43) }, body: '{}' });
    const start = await api('start'); assert.equal(start.status, 200, await start.clone().text());
    const link = (await start.json() as any).authorizationUrl;
    const page = await mf.dispatchFetch(link); assert.equal(page.status, 200);
    const cookie = page.headers.get('set-cookie')!.split(';')[0]!;
    const csrf = /name="csrf" value="([^"]+)"/.exec(await page.text())![1]!;
    const begin = await mf.dispatchFetch(link, { method: 'POST', redirect: 'manual', headers: { Origin: AUTH_ORIGIN, Cookie: cookie, 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ csrf }).toString() });
    assert.equal(begin.status, 303); const state = new URL(begin.headers.get('location')!).searchParams.get('state')!;
    const done = await mf.dispatchFetch(AUTH_ORIGIN + CONNECT_CALLBACK + '?state=' + state + '&code=fake', { headers: { Cookie: cookie } });
    assert.equal(done.status, 200, await done.clone().text()); assert.equal(exchanges, 1);
    const status = await (await api('status')).json() as any;
    assert.equal(status.status, 'connected'); assert.equal(status.serviceEnabled, false);
    assert.equal((await api('disconnect')).status, 200); assert.equal((await api('status')).status, 403);
  } finally { await mf.dispose(); }
});

test('Cloudflare runtime: 実Workersランタイムで停止・認証拒否、公開の登録/秘密APIなし', async () => {
  const mf = new Miniflare(convertV4MiniflareOptions({ ...base, compatibilityFlags: [...base.compatibilityFlags], script: await bundle('backend/cloudflare/worker.ts'),
    durableObjects: { BOT_COORDINATOR: { className: 'BotCoordinator', useSQLite: true } },
    bindings: { BOT_POSTING_ENABLED: 'false', BOT_CHANNEL_ID: 'UCV3VeoFI04L79MqwuApT-Hg' } }));
  try {
    const health = await mf.dispatchFetch('https://test.invalid/health');
    assert.equal(health.status, 200); assert.equal((await health.json() as any).productionReady, false);
    const options = { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + 'a'.repeat(43) }, body: '{}' };
    const off = await mf.dispatchFetch('https://test.invalid/v1/bot/posts', options);
    assert.equal(off.status, 503); assert.equal((await off.json() as any).error.code, 'SERVICE_DISABLED');
    for (const path of ['/v1/connections', '/oauth/callback', '/admin', '/secrets', AUTH_PATH, CALLBACK_PATH]) {
      assert.equal((await mf.dispatchFetch('https://test.invalid' + path, options)).status, 404);
    }
    const stub = (await mf.getDurableObjectNamespace('BOT_COORDINATOR'));
    const result = await stub.get(stub.idFromName('shared-youtube-bot-v1')).fetch('https://internal/v1/bot/posts', options);
    assert.equal(result.status, 503);
  } finally { await mf.dispose(); }
});

test('Cloudflare OAuth: 実ランタイムで暗号化・認証・再起動後の接続結果を確認し投稿はOFFのまま', async () => {
  const folder = await mkdtemp(join(tmpdir(), 'joinqueue-cf-test-'));
  const setup = randomBytes(32).toString('base64url'); const bot = 'UC' + 'a'.repeat(22); let exchanges = 0;
  const options = convertV4MiniflareOptions({ ...base, compatibilityFlags: [...base.compatibilityFlags], script: await bundle('backend/cloudflare/worker.ts'),
    durableObjects: { BOT_COORDINATOR: { className: 'BotCoordinator', useSQLite: true } },
    bindings: { BOT_POSTING_ENABLED: 'false', BOT_CHANNEL_ID: bot, BOT_AUTH_ENABLED: 'true', BOT_AUTH_EXPIRES_AT: String(Date.now() + 3600_000),
      BOT_AUTH_SETUP_HASH: createHash('sha256').update(setup).digest('hex'), BOT_VAULT_KEY: randomBytes(32).toString('base64url'),
      GOOGLE_CLIENT_ID: 'fake-client', GOOGLE_CLIENT_SECRET: 'fake-secret' },
    outboundService: async request => {
      if (request.url === 'https://oauth2.googleapis.com/token') {
        const fields = new URLSearchParams(await request.text());
        assert.equal(fields.get('client_secret'), 'fake-secret');
        if (fields.get('grant_type') === 'authorization_code') exchanges++;
        return Response.json({ access_token: 'fake-access', refresh_token: 'fake-refresh', expires_in: 3600, token_type: 'Bearer', scope: BOT_SCOPE });
      }
      assert.equal(request.url, 'https://www.googleapis.com/youtube/v3/channels?part=id&mine=true');
      return Response.json({ items: [{ id: bot }] });
    },
  });
  options.resourcePersistencePath = folder; let mf = new Miniflare(options);
  try {
    const page = await mf.dispatchFetch(AUTH_ORIGIN + AUTH_PATH);
    assert.equal(page.status, 200); const cookie = page.headers.get('set-cookie')!.split(';')[0]!;
    const csrf = /name="csrf" value="([^"]+)"/.exec(await page.text())![1]!;
    const started = await mf.dispatchFetch(AUTH_ORIGIN + AUTH_PATH, { method: 'POST', redirect: 'manual',
      headers: { Origin: AUTH_ORIGIN, Cookie: cookie, 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ csrf, setup }).toString() });
    assert.equal(started.status, 303, await started.clone().text()); const state = new URL(started.headers.get('location')!).searchParams.get('state')!;
    // The encrypted PKCE verifier survives an actual runtime restart before callback.
    await mf.dispose(); mf = new Miniflare(options);
    const callbackUrl = AUTH_ORIGIN + CALLBACK_PATH + '?state=' + state + '&code=fake-code';
    const callback = await mf.dispatchFetch(callbackUrl, { redirect: 'manual', headers: { Cookie: cookie } });
    assert.equal(callback.status, 303, await callback.clone().text()); assert.equal(exchanges, 1);
    await mf.dispose(); mf = new Miniflare(options);
    const result = await mf.dispatchFetch(AUTH_ORIGIN + AUTH_PATH + '/result', { headers: { Cookie: cookie } });
    assert.equal(result.status, 200); assert.match(await result.text(), /Botの認証が完了/);
    assert.equal((await mf.dispatchFetch(callbackUrl, { redirect: 'manual', headers: { Cookie: cookie } })).status, 403); assert.equal(exchanges, 1);
    assert.equal((await mf.dispatchFetch(AUTH_ORIGIN + AUTH_PATH)).status, 409);
    const posting = await mf.dispatchFetch(AUTH_ORIGIN + '/v1/bot/posts', { method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + 'a'.repeat(43) }, body: '{}' });
    assert.equal(posting.status, 503); assert.equal((await posting.json() as any).error.code, 'SERVICE_DISABLED');
  } finally {
    await mf.dispose(); assert.equal(dirname(resolve(folder)), resolve(tmpdir())); assert.ok(basename(folder).startsWith('joinqueue-cf-test-'));
    await rm(folder, { recursive: true, force: true });
  }
});

test('Cloudflare SQLite: 永続化・並行重複・制限・rollback・不明結果を実ランタイムで検証', async () => {
  const folder = await mkdtemp(join(tmpdir(), 'joinqueue-cf-test-'));
  const script = await bundle('tests/fixtures/cloudflare-ledger.ts');
  const options = convertV4MiniflareOptions({ ...base, compatibilityFlags: [...base.compatibilityFlags], script,
    durableObjects: { LEDGER: { className: 'TestLedger', useSQLite: true } } });
  // Miniflare 5 uses one persistence root; the v4 converter does not carry it over.
  options.resourcePersistencePath = folder;
  let mf = new Miniflare(options);
  const send = async (input: unknown): Promise<any> => {
    const response = await mf.dispatchFetch('https://test.invalid/test', { method: 'POST', body: JSON.stringify(input) });
    assert.equal(response.status, 200); return response.json();
  };
  const now = 1_000_000;
  const post = { channelConnectionId: 'test-connection', videoId: 'abcdefghijk', eventId: 'first', createdAt: now,
    templateId: 'called', variables: { members: [{ name: 'test-name', handle: '@testhandle' }], group: 1 } };
  try {
    await send({ action: 'seed', now });
    const duplicate = await Promise.all([send({ post, now }), send({ post, now })]);
    assert.ok(duplicate.some(r => r.body.status === 'sent'));
    assert.equal((await send({ action: 'snapshot' })).rows.length, 1);
    assert.equal((await send({ post: { ...post, variables: { members: [{ name: 'changed' }], group: 1 } }, now })).http, 409);
    assert.equal((await send({ post: { ...post, eventId: 'second' }, now })).http, 429);
    const data = { requestId: 'duplicate-request-id', userId: 'test-user', channelId: 'UC' + 'b'.repeat(22), eventHash: 'pending', fingerprint: 'p', contentHash: 'p' };
    await send({ action: 'reserve', data, now: now + 70_000 });
    const rollback = await send({ action: 'reserve', data: { ...data, eventHash: 'rolledback', contentHash: 'new' }, now: now + 140_000 });
    assert.equal(rollback.http, 503); // Duplicate primary key -> entire reservation rolls back.
    assert.equal((await send({ action: 'snapshot' })).rows.length, 2);
    const unknownPost = { ...post, eventId: 'unknown', createdAt: now + 210_000 };
    assert.equal((await send({ post: unknownPost, now: now + 210_000, fail: true })).body.status, 'unknown');
    const snapshot = await send({ action: 'snapshot' });
    assert.ok(!JSON.stringify(snapshot).includes('a'.repeat(43)));
    assert.ok(!JSON.stringify(snapshot).includes('@testhandle'));
    // Recreate the entire runtime, not just a JS store, on the same SQLite directory.
    await mf.dispose(); mf = new Miniflare(options);
    assert.equal((await send({ post, now: now + 220_000 })).body.status, 'sent');
    assert.equal((await send({ post: unknownPost, now: now + 220_000 })).body.status, 'unknown');
    assert.equal((await send({ action: 'previous', eventHash: 'pending', fingerprint: 'p' })).body.status, 'unknown');
    assert.equal((await send({ action: 'snapshot' })).rows.length, 3);
    assert.equal((await send({ post: { ...post, eventId: 'daily', createdAt: now + 300_000 }, now: now + 300_000, limits: { dailyUnits: 156 } })).body.error.code, 'QUOTA_EXHAUSTED');
    for (let i = 0; i < 60; i++) assert.equal((await send({ action: 'ingress', now })).ok, true);
    assert.equal((await send({ action: 'ingress', now })).body.error.code, 'RATE_LIMITED');
    await mf.dispose(); mf = new Miniflare(options);
    assert.equal((await send({ action: 'ingress', now })).body.error.code, 'RATE_LIMITED');
    assert.equal((await send({ action: 'ingress', now: now + 60_000 })).ok, true);
    await send({ action: 'disabled' });
    assert.equal((await send({ post: { ...post, eventId: 'disabled', createdAt: now }, now })).body.error.code, 'SERVICE_DISABLED');
  } finally {
    await mf.dispose();
    // Delete only this test's freshly created, validated OS temporary directory.
    assert.equal(dirname(resolve(folder)), resolve(tmpdir())); assert.ok(basename(folder).startsWith('joinqueue-cf-test-'));
    await rm(folder, { recursive: true, force: true });
  }
});
