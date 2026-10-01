import { randomUUID } from 'node:crypto';
import { BotFault, digest } from '../policy';
import { CONNECTION_RETENTION_MS, type SqlDriver } from '../sql-store';
import { BotVault, boundedText, type BotAuthEnv } from './bot-auth';

export const CREATOR_SCOPE = 'https://www.googleapis.com/auth/youtube.readonly';
export const CREATOR_CHECK_MS = 86_400_000;
const RETRY_MS = 900_000;
const token = (v: unknown): v is string => typeof v === 'string' && /^[\x21-\x7e]{1,8192}$/.test(v);
const unavailable = () => new BotFault('CHANNEL_AUTH_UNAVAILABLE', 503, 900);
export interface CreatorEnv extends BotAuthEnv {
  CHANNEL_GRANTS_ENABLED?: string;
  CREATOR_GOOGLE_CLIENT_ID?: string;
  CREATOR_GOOGLE_CLIENT_SECRET?: string;
  CREATOR_GOOGLE_PROJECT_ID?: string;
  BOT_GOOGLE_PROJECT_ID?: string;
  BOT_DATA_LIFECYCLE_ENABLED?: string;
}

// Project IDs must be verified by the operator in Google Console before enabling.
// Different clients in the SAME project do not isolate Google's grant revocation.
export function creatorConfigured(env: CreatorEnv): boolean {
  const project = /^[a-z][a-z0-9-]{4,28}[a-z0-9]$/;
  return env.CHANNEL_GRANTS_ENABLED === 'true' && token(env.CREATOR_GOOGLE_CLIENT_ID) &&
    token(env.CREATOR_GOOGLE_CLIENT_SECRET) && project.test(env.CREATOR_GOOGLE_PROJECT_ID ?? '') &&
    project.test(env.BOT_GOOGLE_PROJECT_ID ?? '') && env.CREATOR_GOOGLE_PROJECT_ID !== env.BOT_GOOGLE_PROJECT_ID &&
    env.CREATOR_GOOGLE_CLIENT_ID !== env.GOOGLE_CLIENT_ID && /^[\w-]{43}$/.test(env.BOT_VAULT_KEY ?? '');
}

/** Server-only encrypted readonly grants. No token getter, HTTP export or Bot-vault mutation. */
export class CreatorGrants {
  private vault: BotVault;
  private pending = new Map<string, Promise<void>>();
  constructor(private db: SqlDriver, private env: CreatorEnv, private request: typeof fetch = fetch, private clock = Date.now) {
    this.request = request.bind(globalThis);
    this.vault = new BotVault(db, {...env, GOOGLE_CLIENT_ID: env.CREATOR_GOOGLE_CLIENT_ID});
    db.exec(`CREATE TABLE IF NOT EXISTS creator_grants (
      id TEXT PRIMARY KEY, connectionId TEXT UNIQUE NOT NULL, channelId TEXT NOT NULL, encrypted TEXT NOT NULL,
      clientHash TEXT NOT NULL, createdAt INTEGER NOT NULL, checkedAt INTEGER NOT NULL, nextCheckAt INTEGER NOT NULL,
      expiresAt INTEGER NOT NULL, status TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS creator_grant_due ON creator_grants(nextCheckAt);
      CREATE INDEX IF NOT EXISTS creator_grant_channel ON creator_grants(channelId);
      CREATE TABLE IF NOT EXISTS creator_revocations (channelHash TEXT PRIMARY KEY, revokedAt INTEGER NOT NULL);`);
  }
  configured(): void { if (!creatorConfigured(this.env)) throw new BotFault('SERVICE_DISABLED', 503); }
  async prepare(connectionId: string, channelId: string, refresh: unknown, lifetime?: unknown, authStartedAt = this.clock()) {
    this.configured();
    if (!token(refresh) || !/^UC[\w-]{22}$/.test(channelId) || channelId === this.env.BOT_CHANNEL_ID) throw unavailable();
    let expiresAt = 0;
    if (lifetime !== undefined) {
      if (!Number.isSafeInteger(lifetime) || Number(lifetime) <= 60 || Number(lifetime) > 315_360_000) throw unavailable();
      expiresAt = this.clock() + (Number(lifetime) - 60) * 1000;
    }
    const id = randomUUID();
    const encrypted = await this.vault.crypt(refresh, `creator-refresh:${id}:${channelId}`);
    return {id, connectionId, channelId, encrypted, expiresAt, createdAt: this.clock(), authStartedAt};
  }
  // Caller commits this with its connection transaction, AFTER rechecking pending OAuth.
  save(p: Awaited<ReturnType<CreatorGrants['prepare']>>): void {
    this.configured();
    const barrier = this.db.prepare('SELECT revokedAt FROM creator_revocations WHERE channelHash=?').get(digest(p.channelId));
    if (barrier && p.authStartedAt <= Number(barrier.revokedAt)) throw new BotFault('CHANNEL_NOT_LINKED', 403);
    if (Number(this.db.prepare('SELECT count(*) AS n FROM creator_grants WHERE channelId=?').get(p.channelId)?.n) >= 8) throw new BotFault('RATE_LIMITED', 429, 3600);
    if (this.db.prepare("SELECT id FROM creator_grants WHERE channelId=? AND status='revoking'").get(p.channelId)) throw unavailable();
    this.db.prepare('INSERT INTO creator_grants VALUES (?,?,?,?,?,?,?,?,?,?)').run(p.id, p.connectionId, p.channelId, p.encrypted,
      digest(this.env.CREATOR_GOOGLE_CLIENT_ID!), p.createdAt, p.createdAt, p.createdAt + CREATOR_CHECK_MS, p.expiresAt, 'active');
  }
  private stop(channelId: string): void {
    const user = 'youtube:' + channelId;
    this.db.prepare('UPDATE devices SET revoked=1 WHERE userId=?').run(user);
    this.db.prepare('UPDATE connections SET revoked=1 WHERE userId=?').run(user);
    this.db.prepare("UPDATE channel_pairings SET status='revoked',verifier=NULL WHERE channelId=?").run(channelId);
  }
  private invalidate(id: string): void {
    this.db.transaction(() => {
      const row = this.db.prepare('SELECT connectionId FROM creator_grants WHERE id=?').get(id);
      if (!row) return;
      this.db.prepare('UPDATE devices SET revoked=1 WHERE deviceId IN (SELECT deviceId FROM channel_pairings WHERE connectionId=?)').run(String(row.connectionId));
      this.db.prepare('UPDATE connections SET revoked=1 WHERE id=?').run(String(row.connectionId));
      this.db.prepare("UPDATE channel_pairings SET status='revoked',verifier=NULL WHERE connectionId=?").run(String(row.connectionId));
      this.db.prepare('DELETE FROM creator_grants WHERE id=?').run(id);
    });
  }
  async ensure(connectionId: string): Promise<void> {
    this.configured();
    const inFlight = this.pending.get(connectionId); if (inFlight) return inFlight;
    const task = this.check(connectionId); this.pending.set(connectionId, task);
    try { await task; } finally { this.pending.delete(connectionId); }
  }
  private async check(connectionId: string): Promise<void> {
    const row = this.db.prepare('SELECT * FROM creator_grants WHERE connectionId=?').get(connectionId);
    if (!row || row.status !== 'active' || row.clientHash !== digest(this.env.CREATOR_GOOGLE_CLIENT_ID!)) throw new BotFault('CHANNEL_NOT_LINKED', 403);
    if (Number(row.expiresAt) !== 0 && Number(row.expiresAt) <= this.clock()) { this.invalidate(String(row.id)); throw new BotFault('CHANNEL_NOT_LINKED', 403); }
    if (Number(row.nextCheckAt) > this.clock()) {
      if (this.clock() - Number(row.checkedAt) >= CREATOR_CHECK_MS) throw unavailable();
      return;
    }
    // Reserve a retry window BEFORE awaiting. Restart/concurrency cannot flood Google.
    this.db.prepare("UPDATE creator_grants SET nextCheckAt=? WHERE id=? AND status='active'").run(this.clock() + RETRY_MS, String(row.id));
    try {
      const refresh = await this.vault.crypt(String(row.encrypted), `creator-refresh:${row.id}:${row.channelId}`, true);
      const r = await this.request('https://oauth2.googleapis.com/token', {method:'POST', redirect:'manual', signal:AbortSignal.timeout(8000),
        headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:new URLSearchParams({grant_type:'refresh_token',
          client_id:this.env.CREATOR_GOOGLE_CLIENT_ID!, client_secret:this.env.CREATOR_GOOGLE_CLIENT_SECRET!, refresh_token:refresh})});
      const data = JSON.parse(await boundedText(r, 32768));
      if (r.status === 400 && data?.error === 'invalid_grant') { this.invalidate(String(row.id)); throw new BotFault('CHANNEL_NOT_LINKED', 403); }
      if (!r.ok || !token(data?.access_token) || data?.token_type?.toLowerCase() !== 'bearer' ||
        !Number.isSafeInteger(data?.expires_in) || data.expires_in <= 60 || data.expires_in > 86400 ||
        (data.scope !== undefined && data.scope !== CREATOR_SCOPE)) throw unavailable();
      // No access token is cached/persisted or used to fetch incoming comments.
      const changed = this.db.prepare("UPDATE creator_grants SET checkedAt=?,nextCheckAt=? WHERE id=? AND status='active' AND encrypted=?")
        .run(this.clock(), this.clock() + CREATOR_CHECK_MS, String(row.id), String(row.encrypted));
      if (changed.changes !== 1) throw new BotFault('CHANNEL_NOT_LINKED', 403);
    } catch (e) { throw e instanceof BotFault ? e : unavailable(); }
  }
  async revoke(channelId: string): Promise<void> {
    this.configured();
    // Local posting stops even if Google's revocation endpoint is temporarily down.
    this.db.transaction(() => {
      this.stop(channelId);
      this.db.prepare('INSERT OR REPLACE INTO creator_revocations VALUES (?,?)').run(digest(channelId), this.clock());
      this.db.prepare("UPDATE creator_grants SET status='revoking',nextCheckAt=? WHERE channelId=?").run(this.clock(), channelId);
    });
    const rows = this.db.prepare('SELECT id FROM creator_grants WHERE channelId=?').get(channelId);
    while (rows && this.db.prepare('SELECT id FROM creator_grants WHERE channelId=?').get(channelId)) {
      const row = this.db.prepare('SELECT * FROM creator_grants WHERE channelId=?').get(channelId)!;
      await this.revokeRow(row);
    }
  }
  private async revokeRow(row: Record<string, unknown>): Promise<void> {
    this.db.prepare('UPDATE creator_grants SET nextCheckAt=? WHERE id=?').run(this.clock() + RETRY_MS, String(row.id));
    try {
      const refresh = await this.vault.crypt(String(row.encrypted), `creator-refresh:${row.id}:${row.channelId}`, true);
      const r = await this.request('https://oauth2.googleapis.com/revoke', {method:'POST', redirect:'manual', signal:AbortSignal.timeout(8000),
        headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:new URLSearchParams({token:refresh})});
      if (r.status !== 200) {
        const data = JSON.parse(await boundedText(r, 32768));
        if (r.status !== 400 || data?.error !== 'invalid_token') throw unavailable();
      }
      this.db.prepare("DELETE FROM creator_grants WHERE id=? AND status='revoking'").run(String(row.id));
    } catch { throw unavailable(); }
  }
  async sweep(): Promise<void> {
    this.configured();
    // Bounded batch. Persisted nextCheckAt prevents one failure starving fresh creators.
    for (let i = 0; i < 8; i++) {
      const row = this.db.prepare('SELECT * FROM creator_grants WHERE nextCheckAt<=? ORDER BY nextCheckAt,id LIMIT 1').get(this.clock());
      if (!row) break;
      try {
        if (row.status === 'revoking') await this.revokeRow(row);
        else if (this.env.BOT_DATA_LIFECYCLE_ENABLED === 'true' && Number(row.createdAt) <= this.clock() - CONNECTION_RETENTION_MS) await this.revoke(String(row.channelId));
        else await this.ensure(String(row.connectionId));
      } catch {
        this.db.prepare('UPDATE creator_grants SET nextCheckAt=? WHERE id=? AND nextCheckAt<=?').run(this.clock() + RETRY_MS, String(row.id), this.clock());
        // No raw Google errors/tokens in logs; failed checks stay blocked until retry.
      }
    }
  }
}
