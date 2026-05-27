import sqlite3
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.sqlite_persistence_service import SQLitePersistenceService

INITIAL = {
    "is_open": True,
    "priority_mode": True,
    "cooldown_seconds": 40,
    "current": [],
    "waiting": [],
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
