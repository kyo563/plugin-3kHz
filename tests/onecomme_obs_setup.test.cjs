const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function setup() {
    const html = fs.readFileSync('static/onecomme-obs-setup.html', 'utf8');
    const href = html.match(/id="obs-drag-source"[^>]*href="([^"]+)"/)[1].replaceAll('&amp;', '&');
    const elements = new Map();
    for (const id of ['obs-drag-source', 'obs-drag-result', 'download-template', 'copy-control']) {
        elements.set(id, {href, listeners: {}, textContent: '', blurred: false,
            addEventListener(type, listener) { this.listeners[type] = listener; },
            blur() { this.blurred = true; }});
    }
    vm.runInNewContext(fs.readFileSync('static/onecomme-obs-setup.js', 'utf8'), {
        document: {getElementById: id => elements.get(id)},
        location: {href: 'http://127.0.0.1:18765/obs-setup#key=PRIVATE-ADMIN-KEY'}
    });
    return elements;
}

test('OBS drag sends the named 1200x600 read-only URL with no management key', () => {
    const elements = setup();
    const data = new Map([['text/html', 'private-existing-drag-data']]);
    const transfer = {clearData() { data.clear(); }, setData(type, value) { data.set(type, value); }};
    elements.get('obs-drag-source').listeners.dragstart({dataTransfer: transfer});
    assert.deepEqual([...data.keys()], ['text/uri-list', 'text/plain']);
    assert.equal(data.get('text/plain'), data.get('text/uri-list'));
    const url = new URL(data.get('text/uri-list'));
    assert.equal(url.origin, 'http://127.0.0.1:18765');
    assert.equal(url.pathname, '/onecomme-overlay');
    assert.deepEqual([...url.searchParams], [['layer-name', '待機列表示'], ['layer-width', '1200'], ['layer-height', '600']]);
    assert.equal(url.hash, '');
    assert.ok(!url.href.includes('PRIVATE-ADMIN-KEY'));
    assert.equal(transfer.effectAllowed, 'copy');
});

test('click explains the drag operation without navigating or claiming success', () => {
    const elements = setup();
    let prevented = false;
    const source = elements.get('obs-drag-source');
    source.listeners.click({preventDefault() { prevented = true; }});
    assert.equal(prevented, true);
    assert.ok(elements.get('obs-drag-result').textContent.includes('OBSのプレビュー画面'));
    source.listeners.dragend();
    assert.equal(source.blurred, true);
});
