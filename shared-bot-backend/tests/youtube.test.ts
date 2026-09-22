import { test } from 'node:test';
import assert from 'node:assert/strict';
import { YouTubeApi } from '../backend/youtube';

const bot = `UC${'a'.repeat(22)}`; const owner = `UC${'b'.repeat(22)}`;
const video = { id: 'abcdefghijk', snippet: { channelId: owner, liveBroadcastContent: 'live' },
  liveStreamingDetails: { actualStartTime: '2026-09-22T00:00:00Z', activeLiveChatId: 'verified-chat' } };
function apiFixture(replies: Array<unknown | Response | Error> = [{ items: [{ id: bot }] }, { items: [video] }, { id: 'sent-message' }]) {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const transport: typeof fetch = async (input, init) => {
    calls.push({ url: String(input), init });
    const reply = replies.shift();
    if (reply instanceof Error) throw reply;
    if (reply instanceof Response) return reply;
    return new Response(JSON.stringify(reply), { status: 200, headers: { 'Content-Type': 'application/json' } });
  };
  return { api: new YouTubeApi({ async accessToken() { return 'test-server-only-token'; } }, bot, transport), calls };
}
const fault = (code: string) => (error: any) => { assert.equal(error.code, code); assert.ok(!error.message.includes('test-server-only-token')); return true; };

test('YouTube: Bot本人・配信所有者・稼働チャットを検証してから投稿する', async () => {
  const f = apiFixture();
  const chat = await f.api.resolveChat(video.id, owner); assert.equal(chat, 'verified-chat');
  await f.api.post(chat, '@taro さん、順番です。');
  assert.deepEqual(f.calls.map(c => new URL(c.url).pathname), ['/youtube/v3/channels', '/youtube/v3/videos', '/youtube/v3/liveChat/messages']);
  assert.deepEqual(f.calls.map(c => c.init?.method), ['GET', 'GET', 'POST']);
  assert.ok(f.calls.every(c => c.url.startsWith('https://www.googleapis.com/youtube/v3/') && !c.url.includes('token')));
  assert.ok(f.calls.every(c => c.init?.redirect === 'manual' && c.init.signal instanceof AbortSignal));
  assert.deepEqual(JSON.parse(String(f.calls[2]!.init?.body)), { snippet: { liveChatId: 'verified-chat', type: 'textMessageEvent', textMessageDetails: { messageText: '@taro さん、順番です。' } } });
});

test('YouTube: Botアカウント違い・所有者違い・開始前・終了済み・チャットなしは拒否', async () => {
  const wrongBot = apiFixture([{ items: [{ id: owner }] }]);
  await assert.rejects(wrongBot.api.resolveChat(video.id, owner), fault('BOT_UNAVAILABLE'));
  assert.equal(wrongBot.calls.length, 1);
  for (const [item, code] of [
    [{ ...video, snippet: { ...video.snippet, channelId: bot } }, 'CHANNEL_MISMATCH'],
    [{ ...video, snippet: { ...video.snippet, liveBroadcastContent: 'upcoming' } }, 'LIVE_NOT_ACTIVE'],
    [{ ...video, liveStreamingDetails: { activeLiveChatId: 'chat' } }, 'LIVE_NOT_ACTIVE'],
    [{ ...video, liveStreamingDetails: { ...video.liveStreamingDetails, actualEndTime: 'ended' } }, 'LIVE_NOT_ACTIVE'],
    [{ ...video, liveStreamingDetails: { actualStartTime: 'started' } }, 'CHAT_UNAVAILABLE'],
    [{ ...video, id: 'different01' }, 'LIVE_NOT_ACTIVE'],
  ] as const) {
    const f = apiFixture([{ items: [{ id: bot }] }, { items: [item] }]);
    await assert.rejects(f.api.resolveChat(video.id, owner), fault(code));
    assert.equal(f.calls.filter(c => c.init?.method === 'POST').length, 0);
  }
});

test('YouTube: POSTのタイムアウト・5xx・壊れた応答はunknown、再試行しない', async () => {
  for (const response of [new Error('secret server failure'), new Response('{}', { status: 500 }), new Response('invalid json'), new Response('{}'), new Response('{}', { status: 408 })]) {
    const f = apiFixture([response]);
    await assert.rejects(f.api.post('chat', '呼び出し'), fault('DELIVERY_UNKNOWN'));
    assert.equal(f.calls.length, 1);
  }
});

test('YouTube: APIエラーは公開コードに変換しGoogleの内部応答を返さない', async () => {
  for (const [reason, status, expected] of [
    ['quotaExceeded', 403, 'QUOTA_EXHAUSTED'], ['rateLimitExceeded', 403, 'RATE_LIMITED'],
    ['forbidden', 403, 'BOT_PERMISSION_REQUIRED'], ['liveChatEnded', 403, 'LIVE_NOT_ACTIVE'],
    ['liveChatDisabled', 403, 'CHAT_UNAVAILABLE'], ['liveChatNotFound', 404, 'CHAT_UNAVAILABLE'],
    ['invalidCredentials', 401, 'BOT_UNAVAILABLE'],
  ] as const) {
    const f = apiFixture([new Response(JSON.stringify({ error: { message: 'SECRET_DIAGNOSTIC', errors: [{ reason }] } }), { status })]);
    await assert.rejects(f.api.post('chat', '呼び出し'), (error: any) => { assert.equal(error.code, expected); assert.ok(!error.message.includes('SECRET_DIAGNOSTIC')); return true; });
    assert.equal(f.calls.length, 1);
  }
});

test('YouTube: トークン取得失敗・不正な入力ではHTTPを送らない', async () => {
  let calls = 0;
  const api = new YouTubeApi({ async accessToken() { throw new Error('SECRET'); } }, bot, async () => { calls++; throw new Error(); });
  await assert.rejects(api.resolveChat(video.id, owner), fault('BOT_UNAVAILABLE'));
  await assert.rejects(api.post('chat', 'hello'), fault('BOT_UNAVAILABLE'));
  await assert.rejects(api.resolveChat('https://evil.invalid', owner), fault('INVALID_MESSAGE'));
  await assert.rejects(api.post('chat', 'a'.repeat(201)), fault('INVALID_MESSAGE'));
  assert.equal(calls, 0);
});
