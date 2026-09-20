from pathlib import Path
root = Path(SPECPATH)
a = Analysis([str(root / 'onecomme' / 'helper_entry.py')], pathex=[str(root)],
    binaries=[], datas=[(str(root / 'static'), 'static')], hiddenimports=[],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['webview', 'clr', 'pythonnet', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'cefpython3'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='QueueWorker',
          icon=str(root / 'static' / 'app-icon.ico'), debug=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='runtime')
