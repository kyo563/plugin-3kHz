const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
test('template retries startup and accepts only its own worker ready message', () => {
    const display = {contentWindow: {}, style: {}, src: ''};
    let receive, tick, cleared = false;
    const context = {document: {getElementById: () => display}, window: {addEventListener: (_, fn) => receive = fn},
        setInterval: fn => {tick = fn; return 1;}, clearInterval: () => cleared = true};
    vm.runInNewContext(fs.readFileSync('static/onecomme-template/script.js', 'utf8'), context);
    assert.equal(display.style.visibility, 'hidden');
    tick(); assert.equal(display.src, 'http://127.0.0.1:18765/onecomme-overlay');
    const data = {type: 'waiting-list-display-ready'};
    receive({origin: 'https://evil.example', source: display.contentWindow, data}); tick(); assert.equal(cleared, false);
    receive({origin: 'http://127.0.0.1:18765', source: {}, data}); tick(); assert.equal(cleared, false);
    receive({origin: 'http://127.0.0.1:18765', source: display.contentWindow, data}); tick();
    assert.equal(cleared, true); assert.equal(display.style.visibility, 'visible');
});
