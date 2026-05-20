const q=(s)=>document.querySelector(s);
const list=(id,arr,withCount)=>{const el=q(id);el.innerHTML="";arr.forEach(u=>{const li=document.createElement("li");const name=u.display_name??"";if(withCount&&u.participation_count!==undefined){li.textContent=`${name} [参加: ${u.participation_count}回]`;}else{li.textContent=name;}el.appendChild(li);});};
async function refresh(){const s=await fetch('/api/state').then(r=>r.json());q('#open').textContent=`受付状態: ${s.is_open?'受付中':'受付終了'}`;q('#priority').textContent=`低消化回数優先モード: ${s.priority_mode?'ON':'OFF'}`;list('#now',s.now_view,true);list('#next',s.next_view,true);list('#queue',s.queue_view,true);list('#logs',[...s.logs].reverse().map(t=>({display_name:t})),false);}
async function post(api){await fetch(api,{method:'POST'});await refresh();}
document.querySelectorAll('button[data-api]').forEach(b=>b.addEventListener('click',()=>post(b.dataset.api)));
refresh();setInterval(refresh,2000);
