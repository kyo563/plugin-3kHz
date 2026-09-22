import { BotFault } from './policy';
import type { YouTubeGateway } from './service';

export interface ServerTokenProvider { accessToken(): Promise<string> }
type Fetch = typeof fetch;
const api = 'https://www.googleapis.com/youtube/v3/';
const obj = (v: unknown): Record<string, any> => v !== null && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, any> : {};

/** Server-only transport. Not used by the locked development runner. No comment retrieval. */
export class YouTubeApi implements YouTubeGateway {
  constructor(private readonly tokens: ServerTokenProvider, private readonly botChannelId: string, private readonly request: Fetch = fetch) {
    if (!/^UC[\w-]{22}$/.test(botChannelId)) throw new Error('Bot channel ID required');
  }
  private async call(path: string, body?: unknown): Promise<Record<string, any>> {
    let token: string;
    try { token = await this.tokens.accessToken(); if (!token) throw new Error(); }
    catch { throw new BotFault('BOT_UNAVAILABLE', 503); }
    let response: Response;
    try {
      response = await this.request.call(globalThis, api + path, { method: body === undefined ? 'GET' : 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }), redirect: 'manual', signal: AbortSignal.timeout(8_000) });
    } catch { throw new BotFault(body === undefined ? 'BOT_UNAVAILABLE' : 'DELIVERY_UNKNOWN', 503); }
    // A broken/5xx POST response may follow a successful insert. Never retry it.
    if (response.status >= 500 || response.status === 408) throw new BotFault(body === undefined ? 'BOT_UNAVAILABLE' : 'DELIVERY_UNKNOWN', 503);
    let data: Record<string, any>;
    try { data = obj(await response.json()); }
    catch { throw new BotFault(body === undefined ? 'BOT_UNAVAILABLE' : 'DELIVERY_UNKNOWN', 503); }
    if (!response.ok) {
      const reasons: unknown[] = Array.isArray(obj(data.error).errors) ? obj(data.error).errors.map((e: unknown) => obj(e).reason) : [];
      if (reasons.includes('quotaExceeded') || reasons.includes('dailyLimitExceeded')) throw new BotFault('QUOTA_EXHAUSTED', 429);
      if (response.status === 429 || reasons.includes('rateLimitExceeded') || reasons.includes('userRateLimitExceeded')) throw new BotFault('RATE_LIMITED', 429, 60);
      if (reasons.includes('liveChatEnded')) throw new BotFault('LIVE_NOT_ACTIVE');
      if (reasons.includes('liveChatDisabled') || reasons.includes('liveChatNotFound')) throw new BotFault('CHAT_UNAVAILABLE');
      if (response.status === 403) throw new BotFault('BOT_PERMISSION_REQUIRED', 403);
      throw new BotFault('BOT_UNAVAILABLE', 503);
    }
    return data;
  }
  async resolveChat(videoId: string, ownerChannelId: string): Promise<string> {
    if (!/^[\w-]{11}$/.test(videoId) || !/^UC[\w-]{22}$/.test(ownerChannelId)) throw new BotFault('INVALID_MESSAGE');
    const mine = await this.call('channels?part=id&mine=true');
    if (!Array.isArray(mine.items) || mine.items.length !== 1 || obj(mine.items[0]).id !== this.botChannelId) throw new BotFault('BOT_UNAVAILABLE', 503);
    const data = await this.call(`videos?part=snippet,liveStreamingDetails&id=${encodeURIComponent(videoId)}`);
    if (!Array.isArray(data.items) || data.items.length !== 1 || obj(data.items[0]).id !== videoId) throw new BotFault('LIVE_NOT_ACTIVE');
    const video = obj(data.items[0]); const live = obj(video.liveStreamingDetails);
    if (obj(video.snippet).channelId !== ownerChannelId) throw new BotFault('CHANNEL_MISMATCH', 403);
    if (!live.actualStartTime || live.actualEndTime || obj(video.snippet).liveBroadcastContent !== 'live') throw new BotFault('LIVE_NOT_ACTIVE');
    if (typeof live.activeLiveChatId !== 'string' || !live.activeLiveChatId || live.activeLiveChatId.length > 1000) throw new BotFault('CHAT_UNAVAILABLE');
    return live.activeLiveChatId;
  }
  async post(chatId: string, message: string): Promise<void> {
    if (!chatId || chatId.length > 1000 || !message || [...message].length > 200 || /[\p{Cc}\p{Cf}]/u.test(message)) throw new BotFault('INVALID_MESSAGE');
    const result = await this.call('liveChat/messages?part=snippet', { snippet: {
      liveChatId: chatId, type: 'textMessageEvent', textMessageDetails: { messageText: message },
    } });
    if (typeof result.id !== 'string' || !result.id) throw new BotFault('DELIVERY_UNKNOWN', 503);
  }
}
