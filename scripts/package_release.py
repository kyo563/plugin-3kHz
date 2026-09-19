"""Prepare local artifacts only: never upload, publish or create tags."""
import argparse
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import re
import shutil
import sys
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="0.1.0-preview.22")
    parser.add_argument("--application-path", type=Path, default=ROOT / "dist" / "参加型整列プラグイン")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+[.][0-9]+[.][0-9]+(?:-[a-zA-Z0-9.]+)?", args.version):
        raise ValueError("Invalid version")
    application = args.application_path.resolve()
    if not application.is_relative_to((ROOT / "dist").resolve()):
        raise ValueError("Application folder must be inside dist")
    if not (application / "参加型整列プラグイン.exe").is_file():
        raise RuntimeError("Run build-windows.ps1 first")
    notices = application / "THIRD_PARTY_LICENSES"
    notices.mkdir(exist_ok=True)
    packages = []
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata.get("Name", "").lower()):
        name = dist.metadata.get("Name", "unknown")
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", name)
        files = []
        for item in dist.files or []:
            if any(term in item.name.lower() for term in ("license", "copying", "notice")) and item.suffix.lower() not in {".py", ".pyc"}:
                source = Path(dist.locate_file(item))
                if source.is_file():
                    destination = notices / safe_name / str(item).replace("..", "_").replace("/", "_").replace("\\", "_")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
                    files.append(str(destination.relative_to(application)))
        packages.append({"name":name, "version":dist.version, "license":dist.metadata.get("License-Expression") or dist.metadata.get("License"), "license_files":files})
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copyfile(python_license, notices / "Python-LICENSE.txt")
    (application / "THIRD_PARTY_NOTICES.json").write_text(json.dumps(packages, ensure_ascii=False, indent=2), encoding="utf-8")
    for filename in ("README.md", "README.txt", "はじめに.md"):
        shutil.copyfile(ROOT / "docs" / "USER_GUIDE.md", application / filename)
    (application / "docs").mkdir(exist_ok=True)
    shutil.copyfile(ROOT / "docs" / "EXTERNAL_INPUT.md", application / "docs" / "EXTERNAL_INPUT.md")
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    (application / "BUILD_INFO.json").write_text(json.dumps({"application":"参加型整列プラグイン", "version":args.version, "source_commit":source_commit, "platform":"windows-x64", "prerelease":True}, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copyfile(ROOT / "docs" / "RELEASE_NOTES.md", application / "RELEASE_NOTES.md")
    shutil.copyfile(ROOT / "docs" / "DISTRIBUTION_STATUS.md", application / "配布前の確認事項.md")
    output = ROOT / "dist" / "release"
    output.mkdir(exist_ok=True)
    archive = output / f"Sankagata-Seiretsu-Plugin-{args.version}-windows-x64.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for source in sorted(application.rglob("*")):
            if source.is_file():
                bundle.write(source, Path("参加型整列プラグイン") / source.relative_to(application))
    artifacts = [archive]
    installer = output / f"参加型整列プラグイン-{args.version}-windows-x64-setup.exe"
    if installer.exists(): artifacts.append(installer)
    checksums = [hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name for path in artifacts]
    (output / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    print(json.dumps({"artifacts":[str(p) for p in artifacts], "sha256":checksums, "published":False}, ensure_ascii=False))


if __name__ == "__main__": main()
