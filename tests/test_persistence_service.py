import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.persistence_service import PersistenceService


INITIAL = {
    "is_open": True,
    "current": [],
    "waiting": [],
    "logs": [],
}


def test_get_state_and_reset_state():
    service = PersistenceService(initial_state=INITIAL)

    state = service.get_state()
    state["is_open"] = False
    reset = service.reset_state()

    assert reset["is_open"] is True
    assert service.get_state()["is_open"] is True


def test_set_state_and_mutate_state_update_state():
    service = PersistenceService(initial_state=INITIAL)

    new_state = {"is_open": False, "current": [], "waiting": [], "logs": ["x"]}
    service.set_state(new_state)
    service.mutate_state(lambda state: state["logs"].append("y"))

    assert service.get_state()["is_open"] is False
    assert service.get_state()["logs"] == ["x", "y"]
