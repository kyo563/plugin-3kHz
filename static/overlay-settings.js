(() => {
    const form = document.getElementById('overlay-layout-form');
    const frame = document.getElementById('layout-preview');
    const shell = document.getElementById('layout-preview-shell');
    const message = document.getElementById('layout-result');
    const save = document.getElementById('save-overlay-layout');
    const resetButton = document.getElementById('reset-settings');
    const resetDialog = document.getElementById('reset-settings-dialog');
    const resetMessage = document.getElementById('reset-settings-result');
    const reloadButton = document.getElementById('reload-overlay-layout');
    const confirmReset = document.getElementById('confirm-reset-settings');
    let resetting = false;
    let loaded = false;
    const fontFields = [...form.querySelectorAll('select[name^="font_"]')];
    const fontMessage = document.getElementById('font-import-result');
    let library = [];
    function populateFonts(selected = {}) {
        const choices = [['default','標準'],['gothic','游ゴシック'],['mincho','游明朝'],['meiryo','メイリオ'],['sans','標準ゴシック'],['serif','標準明朝'],...library.map(f=>[f.id,f.name])];
        for(const select of fontFields) {
            const key = select.name.slice(5), value = selected[key] ?? (key === 'all' ? 'default' : '');
            select.replaceChildren();
            const options = key === 'all' ? choices : [['','一括設定に従う'],...choices];
            for(const [id,label] of options) select.add(new Option(label,id));
            if(value && !choices.some(([id])=>id===value)) select.add(new Option('未登録フォント（標準で表示・同じファイルを再登録）',value));
            select.value = value;
        }
    }
    function fontValues() {
        return Object.fromEntries(fontFields.map(select=>[select.name.slice(5), select.value || null]));
    }
    populateFonts();
    window.addEventListener('app-font-error',()=>{fontMessage.textContent='一部のフォントを読み込めません。標準で表示しています。ファイルを再登録してください。';});
    function values() {
        const settings = Object.fromEntries(new FormData(form));
        for (const key of ['width','height','font_size']) settings[key] = Number(settings[key]);
        for (const select of fontFields) delete settings[select.name];
        settings.fonts = fontValues();
        return settings;
    }
    function preview() {
        if (!loaded || !form.checkValidity()) return;
        const settings = values();
        document.getElementById('apply-layout-size').disabled = false;
        document.getElementById('vertical-editor').hidden = settings.layout !== 'vertical';
        document.getElementById('horizontal-editor').hidden = settings.layout !== 'horizontal';
        const scale = Math.min(1, (shell.parentElement.clientWidth - 24) / settings.width, 600 / settings.height);
        shell.style.height = `${settings.height * scale}px`;
        shell.style.width = `${settings.width * scale}px`;
        frame.style.width = `${settings.width}px`; frame.style.height = `${settings.height}px`;
        frame.style.transform = `scale(${scale})`;
        frame.contentWindow.postMessage({type:'overlay-preview', appearance:settings}, location.origin);
        document.getElementById('obs-dimensions').textContent = `OBSブラウザソース：幅 ${settings.width} / 高さ ${settings.height}`;
    }
    async function load() {
        save.disabled = true; resetButton.disabled = true;
        try {
            const r = await fetch('/api/settings/overlay', {signal:AbortSignal.timeout(5000)});
            if (!r.ok) throw new Error();
            const settings = await r.json();
            if (settings.layout === 'custom') { settings.layout = 'vertical'; settings.vertical_text = settings.custom_text; }
            try { const fonts = await fetch('/api/fonts', {signal:AbortSignal.timeout(5000)}); if(fonts.ok) library = await fonts.json(); } catch (_) {}
            populateFonts(settings.fonts);
            for (const [key,value] of Object.entries(settings)) if(key !== 'fonts' && key !== 'name_mode') form.elements.namedItem(key).value = value;
            let nameMode = settings.name_mode;
            if(!nameMode) { const r = await fetch('/api/state',{signal:AbortSignal.timeout(5000)}); if(!r.ok) throw new Error(); nameMode = (await r.json()).show_declared_player_name_on_overlay ? 'youtube_declared' : 'youtube'; }
            form.elements.namedItem('name_mode').value = nameMode;
            loaded = true; preview(); message.textContent = '保存済みの設定を表示しています。';
        } catch (_) { message.textContent = '読み込めません。「保存済み設定を読み込む」で再試行してください。'; }
        finally { save.disabled = !loaded; resetButton.disabled = !loaded || resetting; }
    }
    document.getElementById('apply-layout-size').addEventListener('click', () => {
        if (!loaded) return;
        const horizontal = form.elements.namedItem('layout').value === 'horizontal';
        form.elements.namedItem('width').value = horizontal ? 1200 : 480;
        form.elements.namedItem('height').value = horizontal ? 240 : 600;
        preview();
        message.textContent = '推奨サイズを入力しました（未保存）。保存後、OBSブラウザソースの幅・高さも合わせてください。';
    });
    document.getElementById('overlay-layout').addEventListener('change', () => {
        preview();
    });
    form.addEventListener('input', () => { preview(); message.textContent = 'プレビュー中（未保存）。「保存してOBSに反映」で保存します。'; });
    frame.addEventListener('load', preview);
    window.addEventListener('resize', preview);
    document.getElementById('reload-overlay-layout').onclick = load;
    form.addEventListener('submit', async event => {
        event.preventDefault(); if (!loaded) return;
        save.disabled = true; resetButton.disabled = true;
        const submitted = values();
        try {
            const r = await fetch('/api/settings/overlay', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(submitted),signal:AbortSignal.timeout(5000)});
            if(!r.ok) throw new Error();
            window.AppFonts.apply(submitted.fonts);
            localStorage.setItem('app-font-settings', String(Date.now()));
            message.textContent = '保存しました。管理画面とOBS表示に反映されます。';
        } catch (_) { message.textContent = '保存を確認できません。入力値と接続を確認してください。'; }
        finally { save.disabled = false; resetButton.disabled = !loaded; }
    });
    resetButton.onclick = () => { resetDialog.showModal(); document.getElementById('cancel-reset-settings').focus(); };
    document.getElementById('cancel-reset-settings').onclick = () => resetDialog.close();
    resetDialog.addEventListener('cancel', event => { if (resetting) event.preventDefault(); });
    confirmReset.onclick = async () => {
        if (resetting) return;
        resetting = true;
        confirmReset.disabled = true;
        document.getElementById('cancel-reset-settings').disabled = true;
        save.disabled = true; resetButton.disabled = true; reloadButton.disabled = true;
        try {
            // Omitted fields use the server schema defaults, including future settings.
            const r = await fetch('/api/settings/overlay', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name_mode:'youtube'}), signal:AbortSignal.timeout(5000)});
            if (!r.ok) throw new Error();
            const settings = await r.json();
            if (settings.layout === 'custom') { settings.layout = 'vertical'; settings.vertical_text = settings.custom_text; }
            populateFonts(settings.fonts);
            for (const [key, value] of Object.entries(settings)) if (key !== 'fonts') form.elements.namedItem(key).value = value;
            loaded = true; preview();
            message.textContent = '初期設定を保存しました。';
            window.AppFonts.apply(settings.fonts);
            localStorage.setItem('app-font-settings', String(Date.now()));
            resetMessage.textContent = '設定を初期値に戻して保存しました。';
        } catch (_) { resetMessage.textContent = 'リセットの完了を確認できません。接続を確認し、保存済み設定を読み込んでください。'; }
        finally {
            resetting = false; confirmReset.disabled = false;
            document.getElementById('cancel-reset-settings').disabled = false;
            save.disabled = !loaded; resetButton.disabled = !loaded; reloadButton.disabled = false;
            resetDialog.close(); resetButton.focus();
        }
    };
    document.getElementById('reset-font-overrides').onclick = () => {
        for(const select of fontFields) if(select.name !== 'font_all') select.value = '';
        preview(); message.textContent = '個別指定を解除しました。保存すると反映されます。';
    };
    document.getElementById('font-file').addEventListener('change', async event => {
        const input = event.target, file = input.files[0]; if(!file) return;
        input.disabled = true;
        try {
            if(file.size > 32*1024*1024) throw new Error('フォントは32 MiBまでです。');
            fontMessage.textContent = 'フォントを確認しています…';
            const bytes = await file.arrayBuffer();
            // Browser validates the font before storing it. No OS installation occurs.
            await new FontFace('validation_font',bytes).load();
            const r = await fetch('/api/fonts',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Font-Name':encodeURIComponent(file.name)},body:bytes,signal:AbortSignal.timeout(15000)});
            if(!r.ok) { const error=await r.json(); throw new Error(error.detail || '保存できませんでした。'); }
            const added = await r.json();
            if(!library.some(f=>f.id===added.id)) library.push(added);
            populateFonts(fontValues());
            preview();
            fontMessage.textContent = `「${added.name}」を追加しました。選択欄で指定して保存してください。`;
        } catch(error) { fontMessage.textContent = `追加できませんでした：${error.message}`; }
        finally { input.disabled=false; input.value=''; }
    });
    load();
})();
