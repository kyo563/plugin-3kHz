// Turn plain text into safe display fragments; no HTML/CSS is accepted from the editor.
function overlayTextLines(template, state, appearance) {
    if (!template.trim()) return [];
    const clean = value => String(value ?? '').replace(/[\r\n\t]/g, ' ');
    const tokens = {
        '受付': [state.is_open ? (appearance.open_label ?? '受付中') : (appearance.closed_label ?? '受付終了'), 'status', state.is_open ? 'status-open' : 'status-closed'],
        'NOW見出し': [appearance.now_label ?? 'NOW', 'now-heading', ''],
        'NEXT見出し': [appearance.next_label ?? 'NEXT', 'next-heading', ''],
        'QUEUE見出し': [appearance.queue_label ?? 'QUEUE', 'queue-heading', ''],
        '待機グループ': [`${state.total_waiting_group_count}グループ`, 'summary', ''],
        '待機人数のみ': [`${state.total_waiting_count}人待機中`, 'summary', ''],
        '待機人数': [`${state.total_waiting_group_count}グループ/${state.total_waiting_count}人待機中`, 'summary', '']
    };
    for(const [prefix,users,font] of [['NOW',state.now_view,'now-names'],['NEXT',state.next_view,'next-names']]) {
        for(let i=0;i<3;i++) tokens[`${prefix}${i+1}`] = [users[i]?.display_name || '', font, users[i]?.is_placeholder ? 'placeholder' : ''];
    }
    return template.replace(/\r\n?/g,'\n').split('\n').map(line => line.split(/(\[[^\]\n]+\])/g).filter(Boolean).map(part => {
        const key = part.slice(1,-1);
        const token = Object.hasOwn(tokens, key) ? tokens[key] : null;
        if(part.startsWith('[') && part.endsWith(']') && token) return {text:clean(token[0]),font:token[1],className:token[2]};
        return {text:part,font:'now-names',className:''};
    }));
}
function renderOverlayText(container, template, state, appearance) {
    const lines = overlayTextLines(template,state,appearance);
    const signature = JSON.stringify(lines);
    if(container.dataset.signature === signature) return;
    container.dataset.signature = signature;
    container.replaceChildren();
    for(const parts of lines) {
        const line = document.createElement('div'); line.className = 'custom-line';
        for(const part of parts) {
            const span = document.createElement('span'); span.textContent = part.text;
            span.style.fontFamily = `var(--font-${part.font})`; span.className = part.className;
            line.appendChild(span);
        }
        container.appendChild(line);
    }
}
