(() => {
 const form=document.querySelector('#command-settings-form'), join=document.querySelector('#join-commands'), cancel=document.querySelector('#cancel-commands'), save=document.querySelector('#save-commands'), result=document.querySelector('#commands-result');
 const busy=value=>{join.disabled=cancel.disabled=save.disabled=value;};
 const show=data=>{join.value=data.join.join('\n');cancel.value=data.cancel.join('\n');};
 async function load(){
  try{const r=await fetch('/api/settings/commands',{signal:AbortSignal.timeout(5000)});if(!r.ok)throw new Error();show(await r.json());busy(false);}
  catch(_){result.textContent='文言を読み込めませんでした。画面を開き直してください。';}
 }
 form.addEventListener('submit',async event=>{
  event.preventDefault();busy(true);
  const lines=value=>value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
  try{
   const r=await fetch('/api/settings/commands',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({join:lines(join.value),cancel:lines(cancel.value)}),signal:AbortSignal.timeout(10000)});
   if(!r.ok){result.textContent=r.status===422?'各1〜20個・1〜64文字で入力してください。参加と辞退で同じ文言や互いを含む文言、『』は登録できません。':'保存できませんでした。再試行してください。';return;}
   show(await r.json());result.textContent='保存しました。次のコメントから反映され、次回起動時も有効です。';
  }catch(_){result.textContent='保存結果を確認できませんでした。再試行してください。';}
  finally{busy(false);}
 });
 load();
})();
