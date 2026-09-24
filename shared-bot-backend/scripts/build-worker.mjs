import { build } from 'esbuild';
import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const result = await build({
  absWorkingDir: root, entryPoints: ['backend/cloudflare/worker.ts'],
  outfile: resolve(root, '.worker-build/worker.mjs'), bundle: true,
  platform: 'neutral', format: 'esm', target: 'es2022', external: ['node:crypto', 'node:buffer', 'node:net'],
  sourcemap: false, metafile: true,
});
for (const path of Object.keys(result.metafile.inputs)) {
  assert.ok(!/(^|[\\/])(tests|fixtures|static)([\\/]|$)/.test(path), 'Test/UI files cannot enter the server bundle');
  assert.ok(!/backend[\\/](store|dev|http)\.ts$/.test(path), 'Node local adapters cannot enter the Worker bundle');
  assert.ok(!/src[\\/](ui|onecomme|core)[\\/]/.test(path), 'Local queue data/UI must stay in the plugin');
}
const external = Object.values(result.metafile.outputs).flatMap(output => output.imports);
assert.ok(external.every(item => ['node:crypto', 'node:buffer', 'node:net'].includes(item.path)), 'Unexpected runtime dependency');
console.log('Built isolated Cloudflare Worker (not deployed; posting state is controlled by the deployed environment).');
