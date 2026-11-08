function applyOverlayAppearance(panel, appearance) {
    window.AppFonts.apply(appearance.fonts);
    const background = /^#[0-9a-fA-F]{6}$/.test(appearance.background_color || '') ? appearance.background_color : '#000000';
    const transparency = Number.isFinite(appearance.background_transparency)
        ? Math.min(100, Math.max(0, appearance.background_transparency)) : 100;
    const rgb = [1, 3, 5].map(index => parseInt(background.slice(index, index + 2), 16));
    panel.style.setProperty('--background-color', `rgba(${rgb.join(', ')}, ${(100 - transparency) / 100})`);
    panel.dataset.fontFit = appearance.auto_fit_font === false ? 'fixed' : 'auto';
    panel.style.setProperty('--text-weight', appearance.text_bold === false ? '400' : '700');
    panel.style.setProperty('--text-shadow', appearance.text_shadow === false ? 'none' : '0 1px 3px #000');
    panel.style.setProperty('--text-color', /^#[0-9a-fA-F]{6}$/.test(appearance.text_color || '') ? appearance.text_color : '#ffffff');
    panel.style.setProperty('--font-size', `${appearance.font_size || 28}px`);
}
