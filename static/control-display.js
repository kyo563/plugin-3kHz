(() => {
    const defaults = {avatar:true, username:true, alias:true, memo:true, count:true, order:true};
    const controls = [...document.querySelectorAll('[data-display]')];
    const status = document.querySelector('#control-display-status');
    const retry = document.querySelector('#control-display-retry');
    let saved = {...defaults};
    const view = window.controlListDisplay = {values:{...defaults}};

    function validate(data) {
        if (!data || Object.keys(defaults).some(key => typeof data[key] !== 'boolean')) throw new Error('Invalid settings');
        return Object.fromEntries(Object.keys(defaults).map(key => [key, data[key]]));
    }
    function apply(values) {
        view.values = {...values};
        for (const input of controls) input.checked = values[input.dataset.display];
        window.refreshControlDisplay?.();
    }
    function disable(value) { for (const input of controls) input.disabled = value; }
    async function request(options) {
        const response = await fetch('/api/settings/control-display', {...options, signal:AbortSignal.timeout(5000)});
        if (!response.ok) throw new Error('Settings unavailable');
        return validate(await response.json());
    }
    async function load() {
        disable(true); retry.hidden = true;
        status.textContent = '表示項目を読み込み中…';
        try {
            saved = await request(); apply(saved); disable(false);
            status.textContent = '変更は自動保存されます。OBS表示には影響しません。';
        } catch (_) {
            status.textContent = '表示設定を読み込めません。接続を確認して再読み込みしてください。';
            retry.hidden = false;
        }
    }
    for (const input of controls) input.addEventListener('change', async () => {
        const proposed = {...saved, [input.dataset.display]:input.checked};
        disable(true); apply(proposed); status.textContent = '保存中…';
        try {
            saved = await request({method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(proposed)});
            apply(saved); disable(false); status.textContent = '表示項目を保存しました。';
        } catch (_) {
            apply(saved);
            status.textContent = '保存結果を確認できません。再読み込みして確認してください。';
            retry.hidden = false;
        }
    });
    retry.addEventListener('click', load);
    load();
})();
