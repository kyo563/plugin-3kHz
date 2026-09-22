import { randomUUID } from 'node:crypto';
import { assertFresh, BotFault, digest, failure, parsePost, renderPost, type ApiResult } from './policy';
import { SqlBotStore, DEFAULT_LIMITS, type Limits } from './sql-store';

export interface YouTubeGateway {
  /** Confirms the authenticated bot identity and validates live video's owner. */
  resolveChat(videoId: string, ownerChannelId: string): Promise<string>;
  post(chatId: string, message: string): Promise<void>;
}
export interface AuditEvent { requestId: string; userId?: string; deviceId?: string; status: string; code?: string }

export class BotService {
  private readonly limits: Limits;
  constructor(private readonly store: SqlBotStore, private readonly youtube: YouTubeGateway,
    private readonly audit: (event: AuditEvent) => void = () => {}, private readonly clock = Date.now, limits: Partial<Limits> = {}) {
    this.limits = { ...DEFAULT_LIMITS, ...limits };
    if (Object.values(this.limits).some(value => !Number.isSafeInteger(value) || value < 0)) throw new Error('Invalid limits');
  }
  async submit(authorization: string | undefined, input: unknown): Promise<ApiResult> {
    const requestId = randomUUID();
    let reserved = false; let dispatching = false;
    let userId: string | undefined; let deviceId: string | undefined;
    let result: ApiResult;
    try {
      const principal = this.store.authenticate(authorization, this.clock());
      ({ userId, deviceId } = principal);
      const post = parsePost(input);
      const connection = this.store.connection(post.channelConnectionId, userId);
      const fingerprint = digest(JSON.stringify(post));
      const eventHash = digest(post.eventId);
      const previous = this.store.previous(userId, eventHash, fingerprint);
      if (previous) return previous;
      this.store.assertEnabled(); assertFresh(post, this.clock());
      const message = renderPost(post);
      const raced = this.store.reserve({ requestId, userId, channelId: connection.channelId, eventHash, fingerprint, contentHash: digest(message) }, this.clock(), this.limits);
      if (raced) return raced;
      reserved = true;
      // No waiting/backlog: expire instead of posting old notifications on reconnect.
      const chatId = await this.youtube.resolveChat(post.videoId, connection.channelId);
      this.store.authenticate(authorization, this.clock());
      this.store.connection(post.channelConnectionId, userId);
      this.store.assertEnabled(); assertFresh(post, this.clock());
      dispatching = true;
      await this.youtube.post(chatId, message);
      result = { http: 200, body: { requestId, status: 'sent' } };
    } catch (error) {
      result = failure(requestId, error instanceof BotFault ? error : new BotFault(dispatching ? 'DELIVERY_UNKNOWN' : 'BOT_UNAVAILABLE', 503));
      // A provider quota/auth/connectivity failure must not cause every client to
      // keep hitting the shared bot. Operator review is needed to re-enable it.
      if (reserved && ['QUOTA_EXHAUSTED', 'BOT_UNAVAILABLE'].includes(result.body.error?.code ?? '')) {
        try { this.store.setEnabled(false); } catch { /* Broken storage already fails closed. */ }
      }
    }
    if (reserved) {
      try { this.store.finish(requestId, result); }
      catch { result = failure(requestId, new BotFault('DELIVERY_UNKNOWN', 503)); }
    }
    // Callback never receives raw errors, auth headers, Google responses or message bodies.
    try { this.audit({ requestId, userId, deviceId, status: result.body.status, code: result.body.error?.code }); } catch { /* No resend on log failure. */ }
    return result;
  }
}
