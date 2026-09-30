const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function harness() {
  const element = () => ({style:{setProperty(k,v){this[k]=v;}}, dataset:{}, children:[], replaceChildren(...children){this.children=children;}});
  const panel = element(), output = element();
  const context = {URLSearchParams, AbortSignal, location:{search:''}, console, setTimeout(){},
    fetch:async()=>({status:304}), window:{AppFonts:{apply(){}}}, renderOverlayText(){},
    document:{querySelector:s=>s === '.panel' ? panel : output, createElement:element}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('static/overlay.js','utf8'),context);
  return {context, panel};
}

test('background transparency affects paint only, across layouts and alpha endpoints', () => {
  const {context, panel} = harness();
  for (const layout of ['vertical','horizontal','custom']) {
    for (const [transparency,alpha] of [[0,1],[35,.65],[100,0]]) {
      context.renderOverlay({appearance:{layout,background_color:'#123456',background_transparency:transparency,font_size:56,auto_fit_font:false}});
      assert.equal(panel.style['--background-color'], `rgba(18, 52, 86, ${alpha})`);
      assert.equal(panel.style['--font-size'], '56px');
      assert.equal(panel.dataset.fontFit, 'fixed');
      assert.equal(panel.style.opacity, undefined);
    }
  }
});

test('legacy settings and invalid preview colors safely fall back to transparency', () => {
  const {context, panel} = harness();
  for (const appearance of [{}, {background_color:'red;opacity:0',background_transparency:'50'}]) {
    context.renderOverlay({appearance});
    assert.equal(panel.style['--background-color'],'rgba(0, 0, 0, 0)');
    assert.equal(panel.dataset.fontFit,'auto');
  }
});
