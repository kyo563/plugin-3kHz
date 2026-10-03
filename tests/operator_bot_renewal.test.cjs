'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const {createHash} = require('node:crypto');
const code = fs.readFileSync(path.join(__dirname, '../scripts/operator-bot-renewal/bootstrap.js'), 'utf8');
function harness(hostname = '127.0.0.1') {
    const elements = Object.fromEntries(['status','generate','hash','key','copy-hash','copy-key'].map(id => [id, {
        disabled: id.startsWith('copy-'), value:'', textContent:'', handlers:{},
        addEventListener(type, handler) {this.handlers[type] = handler;}
    }]));
    const copied = [];
    const crypto = {getRandomValues(bytes) {bytes.fill(7); return bytes;},
        subtle:{async digest(kind, bytes) {assert.equal(kind,'SHA-256'); return createHash('sha256').update(bytes).digest();}}};
    vm.runInNewContext(code, {document:{getElementById:id=>elements[id]}, location:{protocol:'http:',hostname},
        window:{isSecureContext:true,crypto},crypto,Uint8Array,TextEncoder,btoa:value=>Buffer.from(value,'binary').toString('base64'),
        navigator:{clipboard:{async writeText(value) {copied.push(value);}}}});
    return {elements,copied};
}
test('operator key is generated once in memory and only copied by explicit clicks', async () => {
    const {elements,copied} = harness();
    await elements.generate.handlers.click();
    const expected = Buffer.alloc(32,7).toString('base64url');
    assert.equal(elements.key.value, expected);
    assert.equal(elements.hash.value,createHash('sha256').update(expected).digest('hex'));
    assert.equal(elements.generate.disabled,true);
    assert.deepEqual(copied,[]);
    await elements.generate.handlers.click();
    assert.equal(elements.key.value,expected);
    await elements['copy-hash'].handlers.click();
    await elements['copy-key'].handlers.click();
    assert.deepEqual(copied,[elements.hash.value,expected]);
});
test('operator helper refuses non-loopback hosting', () => {
    const {elements} = harness('example.com');
    assert.equal(elements.generate.disabled,true);
    assert.equal(elements.generate.handlers.click,undefined);
    assert.equal(elements.key.value,'');
});
test('operator helper has no network or persisted credentials and masks the raw key', () => {
    assert.doesNotMatch(code,/\b(?:fetch|XMLHttpRequest|localStorage|sessionStorage|console|indexedDB)\b/);
    const html = fs.readFileSync(path.join(__dirname,'../scripts/operator-bot-renewal/index.html'),'utf8');
    assert.match(html,/connect-src 'none'/);
    assert.match(html,/id="key" type="password" readonly/);
    assert.match(html,/name|BOT_AUTH_SETUP_HASH/);
    assert.doesNotMatch(html,/\?(?:key|setup)=/);
});
