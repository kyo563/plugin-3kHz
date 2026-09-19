(() => {
 const q=s=>document.querySelector(s), panel=q('#history-panel'), select=q('#history-session'), summary=q('#history-summary'), copy=q('#history-copy');
 let sessions=[], cumulative={}, text='', busy=false;
 function render() {
  const session=sessions.find(s=>s.id===select.value);
  q('#history-list').replaceChildren();
  copy.disabled=!session || !session.users.length;
  if(!session){summary.textContent='まだ対戦履歴はありません。';text='';return;}
  summary.textContent=`ユニーク参加者 ${session.users.length}人 ／ ${session.matches}対戦`;
  const lines=session.users.map((u,i)=>`${i+1}. ${u.display_name}（この配信${u.count}回／累計${cumulative[u.user_id] ?? u.count}回）`);
  session.users.forEach((u,i)=>{const li=document.createElement('li');li.textContent=lines[i];q('#history-list').appendChild(li);});
  text=[session.label,summary.textContent,...lines].join('\n');
 }
 async function load(latest=false){
  try{
   const r=await fetch('/api/control/history',{signal:AbortSignal.timeout(5000)});if(!r.ok)throw new Error();
   const selected=select.value;const data=await r.json();sessions=data.sessions;cumulative=data.cumulative_counts || {};select.replaceChildren();
   [...sessions].reverse().forEach(s=>select.add(new Option(`${s.label} / ${new Date(s.started_at).toLocaleString()}`,s.id)));
   if(!latest && sessions.some(s=>s.id===selected))select.value=selected;
   render();
  }catch(_){summary.textContent='履歴を取得できません。一覧を更新してください。';copy.disabled=true;}
 }
 select.onchange=render;
 q('#history-refresh').onclick=()=>load();
 panel.addEventListener('toggle',()=>{if(panel.open)load();});
 copy.onclick=async()=>{try{await navigator.clipboard.writeText(text);summary.textContent='一覧をコピーしました。';}catch(_){summary.textContent='コピーできません。一覧を選択してCtrl+Cでコピーしてください。';}};
 q('#history-start').onclick=async()=>{
  if(busy || !confirm('ここから新しい配信の履歴として記録します。以前の履歴・待機列・累計回数は残ります。開始しますか？'))return;
  busy=true;q('#history-start').disabled=true;
  try{
   const r=await fetch('/api/control/history/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label:q('#history-label').value}),signal:AbortSignal.timeout(10000)});
   if(!r.ok){const e=await r.json();throw new Error(typeof e.detail==='string'?e.detail:'開始できませんでした');}
   await load(true);
  }catch(e){summary.textContent=e.message;}
  finally{busy=false;q('#history-start').disabled=false;}
 };
})();
