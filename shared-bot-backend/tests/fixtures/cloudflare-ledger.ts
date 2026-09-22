// TEST-ONLY entrypoint. NEVER included in wrangler.jsonc or production build.
import type { DurableObjectState, DurableObjectNamespace } from '@cloudflare/workers-types';
import { SqlBotStore, DEFAULT_LIMITS } from '../../backend/sql-store';
import { durableSqlDriver, takeIngress } from '../../backend/cloudflare/storage';
import { BotFault, failure } from '../../backend/policy';
import { BotService } from '../../backend/service';

export default {
  async fetch(request: Request, env: { LEDGER: DurableObjectNamespace }) {
    return env.LEDGER.get(env.LEDGER.idFromName('test-only')).fetch(request.url, {
      method: request.method, body: await request.text(),
    });
  },
};
export class TestLedger {
  private store: SqlBotStore;
  constructor(private ctx: DurableObjectState) { this.store = new SqlBotStore(durableSqlDriver(ctx.storage)); }
  async fetch(request: Request): Promise<Response> {
    const input = await request.json() as any;
    try {
      if (input.action === 'seed') {
        this.store.provisionDevice('a'.repeat(43), { userId: 'test-user', deviceId: 'test-device' }, input.now + 1_000_000);
        this.store.provisionVerifiedConnection({ id: 'test-connection', userId: 'test-user', channelId: 'UC' + 'a'.repeat(22), verifiedAt: input.now });
        this.store.setEnabled(true); return Response.json({ ok: true });
      }
      if (input.action === 'disabled') { this.store.setEnabled(false); return Response.json({ ok: true }); }
      if (input.action === 'previous') return Response.json(this.store.previous('test-user', input.eventHash, input.fingerprint));
      if (input.action === 'ingress') { takeIngress(durableSqlDriver(this.ctx.storage), input.now); return Response.json({ ok: true }); }
      if (input.action === 'snapshot') {
        const rows = this.ctx.storage.sql.exec('SELECT * FROM posts').toArray();
        const devices = this.ctx.storage.sql.exec('SELECT * FROM devices').toArray();
        return Response.json({ rows, devices });
      }
      if (input.action === 'reserve') {
        this.store.reserve(input.data, input.now, { ...DEFAULT_LIMITS, ...input.limits });
        return Response.json({ ok: true });
      }
      const service = new BotService(this.store, {
        async resolveChat() { return 'test-chat'; },
        async post() {
          if (input.fail) throw new Error('fake-secret');
        },
      }, () => {}, () => input.now, input.limits);
      return Response.json(await service.submit('Bearer ' + 'a'.repeat(43), input.post));
    } catch (error) {
      return Response.json(failure('test', error instanceof BotFault ? error : new BotFault('BOT_UNAVAILABLE', 503)));
    }
  }
}
