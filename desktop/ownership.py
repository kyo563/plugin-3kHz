"""Explicit app-owned inventory. Never recursively delete a user-selected root."""
from contextlib import ExitStack, closing
import json
import os
from pathlib import Path
import stat
import uuid

APP_ID = "WaitingListApp"
RESERVED_FILES = ("desktop.json", "access-keys.json", "runtime.json", "desktop.log", "desktop.log.1", "desktop.log.2")


def safe_path(value) -> Path:
    path = Path(os.path.abspath(os.path.expanduser(str(value))))
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError(f"再解析ポイントは使用できません: {part}")
    return path


def atomic_json(path: Path, value):
    safe_path(path)
    temporary = safe_path(path.with_name(path.name + ".new"))
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


class OwnershipCatalog:
    def __init__(self, root: Path):
        self.root = safe_path(root)
        self.path = self.root / "ownership.json"

    def read(self):
        safe_path(self.path)
        if not self.path.exists():
            return {"app": APP_ID, "version": 1, "entries": []}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("app") != APP_ID or data.get("version") != 1 or not isinstance(data.get("entries"), list):
            raise ValueError("所有台帳を確認できません。削除を中止しました。")
        return data

    def register(self, folder: Path, db: Path, *, adopt_existing: bool = False) -> Path:
        from desktop.runtime import InstanceLock
        self.root.mkdir(parents=True, exist_ok=True)
        with InstanceLock(self.root / ".catalog.lock"):
            data = self.read()
            if data.get("cleanup_ready"):
                raise ValueError("削除処理が未完了です。アンインストールを再実行してください")
            folder, db = safe_path(folder), safe_path(db)
            if folder == folder.parent or folder == Path.home() or folder == self.root.parent:
                raise ValueError("保存先にはアプリ専用フォルダーを指定してください")
            if db.suffix.lower() not in {".sqlite3", ".db"}:
                raise ValueError("DBの拡張子は .sqlite3 または .db を指定してください")
            existing = next((item for item in data["entries"] if item["folder"] == str(folder) and item["db"] == str(db)), None)
            if existing:
                self._validate_entry(existing)
                return Path(existing["cache"])
            # A root already registered for another DB would share settings/cache and is rejected.
            if any(item["folder"] == str(folder) or item["db"] == str(db) for item in data["entries"]):
                raise ValueError("保存先またはDBは別の構成で登録されています。元の指定で起動してください。")
            marker = safe_path(folder / ".waiting-list-owner")
            db_marker = safe_path(db.with_name(db.name + ".waiting-list-owner"))
            if marker.exists() or db_marker.exists():
                raise ValueError("既存の所有マーカーがあります。台帳と保存先を確認してください。")
            # Do not claim arbitrary pre-existing custom databases or reserved files.
            if not adopt_existing and (db.exists() or any((folder / name).exists() for name in RESERVED_FILES)):
                raise ValueError("未登録の既存データがあります。バックアップ後、移行手順（--adopt-existing-data）で所有範囲を登録してください。")
            if adopt_existing and db.exists():
                import sqlite3
                with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as connection:
                    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if not {"participants", "app_state", "operation_logs"}.issubset(tables):
                        raise ValueError("待機列アプリのDBではありません")
                    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                        raise ValueError("DBの整合性検査に失敗しました")
            owner = uuid.uuid4().hex
            cache = safe_path(folder / ("webview-" + owner))
            folder.mkdir(parents=True, exist_ok=True)
            db.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(owner, encoding="utf-8")
            db_marker.write_text(owner + "\n" + str(db), encoding="utf-8")
            cache.mkdir()
            (cache / ".waiting-list-owner").write_text(owner, encoding="utf-8")
            entry = {"folder": str(folder), "db": str(db), "cache": str(cache), "owner": owner}
            data["entries"].append(entry)
            atomic_json(self.path, data)
            return cache

    def _validate_entry(self, entry, *, cleanup_ready=False):
        folder, db, cache = (safe_path(entry[key]) for key in ("folder", "db", "cache"))
        owner = entry["owner"]
        if len(owner) != 32 or any(c not in "0123456789abcdef" for c in owner):
            raise ValueError("不正な所有ID")
        if cache != folder / ("webview-" + owner):
            raise ValueError("不正なキャッシュ保存先")
        marker = safe_path(folder / ".waiting-list-owner")
        db_marker = safe_path(db.with_name(db.name + ".waiting-list-owner"))
        for path, expected in ((marker, owner), (db_marker, owner + "\n" + str(db))):
            if path.exists():
                if path.read_text(encoding="utf-8") != expected:
                    raise ValueError("所有マーカーが一致しません")
            elif not cleanup_ready:
                raise ValueError("所有マーカーがありません")
        cache_marker = safe_path(cache / ".waiting-list-owner")
        if cache.exists() and ((cache_marker.exists() and cache_marker.read_text(encoding="utf-8") != owner) or (not cache_marker.exists() and not cleanup_ready)):
            raise ValueError("キャッシュの所有マーカーが一致しません")
        return folder, db, cache

    def plan(self):
        files, directories, locks = {safe_path(self.root / "ownership.json.new")}, set(), set()
        data = self.read()
        for entry in data["entries"]:
            folder, db, cache = self._validate_entry(entry, cleanup_ready=data.get("cleanup_ready", False))
            locks.add(db.with_suffix(".lock"))
            for name in RESERVED_FILES:
                files.add(safe_path(folder / name))
                files.add(safe_path(folder / (name + ".new")))
            for suffix in ("", "-wal", "-shm", "-journal", ".waiting-list-owner"):
                files.add(safe_path(str(db) + suffix))
            files.add(safe_path(db.with_suffix(".lock")))
            files.add(safe_path(folder / ".waiting-list-owner"))
            if cache.exists():
                for current, subdirs, names in os.walk(cache, followlinks=False):
                    for name in subdirs + names:
                        safe_path(Path(current) / name)
                    directories.add(safe_path(current))
                    files.update(safe_path(Path(current) / name) for name in names)
            directories.add(folder)
        if data.get("cleanup_ready"):
            for path in files:
                if path.exists() and not path.name.endswith(".waiting-list-owner") and path not in locks:
                    raise ValueError("削除中断後に新しいファイルが見つかりました。再確認してください")
        return {"files": sorted(files, key=str), "directories": sorted(directories, key=lambda p: len(p.parts), reverse=True), "locks": sorted(locks, key=str)}

    def remove(self):
        from desktop.runtime import InstanceLock
        if not self.path.exists():
            known = (*RESERVED_FILES, "waiting_list.sqlite3", "webview", ".waiting-list-owner")
            if self.root.exists() and any((self.root / name).exists() for name in known):
                raise ValueError("未登録の旧データが残っています。所有確認・移行を行ってから削除してください。")
            return {"removed": [], "retained": [], "errors": []}
        removed, retained, errors = [], [], []
        with InstanceLock(self.root / ".catalog.lock"):
            plan = self.plan()  # Validate every target before the first deletion.
            with ExitStack() as stack:
                for path in plan["locks"]:
                    stack.enter_context(InstanceLock(path))
                # Keep all markers until data deletion succeeds, allowing safe retries.
                late = [p for p in plan["files"] if p.name.endswith(".waiting-list-owner") or p in plan["locks"]]
                for path in plan["files"]:
                    if path in late:
                        continue
                    try:
                        safe_path(path)
                        if path.exists():
                            path.unlink()
                            removed.append(str(path))
                    except OSError as exc:
                        errors.append(f"{path}: {exc}")
            if not errors:
                data = self.read()
                data["cleanup_ready"] = True
                atomic_json(self.path, data)
                for path in late:
                    try:
                        safe_path(path)
                        path.unlink(missing_ok=True)
                    except OSError as exc:
                        errors.append(f"{path}: {exc}")
            if not errors:
                self.path.unlink()
        if errors:
            return {"removed": removed, "retained": retained, "errors": errors}
        (self.root / ".catalog.lock").unlink(missing_ok=True)
        for path in plan["directories"] + [self.root]:
            try:
                if safe_path(path).exists():
                    path.rmdir()  # Unknown user files are preserved, never swept.
            except OSError:
                retained.append(str(path))
        return {"removed": removed, "retained": retained, "errors": errors}
