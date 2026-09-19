from contextlib import ExitStack
import json
import time
from urllib.request import Request, urlopen
from urllib.error import URLError

from desktop.ownership import safe_path
from desktop.runtime import InstanceLock


def prepare_uninstall(catalog):
    """Ask only authenticated app instances to exit; never terminate by process name."""
    plan = catalog.plan()
    for entry in catalog.read()["entries"]:
        folder = safe_path(entry["folder"])
        runtime = safe_path(folder / "runtime.json")
        keys_path = safe_path(folder / "access-keys.json")
        if not runtime.exists() or not keys_path.exists():
            continue
        port = json.loads(runtime.read_text(encoding="utf-8"))["port"]
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError("実行中ポートの情報が不正です")
        key = json.loads(keys_path.read_text(encoding="utf-8"))["admin"]
        request = Request(f"http://127.0.0.1:{port}/api/desktop/exit", data=b"{}",
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
        try:
            with urlopen(request, timeout=3) as response:
                response.read()
        except URLError:
            pass  # Locks below decide whether the app actually stopped.
    deadline = time.monotonic() + 10
    while True:
        try:
            with ExitStack() as stack:
                for path in plan["locks"]:
                    stack.enter_context(InstanceLock(path))
            return
        except RuntimeError:
            if time.monotonic() >= deadline:
                raise RuntimeError("待機列アプリを終了できませんでした。ウィンドウを閉じて再試行してください。")
            time.sleep(0.2)
