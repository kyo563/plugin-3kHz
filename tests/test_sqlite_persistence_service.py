import sqlite3
import sys
import threading
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.sqlite_persistence_service import SQLitePersistenceService

INITIAL = {
    "is_open": True,
    "priority_mode": True,
    "cooldown_seconds": 40,
    "current": [],
    "waiting": [],
    "user_action_locks": {},
    "show_declared_player_name_on_overlay": False,
    "participation_counts": {},
    "logs": ["init"],
}


def _sample_state():
    return {
        "is_open": False,
        "priority_mode": False,
        "cooldown_seconds": 30,
        "current": [{"user_id": "u1", "display_name": "A", "participation_count": 1}],
        "waiting": [
            {"user_id": "w1", "display_name": "W1", "participation_count": 0},
            {"user_id": "w2", "display_name": "W2", "participation_count": 0},
            {"user_id": "w3", "display_name": "W3", "participation_count": 0},
            {"user_id": "w4", "display_name": "W4", "participation_count": 0},
            {"user_id": "x", "display_name": "参加者募集中", "participation_count": 0, "is_placeholder": True},
        ],
        "user_action_locks": {"comment:abc": "2026-01-01T00:00:40+00:00"},
        "show_declared_player_name_on_overlay": False,
        "participation_counts": {"comment:u1": 1, "comment:w1": -2},
        "logs": ["one", "two"],
    }


def test_sqlite_persists_and_restores_state(tmp_path):
    db_path = tmp_path / "state.sqlite3"
    service1 = SQLitePersistenceService(initial_state=INITIAL, db_path=str(db_path))
    service1.set_state(_sample_state())

    service2 = SQLitePersistenceService(initial_state=INITIAL, db_path=str(db_path))
    restored = service2.get_state()

    assert restored["is_open"] is False
    assert restored["priority_mode"] is False
    assert len(restored["waiting"]) == 4
    assert restored["logs"] == ["one", "two"]
    assert restored["participation_counts"] == {"comment:u1": 1, "comment:w1": 0}


def test_reset_state_restores_initial_and_db(tmp_path):
    db_path = tmp_path / "state.sqlite3"
    service = SQLitePersistenceService(initial_state=INITIAL, db_path=str(db_path))
    service.set_state(_sample_state())

    reset = service.reset_state()

    assert reset["is_open"] is True
    assert reset["waiting"] == []
    assert reset["logs"] == ["init"]


def test_no_next_status_and_no_placeholder_persisted(tmp_path):
    db_path = tmp_path / "state.sqlite3"
    service = SQLitePersistenceService(initial_state=INITIAL, db_path=str(db_path))
    service.set_state(_sample_state())

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT status, display_name FROM participants ORDER BY id").fetchall()

    assert all(status in ("current", "waiting") for status, _ in rows)
    assert all(name != "参加者募集中" for _, name in rows)


def test_user_action_locks_broken_json_fallback_and_old_db_compat(tmp_path):
    db_path = tmp_path / "state.sqlite3"
    service = SQLitePersistenceService(initial_state=INITIAL, db_path=str(db_path))

    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM app_state WHERE key = ?", ("user_action_locks",))
        conn.execute("INSERT OR REPLACE INTO app_state(key, value) VALUES(?, ?)", ("user_action_locks", "{bad json"))

    restored = service.get_state()
    assert restored["user_action_locks"] == {}


def test_participation_counts_broken_json_fallback_and_old_db_compat(tmp_path):
    db_path = tmp_path / "state.sqlite3"
    service = SQLitePersistenceService(initial_state=INITIAL, db_path=str(db_path))
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM app_state WHERE key = ?", ("participation_counts",))
        conn.execute("INSERT OR REPLACE INTO app_state(key, value) VALUES(?, ?)", ("participation_counts", "{bad json"))
    restored = service.get_state()
    assert restored["participation_counts"] == {}


def test_user_action_locks_saved_and_no_userkey_in_db(tmp_path):
    db_path = tmp_path / "state.sqlite3"
    service = SQLitePersistenceService(initial_state=INITIAL, db_path=str(db_path))
    state = _sample_state()
    state["user_action_locks"] = {"comment:hashed": "2026-01-01T00:00:40+00:00"}
    service.set_state(state)

    restored = service.get_state()
    assert restored["user_action_locks"] == state["user_action_locks"]

    with sqlite3.connect(db_path) as conn:
        values = "\n".join(v for (v,) in conn.execute("SELECT value FROM app_state").fetchall())
    assert "user-raw" not in values


def test_mutate_state_is_serialized(tmp_path):
    db_path = tmp_path / "state.sqlite3"
    service = SQLitePersistenceService(initial_state=INITIAL, db_path=str(db_path))

    entered = threading.Event()
    release = threading.Event()
    order = []

    def first_callback(state):
        order.append("first_enter")
        entered.set()
        release.wait(timeout=1)
        state["logs"].append("first")

    def second_callback(state):
        order.append("second_enter")
        state["logs"].append("second")

    t1 = threading.Thread(target=lambda: service.mutate_state(first_callback))
    t2 = threading.Thread(target=lambda: service.mutate_state(second_callback))

    t1.start()
    entered.wait(timeout=1)
    t2.start()
    time.sleep(0.05)

    assert order == ["first_enter"]

    release.set()
    t1.join(timeout=2)
    t2.join(timeout=2)

    assert order == ["first_enter", "second_enter"]


def test_concurrent_mutate_state_does_not_lose_updates(tmp_path):
    db_path = tmp_path / "state.sqlite3"
    service = SQLitePersistenceService(initial_state=INITIAL, db_path=str(db_path))

    def add_log(message):
        service.mutate_state(lambda state: state["logs"].append(message))

    t1 = threading.Thread(target=add_log, args=("a",))
    t2 = threading.Thread(target=add_log, args=("b",))

    t1.start()
    t2.start()
    t1.join(timeout=2)
    t2.join(timeout=2)

    logs = service.get_state()["logs"]
    assert "a" in logs
    assert "b" in logs
