import json
import re
from threading import Lock
from pathlib import Path

from app.security import AccessKeys
from desktop.ownership import atomic_json, safe_path


class DesktopConfig:
    def __init__(self, folder: Path):
        self._write_lock = Lock()
        self.path = safe_path(folder / "desktop.json")
        self.port = 8080
        self.onboarding_completed = False
        if self.path.exists():
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("保存されたポート設定の形式が不正です")
            port = value.get("port", 8080)
            if type(port) is not int or not 1024 <= port <= 65535:
                raise ValueError("保存されたポートが不正です。desktop.jsonを確認してください")
            self.port = port
            completed = value.get("onboarding_completed", False)
            if type(completed) is not bool:
                raise ValueError("初回案内の設定が不正です")
            self.onboarding_completed = completed

    def save_port(self, port: int):
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError("ポートは1024～65535で指定してください")
        with self._write_lock:
            atomic_json(self.path, {"version": 1, "port": port, "onboarding_completed": self.onboarding_completed})
            self.port = port

    def complete_onboarding(self):
        with self._write_lock:
            atomic_json(self.path, {"version": 1, "port": self.port, "onboarding_completed": True})
            self.onboarding_completed = True


def load_keys(folder: Path) -> AccessKeys:
    path = safe_path(folder / "access-keys.json")
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or
            any(not isinstance(data.get(k), str) or not re.fullmatch(r"[A-Za-z0-9_-]{40,128}", data[k]) for k in ("admin", "ingest")) or
            data["admin"] == data["ingest"]):
            raise ValueError("接続キーのファイルが不正です")
        return AccessKeys(admin=data["admin"], ingest=data["ingest"])
    keys = AccessKeys()
    atomic_json(path, {"admin": keys.admin, "ingest": keys.ingest})
    return keys
