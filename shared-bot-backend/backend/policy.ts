import { createHash } from 'node:crypto';
import type { BotErrorCode, BotPostRequest, BotPostResponse, BotName, BotVariables } from '../src/contracts/bot-api';

const messages: Record<BotErrorCode, string> = {
  UNAUTHENTICATED: '接続の認証が必要です。', CHANNEL_NOT_LINKED: 'この端末で利用できるチャンネル接続ではありません。',
  CHANNEL_MISMATCH: '配信のチャンネルが接続先と一致しません。', LIVE_NOT_ACTIVE: '配信が開始されていないか、終了しています。',
  CHAT_UNAVAILABLE: 'ライブチャットを利用できません。', BOT_PERMISSION_REQUIRED: 'Botの投稿権限を確認してください。',
  RATE_LIMITED: '投稿間隔または投稿数の上限に達しました。', QUOTA_EXHAUSTED: '共通Botの利用上限に達しました。',
  DUPLICATE_CONFLICT: '同じイベントIDで異なる投稿要求は送れません。', INVALID_MESSAGE: '投稿要求の形式が正しくありません。',
  BOT_UNAVAILABLE: 'Botに接続できません。', DELIVERY_UNKNOWN: '投稿結果を確認できません。重複防止のため自動再送しません。',
  REQUEST_EXPIRED: '通知が古いため投稿しません。', SERVICE_DISABLED: 'Bot投稿は停止中です。',
};
export class BotFault extends Error {
  constructor(readonly code: BotErrorCode, readonly http = 400, readonly retryAfterSeconds?: number) {
    super(messages[code]);
  }
}
export interface ApiResult { http: number; body: BotPostResponse }
export function failure(requestId: string, fault: BotFault): ApiResult {
  return { http: fault.http, body: { requestId, status: fault.code === 'DELIVERY_UNKNOWN' ? 'unknown' : 'rejected',
    error: { code: fault.code, message: fault.message, ...(fault.retryAfterSeconds === undefined ? {} : { retryAfterSeconds: fault.retryAfterSeconds }) } } };
}
export const digest = (value: string) => createHash('sha256').update(value).digest('hex');
export function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new BotFault('INVALID_MESSAGE');
  return value as Record<string, unknown>;
}
function keys(value: Record<string, unknown>, allowed: string[]): void {
  if (Object.keys(value).some(key => !allowed.includes(key))) throw new BotFault('INVALID_MESSAGE');
}
function text(value: unknown, max: number): string {
  if (typeof value !== 'string' || !value.trim() || value.length > max || /[\p{Cc}\p{Cf}]/u.test(value)) throw new BotFault('INVALID_MESSAGE');
  return value;
}
export function parsePost(value: unknown): BotPostRequest {
  const p = object(value);
  keys(p, ['channelConnectionId', 'videoId', 'eventId', 'createdAt', 'templateId', 'recipient', 'variables']);
  const channelConnectionId = text(p.channelConnectionId, 100);
  const eventId = text(p.eventId, 600);
  const videoId = text(p.videoId, 11);
  if (!/^[\w-]{11}$/.test(videoId) || !Number.isSafeInteger(p.createdAt) || (p.createdAt as number) < 0 ||
      !['called', 'position', 'announcement'].includes(p.templateId as string)) throw new BotFault('INVALID_MESSAGE');
  const v = object(p.variables);
  const number = (value: unknown, min: number, max: number): number => {
    if (!Number.isSafeInteger(value) || (value as number) < min || (value as number) > max) throw new BotFault('INVALID_MESSAGE');
    return value as number;
  };
  const person = (value: Record<string, unknown>): BotName => {
    const name = text(value.name, 100);
    if (/[\/:]|www\./iu.test(name)) throw new BotFault('INVALID_MESSAGE');
    const handle = value.handle === undefined ? undefined : text(value.handle, 100);
    if (handle !== undefined && !/^@[\p{L}\p{M}\p{N}_.·-]+$/u.test(handle)) throw new BotFault('INVALID_MESSAGE');
    return { name, ...(handle ? { handle } : {}) };
  };
  let variables: BotVariables;
  if (p.templateId === 'called') {
    keys(v, ['members', 'group']);
    if (!Array.isArray(v.members) || !v.members.length || v.members.length > 10 || p.recipient !== undefined) throw new BotFault('INVALID_MESSAGE');
    variables = { group: number(v.group, 1, 1_000_000), members: v.members.map(m => { const member = object(m); keys(member, ['name', 'handle']); return person(member); }) };
  } else if (p.templateId === 'position') {
    keys(v, ['name', 'handle', 'state', 'position', 'group']);
    if (!['waiting', 'now', 'not-queued'].includes(v.state as string) || p.recipient === undefined) throw new BotFault('INVALID_MESSAGE');
    variables = { ...person(v), state: v.state as BotVariables['state'] };
    if (v.state === 'waiting') variables.position = number(v.position, 1, 500);
    else if (v.position !== undefined) throw new BotFault('INVALID_MESSAGE');
    if (v.state !== 'not-queued') variables.group = number(v.group, 1, 1_000_000);
    else if (v.group !== undefined) throw new BotFault('INVALID_MESSAGE');
  } else {
    keys(v, ['waitingCount', 'groupCount', 'groupSize']);
    if (p.recipient !== undefined) throw new BotFault('INVALID_MESSAGE');
    const waitingCount = number(v.waitingCount, 0, 500), groupSize = number(v.groupSize, 1, 10), groupCount = number(v.groupCount, 0, 500);
    if (groupCount !== Math.ceil(waitingCount / groupSize)) throw new BotFault('INVALID_MESSAGE');
    variables = { waitingCount, groupCount, groupSize };
  }
  let recipient: BotPostRequest['recipient'];
  if (p.recipient !== undefined) {
    const r = object(p.recipient); keys(r, ['service', 'userId']);
    if (r.service !== 'youtube') throw new BotFault('INVALID_MESSAGE');
    recipient = { service: 'youtube', userId: text(r.userId, 200) };
  }
  const result: BotPostRequest = { channelConnectionId, videoId, eventId, createdAt: p.createdAt as number,
    templateId: p.templateId as BotPostRequest['templateId'], ...(recipient ? { recipient } : {}),
    variables };
  if ([...renderPost(result)].length > 200) throw new BotFault('INVALID_MESSAGE');
  return result;
}
export function assertFresh(post: BotPostRequest, now: number): void {
  if (now - post.createdAt > 60_000 || post.createdAt > now + 5_000) throw new BotFault('REQUEST_EXPIRED');
}
export function renderPost(post: BotPostRequest): string {
  const name = post.variables.handle ?? post.variables.name;
  switch (post.templateId) {
    case 'called': return `NOW（第${post.variables.group}グループ）：${post.variables.members!.map(m => `${m.handle ?? m.name} さん`).join('、')}。参加の準備をお願いします。`;
    case 'position': return post.variables.state === 'waiting'
      ? `${name} さん、現在の待機順は${post.variables.position}番目、第${post.variables.group}グループです（NOWを除く）。`
      : post.variables.state === 'now' ? `${name} さんはNOW（第${post.variables.group}グループ）です。`
        : `${name} さんは現在、待機列に登録されていません。`;
    case 'announcement': return `現在の待機人数は${post.variables.waitingCount}名、待機グループ数は${post.variables.groupCount}組です（NOWを除く・1組${post.variables.groupSize}名）。`;
  }
}
