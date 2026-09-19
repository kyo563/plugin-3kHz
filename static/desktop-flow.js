(() => {
    const el = id => document.getElementById(id);
    const welcome = el('welcome-dialog'), exitDialog = el('exit-dialog');
    let desktop = false;
    window.showExitDialog = () => {
        if (!desktop) return false;
        if (typeof mutationPending !== 'undefined' && mutationPending) {
            el('operation-message').textContent = '操作の完了を待ってから終了してください。';
            return true;
        }
        if (!exitDialog.open) exitDialog.showModal();
        return true;
    };
    el('exit-app').onclick = window.showExitDialog;
    el('exit-cancel').onclick = () => exitDialog.close();
    el('exit-confirm').onclick = async () => {
        el('exit-confirm').disabled = true;
        try {
            const response = await fetch('/api/desktop/exit', {method:'POST', signal:AbortSignal.timeout(10000)});
            if (!response.ok) throw new Error();
            el('exit-message').textContent = '終了しています…';
        } catch (_) {
            el('exit-message').textContent = '終了を確認できません。ウィンドウが開いている場合は再度お試しください。';
            el('exit-confirm').disabled = false;
        }
    };
    async function finishWelcome() {
        el('welcome-done').disabled = el('welcome-later').disabled = true;
        try {
            const response = await fetch('/api/desktop/onboarding-complete', {method:'POST', signal:AbortSignal.timeout(5000)});
            if (!response.ok) throw new Error();
            welcome.close();
        } catch (_) { el('welcome-message').textContent = '設定を保存できません。「始める」を押して再試行してください。'; }
        finally { el('welcome-done').disabled = el('welcome-later').disabled = false; }
    }
    el('welcome-done').onclick = el('welcome-later').onclick = finishWelcome;
    welcome.addEventListener('cancel', event => { event.preventDefault(); finishWelcome(); });
    el('welcome-copy').onclick = async () => {
        try {
            await navigator.clipboard.writeText(`${location.origin}/overlay`);
            el('welcome-message').textContent = 'URLをコピーしました。OBSへ貼り付けてください。';
        } catch (_) { el('welcome-message').textContent = `コピーできません。OBSに ${location.origin}/overlay を入力してください。`; }
    };
    async function initialize() {
        try {
            const response = await fetch('/api/desktop-settings', {signal:AbortSignal.timeout(5000)});
            if (!response.ok) return;
            const settings = await response.json();
            desktop = settings.available;
            el('exit-app').hidden = !desktop;
            if (desktop && !settings.onboarding_completed && !document.querySelector('dialog[open]')) welcome.showModal();
        } catch (_) { /* Regular controls remain available; next startup retries setup. */ }
    }
    async function checkDisplay() {
        if (!document.hidden) {
            try {
                const response = await fetch('/api/obs-status', {signal:AbortSignal.timeout(5000)});
                if (!response.ok) throw new Error();
                const status = await response.json();
                el('display-connection').textContent = status.last_access_seconds !== null && status.last_access_seconds < 10
                    ? '表示ページ: 接続あり' : '表示ページ: 最近の接続なし';
                el('display-connection').title = 'OBSでの実際の見え方はOBSのプレビューで確認してください。';
            } catch (_) { el('display-connection').textContent = '表示ページ: 接続確認できません'; }
        }
        setTimeout(checkDisplay, 5000);
    }
    initialize(); checkDisplay();
})();
