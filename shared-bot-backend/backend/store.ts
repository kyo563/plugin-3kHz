import { DatabaseSync } from 'node:sqlite';
import { SqlBotStore, type SqlDriver } from './sql-store';
export { DEFAULT_LIMITS, REQUEST_UNITS, type Limits, type Connection, type Principal } from './sql-store';

/** Local Node adapter. Never imported into the Workers bundle. */
export class BotStore extends SqlBotStore {
  private readonly sqlite: DatabaseSync;
  constructor(path: string) {
    const sqlite = new DatabaseSync(path);
    sqlite.exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;');
    const driver: SqlDriver = {
      exec: sql => sqlite.exec(sql),
      prepare: sql => sqlite.prepare(sql),
      transaction<T>(callback: () => T): T {
        sqlite.exec('BEGIN IMMEDIATE');
        try { const result = callback(); sqlite.exec('COMMIT'); return result; }
        catch (error) { sqlite.exec('ROLLBACK'); throw error; }
      },
    };
    super(driver);
    this.sqlite = sqlite;
  }
  close(): void { this.sqlite.close(); }
}
