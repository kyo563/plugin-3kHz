import { BotFault, digest, failure, type ApiResult } from './policy';

export type SqlValue = string | number;
export interface SqlDriver {
  exec(sql: string): void;
  prepare(sql: string): {
    get(...args: SqlValue[]): Record<string, unknown> | undefined;
    run(...args: SqlValue[]): { changes: number | bigint };
  };
  transaction<T>(callback: () => T): T;
}

export interface Principal { userId: string; deviceId: string }
export interface Connection { id: string; userId: string; channelId: string; verifiedAt: number; revoked: number }
export interface Limits { userPerMinute: number; channelPerMinute: number; globalPerMinute: number; channelGapMs: number; globalGapMs: number; dailyUnits: number }
export const DEFAULT_LIMITS: Limits = { userPerMinute: 12, channelPerMinute: 6, globalPerMinute: 20, channelGapMs: 10_000, globalGapMs: 1_000, dailyUnits: 8_000 };
export const REQUEST_UNITS = 52; // channels.list + videos.list + liveChatMessages.insert; no refund on failure.

/** Single-service SQLite ledger. No Google credentials, message body, memo or raw token. */
export class SqlBotStore {
  constructor(protected readonly db: SqlDriver) {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS devices (hash TEXT PRIMARY KEY, userId TEXT NOT NULL, deviceId TEXT NOT NULL,
        expiresAt INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS connections (id TEXT PRIMARY KEY, userId TEXT NOT NULL, channelId TEXT NOT NULL,
        verifiedAt INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS posts (requestId TEXT PRIMARY KEY, userId TEXT NOT NULL, channelId TEXT NOT NULL,
        eventHash TEXT NOT NULL, fingerprint TEXT NOT NULL, contentHash TEXT NOT NULL, createdAt INTEGER NOT NULL,
        result TEXT, UNIQUE(userId, eventHash));
      CREATE INDEX IF NOT EXISTS post_time ON posts(createdAt);
      CREATE INDEX IF NOT EXISTS post_user_time ON posts(userId,createdAt);
      CREATE INDEX IF NOT EXISTS post_channel_time ON posts(channelId,createdAt);
      CREATE INDEX IF NOT EXISTS post_content_time ON posts(channelId,contentHash,createdAt);
      CREATE TABLE IF NOT EXISTS switches (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL);
      INSERT OR IGNORE INTO switches VALUES (1, 0);`);
  }
  /** Trusted operator / future verified OAuth service ONLY. Never exposed by HTTP. */
  provisionDevice(token: string, principal: Principal, expiresAt: number): void {
    if (!/^[A-Za-z0-9_-]{43,128}$/.test(token) || !Number.isSafeInteger(expiresAt) || !principal.userId || !principal.deviceId) throw new Error('Invalid provision');
    this.db.prepare('INSERT INTO devices (hash,userId,deviceId,expiresAt) VALUES (?,?,?,?)')
      .run(digest(token), principal.userId, principal.deviceId, expiresAt);
  }
  /** Caller must have verified channel ownership out of band; no self-claim API. */
  provisionVerifiedConnection(connection: Omit<Connection, 'revoked'>): void {
    if (!/^UC[\w-]{22}$/.test(connection.channelId) || !connection.userId || !connection.id || !Number.isSafeInteger(connection.verifiedAt) || connection.verifiedAt <= 0) throw new Error('Invalid verified connection');
    this.db.prepare('INSERT INTO connections (id,userId,channelId,verifiedAt) VALUES (?,?,?,?)')
      .run(connection.id, connection.userId, connection.channelId, connection.verifiedAt);
  }
  revokeDevice(deviceId: string): void { this.db.prepare('UPDATE devices SET revoked=1 WHERE deviceId=?').run(deviceId); }
  revokeConnection(id: string): void { this.db.prepare('UPDATE connections SET revoked=1 WHERE id=?').run(id); }
  setEnabled(enabled: boolean): void { this.db.prepare('UPDATE switches SET enabled=? WHERE id=1').run(enabled ? 1 : 0); }
  assertEnabled(): void {
    if (this.db.prepare('SELECT enabled FROM switches WHERE id=1').get()?.enabled !== 1) throw new BotFault('SERVICE_DISABLED', 503);
  }
  authenticate(header: string | undefined, now: number): Principal {
    if (!header || !/^Bearer [A-Za-z0-9_-]{43,128}$/.test(header)) throw new BotFault('UNAUTHENTICATED', 401);
    const row = this.db.prepare('SELECT userId,deviceId FROM devices WHERE hash=? AND revoked=0 AND expiresAt>?')
      .get(digest(header.slice(7)), now);
    if (!row) throw new BotFault('UNAUTHENTICATED', 401);
    return { userId: String(row.userId), deviceId: String(row.deviceId) };
  }
  connection(id: string, userId: string): Connection {
    const row = this.db.prepare('SELECT * FROM connections WHERE id=? AND userId=? AND revoked=0 AND verifiedAt>0').get(id, userId);
    if (!row) throw new BotFault('CHANNEL_NOT_LINKED', 403);
    return row as unknown as Connection;
  }
  previous(userId: string, eventHash: string, fingerprint: string): ApiResult | undefined {
    const old = this.db.prepare('SELECT requestId,fingerprint,result FROM posts WHERE userId=? AND eventHash=?').get(userId, eventHash);
    if (!old) return;
    if (old.fingerprint !== fingerprint) throw new BotFault('DUPLICATE_CONFLICT', 409);
    // Pending records survive a crash. They are NEVER automatically re-dispatched.
    return old.result ? JSON.parse(String(old.result)) as ApiResult : failure(String(old.requestId), new BotFault('DELIVERY_UNKNOWN', 409));
  }
  reserve(data: { requestId: string; userId: string; channelId: string; eventHash: string; fingerprint: string; contentHash: string }, now: number, limits: Limits): ApiResult | undefined {
    return this.db.transaction(() => {
      const previous = this.previous(data.userId, data.eventHash, data.fingerprint);
      if (previous) return previous;
      this.assertEnabled();
      const count = (sql: string, ...args: (string | number)[]) => Number(this.db.prepare(sql).get(...args)?.n ?? 0);
      if (count('SELECT count(*) AS n FROM posts WHERE createdAt>?', now - 86_400_000) * REQUEST_UNITS + REQUEST_UNITS > limits.dailyUnits) throw new BotFault('QUOTA_EXHAUSTED', 429);
      const userCount = count('SELECT count(*) AS n FROM posts WHERE userId=? AND createdAt>?', data.userId, now - 60_000);
      const channelCount = count('SELECT count(*) AS n FROM posts WHERE channelId=? AND createdAt>?', data.channelId, now - 60_000);
      const globalCount = count('SELECT count(*) AS n FROM posts WHERE createdAt>?', now - 60_000);
      const lastChannel = count('SELECT max(createdAt) AS n FROM posts WHERE channelId=?', data.channelId);
      const lastGlobal = count('SELECT max(createdAt) AS n FROM posts');
      const sameContent = count('SELECT count(*) AS n FROM posts WHERE channelId=? AND contentHash=? AND createdAt>?', data.channelId, data.contentHash, now - 60_000);
      if (userCount >= limits.userPerMinute || channelCount >= limits.channelPerMinute || globalCount >= limits.globalPerMinute ||
          (lastChannel > 0 && now - lastChannel < limits.channelGapMs) || (lastGlobal > 0 && now - lastGlobal < limits.globalGapMs) || sameContent > 0) throw new BotFault('RATE_LIMITED', 429, 60);
      this.db.prepare('INSERT INTO posts (requestId,userId,channelId,eventHash,fingerprint,contentHash,createdAt) VALUES (?,?,?,?,?,?,?)')
        .run(data.requestId, data.userId, data.channelId, data.eventHash, data.fingerprint, data.contentHash, now);
      return undefined;
    });
  }
  finish(requestId: string, result: ApiResult): void {
    const saved = this.db.prepare('UPDATE posts SET result=? WHERE requestId=? AND result IS NULL').run(JSON.stringify(result), requestId);
    if (saved.changes !== 1) throw new Error('Ledger state changed');
  }
}
