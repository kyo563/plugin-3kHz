const q = (selector) => document.querySelector(selector);
q("#overlay-url").textContent = `${window.location.origin}/overlay`;

let latestState = null;
let draggingParticipant = false;
let contextTarget = null;
let mutationPending = false;
let refreshSequence = 0;

function setConnectionError(message) { q("#conn").textContent = `接続状態: ${message}`; q('#reconnect').hidden = message === '管理APIに接続済み'; }

function formatDisplayName(user, withCount) {
    const name = user.youtube_handle || user.display_name || "";
    const declared = user.declared_player_name || user.youtube_nickname;
    const merged = !user.is_placeholder && declared && declared !== name ? `${name}（${declared}）` : name;
    if (withCount && !user.is_placeholder && user.participation_count !== undefined) {
        return `${merged} [参加: ${user.participation_count}回]`;
    }
    return merged;
}

function participantItem(user, { draggable = false, listType = "", position = null } = {}) {
    const li = document.createElement("li");
    const label = document.createElement('span');
    label.className = 'participant-label'; label.textContent = formatDisplayName(user, false); label.title = label.textContent;
    if (position !== null) {
        const order = document.createElement('span');
        order.className = 'participant-order';
        order.textContent = `${position + 1}${position < 3 ? ' 次' : ''}`;
        order.title = position < 3 ? '次の対戦の参加者（NEXT）' : '待機順';
        li.appendChild(order);
    }
    if (listType === 'waiting' && user.user_id && !user.is_placeholder) {
        const avatar = document.createElement('span');
        avatar.className = 'participant-avatar'; avatar.textContent = '●';
        avatar.setAttribute('aria-hidden', 'true');
        if (user.avatar_url) {
            try {
                const url = new URL(user.avatar_url);
                if (url.protocol === 'https:' && /(^|\.)(ggpht\.com|googleusercontent\.com)$/.test(url.hostname) && !url.username && !url.password && (!url.port || url.port === '443')) {
                    const img = document.createElement('img');
                    img.alt = ''; img.width = 28; img.height = 28;
                    img.loading = 'lazy'; img.decoding = 'async'; img.referrerPolicy = 'no-referrer'; img.draggable = false;
                    img.addEventListener('error', () => { img.hidden = true; });
                    img.src = url.href;
                    avatar.appendChild(img);
                }
            } catch (_) { /* Missing or invalid images keep the placeholder. */ }
        }
        li.appendChild(avatar);
    }
    li.appendChild(label);
    if (user.user_id && !user.is_placeholder && user.participation_count !== undefined) {
        const count = document.createElement('span'); count.className='participant-count';
        count.textContent = `${user.participation_count}回`; count.title='参加回数'; li.appendChild(count);
    }
    li.dataset.userId = user.user_id || "";
    li.dataset.placeholder = user.is_placeholder ? "1" : "0";
    if (draggable && !user.is_placeholder && user.user_id) {
        li.draggable = true;
        li.dataset.listType = listType;
        li.addEventListener("dragstart", (e) => {
            if (mutationPending) { e.preventDefault(); return; }
            draggingParticipant = true;
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData("text/plain", user.user_id);
        });
        li.addEventListener("dragend", () => { draggingParticipant = false; });
        li.addEventListener("dragover", (e) => e.preventDefault());
        li.addEventListener("drop", async (e) => {
            e.preventDefault();
            draggingParticipant = false;
            const dragId = e.dataTransfer.getData("text/plain");
            const dropId = user.user_id;
            if (!dragId || !dropId || dragId === dropId) return;
            const rect = li.getBoundingClientRect();
            await reorderWaitingWithDrag(dragId, dropId, e.clientY >= rect.top + rect.height / 2);
        });
    }

    if (!user.is_placeholder && user.user_id) {
        li.addEventListener("contextmenu", (e) => showContextMenu(e, user));
        const edit = document.createElement('button'); edit.type = 'button'; edit.textContent = '編集'; edit.setAttribute('aria-label','名前を編集'); edit.title='名前を編集';
        edit.addEventListener('click', async event => {
            event.stopPropagation();
            const name = window.prompt('表示用の名前を入力（32文字まで／空欄で元の名前に戻す）', user.declared_player_name || user.youtube_nickname || '');
            if(name !== null) await post('/api/control/update-declared-player-name', {user_id:user.user_id,declared_player_name:name});
        });
        li.appendChild(edit);
        const remove = document.createElement('button');
        remove.type = 'button'; remove.textContent = '削除'; remove.className = 'remove-participant';
        remove.setAttribute('aria-label', `${formatDisplayName(user, false)}を参加者一覧から削除`);
        remove.addEventListener('click', async event => {
            event.stopPropagation();
            if (mutationPending) return;
            if (!window.confirm(`${formatDisplayName(user, false)} を参加者一覧から削除しますか？空いたNOW枠には待機先頭から補充します。参加回数と記録済みの対戦履歴は残ります。`)) return;
            await post('/api/control/remove-user', {user_id:user.user_id});
        });
        li.appendChild(remove);
    }
    return li;
}

function renderList(selector, users, opts = {}) {
    const el = q(selector); const signature = JSON.stringify(users);
    if (el.dataset.signature === signature) return;
    el.dataset.signature = signature; el.innerHTML = "";
    users.forEach((user, index) => el.appendChild(participantItem(user, {...opts, position: opts.listType === "waiting" ? index : null})));
}

function renderLogs(logs) {
    renderList("#logs", [...logs].reverse().map((text) => ({ display_name: text })), { draggable: false });
}

async function fetchState(){ try{ const r=await fetch('/api/state', {signal:AbortSignal.timeout(5000)}); if(!r.ok) throw new Error(`HTTP ${r.status}`); setConnectionError('管理APIに接続済み'); return await r.json(); }catch(e){console.error(e); setConnectionError('状態取得に失敗しました'); return null;}}

function renderState(state){
    latestState = state;
    q("#total-matches").textContent = `総対戦回数：${state.total_match_count ?? 0}回`;
    q('#toggle-reception').textContent = state.is_open ? '受付中止' : '受付を開始';
    q('#toggle-reception').disabled = mutationPending;
    q("#undo").disabled = mutationPending || !state.undo_available;
    renderSearch();
    q('#open').textContent=`受付状態: ${state.is_open ? '受付中':'受付終了'}`;
    q('#priority').className = state.priority_mode ? 'priority-on' : 'priority-off';
    q('#toggle-priority').className = state.priority_mode ? 'priority-on' : 'priority-off';
    q('#toggle-priority').setAttribute('aria-pressed', String(state.priority_mode));
    q('#toggle-priority').textContent = state.priority_mode ? '✓ 初回参加優先モード：ON（クリックでOFF）' : '初回参加優先モード：OFF（クリックでON）';
    q('#priority').textContent=`初回参加優先モード: ${state.priority_mode ? 'ON':'OFF'}`;
    renderList('#now',state.now_view,{ draggable: false });
    q("#waiting-count").textContent = `${state.waiting.length}人`;
    renderList('#waiting',state.waiting,{ draggable: true, listType: "waiting" });
    renderLogs(state.logs);
}

async function refresh(){
    const sequence = ++refreshSequence;
    const s = await fetchState();
    if (s && sequence === refreshSequence && !draggingParticipant) renderState(s);
}
async function poll(){ if(!document.hidden) await refresh(); setTimeout(poll, 2000); }

async function post(api, payload){
    if (mutationPending) return false;
    if (api === '/api/control/reset' && !window.confirm('待機列・参加回数・総対戦回数・対戦履歴・設定を初期状態に戻します。元には戻せません。実行しますか？')) return;
    mutationPending = true;
    ++refreshSequence;
    document.querySelectorAll('button[data-api]').forEach(button => { button.disabled = true; });
    try{
        const options = { method:'POST', signal: AbortSignal.timeout(10000), headers: { "Content-Type": "application/json" } };
        if (payload) options.body = JSON.stringify(payload);
        const r=await fetch(api, options);
        if(!r.ok) {
            const error = await r.json();
            throw new Error(typeof error.detail === 'string' ? error.detail : '入力内容を確認してください');
        }
        q('#operation-message').textContent = '操作を完了しました';
        await refresh();
        return true;
    }catch(e){console.error(e); setConnectionError('操作に失敗しました'); q('#operation-message').textContent = ['TypeError', 'TimeoutError', 'AbortError'].includes(e.name) ? '操作結果を確認できません。再送する前に待機列の現在の状態を確認してください。' : e.message; return false;}
    finally {
        mutationPending = false;
        document.querySelectorAll('button[data-api]').forEach(button => { button.disabled = false; });
        q('#undo').disabled = !latestState?.undo_available;
    }
}

async function reorderWaitingWithDrag(dragId, dropId, after = false) {
    if (!latestState) return;
    const waiting = [...latestState.waiting];
    const from = waiting.findIndex((u) => u.user_id === dragId);
    const to = waiting.findIndex((u) => u.user_id === dropId);
    if (from < 0 || to < 0) return;
    const [moved] = waiting.splice(from, 1);
    const target = waiting.findIndex((u) => u.user_id === dropId);
    if (target < 0) return;
    waiting.splice(target + (after ? 1 : 0), 0, moved);
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
    menu.style.position = 'fixed';
    const rect = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(event.clientX, window.innerWidth - rect.width - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(event.clientY, window.innerHeight - rect.height - 8))}px`;
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
    if (action === "correct-count") {
        countTargetId = userId;
        q('#count-target').textContent = contextTarget.display_name;
        q('#count-value').value = contextTarget.participation_count;
        q('#count-dialog').showModal();
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
q('#reconnect').addEventListener('click', refresh);
window.controlFormatDisplayName = formatDisplayName;
poll();

// Test controls are opt-in; a failed capability request leaves them hidden.
fetch('/api/capabilities')
  .then(response => response.ok ? response.json() : null)
  .then(capabilities => {
    document.querySelector('#development-actions').hidden = capabilities?.development !== true;
  })
  .catch(() => {});


function renderSearch() {
    const list = q('#search-results');
    const term = q('#participant-search').value.trim().toLocaleLowerCase();
    const users = latestState ? [...latestState.current, ...latestState.waiting] : [];
    const matches = term ? users.filter(u => [u.display_name, u.youtube_handle, u.youtube_nickname, u.declared_player_name, u.user_id]
        .some(value => (value || '').toLocaleLowerCase().includes(term))) : [];
    const signature = JSON.stringify([term, matches]);
    if (list.dataset.signature === signature) return;
    list.dataset.signature = signature;
    list.replaceChildren();
    for (const user of matches) {
        const li = document.createElement('li');
        const label = document.createElement('span');
        label.textContent = `${formatDisplayName(user, true)} / ID: ${user.user_id} `;
        li.append(label);
        const button = document.createElement('button');
        button.textContent = '回数補正';
        button.addEventListener('click', () => { contextTarget = user; runContextAction('correct-count'); });
        li.append(button); list.append(li);
    }
    if (term && !matches.length) list.textContent = '一致する参加者はいません';
}
q('#participant-search').addEventListener('input', renderSearch);
q('#add-participant').addEventListener('submit', async event => {
    event.preventDefault();
    const button = event.submitter;
    if (button) button.disabled = true;
    try {
        if (await post('/api/control/add-user', {display_name: q('#add-name').value,
            user_id: q('#add-id').value || null})) {
            q('#add-name').value = ''; q('#add-id').value = ''; q('#add-name').focus();
        }
    } finally { if (button) button.disabled = false; }
});
q('#backup-download').addEventListener('click', async () => {
    try {
        const response = await fetch('/api/control/backup');
        if (!response.ok) throw new Error((await response.json()).detail);
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement('a'); link.href = url;
        link.download = `waiting-list-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
        document.body.append(link); link.click(); link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 10000);
        q('#operation-message').textContent = '保存を開始しました。保存先にJSONがあることを確認してください';
    } catch (error) { q('#operation-message').textContent = `保存できません: ${error.message}`; }
});
q('#backup-restore').addEventListener('click', async () => {
    try {
        const file = q('#backup-file').files[0];
        if (!file) throw new Error('JSONファイルを選択してください');
        if (file.size > 4 * 1024 * 1024 - 1024) throw new Error('ファイルは4 MiB未満にしてください');
        const backup = JSON.parse(await file.text());
        if (backup.format !== 'waiting-list-backup' || backup.version !== 1 ||
            !Array.isArray(backup.state?.current) || !Array.isArray(backup.state?.waiting)) {
            throw new Error('対応するバックアップではありません');
        }
        const current = await fetchState();
        if (!current) throw new Error('現在の状態を取得できません');
        if (!window.confirm(`NOW ${backup.state.current.length}人・待機 ${backup.state.waiting.length}人を復元します。現在の待機列・回数・設定を上書きします。先に現在のバックアップを保存してください。復元は元に戻せません。実行しますか？`)) return;
        await post('/api/control/restore', {backup, expected_revision: current.revision});
    } catch (error) { q('#operation-message').textContent = `復元できません: ${error.message}`; }
});
document.addEventListener('keydown', event => {
    if (document.querySelector('dialog[open]') || mutationPending || !q('#shortcuts-enabled').checked || !document.hasFocus() || event.repeat || event.isComposing ||
        !event.altKey || event.ctrlKey || event.metaKey || event.shiftKey ||
        event.target.closest('input,textarea,select,[contenteditable="true"]')) return;
    const key = event.key.toLowerCase();
    if (!['n', 'z', 'f'].includes(key)) return;
    event.preventDefault();
    if (key === 'f') { q('#participant-search').closest('details').open = true; q('#participant-search').focus(); }
    if (key === 'z' && !q('#undo').disabled) post('/api/control/undo');
    if (key === 'n' && window.confirm('次の対戦へ進めますか？ NOWの参加回数が1増えます。')) post('/api/control/move-next');
});

let countTargetId = null;
q('#count-cancel').addEventListener('click', () => q('#count-dialog').close());
q('#count-form').addEventListener('submit', async event => {
    event.preventDefault();
    const value = q('#count-value').value;
    if (!/^\d+$/.test(value) || Number(value) > 2147483647 || !countTargetId) return;
    const target = countTargetId;
    q('#count-dialog').close();
    await post('/api/control/correct-count', {user_id:target, participation_count:Number(value)});
});
