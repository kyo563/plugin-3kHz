from __future__ import annotations

from copy import deepcopy
from typing import Callable


class PersistenceService:
    def __init__(self, initial_state: dict):
        self._initial_state = deepcopy(initial_state)
        self._state = deepcopy(initial_state)

    def get_state(self) -> dict:
        return self._state

    def set_state(self, state: dict) -> None:
        self._state = state

    def reset_state(self) -> dict:
        self._state = deepcopy(self._initial_state)
        return self._state

    def mutate_state(self, callback: Callable[[dict], None]) -> dict:
        callback(self._state)
        return self._state
