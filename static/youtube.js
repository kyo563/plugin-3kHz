(() => {
    const form = document.getElementById('youtube-form');
    const connect = document.getElementById('youtube-connect');
    const stop = document.getElementById('youtube-stop');
    const status = document.getElementById('youtube-status');
    const key = document.getElementById('youtube-key');
    let busy = false;
    async function showStatus() {
        try {
            const response = await fetch('/api/youtube/status', {signal:AbortSignal.timeout(5000)});
            if (!response.ok) throw new Error();
            const state = await response.json();
            status.textContent = `${state.message} ／ コメント受信 ${state.received}件・参加/辞退コマンド ${state.commands}件`;
            status.style.color = state.status === 'connected' ? '#86efac' : state.status === 'error' ? '#fca5a5' : '';
            const active = ['connecting', 'connected', 'retrying'].includes(state.status);
            connect.disabled = busy || active;
            stop.disabled = busy || !active;
        } catch (_) { status.textContent = '受信状態を確認できません。アプリとの接続を確認してください。'; }
    }
    async function action(path, body) {
        if (busy) return;
        busy = true; connect.disabled = true; stop.disabled = true;
        try {
            const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body), signal:AbortSignal.timeout(20000)});
            if (!response.ok) throw new Error('配信URLとAPIキーの形式、アプリとの接続を確認してください。');
            key.value = '';
        } catch (error) { status.textContent = error.message; return; }
        finally { busy = false; connect.disabled = false; stop.disabled = false; }
        await showStatus();
    }
    form.addEventListener('submit', event => {
        event.preventDefault();
        action('/api/youtube/connect', {url:document.getElementById('youtube-url').value.trim(), api_key:key.value.trim()});
    });
    stop.addEventListener('click', () => action('/api/youtube/disconnect', {}));
    async function refresh() {
        if (!busy) await showStatus();
        setTimeout(refresh, 3000);
    }
    refresh();
})();
