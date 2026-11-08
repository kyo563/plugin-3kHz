"""Read-only content and checksum checks for a packaged OneComme release."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import unicodedata
import re
import stat
import sys
import zipfile

RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])$", re.I)
FORBIDDEN = re.compile(r"(?i)(\.sqlite|access-keys|ownership\.json|\.env|\.dev\.vars|client_secret|credentials\.json|\.log$)")


def check_paths(archive, prefix):
    files = set()
    assert sum(item.file_size for item in archive.infolist()) <= 256 * 1024 * 1024, "Archive is too large"
    directories = set()
    for item in archive.infolist():
        name = item.filename
        parts = name.split("/")
        assert name == item.orig_filename and name.startswith(prefix) and not item.is_dir(), "Unexpected archive entry"
        assert not stat.S_ISLNK(item.external_attr >> 16), "Unexpected archive link"
        assert not FORBIDDEN.search(name), "Private runtime file in release"
        for part in parts:
            assert part and part not in {".", ".."} and not part.endswith((" ", ".")), "Unsafe Windows path"
            assert not re.search(r'[\\<>:"|?*\x00-\x1f]', part), "Unsafe Windows path"
            assert not RESERVED.fullmatch(part.split(".", 1)[0].rstrip(" ")), "Reserved Windows path"
        key = tuple(unicodedata.normalize("NFC", part).casefold() for part in parts)
        parents = {key[:end] for end in range(1, len(key))}
        assert key not in files and key not in directories and not files.intersection(parents), "Colliding archive path"
        files.add(key)
        directories.update(parents)


if not __debug__:
    raise RuntimeError("Run the archive verifier with assertions enabled")

archive_path = Path(sys.argv[1])
version = sys.argv[2] if len(sys.argv) > 2 else '0.1.7'
assert re.fullmatch(r'\d+\.\d+(?:\.\d+)?', version), 'Invalid version'
with zipfile.ZipFile(archive_path) as archive:
    names = archive.namelist()
    root = 'sankagata-seiretsu/'
    check_paths(archive, root)
    assert archive.testzip() is None, 'Damaged archive'
    plugin_version = version if version.count('.') == 2 else version + '.0'
    assert f"version: '{plugin_version}'".encode() in archive.read(root + 'plugin.js')
    static = root + 'runtime/_internal/static/'
    for asset in ('control-display.html', 'control-display.js', 'control-display.css'):
        assert static + asset in names
    assert b'id="obs-drag-source"' in archive.read(static + 'onecomme-obs-setup.html')
    assert b'settings.show_participation_number = participation.checked' in archive.read(static + 'overlay-settings.js')
    assert b'appearance.show_participation_number' in archive.read(static + 'overlay.js')
    assert b'background_transparency' in archive.read(static + 'overlay-settings.js')
    assert b'--background-color' in archive.read(static + 'overlay.css')
    assert b'auto_fit_font' in archive.read(static + 'settings.html')
    assert static + 'onecomme-obs-setup.css' in names
    if tuple(map(int, version.split('.'))) >= (0, 1, 6):
        bot_html = archive.read(static + 'bot.html').decode('utf-8')
        assert '@参加列整理bot または @bot を含むコメント' in bot_html
        assert 'https://www.youtube.com/channel/UCV3VeoFI04L79MqwuApT-Hg' in bot_html
        assert 'この配信での参加回数が少ないユーザー' in archive.read(static + 'control.html').decode('utf-8')
    if tuple(map(int, version.split('.'))) >= (0, 1, 7):
        control_js = archive.read(static + 'control.js').decode('utf-8')
        assert '/api/control/move-current-to-waiting' in control_js
        assert 'expected_revision: latestState.revision' in control_js
        assert "draggable: document.body?.dataset.onecomme === 'true'" in control_js
    if tuple(map(int, version.split('.'))) >= (1, 11):
        for asset in ('obs-counter.html', 'obs-counter.js', 'obs-counter.css', 'obs-counter-fields.html',
                      'obs-counter-settings.js', 'overlay-appearance.js'):
            assert static + asset in names
    with zipfile.ZipFile(io.BytesIO(archive.read(root + 'Taikiretsu-Template.zip'))) as template:
        check_paths(template, 'taikiretsu-display/')
        assert len(template.namelist()) == 5
        assert all(PurePosixPath(name).parent.as_posix() == 'taikiretsu-display' for name in template.namelist())
        for name in template.namelist():
            assert template.read(name) == archive.read(static + 'onecomme-template/' + PurePosixPath(name).name)
        meta = json.loads(template.read('taikiretsu-display/template.json'))
        assert meta['name'] == '待機列整理アプリ｜OBS表示'
        assert meta['description'] == 'コメント欄から参加者をリストアップするプラグインです。表示設定はプラグイン管理画面から。'
        assert template.read('taikiretsu-display/thumb.png').startswith(b'\x89PNG\r\n\x1a\n')
digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
assert digest + '  ' + archive_path.name in archive_path.with_name('SHA256SUMS.txt').read_text(encoding='utf-8')
print(json.dumps({'archive_ok': True, 'files': len(names), 'bytes': archive_path.stat().st_size, 'sha256': digest}))
