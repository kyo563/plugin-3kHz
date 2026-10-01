(() => {
    const select = document.getElementById('onecomme-stream');
    const button = document.getElementById('onecomme-select');
    const status = document.getElementById('onecomme-status');
    let signature = '', busy = false;
    async function refresh() {
        try {
            const response = await fetch('/api/onecomme/status', {signal: AbortSignal.timeout(5000)});
            if (!response.ok) throw new Error();
            const s = await response.json();
            const next = JSON.stringify(s.frames);
            if (select && signature !== next) {
                const chosen = select.value || s.selected;
                select.replaceChildren(new Option('受信を停止', ''));
                s.frames.forEach(frame => select.add(new Option(frame.name, frame.id)));
                select.value = chosen;
                signature = next;
            }
            status.textContent = `${s.connected ? (s.selected ? 'わんコメ連携中' : '配信を選択してください') : 'わんコメからの接続待ち'} ／ コマンド ${s.commands}件`;
            if (s.dropped) status.textContent += ` ／ ${s.dropped}件を処理できませんでした。参加者一覧をご確認ください`;
            const reasons = {unselected:'選択した配信以外のコメントです',history:'選択前の履歴、または時刻が合わないコメントです',invalid_timestamp:'コメントの時刻形式を確認できません',ignored:'参加・辞退キーワード以外のコメントです',bot_handled:'Botへの呼びかけとして処理しました',processed:'コメントを判定しました。受付中止・連続操作制限・NOW参加中などは管理画面の操作ログで確認できます'};
            reasons.accepted = 'コメントを判定しました。反映されない場合は受付状態・連続操作制限・NOW参加中かを管理画面の操作ログで確認してください';
            const diagnostic = document.getElementById('onecomme-diagnostic');
            if (diagnostic) diagnostic.textContent = `受信 ${s.received}件 ／ ${reasons[s.last_result] || s.last_result || 'まだコメントを受信していません'}${s.dropped ? '。形式不一致や転送失敗の可能性があります。' : ''}`;
            if (button) button.disabled = busy || !s.connected;
        } catch (_) { status.textContent = 'わんコメ側でプラグインが有効か確認してください'; }
    }
    button?.addEventListener('click', async () => {
        if (busy) return;
        busy = true; button.disabled = true;
        try {
            const r = await fetch('/api/onecomme/select', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({frame_id: select.value}), signal: AbortSignal.timeout(5000)});
            if (!r.ok) throw new Error();
        } catch (_) { status.textContent = '配信を選択できませんでした。わんコメでコメントを受信してから再度お試しください'; }
        finally { busy = false; }
        await refresh();
    });
    async function tick() { if (!busy) await refresh(); setTimeout(tick, 2000); }
    tick();
})();
