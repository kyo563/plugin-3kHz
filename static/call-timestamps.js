(() => {
    const panel = document.querySelector('#history-panel');
    const video = document.querySelector('#call-timestamps-video');
    const copy = document.querySelector('#call-timestamps-copy');
    const save = document.querySelector('#call-timestamps-save');
    const result = document.querySelector('#call-timestamps-result');
    const output = document.querySelector('#call-timestamps-text');
    let sequence = 0;

    async function load(selected = video.value) {
        const version = ++sequence;
        const query = selected ? '?video_id=' + encodeURIComponent(selected) : '';
        copy.disabled = save.disabled = true;
        output.value = '';
        try {
            const response = await fetch('/api/control/call-timestamps' + query, { signal: AbortSignal.timeout(5000) });
            if (!response.ok) throw new Error();
            const data = await response.json();
            if (version !== sequence) return;
            video.replaceChildren(...data.videos.map(item => {
                const date = item.recorded_at ? new Date(item.recorded_at).toLocaleString() + ' / ' : '';
                return new Option(date + item.video_id, item.video_id);
            }));
            video.value = data.video_id;
            output.value = data.text;
            copy.disabled = save.disabled = !data.text;
            result.textContent = data.text ? '' : 'この配信に記録された次局通知はありません。';
        } catch (_) {
            if (version === sequence) result.textContent = 'タイムスタンプを読み込めません。「一覧を更新」を押してください。';
        }
    }

    panel.addEventListener('toggle', () => { if (panel.open) void load(); });
    document.querySelector('#history-refresh').addEventListener('click', () => void load());
    video.addEventListener('change', () => void load());
    copy.addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(output.value);
            result.textContent = '対局タイムスタンプをコピーしました。';
        } catch (_) {
            output.select();
            result.textContent = '選択したテキストをコピーしてください。';
        }
    });
    save.addEventListener('click', () => {
        const url = URL.createObjectURL(new Blob([output.value], { type: 'text/plain;charset=utf-8' }));
        const link = document.createElement('a');
        link.href = url;
        link.download = `対局タイムスタンプ-${video.value}.txt`;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
})();
