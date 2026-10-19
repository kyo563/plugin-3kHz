(() => {
    const get = id => document.getElementById(id);
    const dialog = get('session-reset-dialog'), resetStatus = get('session-reset-status'), downloadStatus = get('diagnostic-tools-status');
    let pending = false, revision = null;
    get('session-count-reset').addEventListener('click', async () => {
        if (pending || mutationPending) return;
        pending = true;
        try {
            const state = await fetchState();
            if (!state) throw new Error('状態を確認できません。接続を確認してください。');
            revision = state.revision;
            dialog.showModal();
        } catch (error) { resetStatus.textContent = error.message; }
        finally { pending = false; }
    });
    get('session-reset-cancel').addEventListener('click', () => dialog.close());
    get('session-reset-confirm').addEventListener('click', async () => {
        if (pending || mutationPending || revision === null) return;
        pending = true;
        get('session-reset-confirm').disabled = true;
        try {
            if (await post('/api/control/reset-session-counts', {confirmed:true,expected_revision:revision})) {
                dialog.close(); revision = null;
                resetStatus.textContent = '今回の参加回数を0にしました。累計参加回数と待機列はそのままです。';
            } else { dialog.close(); resetStatus.textContent = 'リセットを確認できませんでした。管理画面の操作結果を確認してください。'; }
        } finally { pending = false; get('session-reset-confirm').disabled = false; }
    });
    get('diagnostic-log-download').addEventListener('click', async () => {
        if (pending) return;
        pending = true; get('diagnostic-log-download').disabled = true;
        try {
            const response = await fetch('/api/control/diagnostic-log', {signal:AbortSignal.timeout(10000)});
            if (!response.ok) throw new Error('ログを取得できません。接続を確認してください。');
            const blob = await response.blob(), url = URL.createObjectURL(blob);
            const link = document.createElement('a'); link.href = url;
            link.download = 'JoinQueue-operation-log.txt';
            document.body.append(link); link.click(); link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 10000);
            downloadStatus.textContent = 'ログの保存を開始しました。保存したテキストを確認してください。';
        } catch (error) { downloadStatus.textContent = error.message; }
        finally { pending = false; get('diagnostic-log-download').disabled = false; }
    });
})();
