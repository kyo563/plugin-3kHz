(() => {
    const form = document.getElementById('obs-counter-form');
    const status = document.getElementById('obs-counter-result');
    const save = document.getElementById('obs-counter-save');
    const api = '/api/settings/obs-counters';
    const fields = Array.from(form.querySelectorAll('[data-obs-counter]'), group => ({
        kind: group.dataset.obsCounter,
        token: group.dataset.token,
        input: group.querySelector('input[name]'),
        output: group.querySelector('output'),
        insert: group.querySelector('[data-insert-token]'),
        reset: group.querySelector('[data-reset-wording]'),
    }));

    function preview(field) {
        const {kind, input, token, output} = field;
        const valid = input.value.includes(token) && input.value.length <= input.maxLength;
        input.setCustomValidity(valid ? '' : '80文字以内で ' + token + ' を入れてください。');
        output.textContent = input.value.replaceAll(token, kind === 'round' ? '3' : '8');
    }

    function edited(field) {
        preview(field);
        status.textContent = '未保存です。保存するとOBSに反映されます。';
    }

    function setDisabled(disabled) {
        save.disabled = disabled;
        for (const {input, insert, reset} of fields) input.disabled = insert.disabled = reset.disabled = disabled;
    }

    async function load() {
        try {
            const response = await fetch(api, {signal: AbortSignal.timeout(5000)});
            if (!response.ok) throw new Error();
            const {wording, defaults} = await response.json();
            for (const field of fields) {
                const {kind, input, token, insert, reset} = field;
                input.value = wording[kind];
                preview(field);
                input.addEventListener('input', () => edited(field));
                insert.addEventListener('click', () => {
                    input.setRangeText(token, input.selectionStart, input.selectionEnd, 'end');
                    input.focus();
                    edited(field);
                });
                reset.addEventListener('click', () => {
                    input.value = defaults[kind];
                    edited(field);
                });
            }
            setDisabled(false);
        } catch (_) {
            status.textContent = '文言を読み込めません。接続を確認して設定画面を開き直してください。';
        }
    }

    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (save.disabled) return;
        const wording = Object.fromEntries(fields.map(({kind, input}) => [kind, input.value]));
        setDisabled(true);
        try {
            const response = await fetch(api, {method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(wording), signal: AbortSignal.timeout(5000)});
            if (!response.ok) throw new Error();
            const saved = await response.json();
            for (const field of fields) {
                field.input.value = saved[field.kind];
                preview(field);
            }
            status.textContent = '保存しました。OBSに反映されます。';
        } catch (_) {
            status.textContent = '保存を確認できません。入力内容と接続を確認してください。';
        } finally {
            setDisabled(false);
        }
    });

    void load();
})();
