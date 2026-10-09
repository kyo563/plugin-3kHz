// Explicit operator-run production smoke check. Never authorizes Google or posts to YouTube.
// Creates one short-lived synthetic pairing, then cancels only that pairing.
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';

const origin = 'https://joinqueue-bot-backend.joinqueue.workers.dev';
const device = randomBytes(32).toString('base64url');
const results = [];
let created = false;
const request = (path, init = {}) => fetch(origin + path, {
  ...init, redirect: 'manual', signal: AbortSignal.timeout(15000),
});
const connection = path => request('/v1/connections/' + path, {
  method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + device }, body: '{}',
});
try {
  const health = await request('/health');
  assert.equal(health.status, 200);
  assert.equal((await health.json()).service, 'joinqueue-bot-backend');
  results.push('health: OK (not evidence of Google authorization or readiness)');
  const operator = await request('/operator/bot-auth');
  assert.equal(operator.status, 404);
  results.push('operator authorization entry: closed');
  const unauthenticated = await request('/v1/bot/posts', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
  });
  assert.equal(unauthenticated.status, 401);
  assert.equal((await unauthenticated.json()).error.code, 'UNAUTHENTICATED');
  results.push('unauthenticated posting: rejected');
  const started = await connection('start');
  assert.equal(started.status, 200);
  const pairing = await started.json();
  created = true;
  const target = new URL(pairing.authorizationUrl);
  assert.equal(target.origin, origin);
  assert.equal(target.pathname, '/connect');
  const page = await fetch(target, { redirect: 'manual', signal: AbortSignal.timeout(15000) });
  assert.equal(page.status, 200);
  const text = await page.text();
  assert.ok(text.includes('privacy-creator-grants-v1'));
  assert.ok(text.includes('読み取り専用の更新用認証情報をサーバーだけに暗号化保存'));
  assert.ok(text.includes('https://kyo563.github.io/privacy.html'));
  assert.equal(page.headers.get('Cache-Control'), 'no-store');
  assert.ok(page.headers.get('Set-Cookie')?.includes('Secure; HttpOnly; SameSite=Lax'));
  results.push('new creator consent page, server configuration and cookie protection: OK');
  const pendingResponse = await connection('status');
  assert.equal(pendingResponse.status, 200);
  const pending = await pendingResponse.json();
  assert.equal(pending.status, 'pending');
  assert.equal(pending.stage, 'new');
  assert.equal(pending.pairingId, target.searchParams.get('id'));
  assert.equal(pending.expiresAt, pairing.expiresAt);
  const restarted = await connection('start');
  assert.equal(restarted.status, 200);
  const renewed = await restarted.json();
  assert.notEqual(renewed.authorizationUrl, pairing.authorizationUrl);
  const oldLink = await fetch(target, { redirect: 'manual', signal: AbortSignal.timeout(15000) });
  assert.equal(oldLink.status, 403);
  const newLink = await fetch(renewed.authorizationUrl, { redirect: 'manual', signal: AbortSignal.timeout(15000) });
  assert.equal(newLink.status, 200);
  const refreshedResponse = await connection('status');
  assert.equal(refreshedResponse.status, 200);
  const refreshed = await refreshedResponse.json();
  assert.equal(refreshed.stage, 'new');
  assert.equal(refreshed.pairingId, new URL(renewed.authorizationUrl).searchParams.get('id'));
  results.push('pending status and same-device authorization recovery: OK; stale link rejected');
  // No consent form submission, OAuth redirect, callback, check or Bot test request.
} catch {
  process.exitCode = 1;
  results.push('FAIL: production smoke check failed; raw responses and pairing secrets are not logged');
} finally {
  if (created) {
    try {
      const cancelled = await connection('disconnect');
      assert.equal(cancelled.status, 200);
      assert.equal((await cancelled.json()).status, 'disconnected');
      results.push('synthetic pending pairing: cancelled');
    } catch {
      process.exitCode = 1;
      results.push('FAIL: synthetic pairing cancellation failed; it expires after ten minutes');
    }
  }
  console.log(results.join('\n'));
}
