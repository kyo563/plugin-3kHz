import type { DurableObjectStorage } from '@cloudflare/workers-types';
import { BotFault } from '../policy';
import type { SqlDriver } from '../sql-store';

/** SQL transactions must use transactionSync, never BEGIN/COMMIT statements. */
export function durableSqlDriver(storage: DurableObjectStorage): SqlDriver {
  return {
    exec(sql) { storage.sql.exec(sql).toArray(); },
    prepare(sql) {
      return {
        get(...args) { return storage.sql.exec(sql, ...args).toArray()[0]; },
        run(...args) {
          storage.sql.exec(sql, ...args).toArray();
          return { changes: Number(storage.sql.exec('SELECT changes() AS n').one().n) };
        },
      };
    },
    transaction: callback => storage.transactionSync(callback),
  };
}

/** Persistent per-source ingress counters, pruned after a minute; no raw IP/auth stored. */
export function takeIngress(driver: SqlDriver, now = Date.now(), source = 'global'): void {
  driver.transaction(() => {
    driver.exec('CREATE TABLE IF NOT EXISTS ingress_sources (source TEXT PRIMARY KEY, start INTEGER NOT NULL, n INTEGER NOT NULL)');
    driver.prepare('DELETE FROM ingress_sources WHERE start<=?').run(now - 60_000);
    const row = driver.prepare('SELECT start,n FROM ingress_sources WHERE source=?').get(source);
    if (!row || now - Number(row.start) >= 60_000) {
      driver.prepare('INSERT OR REPLACE INTO ingress_sources VALUES (?,?,1)').run(source, now);
    } else {
      if (Number(row.n) >= 60) throw new BotFault('RATE_LIMITED', 429, 60);
      driver.prepare('UPDATE ingress_sources SET n=n+1 WHERE source=?').run(source);
    }
  });
}
