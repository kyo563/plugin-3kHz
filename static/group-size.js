(() => {
    const form = document.querySelector('#group-size-form');
    const size = document.querySelector('#group-size');
    const save = document.querySelector('#group-size-save');
    const result = document.querySelector('#group-size-result');
    const url = '/api/settings/group-size';

    async function request(options = {}) {
        const response = await fetch(url, { ...options, signal: AbortSignal.timeout(5000) });
        if (!response.ok) throw new Error();
        return response.json();
    }

    request().then(data => {
        size.value = String(data.group_size);
        size.disabled = save.disabled = false;
    }).catch(() => { result.textContent = '参加人数を読み込めません。ページを再読み込みしてください。'; });

    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (save.disabled) return;
        size.disabled = save.disabled = true;
        result.textContent = '';
        try {
            const data = await request({
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ group_size: Number(size.value) }),
            });
            size.value = String(data.group_size);
            result.textContent = `参加人数を${data.group_size}名に変更しました。`;
        } catch (_) {
            result.textContent = '参加人数の保存を確認できません。再読み込みして現在の設定を確認してください。';
        } finally {
            size.disabled = save.disabled = false;
        }
    });
})();
