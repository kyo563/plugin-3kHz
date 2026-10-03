// TEST ONLY. Production entrypoint never exports these inspection/seed routes.
import type { DurableObjectState } from '@cloudflare/workers-types';
import worker, { BotCoordinator, type WorkerEnv } from '../../backend/cloudflare/worker';

export default worker;
export class TestPrivacyCoordinator extends BotCoordinator {
  constructor(private readonly testState: DurableObjectState, env: WorkerEnv) { super(testState, env); }
  override async fetch(request: Request): Promise<Response> {
    const action = new URL(request.url).pathname;
    if (action === '/test/seed') {
      this.testState.storage.sql.exec("INSERT INTO connections (id,userId,channelId,verifiedAt,revoked,lastUsedAt) VALUES ('expired-test','youtube:test','UCaaaaaaaaaaaaaaaaaaaaaa',?,0,?)", Date.now() - 30 * 86400_000, Date.now() - 91 * 86400_000);
      return Response.json({ok: true});
    }
    if (action === '/test/alarm') {
      await super.alarm();
      return Response.json({alarm: await this.testState.storage.getAlarm(), rows: this.testState.storage.sql.exec('SELECT COUNT(*) AS n FROM connections').one().n,
        grants:this.testState.storage.sql.exec('SELECT COUNT(*) AS n FROM creator_grants').one().n});
    }
    if (action === '/test/creator-due') {
      this.testState.storage.sql.exec("UPDATE creator_grants SET checkedAt=?,nextCheckAt=?",Date.now()-25*3600000,Date.now()-1);
      return Response.json({ok:true});
    }
    if (action === '/test/creator-idle') {
      this.testState.storage.sql.exec('UPDATE connections SET lastUsedAt=?,verifiedAt=?',Date.now()-91*86400_000,Date.now());
      this.testState.storage.sql.exec('UPDATE devices SET expiresAt=?',Date.now()+90*86400_000);
      this.testState.storage.sql.exec('UPDATE creator_grants SET nextCheckAt=?',Date.now()-1);
      return Response.json({ok:true});
    }
    return super.fetch(request);
  }
}
