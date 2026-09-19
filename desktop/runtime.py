from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path

import uvicorn
from desktop.ownership import safe_path


def data_directory() -> Path:
    override = os.environ.get("WAITING_LIST_DATA_DIR")
    if override:
        return safe_path(override)
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError("LOCALAPPDATA が見つかりません。Windowsで起動してください。")
    return safe_path(Path(local) / "WaitingListApp")


def configure_storage() -> Path:
    folder = data_directory()
    folder.mkdir(parents=True, exist_ok=True)
    db = safe_path(os.environ.get("WAITING_LIST_DB_PATH") or folder / "waiting_list.sqlite3")
    os.environ["WAITING_LIST_DB_PATH"] = str(db)
    os.environ["WAITING_LIST_DESKTOP"] = "1"
    return folder


class AlreadyRunningError(RuntimeError):
    pass


class InstanceLock:
    """OS-owned lock released even after a crash; stale files are harmless."""

    def __init__(self, path: Path):
        self.path = safe_path(path)
        self.file = None

    def __enter__(self):
        import msvcrt

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            self.file.close()
            self.file = None
            raise AlreadyRunningError("同じ保存先のアプリが既に起動しています。既存のウィンドウを確認してください。") from exc
        return self

    def __exit__(self, *_):
        if self.file:
            self.file.close()
            self.file = None


class LocalServer:
    def __init__(self, app, port: int = 8080):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            self.socket.bind(("127.0.0.1", port))
            self.socket.listen(128)
        except OSError as exc:
            self.socket.close()
            raise RuntimeError(f"ポート {port} を使用できません。同じアプリが起動中でないか確認してください。別アプリが使用中なら --port 8081 などを指定して起動できます。成功時に保存されます。OBSのURLも新しい番号に変更してください。") from exc
        self.port = self.socket.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.server = uvicorn.Server(uvicorn.Config(
            app, host="127.0.0.1", port=self.port, loop="asyncio", http="h11",
            ws="none", log_config=None, access_log=False, timeout_graceful_shutdown=5,
        ))
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [self.socket]}, daemon=True)

    def start(self):
        self.thread.start()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.server.started:
                return self
            if not self.thread.is_alive():
                break
            time.sleep(0.05)
        self.stop()
        raise RuntimeError("ローカルサーバーを起動できませんでした。desktop.logを確認してください。")

    def stop(self):
        self.server.should_exit = True
        if self.thread.ident is not None:
            self.thread.join(timeout=8)
        self.socket.close()
        if self.thread.is_alive():
            raise RuntimeError("ローカルサーバーの停止がタイムアウトしました。")

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.stop()
