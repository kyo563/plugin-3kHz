// TEST ONLY. Production entrypoint never exports these inspection/seed routes.
import type { DurableObjectState } from '@cloudflare/workers-types';
import worker, { BotCoordinator, type WorkerEnv } from '../../backend/cloudflare/worker';

export default worker;
export class TestPrivacyCoordinator extends BotCoordinator {
  constructor(private readonly testState: DurableObjectState, env: WorkerEnv) { super(testState, env); }
  override async fetch(request: Request): Promise<Response> {
    const action = new URL(request.url).pathname;
    if (action === '/test/seed') {
      this.testState.storage.sql.exec("INSERT INTO connections VALUES ('expired-test','youtube:test','UCaaaaaaaaaaaaaaaaaaaaaa',?,0)", Date.now() - 30 * 86400_000);
      return Response.json({ok: true});
    }
    if (action === '/test/alarm') {
      await super.alarm();
      return Response.json({alarm: await this.testState.storage.getAlarm(), rows: this.testState.storage.sql.exec('SELECT COUNT(*) AS n FROM connections').one().n});
    }
    return super.fetch(request);
  }
}
