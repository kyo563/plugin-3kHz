'use strict';
(() => {
    const status = document.getElementById('status');
    const generate = document.getElementById('generate');
    const hash = document.getElementById('hash');
    const key = document.getElementById('key');
    const copyHash = document.getElementById('copy-hash');
    const copyKey = document.getElementById('copy-key');
    let used = false;
    const local = location.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(location.hostname);
    if (!local || !window.isSecureContext || !window.crypto?.subtle) {
        generate.disabled = true;
        status.textContent = 'このツールは安全なローカルPCのURLからのみ利用できます。';
        return;
    }
    generate.addEventListener('click', async () => {
        if (used) return;
        used = true;
        generate.disabled = true;
        try {
            const bytes = crypto.getRandomValues(new Uint8Array(32));
            const value = btoa(String.fromCharCode(...bytes)).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
            const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
            hash.value = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
            key.value = value;
            copyHash.disabled = copyKey.disabled = false;
            status.textContent = '作成しました。まずハッシュをCloudflareの指定したSecret欄へ登録してください。';
        } catch {
            status.textContent = '作成できませんでした。値は送信・保存していません。ページを開き直してください。';
        }
    });
    for (const [button, field, text] of [[copyHash, hash, 'ハッシュ'], [copyKey, key, '設定キー']]) {
        button.addEventListener('click', async () => {
            if (button.disabled || !field.value) return;
            try {
                await navigator.clipboard.writeText(field.value);
                status.textContent = text + 'をコピーしました。指定した欄にだけ貼り付けてください。';
            } catch {
                status.textContent = 'コピーできませんでした。ブラウザーのクリップボード許可を確認してください。';
            }
        });
    }
})();
