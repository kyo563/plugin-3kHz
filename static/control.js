const q = (selector) => document.querySelector(selector);

function setConnectionError(message) { q("#conn").textContent = `接続状態: ${message}`; }

function formatDisplayName(user, withCount) {
    const name = user.display_name ?? "";
    const declared = user.declared_player_name;
    const merged = (!user.is_placeholder && declared) ? `${name}（${declared}）` : name;
    if (withCount && !user.is_placeholder && user.participation_count !== undefined) {
        return `${merged} [参加: ${user.participation_count}回]`;
    }
    return merged;
}

function renderList(selector, users, withCount) {
    const el = q(selector); el.innerHTML = "";
    users.forEach((user) => { const li = document.createElement("li"); li.textContent = formatDisplayName(user, withCount); el.appendChild(li); });
}

async function fetchState(){ try{ const r=await fetch('/api/state'); if(!r.ok) throw new Error(`HTTP ${r.status}`); setConnectionError('Mock Provider connected'); return await r.json(); }catch(e){console.error(e); setConnectionError('状態取得に失敗しました'); return null;}}
function renderState(state){ q('#open').textContent=`受付状態: ${state.is_open ? '受付中':'受付終了'}`; q('#priority').textContent=`低消化回数優先モード: ${state.priority_mode ? 'ON':'OFF'}`; renderList('#now',state.now_view,true); renderList('#next',state.next_view,true); renderList('#queue',state.queue_view,true); renderList('#logs',[...state.logs].reverse().map((text)=>({display_name:text})),false); }
async function refresh(){ const s=await fetchState(); if(s) renderState(s); }
async function post(api){ try{const r=await fetch(api,{method:'POST'}); if(!r.ok) throw new Error(`HTTP ${r.status}`); await refresh();}catch(e){console.error(e); setConnectionError('操作に失敗しました');}}
document.querySelectorAll('button[data-api]').forEach((b)=>b.addEventListener('click',()=>post(b.dataset.api)));
window.controlFormatDisplayName = formatDisplayName;
refresh(); setInterval(refresh,2000);
