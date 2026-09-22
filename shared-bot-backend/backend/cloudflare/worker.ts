import type { DurableObjectNamespace, DurableObjectState } from '@cloudflare/workers-types';
import { BotFault } from '../policy';
import { BotService } from '../service';
import { SqlBotStore } from '../sql-store';
import { YouTubeApi } from '../youtube';
import { apiResponse, boundedJson, json, rejected, validatePostRequest } from './http';
import { durableSqlDriver, takeIngress } from './storage';
import { GoogleRefreshTokens, type GoogleBotSecrets } from './tokens';
import { AUTH_PATH, BotAuthorization, BotVault, authBoundary, boundedText, type BotAuthEnv } from './bot-auth';
import { ChannelConnections, channelBoundary, isChannelRoute, type ChannelEnv } from './channel-connect';
import { applyPostingApproval } from './posting-approval';

export interface WorkerEnv extends GoogleBotSecrets, BotAuthEnv, ChannelEnv {
  BOT_COORDINATOR: DurableObjectNamespace;
  BOT_POSTING_ENABLED?: string;
  BOT_POSTING_APPROVAL_ID?: string;
  BOT_CHANNEL_ID: string;
}
// All channels/devices share ONE ledger, including quota and the circuit breaker.
// Never derive this name from client input. Changing it would reset safeguards.
const COORDINATOR_NAME = 'shared-youtube-bot-v1';

export default {
  async fetch(request: Request, env: WorkerEnv): Promise<Response> {
    try {
      const url = new URL(request.url);
      if (isChannelRoute(url.pathname)) {
        if (!channelBoundary(request, env)) return json({ error: { code: 'NOT_FOUND' } }, 404);
        const stub = env.BOT_COORDINATOR.get(env.BOT_COORDINATOR.idFromName(COORDINATOR_NAME));
        const headers: Record<string, string> = {};
        for (const name of ['Origin', 'Cookie', 'Content-Type', 'Authorization']) {
          const value = request.headers.get(name); if (value !== null) headers[name] = value;
        }
        const result = await stub.fetch(request.url, { method: request.method, headers, redirect: 'manual',
          ...(request.method === 'POST' ? { body: await boundedText(request, 8192) } : {}) });
        return new Response(await result.text(), { status: result.status, headers: Object.fromEntries(result.headers) });
      }
      if (url.pathname === AUTH_PATH || url.pathname.startsWith(AUTH_PATH + '/')) {
        if (!authBoundary(request, env)) return json({ error: { code: 'NOT_FOUND' } }, 404);
        const stub = env.BOT_COORDINATOR.get(env.BOT_COORDINATOR.idFromName(COORDINATOR_NAME));
        const headers: Record<string, string> = {};
        for (const name of ['Origin', 'Cookie', 'Content-Type']) { const value = request.headers.get(name); if (value !== null) headers[name] = value; }
        const result = await stub.fetch(request.url, { method: request.method, headers, redirect: 'manual',
          ...(request.method === 'POST' ? { body: await boundedText(request, 4096) } : {}) });
        return new Response(await result.text(), { status: result.status, headers: Object.fromEntries(result.headers) });
      }
      if (url.protocol !== 'https:' || request.headers.has('Origin')) return rejected(new BotFault('UNAUTHENTICATED', 403));
      if (url.pathname === '/health' && !url.search && request.method === 'GET') {
        return json({ service: 'joinqueue-bot-backend', mode: 'cloudflare-development', productionReady: false });
      }
      const invalid = validatePostRequest(request); if (invalid) return invalid;
      // Deployment switch plus the persisted store switch (default OFF) must BOTH allow posting.
      if (env.BOT_POSTING_ENABLED !== 'true') return rejected(new BotFault('SERVICE_DISABLED', 503));
      const input = await boundedJson(request);
      const stub = env.BOT_COORDINATOR.get(env.BOT_COORDINATOR.idFromName(COORDINATOR_NAME));
      const response = await stub.fetch('https://coordinator.internal/v1/bot/posts', {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: request.headers.get('Authorization')! },
        body: JSON.stringify(input),
      });
      return new Response(await response.text(), { status: response.status, headers: Object.fromEntries(response.headers) });
    } catch (error) { return rejected(error instanceof BotFault ? error : new BotFault('BOT_UNAVAILABLE', 503)); }
  },
};

/** Only fetch is exposed. Provisioning/enable methods are deliberately NOT RPC endpoints. */
export class BotCoordinator {
  #store: SqlBotStore;
  #service: BotService;
  #ctx: DurableObjectState;
  #env: WorkerEnv;
  #authorization: BotAuthorization;
  #connections: ChannelConnections;
  constructor(ctx: DurableObjectState, env: WorkerEnv) {
    this.#ctx = ctx; this.#env = env;
    const driver = durableSqlDriver(ctx.storage);
    this.#store = new SqlBotStore(driver);
    const vault = new BotVault(driver, env);
    applyPostingApproval(driver, env.BOT_POSTING_ENABLED, env.BOT_POSTING_APPROVAL_ID, vault.connected());
    this.#authorization = new BotAuthorization(driver, env);
    const youtube = new YouTubeApi(new GoogleRefreshTokens(env, fetch, Date.now,
      () => vault.refreshToken()), env.BOT_CHANNEL_ID);
    this.#service = new BotService(this.#store, youtube, event => console.log(JSON.stringify(event)));
    this.#connections = new ChannelConnections(driver, env, youtube);
  }
  async fetch(request: Request): Promise<Response> {
    try {
      const url = new URL(request.url);
      if (isChannelRoute(url.pathname)) {
        if (!channelBoundary(request, this.#env)) return json({ error: { code: 'NOT_FOUND' } }, 404);
        takeIngress(durableSqlDriver(this.#ctx.storage));
        return await this.#connections.handle(request);
      }
      if (url.pathname === AUTH_PATH || url.pathname.startsWith(AUTH_PATH + '/')) {
        if (!authBoundary(request, this.#env)) return json({ error: { code: 'NOT_FOUND' } }, 404);
        takeIngress(durableSqlDriver(this.#ctx.storage));
        return await this.#authorization.handle(request);
      }
      const invalid = validatePostRequest(request); if (invalid) return invalid;
      if (this.#env.BOT_POSTING_ENABLED !== 'true') return rejected(new BotFault('SERVICE_DISABLED', 503));
      takeIngress(durableSqlDriver(this.#ctx.storage));
      const input = await boundedJson(request);
      return apiResponse(await this.#service.submit(request.headers.get('Authorization') ?? undefined, input));
    } catch (error) { return rejected(error instanceof BotFault ? error : new BotFault('BOT_UNAVAILABLE', 503)); }
  }
}
