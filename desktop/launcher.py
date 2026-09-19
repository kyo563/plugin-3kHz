from __future__ import annotations

import argparse
import os
import sys
import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import time

from desktop.runtime import InstanceLock, LocalServer, configure_storage
from desktop.activation import single_instance
from desktop.config import DesktopConfig, load_keys
from desktop.ownership import OwnershipCatalog, safe_path, atomic_json


def main() -> int:
    parser = argparse.ArgumentParser(description="参加型整列プラグイン 1.1.1")
    parser.add_argument("--port", type=int)
    parser.add_argument("--prepare-uninstall", action="store_true")
    parser.add_argument("--adopt-existing-data", action="store_true")
    parser.add_argument("--uninstall-data", action="store_true")
    parser.add_argument("--uninstall-check", action="store_true")
    parser.add_argument("--smoke-delay", type=float, default=0)
    parser.add_argument("--smoke-report", type=Path, help="検証専用: 画面読込を確認して自動終了しJSONを保存")
    parser.add_argument("--development", action="store_true", help="検証専用: テスト操作APIを有効にする")
    args = parser.parse_args()
    try:
        catalog = OwnershipCatalog(Path(os.environ["LOCALAPPDATA"]) / "WaitingListApp")
        if args.prepare_uninstall:
            from desktop.uninstall import prepare_uninstall
            prepare_uninstall(catalog)
            return 0
        if args.uninstall_data or args.uninstall_check:
            if args.uninstall_check:
                from contextlib import ExitStack
                plan = catalog.plan()
                with ExitStack() as stack:
                    for lock in plan["locks"]:
                        stack.enter_context(InstanceLock(lock))
                return 0
            result = catalog.remove()
            for _ in range(15):
                if not result["errors"]:
                    break
                time.sleep(0.2)
                result = catalog.remove()
            if result["errors"]:
                raise RuntimeError("一部データを削除できませんでした。アプリを閉じて再実行してください。\n" + "\n".join(result["errors"]))
            return 0
        if args.port is not None and not 1024 <= args.port <= 65535:
            raise ValueError("ポートは1024～65535を指定してください。")
        folder = configure_storage()
        db = Path(os.environ["WAITING_LIST_DB_PATH"])
        with single_instance(folder, db) as acquired:
            if not acquired:
                return 0
            cache = catalog.register(folder, db, adopt_existing=args.adopt_existing_data)
            config = DesktopConfig(folder)
            port = args.port if args.port is not None else config.port
            keys = load_keys(folder)
            logging.basicConfig(level=logging.INFO, handlers=[RotatingFileHandler(
                folder / "desktop.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"
            )])
            # Acquire before starting the app lifespan, which initializes SQLite.
            from app.main import create_app
            app = create_app(db_path=str(db), desktop=True, development=args.development, access_keys=keys, desktop_config=config)
            import webview
            webview.settings["ALLOW_DOWNLOADS"] = True

            with LocalServer(app, port) as server:
                atomic_json(folder / "runtime.json", {"port": port, "db": str(db)})
                if args.port is not None:
                    config.save_port(port)
                window = webview.create_window(
                    "参加型整列プラグイン 1.1.1", server.url + "/control#key=" + keys.admin,
                    width=440, height=800, min_size=(320, 480),
                    confirm_close=False,
                )
                def activate_window():
                    window.restore()
                    window.show()
                    result["activation_count"] = result.get("activation_count", 0) + 1
                window.events.shown += lambda: setattr(app.state, "request_activate", activate_window)
                closing_for_uninstall = False
                def request_exit():
                    import threading
                    def close_owned_window():
                        nonlocal closing_for_uninstall
                        closing_for_uninstall = True
                        window.destroy()
                    threading.Timer(0.2, close_owned_window).start()
                app.state.request_exit = request_exit
                if not args.smoke_report:
                    from threading import Event, Thread
                    close_prompt_pending = Event()
                    def confirm_exit():
                        if closing_for_uninstall:
                            return True
                        if close_prompt_pending.is_set():
                            return False
                        close_prompt_pending.set()
                        def prompt_after_close_cancelled():
                            try:
                                if window.events.loaded.is_set():
                                    try:
                                        if window.evaluate_js("window.showExitDialog ? window.showExitDialog() : false"):
                                            return
                                    except Exception:
                                        pass
                                if window.create_confirmation_dialog("アプリを終了しますか？", "待機列は保存されています。OBS表示の更新は止まります。"):
                                    request_exit()
                            finally:
                                close_prompt_pending.clear()
                        # FormClosing runs on the UI thread. Never wait for WebView
                        # JavaScript there: its completion also needs that thread.
                        Thread(target=prompt_after_close_cancelled, daemon=True).start()
                        return False
                    window.events.closing += confirm_exit
                result = {}

                def verify_window():
                    try:
                        deadline = time.monotonic() + 25
                        while time.monotonic() < deadline:
                            if window.evaluate_js("document.querySelector('#conn')?.textContent") == "接続状態: 管理APIに接続済み":
                                result.update(ok=True, title=window.evaluate_js("document.title"), url=server.url)
                                result["operator_tools_loaded"] = window.evaluate_js("!!document.querySelector('#backup-restore') && !!document.querySelector('#add-participant') && !!document.querySelector('#undo')")
                                result["development_hidden"] = window.evaluate_js("document.querySelector('#development-actions').hidden")
                                result["youtube_controls_loaded"] = window.evaluate_js("!!document.querySelector('#youtube-url') && !!document.querySelector('#youtube-key') && !!document.querySelector('#youtube-connect')")
                                if not result["youtube_controls_loaded"]:
                                    raise RuntimeError("YouTubeコメント受信画面を読み込めませんでした")
                                window.load_url(server.url + "/obs-setup")
                                for _ in range(100):
                                    if window.evaluate_js("document.querySelector('#access-status')?.textContent?.startsWith('アプリ起動済み')"):
                                        result["obs_setup_loaded"] = True
                                        break
                                    time.sleep(0.1)
                                if not result.get("obs_setup_loaded"):
                                    raise RuntimeError("OBS設定画面を読み込めませんでした")
                                time.sleep(min(max(args.smoke_delay, 0), 60))
                                return
                            time.sleep(0.2)
                        raise RuntimeError("管理画面の状態取得が完了しませんでした。")
                    except Exception as exc:
                        result.update(ok=False, error=str(exc))
                    finally:
                        window.destroy()

                webview.start(
                    verify_window if args.smoke_report else None,
                    gui="edgechromium", debug=False, private_mode=False,
                    storage_path=str(cache),
                    icon=str(Path(__file__).resolve().parents[1] / "static" / "app-icon.ico"),
                )
            safe_path(folder / "runtime.json").unlink(missing_ok=True)
            if args.smoke_report:
                args.smoke_report.parent.mkdir(parents=True, exist_ok=True)
                result["server_stopped"] = not server.thread.is_alive()
                args.smoke_report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                return 0 if result.get("ok") and result["server_stopped"] else 1
        return 0
    except Exception as exc:
        logging.exception("Desktop startup/shutdown failed")
        message = f"{exc}\n\n詳細は保存先のdesktop.logを確認してください。画面を開けない場合はMicrosoft Edge WebView2 Runtimeも確認してください。"
        if args.smoke_report:
            args.smoke_report.parent.mkdir(parents=True, exist_ok=True)
            args.smoke_report.write_text(json.dumps({"ok": False, "error": message}, ensure_ascii=False), encoding="utf-8")
        else:
            ctypes.windll.user32.MessageBoxW(None, message, "参加型整列プラグイン — 起動エラー", 0x10)
        return 1
