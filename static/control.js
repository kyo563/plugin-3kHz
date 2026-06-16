const q = (selector) => document.querySelector(selector);

let latestState = null;
let contextTarget = null;

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

function participantItem(user, { draggable = false, listType = "" } = {}) {
    const li = document.createElement("li");
    li.textContent = formatDisplayName(user, true);
    li.dataset.userId = user.user_id || "";
    li.dataset.placeholder = user.is_placeholder ? "1" : "0";
    if (draggable && !user.is_placeholder && user.user_id) {
        li.draggable = true;
        li.dataset.listType = listType;
        li.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/plain", user.user_id));
        li.addEventListener("dragover", (e) => e.preventDefault());
        li.addEventListener("drop", async (e) => {
            e.preventDefault();
            const dragId = e.dataTransfer.getData("text/plain");
            const dropId = user.user_id;
            if (!dragId || !dropId || dragId === dropId) return;
            await reorderWaitingWithDrag(dragId, dropId);
        });
    }

    if (!user.is_placeholder && user.user_id) {
        li.addEventListener("contextmenu", (e) => showContextMenu(e, user));
    }
    return li;
}

function renderList(selector, users, opts = {}) {
    const el = q(selector); el.innerHTML = "";
    users.forEach((user) => el.appendChild(participantItem(user, opts)));
}

function renderLogs(logs) {
    renderList("#logs", [...logs].reverse().map((text) => ({ display_name: text })), { draggable: false });
}

async function fetchState(){ try{ const r=await fetch('/api/state'); if(!r.ok) throw new Error(`HTTP ${r.status}`); setConnectionError('管理APIに接続済み'); return await r.json(); }catch(e){console.error(e); setConnectionError('状態取得に失敗しました'); return null;}}

function renderState(state){
    latestState = state;
    q('#open').textContent=`受付状態: ${state.is_open ? '受付中':'受付終了'}`;
    q('#priority').textContent=`低消化回数優先モード: ${state.priority_mode ? 'ON':'OFF'}`;
    renderList('#now',state.now_view,{ draggable: false });
    renderList('#next',state.next_view,{ draggable: true, listType: "waiting" });
    renderList('#queue',state.queue_view,{ draggable: true, listType: "waiting" });
    renderLogs(state.logs);
}

async function refresh(){ const s=await fetchState(); if(s) renderState(s); }

async function post(api, payload){
    try{
        const options = { method:'POST', headers: { "Content-Type": "application/json" } };
        if (payload) options.body = JSON.stringify(payload);
        const r=await fetch(api, options);
        if(!r.ok) throw new Error(`HTTP ${r.status}`);
        await refresh();
    }catch(e){console.error(e); setConnectionError('操作に失敗しました');}
}

async function reorderWaitingWithDrag(dragId, dropId) {
    if (!latestState) return;
    const waiting = [...latestState.waiting];
    const from = waiting.findIndex((u) => u.user_id === dragId);
    const to = waiting.findIndex((u) => u.user_id === dropId);
    if (from < 0 || to < 0) return;
    const [moved] = waiting.splice(from, 1);
    waiting.splice(to, 0, moved);
    await post('/api/control/reorder-waiting', { ordered_user_ids: waiting.map((u) => u.user_id) });
}

function hideContextMenu() {
    const menu = q("#context-menu");
    menu.style.display = "none";
    contextTarget = null;
}

function showContextMenu(event, user) {
    event.preventDefault();
    const menu = q("#context-menu");
    contextTarget = user;
    menu.style.display = "block";
    menu.style.left = `${event.pageX}px`;
    menu.style.top = `${event.pageY}px`;
}

async function runContextAction(action) {
    if (!contextTarget?.user_id) return;
    const userId = contextTarget.user_id;
    if (action === "move-tail") await post('/api/control/move-to-waiting-tail', { user_id: userId });
    if (action === "remove") await post('/api/control/remove-user', { user_id: userId });
    if (action === "edit-name") {
        const input = window.prompt("申告名を入力してください（空文字で削除）", contextTarget.declared_player_name || "");
        if (input === null) return;
        await post('/api/control/update-declared-player-name', { user_id: userId, declared_player_name: input });
    }
    if (action === "clear-name") await post('/api/control/update-declared-player-name', { user_id: userId, declared_player_name: "" });
    hideContextMenu();
}

document.querySelectorAll('button[data-api]').forEach((b)=>b.addEventListener('click',()=>post(b.dataset.api)));
q("#context-menu").addEventListener("click", (e) => {
    const action = e.target?.dataset?.action;
    if (action) runContextAction(action);
});

document.addEventListener("click", () => hideContextMenu());
window.controlFormatDisplayName = formatDisplayName;
refresh(); setInterval(refresh,2000);
