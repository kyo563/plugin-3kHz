document.getElementById('download-template').addEventListener('click', async () => {
    const result = document.getElementById('template-result');
    try {
        const r = await fetch('/api/onecomme/template', {signal:AbortSignal.timeout(5000)});
        if (!r.ok) throw new Error();
        const url = URL.createObjectURL(await r.blob());
        const link = document.createElement('a'); link.href = url; link.download = 'Taikiretsu-Template.zip';
        document.body.append(link); link.click(); link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
        result.textContent = '保存したZIPを、わんコメのテンプレート一覧へ追加してください。';
    } catch (_) { result.textContent = '保存できませんでした。プラグインとの接続を確認してください。'; }
});
document.getElementById('copy-control').addEventListener('click', async () => {
    const result = document.getElementById('connection-result');
    try {
        const r = await fetch('/api/connection', {signal:AbortSignal.timeout(5000)});
        if (!r.ok) throw new Error();
        await navigator.clipboard.writeText((await r.json()).control_url);
        result.textContent = 'コピーしました。';
    } catch (_) { result.textContent = 'コピーできませんでした。Edgeで開いて再度お試しください。'; }
});
