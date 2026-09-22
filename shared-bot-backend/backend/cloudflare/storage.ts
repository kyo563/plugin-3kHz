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

/** Bounded, persistent global ingress counter; no raw IP or auth header stored. */
export function takeIngress(driver: SqlDriver, now = Date.now()): void {
  driver.transaction(() => {
    driver.exec('CREATE TABLE IF NOT EXISTS ingress (id INTEGER PRIMARY KEY CHECK(id=1), start INTEGER NOT NULL, n INTEGER NOT NULL)');
    const row = driver.prepare('SELECT start,n FROM ingress WHERE id=1').get();
    if (!row || now - Number(row.start) >= 60_000) {
      driver.prepare('INSERT OR REPLACE INTO ingress VALUES (1,?,1)').run(now);
    } else {
      if (Number(row.n) >= 60) throw new BotFault('RATE_LIMITED', 429, 60);
      driver.prepare('UPDATE ingress SET n=n+1 WHERE id=1').run();
    }
  });
}
