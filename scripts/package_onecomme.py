"""Separate OneComme release artifact. Does not touch standalone release files."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / 'dist' / 'onecomme-release-1.0.0'
    target = output / 'sankagata-seiretsu'
    target.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'dist' / 'onecomme-worker' / 'runtime'
    if not (source / 'QueueWorker.exe').is_file():
        raise RuntimeError('Build onecomme-worker.spec first')
    shutil.copytree(source, target / 'runtime', dirs_exist_ok=True)
    for name in ('plugin.js', 'index.html', 'open.js', 'README.txt'):
        shutil.copyfile(ROOT / 'onecomme' / name, target / name)
    notices = target / 'THIRD_PARTY_LICENSES'
    notices.mkdir(exist_ok=True)
    for dist in metadata.distributions():
        name = re.sub(r'[^a-zA-Z0-9_.-]', '_', dist.metadata.get('Name', 'unknown'))
        for item in dist.files or []:
            if any(term in item.name.lower() for term in ('license', 'copying', 'notice')) and item.suffix.lower() not in {'.py', '.pyc'}:
                file = Path(dist.locate_file(item))
                if file.is_file():
                    dest = notices / name
                    dest.mkdir(exist_ok=True)
                    shutil.copyfile(file, dest / str(item).replace('..', '_').replace('/', '_').replace('\\', '_'))
    license = Path(sys.base_prefix) / 'LICENSE.txt'
    if license.is_file(): shutil.copyfile(license, notices / 'Python-LICENSE.txt')
    template = target / 'Taikiretsu-Template.zip'
    with zipfile.ZipFile(template, 'w', zipfile.ZIP_DEFLATED) as z:
        for file in sorted((ROOT / 'static' / 'onecomme-template').iterdir()):
            if file.is_file(): z.write(file, Path('taikiretsu-display') / file.name)
    archive = output / 'Taikiretsu-Seiri-App-OneComme-1.0.0-windows-x64.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for file in sorted(target.rglob('*')):
            if file.is_file(): z.write(file, file.relative_to(output))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / 'SHA256SUMS.txt').write_text(digest + '  ' + archive.name + '\n', encoding='utf-8')
    print(json.dumps({'zip': str(archive), 'sha256': digest, 'published': False}, ensure_ascii=False))


if __name__ == '__main__': main()
