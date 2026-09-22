import { createServer } from 'node:http';
import { randomUUID } from 'node:crypto';
import { BotFault, failure } from './policy';
import type { BotService } from './service';

/** LOCAL DEVELOPMENT ONLY. Public hosting needs TLS, proxy trust and edge limits. */
export function createLocalServer(service: BotService) {
  let windowStart = Date.now(); let attempts = 0;
  const server = createServer(async (req, res) => {
    const reply = (status: number, body: unknown) => {
      if (res.destroyed) return;
      res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'", Connection: 'close' });
      res.end(JSON.stringify(body));
    };
    // No browser credential endpoint; the future plugin server component will call
    // the shared backend. No CORS wildcard, proxy headers, redirects or URL fetching.
    if (req.socket.remoteAddress !== '127.0.0.1' || req.headers.host !== `127.0.0.1:${req.socket.localPort}` || req.headers.origin) {
      reply(403, { error: { code: 'FORBIDDEN', message: 'この接続元は許可されていません。' } }); return;
    }
    if (Date.now() - windowStart >= 60_000) { attempts = 0; windowStart = Date.now(); }
    if (++attempts > 60) { reply(429, failure(randomUUID(), new BotFault('RATE_LIMITED', 429, 60)).body); return; }
    if (req.url === '/health' && req.method === 'GET') {
      reply(200, { service: 'joinqueue-bot-backend', mode: 'local-development', publicHostingReady: false }); return;
    }
    if (req.url !== '/v1/bot/posts') { reply(404, { error: { code: 'NOT_FOUND' } }); return; }
    if (req.method !== 'POST') { reply(405, { error: { code: 'METHOD_NOT_ALLOWED' } }); return; }
    if (!/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(req.headers['content-type'] ?? '') || req.headers['content-encoding']) {
      reply(415, { error: { code: 'UNSUPPORTED_MEDIA_TYPE' } }); return;
    }
    try {
      const chunks: Buffer[] = []; let bytes = 0;
      for await (const chunk of req) {
        bytes += Buffer.byteLength(chunk);
        if (bytes > 8_192) { reply(413, { error: { code: 'PAYLOAD_TOO_LARGE' } }); return; }
        chunks.push(Buffer.from(chunk));
      }
      const result = await service.submit(req.headers.authorization, JSON.parse(Buffer.concat(chunks).toString('utf8')));
      if (result.body.error?.retryAfterSeconds) res.setHeader('Retry-After', result.body.error.retryAfterSeconds);
      reply(result.http, result.body);
    } catch {
      reply(400, failure(randomUUID(), new BotFault('INVALID_MESSAGE')).body);
    }
  });
  server.requestTimeout = 10_000;
  server.headersTimeout = 10_000;
  server.timeout = 30_000;
  server.maxHeadersCount = 30;
  server.maxConnections = 20;
  return server;
}
