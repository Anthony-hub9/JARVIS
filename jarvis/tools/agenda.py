import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class AgendaEvent:
    id: int
    title: str
    when: str
    notes: str = ""


class AgendaStore:
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                event_when TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self._conn.commit()

    def add_event(self, title: str, when: str, notes: str = "") -> AgendaEvent:
        cur = self._conn.execute(
            "INSERT INTO events (title, event_when, notes) VALUES (?, ?, ?)",
            (title, when, notes),
        )
        self._conn.commit()
        return AgendaEvent(id=cur.lastrowid or 0, title=title, when=when, notes=notes)

    def list_events(self) -> list[AgendaEvent]:
        rows = self._conn.execute(
            "SELECT id, title, event_when, notes FROM events ORDER BY event_when ASC"
        ).fetchall()
        return [
            AgendaEvent(id=r["id"], title=r["title"], when=r["event_when"], notes=r["notes"])
            for r in rows
        ]

    def upcoming_reminders(self, now: str | None = None) -> list[AgendaEvent]:
        cutoff = now or datetime.now(timezone.utc).isoformat()
        rows = self._conn.execute(
            "SELECT id, title, event_when, notes FROM events WHERE event_when >= ? ORDER BY event_when ASC",
            (cutoff,),
        ).fetchall()
        return [
            AgendaEvent(id=r["id"], title=r["title"], when=r["event_when"], notes=r["notes"])
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()
