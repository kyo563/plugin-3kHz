"""Local OneComme setup state, separate from queue operations and undo."""
import json
import sqlite3
from threading import RLock
from pydantic import BaseModel, ConfigDict, Field


class SetupPreferences(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    completed: bool = False
    deferred: bool = False
    step: int = Field(default=0, ge=0, le=4)
    use_bot: bool = False
    use_obs: bool = True


class SetupStore:
    def __init__(self, path):
        self.path, self.lock = path, RLock()
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS setup_preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL)')

    def read(self, key, default):
        with self.lock, sqlite3.connect(self.path) as db:
            row = db.execute('SELECT value FROM setup_preferences WHERE key=?', (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def write(self, key, value):
        with self.lock, sqlite3.connect(self.path) as db:
            db.execute('INSERT OR REPLACE INTO setup_preferences VALUES (?, ?)', (key, json.dumps(value)))

    def settings(self):
        return SetupPreferences.model_validate(self.read('setup', {}))
