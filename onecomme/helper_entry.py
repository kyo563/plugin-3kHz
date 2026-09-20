"""Private headless worker, owned by the OneComme plugin's stdin lifetime."""
import json
import os
from pathlib import Path
import sys
from threading import Event, Thread

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import create_app
from desktop.runtime import InstanceLock, LocalServer
from desktop.config import load_keys
from desktop.ownership import safe_path


def main():
    # Never reuse the standalone edition's environment overrides or storage.
    folder = safe_path(Path(os.environ["LOCALAPPDATA"]) / "WaitingListAppOneComme")
    folder.mkdir(parents=True, exist_ok=True)
    stopped = Event()

    def watch_parent():
        while sys.stdin.buffer.read(1):
            pass
        stopped.set()

    Thread(target=watch_parent, daemon=True).start()
    with InstanceLock(folder / "worker.lock"):
        keys = load_keys(folder)
        app = create_app(db_path=str(folder / "waiting_list.sqlite3"), desktop=True,
                         access_keys=keys, onecomme=True)
        # Stable and separate from the standalone edition's default 8080.
        with LocalServer(app, 18765) as server:
            print(json.dumps({"base": server.url, "control": server.url + "/control#key=" + keys.admin,
                              "ingest": keys.ingest}), flush=True)
            stopped.wait()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # Credentials, comment bodies and local paths must not enter OneComme logs.
        print(json.dumps({"error": "起動できません。プラグインの重複起動・ポート18765の使用状況を確認してください"}), flush=True)
        raise SystemExit(1)
