const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
test('settings tabs retain form state, use accessible controls, and restore URL selection', () => {
  const elements = {};
  for (const name of ['general', 'bot']) for (const part of ['tab', 'panel']) {
    elements[`settings-${name}-${part}`] = {events:{}, attributes:{}, hidden:false,
      setAttribute(k,v) { this.attributes[k]=v; }, addEventListener(k,v) {this.events[k]=v;}, focus() {this.focused=true;}};
  }
  const location = {href:'http://localhost/settings?tab=bot', search:'?tab=bot'};
  let popstate;
  const context = {document:{getElementById:id=>elements[id]}, location, URL, URLSearchParams, Event,
    history:{pushState(_,__,url) { location.href = 'http://localhost' + url; location.search = new URL(location.href).search; }},
    window:{addEventListener(_,fn) {popstate=fn;}, dispatchEvent(){}}};
  vm.runInNewContext(fs.readFileSync('static/settings-tabs.js','utf8'), context);
  const bot=elements['settings-bot-tab'], general=elements['settings-general-tab'];
  const panel=elements['settings-bot-panel'];
  assert.equal(bot.attributes['aria-selected'],'true');
  panel.unsavedInput='retained';
  general.events.click();
  assert.equal(panel.hidden,true);
  assert.equal(location.search,'');
  general.events.keydown({key:'ArrowRight', preventDefault(){}});
  assert.equal(bot.focused,true);
  assert.equal(panel.hidden,false);
  assert.equal(panel.unsavedInput,'retained');
  assert.equal(general.tabIndex,-1);
  location.search='?tab=unknown'; popstate();
  assert.equal(general.attributes['aria-selected'],'true');
});
