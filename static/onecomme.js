(() => {
    const select = document.getElementById('onecomme-stream');
    const button = document.getElementById('onecomme-select');
    const status = document.getElementById('onecomme-status');
    let signature = '', busy = false, edited = false;
    let pending = null, connected = false, choices = new Map();
    const stop = document.getElementById('onecomme-stop');
    const transition = document.getElementById('onecomme-transition');
    const newSession = document.getElementById('onecomme-new-session');
    const carrySession = document.getElementById('onecomme-carry-session');
    const urlInput = document.getElementById('onecomme-url');
    const urlButton = document.getElementById('onecomme-url-select');
    let urlEdited = false;
    const selectable = choice => !!choice && (choice.service_id || choice.id) && choice.enabled !== false && choice.state !== 'ended';
    function updateChoice() {
        const choice = choices.get(select?.value);
        const hint = document.getElementById('onecomme-choice-hint');
        if (button) button.disabled = busy || !connected || !selectable(choice);
        if (stop) stop.disabled = busy || !connected;
        if (urlButton) urlButton.disabled = busy || !urlInput?.value.trim();
        if (urlInput) urlInput.disabled = busy;
        if (hint) hint.textContent = !connected ? 'わんコメからの接続を待っています。' : !choices.size ? 'わんコメで配信に接続すると、ここに表示されます。' : !choice ? '連携する配信を選んでください。' : choice.enabled === false ? 'この配信は、先にわんコメ側で接続してください。' : choice.state === 'ended' ? 'この配信は終了しています。別の配信を選んでください。' : !choice.id ? 'この接続枠と連携できます。コメントを受信すると対象配信へ自動で紐付きます。' : `選択中：${choice.name}`;
    }
    select?.addEventListener('change', () => { edited = true; updateChoice(); });
    urlInput?.addEventListener('input', () => { urlEdited = true; updateChoice(); });
    async function refresh() {
        try {
            const response = await fetch('/api/onecomme/status', {signal: AbortSignal.timeout(5000)});
            if (!response.ok) throw new Error();
            const s = await response.json();
            pending = s.pending;
            connected = s.connected;
            if (urlInput && !urlEdited) urlInput.value = s.manual_url || '';
            const urlStatus = document.getElementById('onecomme-url-status');
            if (urlStatus) urlStatus.textContent = s.manual_url ? `保存したURL：${s.manual_url} ／ ${s.ready_to_receive ? 'わんコメの接続枠と連携中' : 'わんコメの受信対象を確認中'}` : '';
            const rows = s.services || [];
            const next = JSON.stringify([rows,s.frames,s.selected,s.pinned_service,s.selection_mode]);
            choices = new Map(rows.length ? rows.map(f=>['service:'+f.service_id,f]) : (s.frames || []).map(f=>['video:'+f.id,f]));
            if (select && signature !== next) {
                const active = rows.find(f=>s.url_service_id ? f.service_id === s.url_service_id : s.selection_mode === 'auto' ? f.service_id === s.pinned_service : (f.queue_id || f.id) === s.selected);
                const chosen = edited ? select.value : active ? 'service:'+active.service_id : s.selected ? 'video:'+s.selected : '';
                select.replaceChildren(new Option('配信を選択してください', ''));
                for (const [key,f] of choices) {
                    const label = f.service_name && f.service_name !== f.name ? `${f.name} ／ ${f.service_name}` : f.name;
                    const state = f.enabled === false ? '未接続' : {live:'配信中',upcoming:'開始前',ended:'終了'}[f.state];
                    select.add(new Option(`${label}${state ? `（${state}）` : ''}`, key));
                }
                select.value = choices.has(chosen) ? chosen : '';
                signature = next;
            }
            const remembered = document.getElementById('onecomme-remembered');
            const savedRow = rows.find(f=>f.service_id === s.pinned_service);
            if (remembered) remembered.textContent = s.manual_url ? 'URL指定で連携します。別の配信へは自動で切り替えません。' : s.pinned_service ? `保存した接続先：${savedRow?.service_name || savedRow?.name || '現在見つかりません（別の接続先へは切り替えません）'}` : '接続先が決まると自動で保存します。';
            if (transition) {
                transition.hidden = !pending;
                if (pending) {
                    document.getElementById('onecomme-transition-summary').textContent = `次の対象：${pending.name} ／ 前の配信にNOW ${pending.current_count}人・待機 ${pending.waiting_count}人が残っています。`;
                    newSession.textContent = pending.saved ? '保存済みの状態に戻る' : '待機列を空にして新しく開始';
                    carrySession.hidden = pending.saved;
                    newSession.disabled = carrySession.disabled = busy || !s.connected;
                }
            }
            status.textContent = `${s.connected ? (s.selected || s.ready_to_receive ? 'わんコメ連携中' : s.selection_mode === 'auto' ? 'わんコメ連携中（新着コメント待ち）' : 'わんコメの受信対象を確認中') : 'わんコメからの接続待ち'} ／ コマンド ${s.commands}件`;
            if (pending) status.textContent = '配信切り替えの確認待ち ／ 設定画面で前回の待機者の扱いを選んでください';
            const target = document.getElementById('onecomme-target');
            if (target) {
                const selected = s.services?.find(frame => (frame.queue_id || frame.id) === s.selected);
                const state = {live:'配信中',upcoming:'開始前',ended:'終了',unknown:'開始状態未確認'}[selected?.state];
                const reason = {waiting:'わんコメで対象のYouTube配信に接続してください。',resolving:'わんコメの接続枠と連動中です。コメントを受信すると配信に自動で紐付きます。',multiple:'複数の配信があり対象を特定できません。「別の配信に連携し直す」から選んでください。',stopped:'連携を停止しています。「別の配信に連携し直す」から再開できます。'};
                reason.missing = '保存した接続先が見つかりません。「別の配信に連携し直す」から選び直してください。';
                reason.confirm = '次の配信への切り替えを確認してください。';
                reason.url_waiting = 'URLを保存しました。わんコメで同じ配信に接続してください。配信情報がない場合は受信中の接続枠を選び、このURLで連携してください。';
                reason.url_mismatch = '保存したURLとわんコメの接続先が変わったため、連携を停止しました。URLと接続枠を確認してください。';
                target.textContent = s.selected ? `対象：${s.selected_name || s.selected}${state ? ` ／ ${state}` : ''}（${s.selection_mode === 'auto' ? '自動' : '手動'}）${s.connected ? '' : ' ※わんコメ未接続'}` : s.ready_to_receive ? `対象：${s.selected_name} ／ わんコメと連動中（コメント待ち）` : reason[s.selection_reason] || reason.waiting;
            }
            if (s.dropped) status.textContent += ` ／ ${s.dropped}件を処理できませんでした。参加者一覧をご確認ください`;
            const reasons = {unselected:'選択した配信以外のコメントです',history:'選択前の履歴、または時刻が合わないコメントです',invalid_timestamp:'コメントの時刻形式を確認できません',ignored:'参加・辞退キーワード以外のコメントです',bot_handled:'Botへの呼びかけとして処理しました',processed:'コメントを判定しました。受付中止・連続操作制限・NOW参加中などは管理画面の操作ログで確認できます'};
            reasons.accepted = 'コメントを判定しました。反映されない場合は受付状態・連続操作制限・NOW参加中かを管理画面の操作ログで確認してください';
            const diagnostic = document.getElementById('onecomme-diagnostic');
            if (diagnostic) diagnostic.textContent = `受信 ${s.received}件 ／ ${reasons[s.last_result] || s.last_result || 'まだコメントを受信していません'}${s.dropped ? '。形式不一致や転送失敗の可能性があります。' : ''}`;
            updateChoice();
        } catch (_) { connected = false; updateChoice(); status.textContent = 'わんコメ側でプラグインが有効か確認してください'; }
    }
    button?.addEventListener('click', async () => {
        const choice = choices.get(select.value);
        if (busy || !connected || !selectable(choice)) return;
        await action(choice.service_id ? '/api/onecomme/remember' : '/api/onecomme/select', choice.service_id ? {service_id:choice.service_id} : {frame_id:choice.id,mode:'manual'});
    });
    urlButton?.addEventListener('click', async () => {
        if (busy || !urlInput?.value.trim()) return;
        const choice = choices.get(select?.value);
        // Match resolved URLs on the server; honor an explicit source choice
        // for duplicates or unresolved rows. Never guess from a display name.
        await action('/api/onecomme/select-url', {url:urlInput.value.trim(),
            ...(choice?.service_id && (edited || !choice.id) && selectable(choice) ? {service_id:choice.service_id} : {})});
    });
    async function action(path, body) {
        if (busy) return;
        busy = true;
        updateChoice();
        const result = document.getElementById('onecomme-action-result');
        try {
            const r = await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(5000)});
            if (!r.ok) { const data = await r.json(); throw new Error(typeof data.detail === 'string' ? data.detail : '変更できませんでした。'); }
            edited = false; signature = '';
            urlEdited = false;
            if (result) result.textContent = '保存しました。';
        } catch (e) { if (result) result.textContent = e.message; }
        finally { busy = false; await refresh(); }
    }
    stop?.addEventListener('click',()=>action('/api/onecomme/select',{frame_id:'',mode:'manual'}));
    newSession?.addEventListener('click',()=>pending && action('/api/onecomme/transition',{video_id:pending.video_id,revision:pending.revision,carry:false}));
    carrySession?.addEventListener('click',()=>pending && action('/api/onecomme/transition',{video_id:pending.video_id,revision:pending.revision,carry:true}));
    async function tick() { if (!busy) await refresh(); setTimeout(tick, 2000); }
    tick();
})();
