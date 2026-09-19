(() => {
    const tools = document.getElementById('description-tools');
    const input = document.getElementById('description-text');
    const save = document.getElementById('description-save');
    const copy = document.getElementById('description-copy');
    const reload = document.getElementById('description-reload');
    const result = document.getElementById('description-result');
    let loaded = false, busy = false;
    function controls() {
        input.disabled = busy || !loaded;
        save.disabled = busy || !loaded;
        copy.disabled = busy || !loaded;
        reload.disabled = busy;
    }
    async function load() {
        if (busy) return;
        busy = true; controls();
        try {
            const response = await fetch('/api/settings/description', {signal:AbortSignal.timeout(5000)});
            if (!response.ok) throw new Error();
            input.value = (await response.json()).text;
            loaded = true;
            result.textContent = '保存済みの文章です。編集後は「文章を保存」を押してください。';
        } catch (_) { result.textContent = '読み込めません。保存済みの文章を再読み込みしてください。'; }
        finally { busy = false; controls(); }
    }
    tools.addEventListener('toggle', () => { if (tools.open && !loaded) load(); });
    if (tools.open) load();
    reload.onclick = load;
    input.addEventListener('input', () => { result.textContent = '未保存の変更があります。「文章を保存」を押してください。'; });
    save.onclick = async () => {
        if (busy || !loaded) return;
        const text = input.value;
        busy = true; controls();
        try {
            const response = await fetch('/api/settings/description', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text}),signal:AbortSignal.timeout(5000)});
            if (!response.ok) throw new Error();
            result.textContent = '文章を保存しました。次回もこの内容を使えます。';
        } catch (_) { result.textContent = '保存を確認できません。入力内容をコピーして保管し、接続を確認してください。'; }
        finally { busy = false; controls(); }
    };
    copy.onclick = async () => {
        try {
            await navigator.clipboard.writeText(input.value);
            result.textContent = 'コピーしました。配信の概要欄に貼り付けてください（コピーだけでは保存されません）。';
        } catch (_) {
            input.focus(); input.select();
            result.textContent = '文章を選択しました。Ctrl+Cでコピーしてください。';
        }
    };
})();
