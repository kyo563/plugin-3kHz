"""Lazy compatibility facade for older direct-call tests; HTTP uses app.state."""
import os
from threading import Lock

from app.initial_state import INITIAL_STATE, TEST_USERS
from app.services.application_services import ApplicationServices
from app.services.queue_service import GROUP_SIZE, OPEN_SLOT_LABEL

_legacy_services = None
_legacy_lock = Lock()


def get_legacy_services() -> ApplicationServices:
    global _legacy_services
    with _legacy_lock:
        if _legacy_services is None:
            _legacy_services = ApplicationServices(desktop=os.environ.get("WAITING_LIST_DESKTOP") == "1")
        return _legacy_services


def __getattr__(name):
    aliases = {
        "_persistence_service": "persistence_service",
        "_queue_service": "queue_service",
        "_overlay_service": "overlay_service",
        "_add_counter": "add_counter",
    }
    target = aliases.get(name, name)
    if name in aliases or (not name.startswith("_") and hasattr(ApplicationServices, target)):
        return getattr(get_legacy_services(), target)
    raise AttributeError(name)
