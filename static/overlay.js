const q = (selector) => document.querySelector(selector);

let etag = null;
const previewParams = new URLSearchParams(location.search);
async function fetchOverlayState() {
    try {
        const path = '/api/overlay-state' + (previewParams.get('preview') === '1' ? '?preview=1' : '');
        const response = await fetch(path, {headers: etag ? {'If-None-Match': etag} : {}, signal:AbortSignal.timeout(5000)});
        if (response.status === 304) return null;
        etag = response.headers.get('ETag');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error(error);
        return null;
    }
}

function renderOverlay(state) {
    const appearance = state.appearance || {};
    window.AppFonts.apply(appearance.fonts);
    const panel = q('.panel');
    panel.dataset.layout = appearance.layout || "vertical";
    const output = q('#custom-output');
    output.hidden = false;
    const horizontal = appearance.layout === 'horizontal';
    let templates = horizontal ? [
        appearance.horizontal_status_text ?? '[受付]',
        appearance.horizontal_now_text ?? '[NOW見出し]\n[NOW1]\n[NOW2]\n[NOW3]',
        appearance.horizontal_next_text ?? '[NEXT見出し]\n[NEXT1]\n[NEXT2]\n[NEXT3]',
        appearance.horizontal_queue_text ?? '[QUEUE見出し]\n[待機グループ]\n/[待機人数のみ]'
    ] : [appearance.layout === 'custom' ? (appearance.custom_text ?? '') : (appearance.vertical_text ?? '[受付]\n\n[NOW見出し]\n[NOW1]\n[NOW2]\n[NOW3]\n\n[NEXT見出し]\n[NEXT1]\n[NEXT2]\n[NEXT3]\n\n[QUEUE見出し]\n[待機人数]')];
    if (horizontal) {
        const weights = [.8, 1.4, 1.4, 1.3];
        output.style.gridTemplateColumns = templates.map((text, i) => text.trim() ? `${weights[i]}fr` : null).filter(Boolean).join(' ') || '1fr';
        templates = templates.filter(text => text.trim());
    } else { output.style.gridTemplateColumns = ''; }
    if (output.children.length !== templates.length) output.replaceChildren(...templates.map(() => document.createElement('div')));
    templates.forEach((text, i) => renderOverlayText(output.children[i], text, state, appearance));
    const lineCount = Math.max(1, ...templates.map(text => text.replace(/\r\n?/g,'\n').split('\n').length));
    panel.style.setProperty('--line-units', String(lineCount * 1.3 + .5));
    panel.style.setProperty('--overlay-width', `${appearance.width || 480}px`);
    panel.style.setProperty('--overlay-height', `${appearance.height || 600}px`);
    panel.style.setProperty('--font-size', `${appearance.font_size || 28}px`);

}

async function refresh() {
    // OBS can mark a visible source hidden internally: always poll the live overlay.
    const state = await fetchOverlayState();
    if (state) renderOverlay(state);
    setTimeout(refresh, 2000);
}
function sampleState(appearance = {}) {
    const mode = appearance.name_mode || 'youtube';
    const named = (account, declared) => ({display_name: mode === 'declared' ? declared : mode === 'youtube_declared' ? `${account}（${declared}）` : mode === 'declared_youtube' ? `${declared}（${account}）` : account});
    return {is_open:true, appearance,
      now_view:[named('@sample_aoi','サンプル：あおい'),named('@sample_long_name_for_preview','サンプル：長い名前の表示確認'),{display_name:'参加者募集中',is_placeholder:true}],
      next_view:[named('@sample_next_a','サンプル：次の方A'),named('@sample_next_b','サンプル：次の方B'),named('@sample_next_c','サンプル：次の方C')],
      total_waiting_count:5,total_waiting_group_count:2};
}
if (previewParams.get('sample') === '1') {
    let customPreview = false;
    renderOverlay(sampleState());
    fetch('/api/overlay-state?preview=1').then(r=>r.ok?r.json():null).then(s=>{if(s && !customPreview)renderOverlay(sampleState(s.appearance));}).catch(()=>{});
    window.addEventListener('message', event => {
        if(event.origin === location.origin && event.source === window.parent && event.data?.type === 'overlay-preview') {
            customPreview = true;
            renderOverlay(sampleState(event.data.appearance));
        }
    });
} else { refresh(); }
