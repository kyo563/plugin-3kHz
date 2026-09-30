(() => {
    const standard = '"Noto Sans JP", "Yu Gothic", "Meiryo", sans-serif';
    const builtins = {default:standard, gothic:'"Yu Gothic", "Meiryo", sans-serif', mincho:'"Yu Mincho", "MS PMincho", serif', meiryo:'"Meiryo", sans-serif', sans:'sans-serif', serif:'serif'};
    const pending = new Map();
    const fields = ['ui_body','ui_heading','ui_controls','status','now_heading','next_heading','queue_heading','now_names','next_names','summary'].filter(field => document.body.classList.contains('is-overlay') ? !field.startsWith('ui_') : field.startsWith('ui_'));
    function systemName(id) {
        if (!/^system:(?:[a-f0-9]{2}){1,512}$/.test(id || '')) return null;
        try {
            const name = new TextDecoder('utf-8', {fatal:true}).decode(Uint8Array.from(id.slice(7).match(/../g), hex => parseInt(hex,16)));
            return name.trim() && [...name].length <= 128 && !/\p{C}/u.test(name) ? name : null;
        } catch (_) { return null; }
    }
    function family(id) {
        if (builtins[id]) return builtins[id];
        const name = systemName(id);
        // Escape every codepoint as CSS; font names can never become CSS syntax or URLs.
        if (name) return `"${[...name].map(c => '\\' + c.codePointAt(0).toString(16) + ' ').join('')}", ${standard}`;
        if (!/^[a-f0-9]{64}$/.test(id || '')) return standard;
        if (pending.get(id)?.status === 'error') { document.fonts.delete(pending.get(id)); pending.delete(id); }
        if (!pending.has(id)) {
            const face = new FontFace(`appfont_${id}`, `url("/api/font-assets/${id}")`);
            pending.set(id, face);
            document.fonts.add(face);
            face.load().catch(() => window.dispatchEvent(new CustomEvent('app-font-error')));
        }
        return `"appfont_${id}", ${standard}`;
    }
    function apply(fonts = {}) {
        const all = fonts.all || 'default';
        const selected = field => fonts[field] || (!field.startsWith('ui_') && fonts.obs_all) || all;
        const used = new Set(fields.map(selected));
        for(const [id,face] of pending) if(!used.has(id)) { document.fonts.delete(face); pending.delete(id); }
        for (const field of fields) document.documentElement.style.setProperty(`--font-${field.replaceAll('_','-')}`, family(selected(field)));
    }
    window.AppFonts = {apply, builtins, family, systemName};
    if (!document.body.classList.contains('is-overlay')) {
        async function refresh() {
            try {
                const r = await fetch('/api/overlay-state?preview=1', {signal:AbortSignal.timeout(5000)});
                if(r.ok) apply((await r.json()).appearance?.fonts);
            } catch (_) { /* Retain usable default when disconnected. */ }
        }
        refresh();
        window.addEventListener('storage', event => {if(event.key === 'app-font-settings') refresh();});
        window.addEventListener('focus', refresh);
    }
})();
