(() => {
    let busy = false, attempts = 0;
    async function open() {
        if (busy) return;
        busy = true;
        try {
            const r = await fetch('/api/plugins/jp.kyo563.sankagata-seiretsu', {cache: 'no-store', signal: AbortSignal.timeout(5000)});
            if (!r.ok) throw new Error();
            const data = await r.json();
            const result = data.response;
            if (result?.ready && /^http:\/\/127\.0\.0\.1:18765\/control#key=[A-Za-z0-9_-]{40,128}$/.test(result.control)) {
                location.replace(result.control); return;
            }
            document.getElementById('status').textContent = result?.message || 'プラグインを有効にしてください';
        } catch (_) { document.getElementById('status').textContent = 'わんコメへの接続を確認してください'; }
        finally { busy = false; }
        if (++attempts < 15) setTimeout(open, 2000);
    }
    document.getElementById('retry').addEventListener('click', () => { attempts = 0; open(); });
    open();
})();
