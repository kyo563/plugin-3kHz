import { SqlBotStore, type SqlDriver } from '../sql-store';

/** Operator-owned deployment setting only. Never reopens a tripped breaker on restart. */
export function applyPostingApproval(db: SqlDriver, enabled: string | undefined, approval: string | undefined, botConnected: boolean): void {
  db.exec('CREATE TABLE IF NOT EXISTS posting_approvals (id TEXT PRIMARY KEY)');
  if (enabled !== 'true' || !botConnected || !approval || !/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/.test(approval)) return;
  db.transaction(() => {
    if (db.prepare('SELECT id FROM posting_approvals WHERE id=?').get(approval)) return;
    db.prepare('INSERT INTO posting_approvals VALUES (?)').run(approval);
    new SqlBotStore(db).setEnabled(true);
  });
}
