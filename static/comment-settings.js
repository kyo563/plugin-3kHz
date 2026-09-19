(() => {
 const form=document.querySelector('#comment-settings-form'), input=document.querySelector('#cooldown-seconds'), save=document.querySelector('#save-comment-settings'), reload=document.querySelector('#reload-comment-settings'), message=document.querySelector('#comment-settings-result');
 let loaded=false,busy=false;
 function controls(){input.disabled=busy||!loaded;save.disabled=busy||!loaded;reload.disabled=busy;}
 async function load(){
  if(busy)return;busy=true;controls();
  try{const r=await fetch('/api/settings/comments',{signal:AbortSignal.timeout(5000)});if(!r.ok)throw new Error();input.value=(await r.json()).cooldown_seconds;loaded=true;message.textContent='保存済みの制限時間です。';}
  catch(_){message.textContent='読み込めません。保存済みの時間を読み込んでください。';}
  finally{busy=false;controls();}
 }
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(busy||!loaded||!form.reportValidity())return;
  const seconds=Number(input.value);busy=true;controls();
  try{const r=await fetch('/api/settings/comments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cooldown_seconds:seconds}),signal:AbortSignal.timeout(10000)});if(!r.ok)throw new Error();message.textContent=seconds===0?'保存しました。連続操作の制限は無効です。':`${seconds}秒に保存しました。次回もこの時間を使います。`;}
  catch(_){message.textContent='保存を確認できません。保存済みの時間を読み込んで確認してください。';}
  finally{busy=false;controls();}
 });
 input.addEventListener('input',()=>{message.textContent='未保存です。「制限時間を保存」を押してください。';});
 reload.onclick=load;load();
})();
