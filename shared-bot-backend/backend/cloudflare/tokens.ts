import { BotFault } from '../policy';
import type { ServerTokenProvider } from '../youtube';

/** Supplied exclusively by server secret bindings. Never returned or serialized. */
export interface GoogleBotSecrets {
  GOOGLE_CLIENT_ID?: string;
  GOOGLE_CLIENT_SECRET?: string;
  GOOGLE_BOT_REFRESH_TOKEN?: string;
}

export class GoogleRefreshTokens implements ServerTokenProvider {
  #secrets: GoogleBotSecrets;
  #request: typeof fetch;
  #clock: () => number;
  #cached?: { token: string; expiresAt: number };
  #pending?: Promise<string>;
  #retryAt = 0;
  #readRefresh?: () => Promise<string>;
  constructor(secrets: GoogleBotSecrets, request: typeof fetch = fetch, clock = Date.now, readRefresh?: () => Promise<string>) {
    this.#secrets = { GOOGLE_CLIENT_ID: secrets.GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET: secrets.GOOGLE_CLIENT_SECRET,
      GOOGLE_BOT_REFRESH_TOKEN: secrets.GOOGLE_BOT_REFRESH_TOKEN };
    this.#request = request.bind(globalThis); this.#clock = clock;
    this.#readRefresh = readRefresh;
  }
  async accessToken(): Promise<string> {
    if (this.#cached && this.#cached.expiresAt > this.#clock()) return this.#cached.token;
    if (this.#pending) return this.#pending;
    if (this.#clock() < this.#retryAt) throw new BotFault('BOT_UNAVAILABLE', 503);
    this.#pending = this.refresh();
    try { return await this.#pending; }
    finally { this.#pending = undefined; }
  }
  private async refresh(): Promise<string> {
    try {
      const { GOOGLE_CLIENT_ID: id, GOOGLE_CLIENT_SECRET: secret } = this.#secrets;
      const refresh = this.#readRefresh ? await this.#readRefresh() : this.#secrets.GOOGLE_BOT_REFRESH_TOKEN;
      if (![id, secret, refresh].every(v => typeof v === 'string' && v.length > 0 && v.length <= 8192 && !/[\r\n]/.test(v))) throw new Error();
      const started = this.#clock();
      const response = await this.#request('https://oauth2.googleapis.com/token', {
        method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ client_id: id!, client_secret: secret!, refresh_token: refresh!, grant_type: 'refresh_token' }),
        redirect: 'manual', signal: AbortSignal.timeout(8_000),
      });
      if (!response.ok) throw new Error();
      const data: unknown = await response.json();
      if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error();
      const p = data as Record<string, unknown>;
      if (typeof p.access_token !== 'string' || !/^[\x21-\x7e]{1,8192}$/.test(p.access_token) ||
          typeof p.token_type !== 'string' || p.token_type.toLowerCase() !== 'bearer' ||
          typeof p.expires_in !== 'number' || !Number.isSafeInteger(p.expires_in) || p.expires_in <= 60 || p.expires_in > 86_400) throw new Error();
      const expiresAt = started + (p.expires_in - 60) * 1000;
      if (expiresAt <= this.#clock()) throw new Error();
      this.#cached = { token: p.access_token, expiresAt };
      return p.access_token;
    } catch {
      this.#cached = undefined; this.#retryAt = this.#clock() + 60_000;
      // Never propagate Google's response, a fetch error, or any secret binding.
      throw new BotFault('BOT_UNAVAILABLE', 503);
    }
  }
}
