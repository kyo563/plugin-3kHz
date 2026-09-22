import { mkdirSync } from 'node:fs';
import { isAbsolute, join } from 'node:path';
import { BotStore } from './store';
import { BotService } from './service';
import { BotFault } from './policy';
import { createLocalServer } from './http';

// No .env, Google credentials, production sender or automatic provisioning here.
// Keep server operational data OUTSIDE this OneDrive/source/distribution directory.
const localDataRoot = process.env.LOCALAPPDATA;
if (!localDataRoot || !isAbsolute(localDataRoot)) throw new Error('Windows LOCALAPPDATA is required for this development runner');
const dataDirectory = join(localDataRoot, 'JoinQueueBot', 'development');
mkdirSync(dataDirectory, { recursive: true });
const store = new BotStore(join(dataDirectory, 'backend.sqlite'));
store.setEnabled(false);
const disabled = async (): Promise<never> => { throw new BotFault('SERVICE_DISABLED', 503); };
const service = new BotService(store, { resolveChat: disabled, post: disabled }, event => console.log(JSON.stringify(event)));
const server = createLocalServer(service);
server.listen(11182, '127.0.0.1', () => console.log('Backend development only (posting disabled): http://127.0.0.1:11182/health'));
server.on('error', () => { console.error('BACKEND_START_FAILED'); store.close(); process.exitCode = 1; });
for (const signal of ['SIGINT', 'SIGTERM'] as const) process.once(signal, () => server.close(() => store.close()));
