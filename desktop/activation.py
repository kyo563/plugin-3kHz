"""Activate only the authenticated instance registered for this database."""
from contextlib import contextmanager
import json
import time
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.error import URLError
from desktop.runtime import InstanceLock, AlreadyRunningError
from desktop.config import load_keys
from desktop.ownership import safe_path

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def activate_existing(folder, db, *, attempts=12):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    for attempt in range(attempts):
        try:
            runtime = json.loads(safe_path(folder / "runtime.json").read_text(encoding="utf-8"))
            if safe_path(runtime["db"]) != safe_path(db):
                return False
            port = runtime["port"]
            if type(port) is not int or not 1024 <= port <= 65535:
                return False
            # Never create credentials while the first instance is starting.
            if not safe_path(folder / "access-keys.json").is_file():
                raise FileNotFoundError()
            key = load_keys(folder).admin
            request = Request(f"http://127.0.0.1:{port}/api/desktop/activate", data=b"{}",
                headers={"Content-Type":"application/json", "Authorization":"Bearer " + key})
            with opener.open(request, timeout=1) as response:
                return json.load(response).get("activated") is True
        except (OSError, URLError, ValueError, KeyError, TypeError):
            if attempt + 1 < attempts:
                time.sleep(.25)
    return False

@contextmanager
def single_instance(folder, db):
    lock = InstanceLock(db.with_suffix(".lock"))
    try:
        lock.__enter__()
    except AlreadyRunningError:
        if not activate_existing(folder, db):
            raise AlreadyRunningError("アプリは起動中ですが画面を表示できませんでした。少し待ってから再度起動するか、タスクバーのアプリを選んでください。")
        yield False
        return
    try:
        yield True
    finally:
        lock.__exit__(None, None, None)
