const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
function harness(){
 const element=()=>({dataset:{},style:{},children:[],textContent:'',replaceChildren(){this.children=[];},appendChild(child){this.children.push(child);}});
 const sandbox={document:{createElement:element}}; vm.createContext(sandbox);
 vm.runInContext(fs.readFileSync('static/overlay-text.js','utf8'),sandbox);
 return {sandbox,element};
}
const state={is_open:true,total_waiting_count:4,total_waiting_group_count:2,now_view:[{display_name:'Alice'}],next_view:[{display_name:'Bob'}]};
test('empty and trailing lines stay editable while dynamic values refresh',()=>{
 const {sandbox}=harness();
 const text='[受付]\n\n[NOW1]\n\n[NEXT1] [待機人数]\n';
 const lines=sandbox.overlayTextLines(text,state,{});
 assert.equal(lines.length,6); assert.equal(lines[1].length,0); assert.equal(lines[5].length,0);
 assert.equal(lines[2][0].text,'Alice'); assert.equal(lines[4][2].text,'2グループ/4人待機中');
 const changed=sandbox.overlayTextLines(text,{...state,now_view:[{display_name:'Carol'}]},{});
 assert.equal(changed[2][0].text,'Carol'); assert.equal(changed.length,6);
 assert.equal(sandbox.overlayTextLines(text.replace('\n\n','\n'),state,{}).length,5);
});
test('rendered values and typed markup are text, not HTML, and retain font roles',()=>{
 const {sandbox,element}=harness(); const output=element();
 sandbox.renderOverlayText(output,'<img src=x> [NOW1]\n[__proto__]',{...state,now_view:[{display_name:'<script>\nname'}]},{});
 assert.equal(output.children[0].children[0].textContent,'<img src=x> ');
 assert.equal(output.children[0].children[1].textContent,'<script> name');
 assert.equal(output.children[0].children[1].style.fontFamily,'var(--font-now-names)');
 assert.equal(output.children[1].children[0].textContent,'[__proto__]');
});
test('empty template hides every line of content without resetting to a preset',()=>{
 const {sandbox}=harness(); const lines=sandbox.overlayTextLines('',state,{});
 assert.equal(lines.length,0);
});

test('deleting heading lines removes their rendered rows and never adds default headings',()=>{
 const {sandbox,element}=harness(); const output=element();
 sandbox.renderOverlayText(output,'[受付]\n[NOW見出し]\n[NOW1]',state,{});
 assert.equal(output.children.length,3);
 sandbox.renderOverlayText(output,'[NOW1]',state,{});
 assert.equal(output.children.length,1);
 assert.equal(output.children[0].children[0].textContent,'Alice');
 sandbox.renderOverlayText(output,'',state,{});
 assert.equal(output.children.length,0);
});
