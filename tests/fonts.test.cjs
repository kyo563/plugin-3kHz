const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const id = name => 'system:' + Buffer.from(name).toString('hex');
function harness(overlay) {
    const styles = {}, fonts = new Set();
    const context = {TextDecoder, Uint8Array, console, AbortSignal,
        FontFace:class {constructor(name,source){this.name=name;this.source=source;} load(){return Promise.resolve(this);}},
        window:{addEventListener(){},dispatchEvent(){}}, fetch:async()=>({ok:false}),
        document:{body:{classList:{contains:()=>overlay}},fonts,
            documentElement:{style:{setProperty:(k,v)=>styles[k]=v}}}};
    vm.createContext(context);
    vm.runInContext(fs.readFileSync('static/fonts.js','utf8'),context);
    return {api:context.window.AppFonts, styles, fonts};
}
test('OBS baseline applies only to OBS; specific overrides and legacy all still win correctly', () => {
    const obs=harness(true), ui=harness(false);
    const settings={all:'meiryo',obs_all:'mincho',now_names:'gothic',ui_heading:'serif'};
    obs.api.apply(settings); ui.api.apply(settings);
    assert.equal(obs.styles['--font-status'],obs.api.builtins.mincho);
    assert.equal(obs.styles['--font-now-names'],obs.api.builtins.gothic);
    assert.equal(ui.styles['--font-ui-body'],ui.api.builtins.meiryo);
    assert.equal(ui.styles['--font-ui-heading'],ui.api.builtins.serif);
    obs.api.apply({all:'meiryo'});
    assert.equal(obs.styles['--font-status'],obs.api.builtins.meiryo);
});
test('system font names are strictly decoded and CSS escaped without network or files', () => {
    const h=harness(true);
    for(const name of ['游ゴシック','Arial','a";background:url(https://example.org);\\']) {
        assert.equal(h.api.systemName(id(name)),name);
        const css=h.api.family(id(name));
        assert.ok(css.startsWith('"\\'));
        assert.ok(!css.includes('url('));
        assert.ok(css.endsWith(h.api.builtins.default));
    }
    for(const invalid of ['system:ff','system:00','system:abc',id(' '),id('a\n'),id('x'.repeat(129))]) {
        assert.equal(h.api.systemName(invalid),null);
        assert.equal(h.api.family(invalid),h.api.builtins.default);
    }
    assert.equal(h.fonts.size,0);
});
test('uploaded font loading continues working with OBS-wide selection', () => {
    const h=harness(true), key='a'.repeat(64);
    h.api.apply({obs_all:key});
    assert.equal(h.fonts.size,1);
    assert.match(h.styles['--font-summary'],/appfont_/);
    h.api.apply({obs_all:id('Arial')});
    assert.equal(h.fonts.size,0);
});
