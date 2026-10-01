import { BotFault, digest } from '../policy';
import { CONNECTION_RETENTION_MS, SqlBotStore, type SqlDriver } from '../sql-store';

export const PRIVACY_ALARM_MS = 3_600_000;
const SECURITY_MS = 86_400_000;

/** Service-owned records only. Never touches Bot vault, switches, approval or local queue data. */
export class PrivacyRecords {
  constructor(private readonly db: SqlDriver) {
    db.exec(`CREATE TABLE IF NOT EXISTS erasure_receipts (tokenHash TEXT PRIMARY KEY, channelHash TEXT NOT NULL, expiresAt INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS erasure_barriers (channelHash TEXT PRIMARY KEY, erasedAt INTEGER NOT NULL);`);
  }
  receipt(tokenHash: string, confirmation: string, now: number): boolean {
    return Boolean(this.db.prepare('SELECT tokenHash FROM erasure_receipts WHERE tokenHash=? AND channelHash=? AND expiresAt>?').get(tokenHash, digest(confirmation), now));
  }
  wasErased(tokenHash: string, now: number): boolean {
    return Boolean(this.db.prepare('SELECT tokenHash FROM erasure_receipts WHERE tokenHash=? AND expiresAt>?').get(tokenHash, now));
  }
  assertFreshPairing(channelId: string, createdAt: number): void {
    const row = this.db.prepare('SELECT erasedAt FROM erasure_barriers WHERE channelHash=?').get(digest(channelId));
    if (row && createdAt <= Number(row.erasedAt)) throw new BotFault('UNAUTHENTICATED', 403);
  }
  erase(userId: string, channelId: string, tokenHash: string, now: number): void {
    if (userId !== 'youtube:' + channelId) throw new BotFault('UNAUTHENTICATED', 403);
    this.db.transaction(() => {
      new SqlBotStore(this.db).preserveLimits(now);
      this.db.prepare('DELETE FROM channel_checks WHERE deviceId IN (SELECT deviceId FROM devices WHERE userId=?)').run(userId);
      this.db.prepare('DELETE FROM channel_pairings WHERE channelId=? OR deviceId IN (SELECT deviceId FROM devices WHERE userId=?)').run(channelId, userId);
      this.db.prepare('DELETE FROM devices WHERE userId=?').run(userId);
      this.db.prepare('DELETE FROM connections WHERE userId=?').run(userId);
      this.db.prepare('DELETE FROM posts WHERE userId=?').run(userId);
      // An OAuth callback already in flight must not recreate an erased connection.
      this.db.prepare('INSERT OR REPLACE INTO erasure_barriers VALUES (?,?)').run(digest(channelId), now);
      // Lost response can be retried with the SAME credential + confirmation, never a claimed channel alone.
      this.db.prepare('INSERT OR REPLACE INTO erasure_receipts VALUES (?,?,?)').run(tokenHash, digest(channelId), now + SECURITY_MS);
    });
  }
  prune(now: number): void {
    this.db.transaction(() => {
      new SqlBotStore(this.db).preserveLimits(now);
      // Delete children before their expired/revoked parent connections.
      const stale = 'SELECT id FROM connections WHERE verifiedAt<=? OR revoked=1';
      this.db.prepare(`DELETE FROM posts WHERE userId IN (SELECT userId FROM connections WHERE verifiedAt<=? OR revoked=1)
        AND NOT EXISTS (SELECT 1 FROM connections c WHERE c.userId=posts.userId AND c.verifiedAt>? AND c.revoked=0)`)
        .run(now - CONNECTION_RETENTION_MS, now - CONNECTION_RETENTION_MS);
      this.db.prepare('DELETE FROM channel_checks WHERE deviceId IN (SELECT deviceId FROM channel_pairings WHERE connectionId IN (' + stale + '))').run(now - CONNECTION_RETENTION_MS);
      this.db.prepare('DELETE FROM devices WHERE deviceId IN (SELECT deviceId FROM channel_pairings WHERE connectionId IN (' + stale + '))').run(now - CONNECTION_RETENTION_MS);
      this.db.prepare('DELETE FROM channel_pairings WHERE connectionId IN (' + stale + ')').run(now - CONNECTION_RETENTION_MS);
      this.db.prepare('DELETE FROM connections WHERE verifiedAt<=? OR revoked=1').run(now - CONNECTION_RETENTION_MS);
      this.db.prepare('DELETE FROM channel_checks WHERE deviceId IN (SELECT deviceId FROM devices WHERE expiresAt<=? OR revoked=1)').run(now);
      this.db.prepare('DELETE FROM channel_pairings WHERE deviceId IN (SELECT deviceId FROM devices WHERE expiresAt<=? OR revoked=1)').run(now);
      this.db.prepare('DELETE FROM devices WHERE expiresAt<=? OR revoked=1').run(now);
      this.db.prepare("DELETE FROM channel_pairings WHERE status!='connected' AND expiresAt<=?").run(now);
      this.db.prepare('DELETE FROM posts WHERE createdAt<=?').run(now - CONNECTION_RETENTION_MS);
      this.db.prepare('DELETE FROM erasure_receipts WHERE expiresAt<=?').run(now);
      this.db.prepare('DELETE FROM erasure_barriers WHERE erasedAt<=?').run(now - SECURITY_MS);
      if (this.db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='creator_revocations'").get()) {
        this.db.prepare('DELETE FROM creator_revocations WHERE revokedAt<=?').run(now - SECURITY_MS);
      }
      this.db.prepare('DELETE FROM channel_checks WHERE checkedAt<=?').run(now - SECURITY_MS);
      for (const table of ['channel_source_budget', 'channel_oauth_budget', 'channel_probe_budget']) {
        this.db.prepare('DELETE FROM ' + table + ' WHERE startedAt<=?').run(now - SECURITY_MS);
      }
      // No rows in these tables carry Google tokens or local queue/memo/font data.
    });
  }
}
