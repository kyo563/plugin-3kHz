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
    show_participation_number:false, auto_fit_font:true, text_bold:true, text_shadow:true, background_color:'#000000', background_transparency:100, fonts:{all:'default'}};
  let stored = {...defaults, show_participation_number:true};
  const elements = {}, fields = {}, calls = [], previews = [];
  const element = () => ({events:{}, style:{setProperty(k,v){this[k]=v;}}, disabled:false, value:'', checked:false,
    options:[], replaceChildren(){this.options=[];}, add(option){this.options.push(option);},
    addEventListener(name, fn) {this.events[name] = fn;}, focus(){}, close(){}, showModal(){}});
  for (const [key, value] of Object.entries(defaults)) {
    if (key === 'fonts' || (['show_participation_number','text_bold','text_shadow'].includes(key) && !onecomme)) continue;
    fields[key] = {...element(), value:String(value), type:['show_participation_number','auto_fit_font','text_bold','text_shadow'].includes(key) ? 'checkbox' : 'text'};
  }
  const get = id => elements[id] ||= element();
  const fontKeys = ['all','ui_body','ui_heading','ui_controls','status','now_heading','next_heading','queue_heading','now_names','next_names','summary'];
  if (onecomme) fontKeys.push('obs_all');
  for (const key of fontKeys) fields['font_'+key] = {...element(), name:'font_'+key};
  if (onecomme) elements['obs-font-select'] = fields.font_obs_all;
  const form = get('overlay-layout-form');
  form.elements = {namedItem:key=>fields[key] || null};
  form.querySelectorAll = () => fontKeys.map(key=>fields['font_'+key]);
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
  const context = {document:{body:{dataset:{onecomme:String(onecomme)}}, getElementById:id=>!onecomme && ['obs-font-select','obs-font-search'].includes(id) ? null : get(id)},
    Option:class {constructor(text,value){this.textContent=text;this.value=value;}},
    window:{addEventListener(){}, AppFonts:{apply(){},family:id=>id,systemName:()=>null}}, location:{origin:'http://127.0.0.1'},
    localStorage:{setItem(){}}, AbortSignal, FormData,
    fetch:async (path, options = {}) => {
      if (path === '/api/fonts') return {ok:true, json:async()=>[]};
      if (path === '/api/fonts/system') return {ok:true, json:async()=>[{id:'system:417269616c',name:'Arial',japanese:false}]};
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

test('OBS font picker searches without selection loss and clears only OBS overrides on change', async () => {
  const {fields, get, form, calls, previews} = await settingsHarness();
  fields.font_ui_body.value = 'mincho';
  fields.font_now_names.value = 'gothic';
  fields.font_obs_all.value = 'system:417269616c';
  get('obs-font-search').value = 'no match';
  get('obs-font-search').events.input();
  assert.equal(fields.font_obs_all.value, 'system:417269616c');
  assert.equal(fields.font_obs_all.options.find(o=>o.value==='system:417269616c').hidden, false);
  fields.font_obs_all.events.change();
  assert.equal(fields.font_now_names.value, '');
  assert.equal(fields.font_ui_body.value, 'mincho');
  assert.equal(previews.at(-1).fonts.obs_all, 'system:417269616c');
  await form.events.submit({preventDefault(){}});
  assert.equal(calls.at(-1).fonts.obs_all, 'system:417269616c');
  assert.equal(calls.at(-1).fonts.ui_body, 'mincho');
  await get('reload-overlay-layout').onclick();
  assert.equal(fields.font_obs_all.value, 'system:417269616c');
  await get('confirm-reset-settings').onclick();
  assert.equal(fields.font_obs_all.value, '');
});

test('standalone settings still load and save without the new checkbox', async () => {
  const {form, get, calls} = await settingsHarness(false);
  assert.equal(get('save-overlay-layout').disabled, false);
  await form.events.submit({preventDefault(){}});
  assert.equal(Object.hasOwn(calls.at(-1), 'show_participation_number'), false);
  assert.equal(Object.hasOwn(calls.at(-1), 'text_bold'), false);
  assert.equal(Object.hasOwn(calls.at(-1), 'text_shadow'), false);
});

test('text effects preview and persist independently, reload and reset to ON', async () => {
  const {form, fields, get, calls, previews} = await settingsHarness();
  assert.equal(fields.text_bold.checked, true);
  assert.equal(fields.text_shadow.checked, true);
  for (const bold of [false, true]) for (const shadow of [false, true]) {
    fields.text_bold.checked = bold;
    fields.text_shadow.checked = shadow;
    form.events.input();
    assert.equal(previews.at(-1).text_bold, bold);
    assert.equal(previews.at(-1).text_shadow, shadow);
    assert.equal(get('obs-font-sample').style['--sample-weight'], bold ? '700' : '400');
    assert.equal(get('obs-font-sample').style['--sample-shadow'], shadow ? '0 1px 3px #000' : 'none');
    await form.events.submit({preventDefault(){}});
    assert.equal(calls.at(-1).text_bold, bold);
    assert.equal(calls.at(-1).text_shadow, shadow);
    fields.text_bold.checked = !bold;
    fields.text_shadow.checked = !shadow;
    await get('reload-overlay-layout').onclick();
    assert.equal(fields.text_bold.checked, bold);
    assert.equal(fields.text_shadow.checked, shadow);
  }
  fields.text_bold.checked = fields.text_shadow.checked = false;
  await form.events.submit({preventDefault(){}});
  await get('confirm-reset-settings').onclick();
  assert.equal(fields.text_bold.checked, true);
  assert.equal(fields.text_shadow.checked, true);
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
