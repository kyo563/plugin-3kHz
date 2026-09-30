const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('sample preview shows session ordinals for every name mode, never for placeholders', () => {
  const context = {URLSearchParams, AbortSignal, location:{search:''}, window:{},
    fetch:async()=>({status:304}), setTimeout(){}, console};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('static/overlay.js', 'utf8'), context);
  for (const name_mode of ['youtube', 'declared', 'youtube_declared', 'declared_youtube']) {
    const plain = context.sampleState({name_mode});
    const numbered = context.sampleState({name_mode, show_participation_number:true});
    assert.equal(numbered.now_view[0].display_name, plain.now_view[0].display_name + ' *2回目');
    assert.equal(numbered.next_view[0].display_name, plain.next_view[0].display_name + ' *1回目');
    assert.equal(numbered.now_view[2].display_name, '参加者募集中');
    assert.equal(context.sampleState({show_participation_number:false}).now_view[0].display_name.includes('回目'), false);
  }
});

async function settingsHarness(onecomme = true) {
  const defaults = {width:480, height:600, font_size:28, layout:'vertical', name_mode:'youtube',
    show_participation_number:false, auto_fit_font:true, background_color:'#000000', background_transparency:100, fonts:{all:'default'}};
  let stored = {...defaults, show_participation_number:true};
  const elements = {}, fields = {}, calls = [], previews = [];
  const element = () => ({events:{}, style:{}, disabled:false, value:'', checked:false,
    addEventListener(name, fn) {this.events[name] = fn;}, focus(){}, close(){}, showModal(){}});
  for (const [key, value] of Object.entries(defaults)) {
    if (key === 'fonts' || (key === 'show_participation_number' && !onecomme)) continue;
    fields[key] = {...element(), value:String(value), type:['show_participation_number','auto_fit_font'].includes(key) ? 'checkbox' : 'text'};
  }
  const get = id => elements[id] ||= element();
  const form = get('overlay-layout-form');
  form.elements = {namedItem:key=>fields[key] || null};
  form.querySelectorAll = () => [];
  form.checkValidity = () => true;
  get('layout-preview-shell').parentElement = {clientWidth:840};
  get('layout-preview').contentWindow = {postMessage(message) {previews.push(message.appearance);}};
  class FormData {
    *[Symbol.iterator]() {
      for (const [key, field] of Object.entries(fields)) {
        if (field.type !== 'checkbox') yield [key, field.value];
        else if (field.checked) yield [key, 'on'];
      }
    }
  }
  const context = {document:{body:{dataset:{onecomme:String(onecomme)}}, getElementById:get},
    window:{addEventListener(){}, AppFonts:{apply(){}}}, location:{origin:'http://127.0.0.1'},
    localStorage:{setItem(){}}, AbortSignal, FormData,
    fetch:async (path, options = {}) => {
      if (path === '/api/fonts') return {ok:true, json:async()=>[]};
      if (options.body) {const body = JSON.parse(options.body); calls.push(body); stored = {...defaults, ...body};}
      return {ok:true, json:async()=>stored};
    }};
  vm.runInNewContext(fs.readFileSync('static/overlay-settings.js', 'utf8'), context);
  await new Promise(resolve=>setImmediate(resolve));
  return {fields, get, form, calls, previews};
}

test('ordinal checkbox restores, previews, saves booleans both ways and resets', async () => {
  const {fields, get, form, calls, previews} = await settingsHarness();
  const checkbox = fields.show_participation_number;
  assert.equal(checkbox.checked, true);
  assert.equal(previews.at(-1).show_participation_number, true);
  checkbox.checked = false;
  form.events.input();
  assert.equal(previews.at(-1).show_participation_number, false);
  await form.events.submit({preventDefault(){}});
  assert.equal(calls.at(-1).show_participation_number, false);
  checkbox.checked = true;
  await get('reload-overlay-layout').onclick();
  assert.equal(checkbox.checked, false);
  checkbox.checked = true;
  await form.events.submit({preventDefault(){}});
  assert.equal(calls.at(-1).show_participation_number, true);
  await get('confirm-reset-settings').onclick();
  assert.equal(checkbox.checked, false);
  assert.equal(previews.at(-1).show_participation_number, false);
});

test('standalone settings still load and save without the new checkbox', async () => {
  const {form, get, calls} = await settingsHarness(false);
  assert.equal(get('save-overlay-layout').disabled, false);
  await form.events.submit({preventDefault(){}});
  assert.equal(Object.hasOwn(calls.at(-1), 'show_participation_number'), false);
});

test('background and font settings preview, save typed values, reload and reset', async () => {
  const {form, fields, get, calls, previews} = await settingsHarness();
  assert.equal(fields.auto_fit_font.checked, true);
  fields.background_color.value = '#123456';
  fields.background_transparency.value = '35';
  fields.font_size.value = '56';
  fields.auto_fit_font.checked = false;
  form.events.input();
  assert.equal(previews.at(-1).background_transparency, 35);
  assert.equal(previews.at(-1).auto_fit_font, false);
  await form.events.submit({preventDefault(){}});
  assert.equal(calls.at(-1).background_color, '#123456');
  assert.equal(calls.at(-1).font_size, 56);
  assert.equal(calls.at(-1).auto_fit_font, false);
  fields.auto_fit_font.checked = true;
  fields.background_transparency.value = '100';
  await get('reload-overlay-layout').onclick();
  assert.equal(fields.auto_fit_font.checked, false);
  assert.equal(Number(fields.background_transparency.value), 35);
  await get('confirm-reset-settings').onclick();
  assert.equal(fields.auto_fit_font.checked, true);
  assert.equal(Number(fields.background_transparency.value), 100);
  assert.equal(Number(fields.font_size.value), 28);
});
