from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from jarvis.config import settings


@dataclass
class MemoryTurn:
    id: int
    device_id: str
    role: str
    content: str
    created_at: str


@dataclass
class MemoryFact:
    id: int
    key: str
    value: str
    updated_at: str


class MemoryStore:
    """SQLite-backed short-term conversation turns and long-term facts shared across devices."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        resolved_path = settings.memory_db_path if db_path is None else db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(resolved_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL UNIQUE,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def add_turn(self, device_id: str, role: str, content: str) -> MemoryTurn:
        """Append a conversation turn to shared short-term memory."""
        created_at = datetime.now(timezone.utc).isoformat()
        clean_device = device_id.strip() or "unknown"
        clean_role = role.strip() or "user"
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO turns (device_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (clean_device, clean_role, content, created_at),
            )
            self._conn.commit()
            return MemoryTurn(
                id=cur.lastrowid or 0,
                device_id=clean_device,
                role=clean_role,
                content=content,
                created_at=created_at,
            )

    def recent_turns(self, limit: int = 8) -> list[MemoryTurn]:
        """Return up to `limit` most recent turns in chronological order."""
        if limit <= 0:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, device_id, role, content, created_at FROM turns ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        turns = [
            MemoryTurn(
                id=r["id"],
                device_id=r["device_id"],
                role=r["role"],
                content=r["content"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
        turns.reverse()
        return turns

    def save_fact(self, key: str, value: str) -> MemoryFact:
        """Insert or update a persistent long-term fact by key."""
        clean_key = key.strip()
        clean_value = value.strip()
        if not clean_key:
            raise ValueError("Fact key cannot be empty.")
        updated_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO facts (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (clean_key, clean_value, updated_at),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT id, key, value, updated_at FROM facts WHERE key = ?",
                (clean_key,),
            ).fetchone()
        return MemoryFact(
            id=row["id"],
            key=row["key"],
            value=row["value"],
            updated_at=row["updated_at"],
        )

    def search_facts(self, query: str, limit: int = 5) -> list[MemoryFact]:
        """Search persistent facts using case-insensitive LIKE on key and value."""
        if limit <= 0:
            return []
        clean_query = query.strip()
        with self._lock:
            if not clean_query:
                rows = self._conn.execute(
                    "SELECT id, key, value, updated_at FROM facts ORDER BY updated_at DESC, id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                pattern = f"%{clean_query}%"
                rows = self._conn.execute(
                    """
                    SELECT id, key, value, updated_at
                    FROM facts
                    WHERE LOWER(key) LIKE LOWER(?) OR LOWER(value) LIKE LOWER(?)
                    ORDER BY updated_at DESC, id DESC
                    LIMIT ?
                    """,
                    (pattern, pattern, limit),
                ).fetchall()
        return [
            MemoryFact(
                id=r["id"],
                key=r["key"],
                value=r["value"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
