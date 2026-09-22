import { randomUUID } from 'node:crypto';
import { BotFault, failure, type ApiResult } from '../policy';

export function json(value: unknown, status = 200, retryAfter?: number): Response {
  return new Response(JSON.stringify(value), { status, headers: {
    'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'",
    ...(retryAfter === undefined ? {} : { 'Retry-After': String(retryAfter) }),
  } });
}
export function apiResponse(result: ApiResult): Response {
  return json(result.body, result.http, result.body.error?.retryAfterSeconds);
}
export function rejected(fault: BotFault): Response { return apiResponse(failure(randomUUID(), fault)); }

/** No browser CORS, cookie auth, public provisioning, callbacks or free-form endpoint. */
export function validatePostRequest(request: Request): Response | undefined {
  const url = new URL(request.url);
  if (url.protocol !== 'https:' || request.headers.has('Origin')) return rejected(new BotFault('UNAUTHENTICATED', 403));
  if (url.search || url.pathname !== '/v1/bot/posts') return rejected(new BotFault('INVALID_MESSAGE', 404));
  if (request.method !== 'POST') return rejected(new BotFault('INVALID_MESSAGE', 405));
  if (!/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(request.headers.get('Content-Type') ?? '') || request.headers.has('Content-Encoding')) return rejected(new BotFault('INVALID_MESSAGE', 415));
  if (!/^Bearer [A-Za-z0-9_-]{43,128}$/.test(request.headers.get('Authorization') ?? '')) return rejected(new BotFault('UNAUTHENTICATED', 401));
  const length = request.headers.get('Content-Length');
  if (length !== null && (!/^\d+$/.test(length) || Number(length) > 8192)) return rejected(new BotFault('INVALID_MESSAGE', 413));
}

export async function boundedJson(request: Request): Promise<unknown> {
  if (!request.body) throw new BotFault('INVALID_MESSAGE');
  const reader = request.body.getReader(); const chunks: Uint8Array[] = []; let size = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => { reject(new BotFault('REQUEST_EXPIRED', 408)); void reader.cancel().catch(() => {}); }, 5000);
  });
  try {
    for (;;) {
      const part = await Promise.race([reader.read(), deadline]);
      if (part.done) break;
      size += part.value.byteLength;
      if (size > 8192) throw new BotFault('INVALID_MESSAGE', 413);
      chunks.push(part.value);
    }
    const bytes = new Uint8Array(size); let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
  } catch (error) { throw error instanceof BotFault ? error : new BotFault('INVALID_MESSAGE'); }
  finally { clearTimeout(timer); void reader.cancel().catch(() => {}); }
}
