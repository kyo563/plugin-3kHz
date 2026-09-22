import { createHash, randomBytes, timingSafeEqual } from 'node:crypto';
import { Buffer } from 'node:buffer';
import type { SqlDriver } from '../sql-store';
import { BotFault } from '../policy';
import { GoogleRefreshTokens, type GoogleBotSecrets } from './tokens';

export const AUTH_ORIGIN = 'https://joinqueue-bot-backend.joinqueue.workers.dev';
export const AUTH_PATH = '/operator/bot-auth';
export const CALLBACK_PATH = AUTH_PATH + '/callback';
export const BOT_SCOPE = 'https://www.googleapis.com/auth/youtube.force-ssl';
const COOKIE = '__Host-joinqueue-setup';
const random = () => randomBytes(32).toString('base64url');
const hash = (text: string) => createHash('sha256').update(text).digest('hex');
const opaque = (text: unknown): text is string => typeof text === 'string' && /^[A-Za-z0-9_-]{43}$/.test(text);
const token = (text: unknown): text is string => typeof text === 'string' && /^[\x21-\x7e]{1,8192}$/.test(text);
const same = (a: string, b: string) => timingSafeEqual(Buffer.from(hash(a)), Buffer.from(hash(b)));
const fault = () => new BotFault('UNAUTHENTICATED', 403);

export interface BotAuthEnv extends GoogleBotSecrets {
  BOT_CHANNEL_ID: string;
  BOT_AUTH_ENABLED?: string;
  BOT_AUTH_EXPIRES_AT?: string;
  BOT_AUTH_SETUP_HASH?: string;
  BOT_VAULT_KEY?: string;
}

export function authConfigured(env: BotAuthEnv, now = Date.now()): boolean {
  const expiry = Number(env.BOT_AUTH_EXPIRES_AT);
  return env.BOT_AUTH_ENABLED === 'true' && Number.isSafeInteger(expiry) && expiry > now && expiry - now <= 86_400_000 &&
    /^[a-f0-9]{64}$/.test(env.BOT_AUTH_SETUP_HASH ?? '') && opaque(env.BOT_VAULT_KEY) &&
    token(env.GOOGLE_CLIENT_ID) && token(env.GOOGLE_CLIENT_SECRET) && /^UC[\w-]{22}$/.test(env.BOT_CHANNEL_ID);
}

/** Fixed routing before SQL/Google access. No client-controlled callback or return URL. */
export function authBoundary(request: Request, env: BotAuthEnv, now = Date.now()): boolean {
  const url = new URL(request.url);
  if (!authConfigured(env, now) || url.origin !== AUTH_ORIGIN || request.url.length > 12_000 ||
      request.headers.has('Content-Encoding')) return false;
  if (url.pathname === AUTH_PATH) {
    if (url.search) return false;
    if (request.method === 'GET') return !request.headers.has('Origin') || request.headers.get('Origin') === AUTH_ORIGIN;
    return request.method === 'POST' && request.headers.get('Origin') === AUTH_ORIGIN &&
      /^application\/x-www-form-urlencoded(?:;\s*charset=utf-8)?$/i.test(request.headers.get('Content-Type') ?? '');
  }
  if (request.method !== 'GET' || request.headers.has('Origin')) return false;
  return url.pathname === CALLBACK_PATH || (url.pathname === AUTH_PATH + '/result' && !url.search);
}

function cookieValue(request: Request): string {
  const matches = (request.headers.get('Cookie') ?? '').split(';').map(v => v.trim()).filter(v => v.startsWith(COOKIE + '='));
  const value = matches.length === 1 ? matches[0]!.slice(COOKIE.length + 1) : '';
  return opaque(value) ? value : '';
}
function response(body: string, status = 200, extra: Record<string, string> = {}): Response {
  return new Response(body, { status, headers: {
    'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
    'X-Content-Type-Options': 'nosniff',
    'Content-Security-Policy': "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    ...extra,
  } });
}
const cookieHeader = (nonce: string) => `${COOKIE}=${nonce}; Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=600`;

/** AES-GCM additional data binds ciphertext to purpose, Bot and OAuth client. */
export class BotVault {
  #db: SqlDriver; #env: BotAuthEnv;
  constructor(db: SqlDriver, env: BotAuthEnv) {
    this.#db = db; this.#env = env;
    db.exec(`CREATE TABLE IF NOT EXISTS bot_credentials (id INTEGER PRIMARY KEY CHECK(id=1), encrypted TEXT NOT NULL,
      channelId TEXT NOT NULL, clientIdHash TEXT NOT NULL, connectedAt INTEGER NOT NULL, expiresAt INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS bot_auth_session (id INTEGER PRIMARY KEY CHECK(id=1), setupHash TEXT NOT NULL,
      stateHash TEXT NOT NULL, browserHash TEXT NOT NULL, verifier TEXT NOT NULL, expiresAt INTEGER NOT NULL,
      status TEXT NOT NULL);`);
  }
  connected(): boolean { return !!this.#db.prepare('SELECT id FROM bot_credentials WHERE id=1').get(); }
  async crypt(value: string, purpose: string, decrypt = false): Promise<string> {
    if (!opaque(this.#env.BOT_VAULT_KEY)) throw fault();
    const key = await crypto.subtle.importKey('raw', Buffer.from(this.#env.BOT_VAULT_KEY, 'base64url'), 'AES-GCM', false, [decrypt ? 'decrypt' : 'encrypt']);
    const aad = new TextEncoder().encode(`joinqueue-v1:${purpose}:${this.#env.BOT_CHANNEL_ID}:${this.#env.GOOGLE_CLIENT_ID}`);
    if (decrypt) {
      const [iv, data, extra] = value.split('.');
      if (!iv || !data || extra || !/^[A-Za-z0-9_-]{16}$/.test(iv) || !/^[A-Za-z0-9_-]+$/.test(data)) throw fault();
      const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: Buffer.from(iv, 'base64url'), additionalData: aad }, key, Buffer.from(data, 'base64url'));
      return new TextDecoder('utf-8', { fatal: true }).decode(plain);
    }
    const iv = randomBytes(12);
    const data = await crypto.subtle.encrypt({ name: 'AES-GCM', iv, additionalData: aad }, key, new TextEncoder().encode(value));
    return iv.toString('base64url') + '.' + Buffer.from(data).toString('base64url');
  }
  async refreshToken(now = Date.now()): Promise<string> {
    const row = this.#db.prepare('SELECT * FROM bot_credentials WHERE id=1').get();
    if (!row || row.channelId !== this.#env.BOT_CHANNEL_ID || row.clientIdHash !== hash(this.#env.GOOGLE_CLIENT_ID ?? '') ||
        (Number(row.expiresAt) !== 0 && Number(row.expiresAt) <= now)) throw new BotFault('BOT_UNAVAILABLE', 503);
    return this.crypt(String(row.encrypted), 'refresh', true);
  }
}

/** Operator bootstrap only. This does not authenticate/provision plugin users. */
export class BotAuthorization {
  #db: SqlDriver; #env: BotAuthEnv; #request: typeof fetch; #clock: () => number; #vault: BotVault;
  constructor(db: SqlDriver, env: BotAuthEnv, request: typeof fetch = fetch, clock = Date.now) {
    this.#db = db; this.#env = env; this.#request = request.bind(globalThis); this.#clock = clock; this.#vault = new BotVault(db, env);
  }
  async handle(request: Request): Promise<Response> {
    if (!authBoundary(request, this.#env, this.#clock())) return response('認証入口は無効です。', 404);
    const url = new URL(request.url);
    try {
      if (url.pathname === AUTH_PATH + '/result') {
        const row = this.#db.prepare('SELECT * FROM bot_auth_session WHERE id=1').get();
        if (!row || !cookieValue(request) || !same(String(row.browserHash), hash(cookieValue(request))) || Number(row.expiresAt) <= this.#clock()) throw fault();
        const success = row.status === 'connected' && this.#vault.connected();
        return response(`<meta charset="utf-8"><title>JoinQueue Bot 認証結果</title><h1>${success ? 'Botの認証が完了しました' : '認証を完了できませんでした'}</h1><p>${success ? '登録済みBotチャンネルとの一致を確認し、認証情報をサーバーに暗号化保存しました。Bot投稿は停止中です。' : '認証を再試行する場合は、運営者が新しい一回用の認証入口を用意してください。'}</p>`, success ? 200 : 400);
      }
      if (url.pathname === CALLBACK_PATH) return await this.callback(request);
      if (this.#vault.connected()) return response('Botは接続済みです。上書き認証はできません。', 409);
      if (request.method === 'GET') {
        const nonce = random();
        return response(`<meta charset="utf-8"><title>JoinQueue Bot 運営者認証</title><h1>共通Botの認証（運営者専用）</h1><p>配信者向けの接続画面ではありません。@JoinQueueBotだけを認証します。</p><form method="post" autocomplete="off"><input type="hidden" name="csrf" value="${nonce}"><label>一回用の設定キー<input type="password" name="setup" required autocomplete="off" maxlength="43"></label><button>Googleの認証へ進む</button></form>`, 200,
          { 'Set-Cookie': cookieHeader(nonce), 'Referrer-Policy': 'same-origin',
            'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self' https://accounts.google.com" });
      }
      const text = await boundedText(request, 4096); const fields = new URLSearchParams(text);
      if ([...fields.keys()].length !== 2 || fields.getAll('csrf').length !== 1 || fields.getAll('setup').length !== 1) throw fault();
      const csrf = fields.get('csrf')!; const setup = fields.get('setup')!; const browser = cookieValue(request);
      if (!browser || !opaque(csrf) || !same(browser, csrf) || !opaque(setup) || !same(hash(setup), this.#env.BOT_AUTH_SETUP_HASH!)) throw fault();
      const state = random(); const verifier = random(); const encrypted = await this.#vault.crypt(verifier, 'pkce');
      const expiresAt = Math.min(this.#clock() + 600_000, Number(this.#env.BOT_AUTH_EXPIRES_AT));
      this.#db.transaction(() => {
        if (this.#vault.connected()) throw fault();
        const old = this.#db.prepare('SELECT * FROM bot_auth_session WHERE id=1').get();
        if (old && (old.setupHash === this.#env.BOT_AUTH_SETUP_HASH || (['pending', 'consumed'].includes(String(old.status)) && Number(old.expiresAt) > this.#clock()))) throw fault();
        this.#db.prepare('INSERT OR REPLACE INTO bot_auth_session VALUES (1,?,?,?,?,?,?)').run(this.#env.BOT_AUTH_SETUP_HASH!, hash(state), hash(browser), encrypted, expiresAt, 'pending');
      });
      const target = new URL('https://accounts.google.com/o/oauth2/v2/auth');
      target.search = new URLSearchParams({ client_id: this.#env.GOOGLE_CLIENT_ID!, redirect_uri: AUTH_ORIGIN + CALLBACK_PATH,
        response_type: 'code', scope: BOT_SCOPE, access_type: 'offline', prompt: 'consent', state,
        code_challenge: createHash('sha256').update(verifier).digest('base64url'), code_challenge_method: 'S256',
        include_granted_scopes: 'false', login_hint: 'joinqueue.bot@gmail.com' }).toString();
      // Only this fixed Google authorization endpoint may be used as an external form redirect.
      return response('', 303, { Location: target.href, 'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self' https://accounts.google.com" });
    } catch { return response('認証要求を確認できませんでした。秘密情報は表示しません。', 403); }
  }
  async callback(request: Request): Promise<Response> {
    const query = new URL(request.url).searchParams; const state = query.get('state'); const browser = cookieValue(request);
    const allowed = new Set(['state', 'code', 'scope', 'authuser', 'prompt', 'error', 'error_description', 'iss']);
    if (!opaque(state) || !browser || [...query.keys()].some(k => !allowed.has(k) || query.getAll(k).length !== 1) ||
        (query.has('iss') && query.get('iss') !== 'https://accounts.google.com')) throw fault();
    const row = this.#db.transaction(() => {
      const current = this.#db.prepare('SELECT * FROM bot_auth_session WHERE id=1').get();
      if (!current || current.status !== 'pending' || Number(current.expiresAt) <= this.#clock() ||
          current.setupHash !== this.#env.BOT_AUTH_SETUP_HASH || !same(String(current.stateHash), hash(state)) ||
          !same(String(current.browserHash), hash(browser)) || this.#vault.connected()) throw fault();
      // Consume BEFORE any network await; replay/concurrent requests never exchange twice.
      this.#db.prepare("UPDATE bot_auth_session SET status='consumed',verifier='' WHERE id=1").run();
      return current;
    });
    try {
      const code = query.get('code');
      if (query.has('error') || !token(code) || code.length > 4096) throw fault();
      const verifier = await this.#vault.crypt(String(row.verifier), 'pkce', true);
      const data = await this.google('https://oauth2.googleapis.com/token', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ client_id: this.#env.GOOGLE_CLIENT_ID!, client_secret: this.#env.GOOGLE_CLIENT_SECRET!,
          code, grant_type: 'authorization_code', redirect_uri: AUTH_ORIGIN + CALLBACK_PATH, code_verifier: verifier }) });
      if (!token(data.access_token) || !token(data.refresh_token) || data.token_type?.toLowerCase() !== 'bearer' ||
          !Number.isSafeInteger(data.expires_in) || data.expires_in <= 60 || data.expires_in > 86_400 ||
          typeof data.scope !== 'string' || !data.scope.split(' ').includes(BOT_SCOPE)) throw fault();
      // Verify that the refresh grant actually works, then verify the resulting identity.
      const refreshed = await new GoogleRefreshTokens({ GOOGLE_CLIENT_ID: this.#env.GOOGLE_CLIENT_ID,
        GOOGLE_CLIENT_SECRET: this.#env.GOOGLE_CLIENT_SECRET, GOOGLE_BOT_REFRESH_TOKEN: data.refresh_token }, this.#request, this.#clock).accessToken();
      const mine = await this.google('https://www.googleapis.com/youtube/v3/channels?part=id&mine=true', { headers: { Authorization: 'Bearer ' + refreshed } });
      if (!Array.isArray(mine.items) || mine.items.length !== 1 || mine.items[0]?.id !== this.#env.BOT_CHANNEL_ID) throw fault();
      let expiresAt = 0;
      if (data.refresh_token_expires_in !== undefined) {
        if (!Number.isSafeInteger(data.refresh_token_expires_in) || data.refresh_token_expires_in <= 60 || data.refresh_token_expires_in > 315_360_000) throw fault();
        expiresAt = this.#clock() + (data.refresh_token_expires_in - 60) * 1000;
      }
      const encrypted = await this.#vault.crypt(data.refresh_token, 'refresh');
      this.#db.transaction(() => {
        const current = this.#db.prepare('SELECT stateHash,status FROM bot_auth_session WHERE id=1').get();
        if (!current || current.stateHash !== row.stateHash || current.status !== 'consumed' ||
            !authConfigured(this.#env, this.#clock()) || Number(row.expiresAt) <= this.#clock() || this.#vault.connected()) throw fault();
        this.#db.prepare('INSERT INTO bot_credentials VALUES (1,?,?,?,?,?)').run(encrypted, this.#env.BOT_CHANNEL_ID, hash(this.#env.GOOGLE_CLIENT_ID!), this.#clock(), expiresAt);
        this.#db.prepare("UPDATE bot_auth_session SET status='connected' WHERE id=1").run();
      });
    } catch { this.#db.prepare("UPDATE bot_auth_session SET status='failed' WHERE id=1 AND status='consumed' AND stateHash=?").run(String(row.stateHash)); }
    // No codes, tokens, provider responses or error descriptions in the redirect/result.
    return response('', 303, { Location: AUTH_ORIGIN + AUTH_PATH + '/result' });
  }
  async google(url: string, init: RequestInit): Promise<Record<string, any>> {
    const result = await this.#request(url, { ...init, redirect: 'manual', signal: AbortSignal.timeout(8000) });
    if (!result.ok) throw fault();
    const data = JSON.parse(await boundedText(result, 32_768));
    if (!data || typeof data !== 'object' || Array.isArray(data)) throw fault();
    return data;
  }
}

export async function boundedText(message: Request | Response, limit: number): Promise<string> {
  const reader = message.body?.getReader(); if (!reader) throw fault();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<never>((_, reject) => { timer = setTimeout(() => { reject(fault()); void reader.cancel().catch(() => {}); }, 5000); });
  const chunks: Uint8Array[] = []; let size = 0;
  try {
    for (;;) {
      const part = await Promise.race([reader.read(), deadline]); if (part.done) break;
      size += part.value.byteLength; if (size > limit) throw fault(); chunks.push(part.value);
    }
    return new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks));
  } finally { clearTimeout(timer); void reader.cancel().catch(() => {}); }
}
