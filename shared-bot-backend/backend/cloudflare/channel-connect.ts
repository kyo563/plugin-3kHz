import { randomBytes, randomUUID } from 'node:crypto';
import { BotFault, digest } from '../policy';
import { SqlBotStore, type SqlDriver } from '../sql-store';
import type { YouTubeGateway } from '../service';
import { AUTH_ORIGIN, BotVault, boundedText, type BotAuthEnv } from './bot-auth';
import { boundedJson, json, rejected } from './http';

export const CONNECT_CALLBACK = '/connect/callback';
export const CHANNEL_SCOPE = 'https://www.googleapis.com/auth/youtube.readonly';
export interface ChannelEnv extends BotAuthEnv { CHANNEL_CONNECT_ENABLED?: string; BOT_POSTING_ENABLED?: string }
const random = () => randomBytes(32).toString('base64url');
const opaque = (v: unknown): v is string => typeof v === 'string' && /^[A-Za-z0-9_-]{43}$/.test(v);
const denied = () => new BotFault('UNAUTHENTICATED', 403);
const COOKIE = '__Host-joinqueue-channel';
const cookie = (r: Request) => {
  const all = (r.headers.get('Cookie') ?? '').split(';').map(s => s.trim()).filter(s => s.startsWith(COOKIE + '='));
  const value = all.length === 1 ? all[0]!.slice(COOKIE.length + 1) : '';
  return opaque(value) ? value : '';
};
function html(body: string, extra: Record<string, string> = {}, status = 200): Response {
  return new Response('<!doctype html><meta charset="utf-8"><title>JoinQueue チャンネル接続</title>' + body, { status, headers: {
    'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
    'X-Content-Type-Options': 'nosniff',
    'Content-Security-Policy': "default-src 'none'; form-action 'self' https://accounts.google.com; frame-ancestors 'none'; base-uri 'none'", ...extra,
  } });
}
export const isChannelRoute = (path: string) => path === '/connect' || path.startsWith('/connect/') || path.startsWith('/v1/connections/');
export function channelBoundary(r: Request, env: ChannelEnv): boolean {
  const u = new URL(r.url);
  if (u.origin !== AUTH_ORIGIN || r.url.length > 12000 || r.headers.has('Content-Encoding')) return false;
  if (u.pathname.startsWith('/v1/connections/')) {
    return !u.search && !r.headers.has('Origin') && r.method === 'POST' &&
      /^application\/json(?:;\s*charset=utf-8)?$/i.test(r.headers.get('Content-Type') ?? '') &&
      /^Bearer [A-Za-z0-9_-]{43}$/.test(r.headers.get('Authorization') ?? '') &&
      ['start', 'status', 'check', 'disconnect'].includes(u.pathname.slice('/v1/connections/'.length));
  }
  if (env.CHANNEL_CONNECT_ENABLED !== 'true') return false;
  if (u.pathname === CONNECT_CALLBACK) return r.method === 'GET' && !r.headers.has('Origin');
  if (u.pathname !== '/connect') return false;
  if (r.method === 'GET') return !r.headers.has('Origin');
  return r.method === 'POST' && r.headers.get('Origin') === AUTH_ORIGIN &&
    /^application\/x-www-form-urlencoded(?:;\s*charset=utf-8)?$/i.test(r.headers.get('Content-Type') ?? '');
}

/** Streamer proof, never Bot OAuth. Google access is discarded after channels.list(mine=true). */
export class ChannelConnections {
  private store: SqlBotStore;
  private vault: BotVault;
  constructor(private db: SqlDriver, private env: ChannelEnv, private youtube: YouTubeGateway,
    private request: typeof fetch = fetch, private clock = Date.now) {
    this.store = new SqlBotStore(db); this.vault = new BotVault(db, env);
    db.exec(`CREATE TABLE IF NOT EXISTS channel_pairings (
      id TEXT PRIMARY KEY, tokenHash TEXT UNIQUE NOT NULL, browserKey TEXT NOT NULL,
      createdAt INTEGER NOT NULL, expiresAt INTEGER NOT NULL, status TEXT NOT NULL,
      stateHash TEXT, browserHash TEXT, verifier TEXT, channelId TEXT, connectionId TEXT, deviceId TEXT);
      CREATE TABLE IF NOT EXISTS channel_checks (deviceId TEXT PRIMARY KEY, checkedAt INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS channel_probe_budget (deviceId TEXT PRIMARY KEY, startedAt INTEGER NOT NULL, count INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS channel_source_budget (source TEXT PRIMARY KEY, startedAt INTEGER NOT NULL, count INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS channel_oauth_budget (id INTEGER PRIMARY KEY CHECK(id=1), startedAt INTEGER NOT NULL, count INTEGER NOT NULL);`);
  }
  async handle(r: Request): Promise<Response> {
    if (!channelBoundary(r, this.env)) return json({ error: { code: 'NOT_FOUND' } }, 404);
    try {
      const u = new URL(r.url);
      if (u.pathname === CONNECT_CALLBACK) return await this.callback(r);
      if (u.pathname === '/connect') return await this.browser(r);
      const input = await boundedJson(r);
      if (!input || typeof input !== 'object' || Array.isArray(input)) throw new BotFault('INVALID_MESSAGE');
      const body = input as Record<string, unknown>;
      const tokenHash = digest(r.headers.get('Authorization')!.slice(7));
      if (u.pathname.endsWith('/start')) {
        if (this.env.CHANNEL_CONNECT_ENABLED !== 'true' || !this.env.GOOGLE_CLIENT_ID || !this.env.GOOGLE_CLIENT_SECRET || !opaque(this.env.BOT_VAULT_KEY)) throw new BotFault('SERVICE_DISABLED', 503);
        const id = randomUUID(), key = random(), now = this.clock(), expiresAt = now + 600_000;
        this.db.transaction(() => {
          // This header is created only by our edge Worker from Cloudflare's client IP.
          // Rotating a self-chosen device token cannot consume other clients' allowance.
          const source = r.headers.get('X-JoinQueue-Source');
          if (!source || !/^[a-f0-9]{64}$/.test(source)) throw denied();
          this.db.prepare('DELETE FROM channel_source_budget WHERE startedAt<=?').run(now - 86_400_000);
          const budget = this.db.prepare('SELECT * FROM channel_source_budget WHERE source=?').get(source);
          const current = budget && Number(budget.startedAt) > now - 86_400_000;
          if (current && Number(budget.count) >= 20) throw new BotFault('RATE_LIMITED', 429, 3600);
          this.db.prepare('INSERT OR REPLACE INTO channel_source_budget VALUES (?,?,?)').run(source, current ? Number(budget.startedAt) : now, current ? Number(budget.count) + 1 : 1);
          this.db.prepare("DELETE FROM channel_pairings WHERE expiresAt<=? AND status!='connected'").run(now);
          this.db.prepare('INSERT INTO channel_pairings (id,tokenHash,browserKey,createdAt,expiresAt,status) VALUES (?,?,?,?,?,?)').run(id, tokenHash, digest(key), now, expiresAt, 'new');
        });
        return json({ authorizationUrl: AUTH_ORIGIN + '/connect?id=' + id + '&key=' + key, expiresAt, confirmation: id.slice(0, 8) });
      }
      const pairing = this.db.prepare('SELECT * FROM channel_pairings WHERE tokenHash=?').get(tokenHash);
      if (!pairing) throw denied();
      if (u.pathname.endsWith('/disconnect')) {
        // Also cancels a pending or consumed callback; callback rechecks after Google awaits.
        this.db.transaction(() => {
          if (pairing.deviceId) this.store.revokeDevice(String(pairing.deviceId));
          if (pairing.connectionId) this.store.revokeConnection(String(pairing.connectionId));
          this.db.prepare("UPDATE channel_pairings SET status='revoked',verifier=NULL WHERE id=?").run(String(pairing.id));
        });
        return json({ status: 'disconnected' });
      }
      if (pairing.status !== 'connected') {
        if (pairing.status === 'revoked' || pairing.status === 'failed' || Number(pairing.expiresAt) <= this.clock()) throw denied();
        if (!u.pathname.endsWith('/status')) throw new BotFault('CHANNEL_NOT_LINKED', 403);
        return json({ status: 'pending' });
      }
      const principal = this.store.authenticate(r.headers.get('Authorization')!, this.clock());
      const connection = this.store.connection(String(pairing.connectionId), principal.userId);
      let serviceEnabled = this.env.BOT_POSTING_ENABLED === 'true';
      try { this.store.assertEnabled(); } catch { serviceEnabled = false; }
      if (u.pathname.endsWith('/check')) {
        if (!serviceEnabled) throw new BotFault('SERVICE_DISABLED', 503);
        if (typeof body.videoId !== 'string' || !/^[\w-]{11}$/.test(body.videoId)) throw new BotFault('LIVE_NOT_ACTIVE');
        this.db.transaction(() => {
          const last = this.db.prepare('SELECT checkedAt FROM channel_checks WHERE deviceId=?').get(principal.deviceId);
          if (last && Number(last.checkedAt) > this.clock() - 60_000) throw new BotFault('RATE_LIMITED', 429, 60);
          // Global probe budget is separate from the 8,000-unit posting ceiling.
          const key = 'global';
          const budget = this.db.prepare('SELECT * FROM channel_probe_budget WHERE deviceId=?').get(key);
          const current = budget && Number(budget.startedAt) > this.clock() - 86_400_000;
          if (current && Number(budget.count) >= 200) throw new BotFault('RATE_LIMITED', 429, 3600);
          this.db.prepare('INSERT OR REPLACE INTO channel_probe_budget VALUES (?,?,?)').run(key, current ? Number(budget.startedAt) : this.clock(), current ? Number(budget.count) + 1 : 1);
          this.db.prepare('INSERT OR REPLACE INTO channel_checks VALUES (?,?)').run(principal.deviceId, this.clock());
        });
        await this.youtube.resolveChat(body.videoId, connection.channelId);
        this.store.authenticate(r.headers.get('Authorization')!, this.clock()); this.store.connection(connection.id, principal.userId); this.store.assertEnabled();
      }
      return json({ status: 'connected', channelId: connection.channelId, connectionId: connection.id, serviceEnabled });
    } catch (e) { return rejected(e instanceof BotFault ? e : new BotFault('BOT_UNAVAILABLE', 503)); }
  }
  private async browser(r: Request): Promise<Response> {
    const u = new URL(r.url), id = u.searchParams.get('id'), key = u.searchParams.get('key');
    if (!id || !/^[a-f0-9-]{36}$/.test(id) || !opaque(key) || [...u.searchParams.keys()].length !== 2) throw denied();
    const row = this.db.prepare('SELECT * FROM channel_pairings WHERE id=?').get(id);
    if (!row || row.browserKey !== digest(key) || row.status !== 'new' || Number(row.expiresAt) <= this.clock()) throw denied();
    if (r.method === 'GET') {
      const nonce = random();
      return html(`<h1>配信するチャンネルを接続</h1><p>プラグインの確認番号が ${id.slice(0, 8)} であることを確認してください。他人から届いたリンクでは接続しないでください。</p><p>自分の配信チャンネルで認証します。共通Bot用アカウントではありません。読み取り専用で所有チャンネルを確認します。</p><form method="post"><input type="hidden" name="csrf" value="${nonce}"><button>Googleでチャンネルを確認する</button></form>`, { 'Set-Cookie': `${COOKIE}=${nonce}; Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=600` });
    }
    const fields = new URLSearchParams(await boundedText(r, 1024));
    if ([...fields.keys()].length !== 1 || !cookie(r) || fields.get('csrf') !== cookie(r)) throw denied();
    const state = random(), verifier = random();
    const encrypted = await this.vault.crypt(verifier, 'channel-pkce:' + id);
    const updated = this.db.prepare("UPDATE channel_pairings SET status='pending',stateHash=?,browserHash=?,verifier=? WHERE id=? AND status='new' AND expiresAt>?")
      .run(digest(state), digest(cookie(r)), encrypted, id, this.clock());
    if (updated.changes !== 1) throw denied();
    const target = new URL('https://accounts.google.com/o/oauth2/v2/auth');
    target.search = new URLSearchParams({ client_id: this.env.GOOGLE_CLIENT_ID!, redirect_uri: AUTH_ORIGIN + CONNECT_CALLBACK,
      response_type: 'code', scope: CHANNEL_SCOPE, access_type: 'online', prompt: 'select_account',
      state, code_challenge: Buffer.from(digest(verifier), 'hex').toString('base64url'), code_challenge_method: 'S256' }).toString();
    return html('', { Location: target.href }, 303);
  }
  private async google(url: string, init?: RequestInit): Promise<Record<string, any>> {
    const r = await this.request.call(globalThis, url, { ...init, redirect: 'manual', signal: AbortSignal.timeout(8000) });
    if (!r.ok) throw denied();
    const data: unknown = JSON.parse(await boundedText(r, 32768));
    if (!data || typeof data !== 'object' || Array.isArray(data)) throw denied();
    return data as Record<string, any>;
  }
  private async callback(r: Request): Promise<Response> {
    const u = new URL(r.url), state = u.searchParams.get('state');
    if (!opaque(state) || u.searchParams.getAll('state').length !== 1 || !cookie(r)) throw denied();
    const row = this.db.prepare('SELECT * FROM channel_pairings WHERE stateHash=?').get(digest(state));
    if (!row || row.status !== 'pending' || row.browserHash !== digest(cookie(r)) || Number(row.expiresAt) <= this.clock()) throw denied();
    this.db.prepare("UPDATE channel_pairings SET status='consumed' WHERE id=?").run(String(row.id));
    try {
      const code = u.searchParams.get('code');
      if (u.searchParams.has('error') || u.searchParams.getAll('code').length !== 1 || !code || code.length > 4096) throw denied();
      const grant = await this.google('https://oauth2.googleapis.com/token', { method: 'POST', body: new URLSearchParams({
        grant_type: 'authorization_code', client_id: this.env.GOOGLE_CLIENT_ID!, client_secret: this.env.GOOGLE_CLIENT_SECRET!,
        redirect_uri: AUTH_ORIGIN + CONNECT_CALLBACK, code, code_verifier: await this.vault.crypt(String(row.verifier), 'channel-pkce:' + row.id, true),
      }) });
      if (typeof grant.access_token !== 'string' || !/^[\x21-\x7e]{1,8192}$/.test(grant.access_token) || grant.token_type?.toLowerCase() !== 'bearer' ||
        typeof grant.scope !== 'string' || !grant.scope.split(' ').includes(CHANNEL_SCOPE)) throw denied();
      // Reserve shared YouTube lookup quota only AFTER successful Google authentication.
      // Abandoned starts and invalid OAuth codes consume no shared daily lookup allowance.
      this.db.transaction(() => {
        const now = this.clock(), budget = this.db.prepare('SELECT * FROM channel_oauth_budget WHERE id=1').get();
        const current = budget && Number(budget.startedAt) > now - 86_400_000;
        if (current && Number(budget.count) >= 200) throw new BotFault('RATE_LIMITED', 429, 3600);
        this.db.prepare('INSERT OR REPLACE INTO channel_oauth_budget VALUES (1,?,?)').run(current ? Number(budget.startedAt) : now, current ? Number(budget.count) + 1 : 1);
      });
      const mine = await this.google('https://www.googleapis.com/youtube/v3/channels?part=id&mine=true', { headers: { Authorization: 'Bearer ' + grant.access_token } });
      const channelId = mine.items?.[0]?.id;
      if (!Array.isArray(mine.items) || mine.items.length !== 1 || typeof channelId !== 'string' || !/^UC[\w-]{22}$/.test(channelId) || channelId === this.env.BOT_CHANNEL_ID) throw denied();
      this.db.transaction(() => {
        const fresh = this.db.prepare('SELECT status,expiresAt FROM channel_pairings WHERE id=?').get(String(row.id));
        if (fresh?.status !== 'consumed' || Number(fresh.expiresAt) <= this.clock()) throw denied();
        const userId = 'youtube:' + channelId, deviceId = randomUUID(), connectionId = randomUUID();
        this.db.prepare('INSERT INTO devices (hash,userId,deviceId,expiresAt) VALUES (?,?,?,?)').run(String(row.tokenHash), userId, deviceId, this.clock() + 30 * 86_400_000);
        this.store.provisionVerifiedConnection({ id: connectionId, userId, channelId, verifiedAt: this.clock() });
        this.db.prepare("UPDATE channel_pairings SET status='connected',channelId=?,connectionId=?,deviceId=?,verifier=NULL WHERE id=?").run(channelId, connectionId, deviceId, String(row.id));
      });
      // Never returns the device credential or either Google token to this browser.
      return html('<h1>チャンネルを接続しました</h1><p>プラグイン設定へ戻り「認証結果を確認」を押してください。Botはまだ停止中です。</p>');
    } catch {
      this.db.prepare("UPDATE channel_pairings SET status='failed',verifier=NULL WHERE id=? AND status='consumed'").run(String(row.id));
      return html('<h1>接続できませんでした</h1><p>プラグインからやり直し、配信するチャンネルを選んでください。</p>', {}, 400);
    }
  }
}
