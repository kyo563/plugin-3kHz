import { test } from 'node:test';
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { request as httpRequest } from 'node:http';
import { BotStore, REQUEST_UNITS, type Limits } from '../backend/store';
import { BotService, type AuditEvent, type YouTubeGateway } from '../backend/service';
import { BotFault, parsePost, renderPost } from '../backend/policy';
import { createLocalServer } from '../backend/http';
import type { BotPostRequest } from '../src/contracts/bot-api';

const channel = `UC${'a'.repeat(22)}`;
const anotherChannel = `UC${'b'.repeat(22)}`;
test('position replies count NEXT as group one, accept legacy clients, and distinguish currently playing', async () => {
  const f = fixture();
  try {
    const body = f.body({templateId:'position',recipient:{service:'youtube',userId:'viewer'},variables:{name:'Viewer',handle:'@viewer',state:'now'}});
    for (const group of [undefined, 2, 1000000]) {
      const post = parsePost({...body,variables:{...body.variables,...(group === undefined ? {} : {group})}});
      assert.equal(renderPost(post),'@viewer さんは現在参加中です。');
      assert.equal(post.variables.group,undefined);
    }
    for (const [position, group] of [[1,1],[3,1],[4,2],[6,2],[7,3]] as const) {
      const post = parsePost({...body,variables:{...body.variables,state:'waiting',position,group:1000000}});
      assert.equal(post.variables.group,group);
      assert.equal(renderPost(post),`@viewer さん、現在の待機順は${position}番目、第${group}グループです（NOWを除く）。`);
    }
    assert.throws(()=>parsePost({...body,variables:{...body.variables,group:'2'}}));
    assert.equal((await f.submit(body)).body.status,'sent');
    assert.deepEqual(f.sent,['@viewer さんは現在参加中です。']);
  } finally { f.store.close(); }
});
test('connection test only accepts a fixed message and uses existing authorization and limits', async () => {
  const f = fixture();
  try {
    const post = f.body({templateId:'connection-test',variables:{}});
    assert.equal(renderPost(parsePost(post)), 'JoinQueueBot 接続テスト');
    assert.throws(()=>parsePost({...post,variables:{text:'arbitrary'}}));
    assert.throws(()=>parsePost({...post,recipient:{service:'youtube',userId:'a'}}));
    assert.equal((await f.submit(post, '')).body.error?.code,'UNAUTHENTICATED');
    assert.equal((await f.submit(post)).body.status,'sent');
    assert.deepEqual(f.sent,['JoinQueueBot 接続テスト']);
    assert.equal((await f.submit({...post,eventId:'different'})).body.error?.code,'RATE_LIMITED');
  } finally { f.store.close(); }
});
test('plugin safe display names fit a full three-person call and opaque recipients', () => {
  const base = {channelConnectionId:'connection',videoId:'abcdefghijk',eventId:'test',createdAt:1000000};
  const call = parsePost({...base, templateId:'called',variables:{group:1000000,members:[{name:'名'.repeat(45)},{name:'😀'.repeat(22)},{name:'Player： A／ｗｗｗ．example.com'}]}});
  assert.ok([...renderPost(call)].length <= 200);
  assert.equal(parsePost({...base,templateId:'position',recipient:{service:'youtube',userId:'x'.repeat(512)},variables:{name:'Player： A',state:'not-queued'}}).recipient!.userId.length,512);
});
function fixture(limits: Partial<Limits> = {}, path = ':memory:') {
  let now = Date.parse('2026-09-22T00:00:00Z');
  const store = new BotStore(path); const token = randomBytes(32).toString('base64url');
  store.provisionDevice(token, { userId: 'user-1', deviceId: 'device-1' }, now + 3_600_000);
  store.provisionVerifiedConnection({ id: 'connection-1', userId: 'user-1', channelId: channel, verifiedAt: now });
  store.setEnabled(true);
  const sent: string[] = []; const verified: string[] = []; const logs: AuditEvent[] = [];
  const gateway: YouTubeGateway = {
    async resolveChat(video, owner) { verified.push(`${owner}/${video}`); return 'chat'; },
    async post(_chat, message) { sent.push(message); },
  };
  const service = new BotService(store, gateway, event => logs.push(event), () => now, limits);
  const body = (extra: Partial<BotPostRequest> = {}): BotPostRequest => ({ channelConnectionId: 'connection-1', videoId: 'abcdefghijk', eventId: 'event-1', createdAt: now,
    templateId: 'called', variables: { members: [{ name: 'たろう', handle: '@taro' }], group: 1 }, ...extra });
  return { store, token, service, gateway, sent, verified, logs, body, clock: () => now, advance: (ms: number) => { now += ms; },
    submit: (data: unknown = body(), auth = `Bearer ${token}`) => service.submit(auth, data) };
}

test('backend: 認証・チャンネル紐付けなしではYouTubeにアクセスしない', async () => {
  const f = fixture();
  try {
    assert.equal((await f.submit(f.body(), '')).body.error?.code, 'UNAUTHENTICATED');
    assert.equal((await f.submit(f.body(), 'Bearer ' + 'a'.repeat(43))).http, 401);
    f.store.provisionVerifiedConnection({ id: 'other', userId: 'user-2', channelId: anotherChannel, verifiedAt: f.clock() });
    assert.equal((await f.submit(f.body({ channelConnectionId: 'other' }))).body.error?.code, 'CHANNEL_NOT_LINKED');
    assert.equal((await f.submit(f.body({ channelConnectionId: 'missing' }))).http, 403);
    assert.deepEqual(f.verified, []);
  } finally { f.store.close(); }
});

test('backend: サーバーテンプレートのみ投稿し機密・メモ・自由文を拒否する', async () => {
  const f = fixture();
  try {
    for (const input of [null, [], { ...f.body(), text: 'free text' }, { ...f.body(), accessToken: 'secret' },
      f.body({ variables: { name: 'a\nb' } }), f.body({ variables: { name: 'https://spam.invalid' } }),
      f.body({ variables: { members: [{ name: 'name', handle: '@two people' }], group: 1 } }), f.body({ templateId: 'joined' as any, variables: { name: 'a' } }),
      { ...f.body(), variables: { name: 'a', memo: 'private' } }, f.body({ videoId: 'https://evil.test' }),
      f.body({ createdAt: NaN }), f.body({ createdAt: 1.5 }), f.body({ templateId: '__proto__' as any }),
      f.body({ recipient: { service: 'other' as any, userId: 'x' } })]) {
      assert.equal((await f.submit(input)).body.error?.code, 'INVALID_MESSAGE');
    }
    const result = await f.submit();
    assert.equal(result.body.status, 'sent'); assert.equal(f.sent[0], 'NOW（第1グループ）：@taro さん。参加の準備をお願いします。');
    assert.equal(f.verified.length, 1);
    assert.ok(!JSON.stringify(f.logs).includes('@taro')); assert.ok(!JSON.stringify(f.logs).includes(f.token));
  } finally { f.store.close(); }
});

test('backend: 同じイベントの並行要求も1回だけ送信し内容違いは409', async () => {
  const f = fixture();
  try {
    const responses = await Promise.all([f.submit(), f.submit()]);
    assert.equal(f.sent.length, 1);
    assert.deepEqual(responses.map(r => r.body.status).sort(), ['sent', 'unknown']);
    const replay = await f.submit(); assert.equal(replay.body.status, 'sent');
    assert.equal(replay.body.requestId, responses[0]!.body.requestId);
    assert.equal((await f.submit(f.body({ variables: { members: [{ name: '別名' }], group: 1 } }))).http, 409);
    assert.equal(f.sent.length, 1);
  } finally { f.store.close(); }
});

test('backend: 古い通知・未来通知・停止中は拒否', async () => {
  const f = fixture();
  try {
    for (const delta of [-60_001, 5_001]) assert.equal((await f.submit(f.body({ createdAt: f.clock() + delta }))).body.error?.code, 'REQUEST_EXPIRED');
    f.store.setEnabled(false); assert.equal((await f.submit()).body.error?.code, 'SERVICE_DISABLED');
    assert.equal(f.verified.length, 0);
  } finally { f.store.close(); }
});

test('backend: 投稿直前に端末失効・接続失効・期限・全体停止を再確認', async () => {
  for (const action of ['device', 'connection', 'expired', 'disabled']) {
    const f = fixture();
    try {
      f.gateway.resolveChat = async () => {
        if (action === 'device') f.store.revokeDevice('device-1');
        if (action === 'connection') f.store.revokeConnection('connection-1');
        if (action === 'expired') f.advance(61_000);
        if (action === 'disabled') f.store.setEnabled(false);
        return 'chat';
      };
      assert.notEqual((await f.submit()).body.status, 'sent'); assert.equal(f.sent.length, 0);
    } finally { f.store.close(); }
  }
});

test('backend: creator grant checks fail closed without disabling the shared Bot', async () => {
  for (const failAt of [1, 2]) {
    const f = fixture(); let checks = 0;
    try {
      const service = new BotService(f.store, f.gateway, undefined, f.clock, {}, async () => {
        checks++;
        if (checks === failAt) throw new BotFault('CHANNEL_AUTH_UNAVAILABLE', 503, 900);
      });
      const result = await service.submit(`Bearer ${f.token}`, f.body());
      assert.equal(result.body.error?.code, 'CHANNEL_AUTH_UNAVAILABLE');
      assert.equal(f.verified.length, failAt === 1 ? 0 : 1);
      assert.equal(f.sent.length, 0);
      assert.doesNotThrow(() => f.store.assertEnabled());
    } finally { f.store.close(); }
  }
});

test('backend: local revocation during awaited creator check prevents posting', async () => {
  const f = fixture();
  try {
    const service = new BotService(f.store, f.gateway, undefined, f.clock, {}, async () => {
      await Promise.resolve();
      f.store.revokeConnection('connection-1');
    });
    const result = await service.submit(`Bearer ${f.token}`, f.body());
    assert.equal(result.body.error?.code, 'CHANNEL_NOT_LINKED');
    assert.equal(f.verified.length, 0);
    assert.equal(f.sent.length, 0);
    assert.doesNotThrow(() => f.store.assertEnabled());
  } finally { f.store.close(); }
});

test('backend: 利用者・チャンネル・全体の制限と予算をYouTube呼出し前に適用', async () => {
  for (const limits of [{ userPerMinute: 1 }, { channelPerMinute: 1 }, { globalPerMinute: 1 }, { dailyUnits: REQUEST_UNITS }, { channelGapMs: 60_000 }]) {
    const f = fixture(limits);
    try {
      assert.equal((await f.submit()).body.status, 'sent'); f.advance(11_000);
      const second = await f.submit(f.body({ eventId: 'second', variables: { members: [{ name: '次の人' }], group: 2 } }));
      assert.equal(second.http, 429); assert.equal(f.verified.length, 1);
      assert.equal(second.body.error?.code, 'dailyUnits' in limits ? 'QUOTA_EXHAUSTED' : 'RATE_LIMITED');
    } finally { f.store.close(); }
  }
});

test('backend: 異なる接続IDでも同じチャンネルの制限を共有する', async () => {
  const f = fixture({ channelPerMinute: 1 });
  try {
    const token2 = randomBytes(32).toString('base64url');
    f.store.provisionDevice(token2, { userId: 'user-2', deviceId: 'device-2' }, f.clock() + 100_000);
    f.store.provisionVerifiedConnection({ id: 'second', userId: 'user-2', channelId: channel, verifiedAt: f.clock() });
    await f.submit(); f.advance(11_000);
    assert.equal((await f.submit(f.body({ channelConnectionId: 'second', eventId: 'other', variables: { members: [{ name: 'another' }], group: 2 } }), `Bearer ${token2}`)).http, 429);
    assert.equal(f.sent.length, 1);
  } finally { f.store.close(); }
});

test('backend: two creators route independently; foreign connection, own limit and revocation never cross tenants', async () => {
  const f = fixture({userPerMinute: 1, channelPerMinute: 1, globalGapMs: 0, channelGapMs: 0});
  try {
    const token2 = randomBytes(32).toString('base64url'), auth2 = `Bearer ${token2}`;
    f.store.provisionDevice(token2, {userId: 'user-2', deviceId: 'device-2'}, f.clock() + 3_600_000);
    f.store.provisionVerifiedConnection({id: 'connection-2', userId: 'user-2', channelId: anotherChannel, verifiedAt: f.clock()});
    const deliveries: Array<{chat: string; message: string}> = [];
    f.gateway.resolveChat = async (video, owner) => { f.verified.push(`${owner}/${video}`); return `chat:${owner}`; };
    f.gateway.post = async (chat, message) => { deliveries.push({chat, message}); };
    const second = () => f.body({channelConnectionId: 'connection-2', videoId: 'lmnopqrstuv',
      variables: {members: [{name: 'Creator B viewer', handle: '@viewerB'}], group: 2}});
    assert.equal((await f.submit(second())).body.error?.code, 'CHANNEL_NOT_LINKED');
    assert.equal((await f.submit(f.body(), auth2)).body.error?.code, 'CHANNEL_NOT_LINKED');
    assert.deepEqual(f.verified, []);
    assert.equal((await f.submit()).body.status, 'sent');
    assert.equal((await f.submit(f.body({eventId: 'own-limit'}))).body.error?.code, 'RATE_LIMITED');
    // Equal event IDs belong to separate authenticated principals.
    assert.equal((await f.submit(second(), auth2)).body.status, 'sent');
    assert.deepEqual(deliveries.map(d => d.chat), [`chat:${channel}`, `chat:${anotherChannel}`]);
    assert.ok(deliveries[0]!.message.includes('@taro') && !deliveries[0]!.message.includes('@viewerB'));
    assert.ok(deliveries[1]!.message.includes('@viewerB') && !deliveries[1]!.message.includes('@taro'));
    f.store.revokeConnection('connection-1'); f.advance(61_000);
    assert.equal((await f.submit(f.body({eventId: 'revoked', createdAt: f.clock()}))).body.error?.code, 'CHANNEL_NOT_LINKED');
    assert.equal((await f.submit({...second(), eventId: 'b-still-active'}, auth2)).body.status, 'sent');
    assert.equal(deliveries.length, 3); assert.equal(deliveries[2]!.chat, `chat:${anotherChannel}`);
  } finally { f.store.close(); }
});

test('backend: 別イベントIDで同じ文面を連投しても拒否', async () => {
  const f = fixture();
  try {
    await f.submit(); f.advance(11_000);
    assert.equal((await f.submit(f.body({ eventId: 'another' }))).body.error?.code, 'RATE_LIMITED');
    f.advance(60_000); assert.equal((await f.submit(f.body({ eventId: 'later' }))).body.status, 'sent');
  } finally { f.store.close(); }
});

test('backend: 送信タイムアウトはunknownとして保存し再送しない', async () => {
  const f = fixture();
  try {
    let attempts = 0;
    f.gateway.post = async () => { attempts++; throw new Error('refresh_token=secret internal payload'); };
    const response = await f.submit(); assert.equal(response.body.status, 'unknown');
    assert.equal((await f.submit()).body.status, 'unknown'); assert.equal(attempts, 1);
    assert.ok(!JSON.stringify(response).includes('secret')); assert.ok(!JSON.stringify(f.logs).includes('secret'));
  } finally { f.store.close(); }
});

test('backend: DB障害時は投稿せずfail closed', async () => {
  const f = fixture(); f.store.close();
  assert.equal((await f.submit()).http, 503); assert.deepEqual(f.verified, []);
});

test('backend: ディスク再起動で認証・制限・結果を復元しトークン本文は残さない', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'joinqueue-backend-test-'));
  const path = join(directory, 'ledger.sqlite'); const f = fixture({}, path);
  const body = f.body(); await f.submit(body); f.store.close();
  const second = new BotStore(path);
  try {
    const service = new BotService(second, f.gateway, () => {}, f.clock);
    assert.equal((await service.submit(`Bearer ${f.token}`, body)).body.status, 'sent');
    assert.equal(f.sent.length, 1);
    assert.equal((await service.submit(`Bearer ${f.token}`, f.body({ eventId: 'next' }))).http, 429);
    const disk = readFileSync(path).toString('utf8');
    assert.ok(!disk.includes(f.token)); assert.ok(!disk.includes('@taro'));
  } finally { second.close(); rmSync(directory, { recursive: true }); }
});

test('backend: 送信済み結果の保存失敗でも同じ要求を再送しない', async () => {
  const f = fixture();
  try {
    f.store.finish = () => { throw new Error('disk full'); };
    assert.equal((await f.submit()).body.status, 'unknown');
    assert.equal((await f.submit()).body.status, 'unknown'); assert.equal(f.sent.length, 1);
  } finally { f.store.close(); }
});

test('backend HTTP: 接続元、形式、サイズ、認証を検証し公開ペアリングAPIは提供しない', async () => {
  const f = fixture(); const server = createLocalServer(f.service);
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address(); assert.ok(address && typeof address === 'object');
  const base = `http://127.0.0.1:${address.port}`;
  try {
    assert.equal((await fetch(`${base}/health`)).status, 200);
    assert.equal((await fetch(`${base}/health`, { headers: { Origin: 'https://evil.invalid' } })).status, 403);
    // Fetch may replace Host with the URL authority; use raw HTTP for this case.
    const wrongHostStatus = await new Promise<number | undefined>((resolve, reject) => {
      const req = httpRequest(`${base}/health`, { headers: { Host: 'evil.invalid' } }, response => { response.resume(); resolve(response.statusCode); });
      req.on('error', reject); req.end();
    });
    assert.equal(wrongHostStatus, 403);
    assert.equal((await fetch(`${base}/v1/connections`, { method: 'POST' })).status, 404);
    assert.equal((await fetch(`${base}/v1/bot/posts`)).status, 405);
    const send = (body: string, headers: Record<string, string> = {}) => fetch(`${base}/v1/bot/posts`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body });
    assert.equal((await send('{')).status, 400);
    assert.equal((await send('x'.repeat(8_193))).status, 413);
    assert.equal((await send('{}', { 'Content-Type': 'text/plain' })).status, 415);
    assert.equal((await send(JSON.stringify(f.body()))).status, 401);
    const response = await send(JSON.stringify(f.body()), { Authorization: `Bearer ${f.token}` });
    assert.equal(response.status, 200); assert.equal((await response.json()).status, 'sent');
  } finally { server.closeAllConnections(); await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())); f.store.close(); }
});

test('backend: 配信チャンネル不一致のエラーは内部情報なしで返す', async () => {
  const f = fixture();
  try {
    f.gateway.resolveChat = async () => { throw new BotFault('CHANNEL_MISMATCH', 403); };
    assert.equal((await f.submit()).body.error?.code, 'CHANNEL_MISMATCH'); assert.equal(f.sent.length, 0);
  } finally { f.store.close(); }
});

test('backend: Google側のクォータ障害は共通Bot全体を停止する', async () => {
  const f = fixture();
  try {
    let calls = 0;
    f.gateway.resolveChat = async () => { calls++; throw new BotFault('QUOTA_EXHAUSTED', 429); };
    assert.equal((await f.submit()).body.error?.code, 'QUOTA_EXHAUSTED');
    f.advance(60_000);
    assert.equal((await f.submit(f.body({ eventId: 'new' }))).body.error?.code, 'SERVICE_DISABLED');
    assert.equal(calls, 1);
  } finally { f.store.close(); }
});
