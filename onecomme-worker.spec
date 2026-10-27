from pathlib import Path
import ssl
root = Path(SPECPATH)
data_files = [(str(root / 'static'), 'static')]
# Bundled Python may require this CA policy when constructing SSLContext.
ca_policy = Path(ssl.__file__).with_name('codex-rejected-cas.pem')
if ca_policy.is_file():
    data_files.append((str(ca_policy), '.'))
a = Analysis([str(root / 'onecomme' / 'helper_entry.py')], pathex=[str(root)],
    binaries=[], datas=data_files, hiddenimports=[],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['webview', 'clr', 'pythonnet', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'cefpython3'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='QueueWorker',
          icon=str(root / 'static' / 'app-icon.ico'), debug=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='runtime')
