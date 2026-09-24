"""Read-only content and checksum checks for a packaged OneComme release."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

archive_path = Path(sys.argv[1])
with zipfile.ZipFile(archive_path) as archive:
    names = archive.namelist()
    assert archive.testzip() is None, 'Damaged archive'
    assert len(names) == len(set(names)), 'Duplicate archive paths'
    assert all(name.startswith('sankagata-seiretsu/') and '..' not in PurePosixPath(name).parts for name in names)
    forbidden = r'(?i)(\.sqlite|access-keys|ownership\.json|\.env|\.dev\.vars|client_secret|credentials\.json|\.log$)'
    assert not any(re.search(forbidden, name) for name in names), 'Private runtime file in release'
    root = 'sankagata-seiretsu/'
    assert b"version: '0.1.3'" in archive.read(root + 'plugin.js')
    static = root + 'runtime/_internal/static/'
    assert b'id="obs-drag-source"' in archive.read(static + 'onecomme-obs-setup.html')
    assert static + 'onecomme-obs-setup.css' in names
    with zipfile.ZipFile(io.BytesIO(archive.read(root + 'Taikiretsu-Template.zip'))) as template:
        assert len(template.namelist()) == 5
        for name in template.namelist():
            assert template.read(name) == archive.read(static + 'onecomme-template/' + PurePosixPath(name).name)
        meta = json.loads(template.read('taikiretsu-display/template.json'))
        assert meta['name'] == '待機列整理アプリ｜OBS表示'
        assert meta['description'] == 'コメント欄から参加者をリストアップするプラグインです。表示設定はプラグイン管理画面から。'
        assert template.read('taikiretsu-display/thumb.png').startswith(b'\x89PNG\r\n\x1a\n')
digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
assert digest + '  ' + archive_path.name in archive_path.with_name('SHA256SUMS.txt').read_text(encoding='utf-8')
print(json.dumps({'archive_ok': True, 'files': len(names), 'bytes': archive_path.stat().st_size, 'sha256': digest}))
