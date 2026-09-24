import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import worker, { sourceKey, type WorkerEnv } from '../backend/cloudflare/worker';
import { takeIngress } from '../backend/cloudflare/storage';
import type { SqlDriver } from '../backend/sql-store';

const env = { BOT_VAULT_KEY: 'test-only-secret' } as WorkerEnv;
test('edge source ignores forged headers, groups IPv6 /64 and fails closed without Cloudflare IP', () => {
  const key = (ip: string, extra = {}) => sourceKey(new Request('https://test.invalid', {headers:{'CF-Connecting-IP':ip,...extra}}), env);
  assert.equal(key('192.0.2.1'), key('192.0.2.1', {'X-JoinQueue-Source':'forged', 'X-Forwarded-For':'192.0.2.2'}));
  assert.notEqual(key('192.0.2.1'), key('192.0.2.2'));
  assert.equal(key('2001:db8:0:1::1'), key('2001:0db8:0000:0001:ffff:ffff:ffff:ffff'));
  assert.notEqual(key('2001:db8:0:1::1'), key('2001:db8:0:2::1'));
  assert.throws(()=>key('')); assert.throws(()=>key('not-an-ip'));
});

test('edge always replaces client supplied source before forwarding to the private DO', async () => {
  let forwarded: Request | undefined;
  const bindings = {...env, CHANNEL_CONNECT_ENABLED:'true', BOT_COORDINATOR:{
    idFromName:()=> 'test', get:()=>({fetch:async(url: string, init: RequestInit)=>{
      forwarded = new Request(url, init); return Response.json({status:'test'});
    }}),
  }} as unknown as WorkerEnv;
  const req = new Request('https://joinqueue-bot-backend.joinqueue.workers.dev/v1/connections/start', {method:'POST', headers:{
    'CF-Connecting-IP':'192.0.2.1', 'X-JoinQueue-Source':'a'.repeat(64),
    Authorization:'Bearer '+'b'.repeat(43), 'Content-Type':'application/json',
  },body:'{}'});
  assert.equal((await worker.fetch(req, bindings)).status, 200);
  assert.equal(forwarded!.headers.get('X-JoinQueue-Source'), sourceKey(req, bindings));
  assert.notEqual(forwarded!.headers.get('X-JoinQueue-Source'), 'a'.repeat(64));
});

test('one source cannot exhaust ingress of another; counters persist and expire', () => {
  const db = new DatabaseSync(':memory:');
  const driver: SqlDriver = {exec:s=>db.exec(s),prepare:s=>db.prepare(s),transaction:fn=>fn()};
  try {
    for (let i=0;i<60;i++) takeIngress(driver, 100000, 'source-a');
    assert.throws(()=>takeIngress(driver, 100000, 'source-a'));
    takeIngress(driver, 100000, 'source-b');
    takeIngress(driver, 160000, 'source-a');
    assert.equal(db.prepare('SELECT count(*) AS n FROM ingress_sources').get()!.n, 1);
  } finally {db.close();}
});
