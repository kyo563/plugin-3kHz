(() => {
    const kind = location.pathname.split('/').pop();
    const panel = document.getElementById('obs-counter');
    const output = document.getElementById('obs-counter-text');
    let lastAppearance;

    function fitText() {
        output.style.fontSize = '';
        if (panel.hidden || panel.dataset.fontFit === 'fixed') return;
        let size = parseFloat(getComputedStyle(output).fontSize);
        const bottom = panel.getBoundingClientRect().bottom - parseFloat(getComputedStyle(panel).paddingBottom);
        while (size > 12 && output.getBoundingClientRect().bottom > bottom) {
            size = Math.max(12, size - 2);
            output.style.fontSize = size + 'px';
        }
    }

    async function refresh() {
        try {
            const response = await fetch('/api/obs-counters', {signal: AbortSignal.timeout(5000)});
            if (!response.ok) throw new Error();
            const state = await response.json();
            const appearance = state.appearance || {};
            const signature = JSON.stringify(appearance);
            const styleChanged = signature !== lastAppearance;
            if (styleChanged) {
                applyOverlayAppearance(panel, appearance);
                lastAppearance = signature;
            }
            if (styleChanged || output.textContent !== state[kind]) {
                output.textContent = state[kind];
                panel.hidden = !output.textContent;
                fitText();
            }
        } catch (_) {
            output.textContent = '';
            panel.hidden = true;
        }
        setTimeout(refresh, 2000);
    }

    window.addEventListener('resize', fitText);
    document.fonts.addEventListener('loadingdone', fitText);
    void refresh();
})();
