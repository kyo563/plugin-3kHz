# Windows x64, directory distribution; no onefile extraction or bundled browser.
from pathlib import Path

root = Path(SPECPATH)
a = Analysis(
    [str(root / 'desktop_entry.py')], pathex=[str(root)],
    binaries=[], datas=[(str(root / 'static'), 'static')],
    hiddenimports=['webview.platforms.edgechromium', 'webview.platforms.winforms'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'cefpython3'], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='参加型整列プラグイン',
          icon=str(root / "static" / "app-icon.ico"),
          version=str(root / "desktop" / "version_info.txt"),
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='参加型整列プラグイン')
