from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class AgendaEvent:
    id: int
    title: str
    when: str
    notes: str = ""


class GoogleCalendarSync:
    """Optional local OAuth adapter for Google Calendar; gracefully no-ops offline."""

    SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

    def __init__(
        self,
        credentials_path: str | Path = "credentials.json",
        token_path: str | Path = "token.json",
        calendar_id: str = "primary",
    ) -> None:
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.calendar_id = calendar_id

    def is_configured(self) -> bool:
        """Return True when local OAuth credentials file exists."""
        return self.credentials_path.is_file()

    def sync_event(self, event: AgendaEvent) -> bool:
        """Push an AgendaEvent to Google Calendar if configured, else no-op."""
        if not self.is_configured():
            logger.debug(
                "GoogleCalendarSync skipped: credentials file '%s' not found (offline SQLite mode).",
                self.credentials_path,
            )
            return False

        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError:
            logger.info(
                "GoogleCalendarSync skipped: google-api-python-client/google-auth-oauthlib not installed."
            )
            return False

        try:
            creds = None
            if self.token_path.is_file():
                creds = Credentials.from_authorized_user_file(str(self.token_path), self.SCOPES)
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self.credentials_path), self.SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                self.token_path.write_text(creds.to_json(), encoding="utf-8")

            start_dt = datetime.fromisoformat(event.when)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            end_dt = start_dt + timedelta(hours=1)

            service = build("calendar", "v3", credentials=creds)
            body = {
                "summary": event.title,
                "description": event.notes,
                "start": {"dateTime": start_dt.isoformat()},
                "end": {"dateTime": end_dt.isoformat()},
            }
            service.events().insert(calendarId=self.calendar_id, body=body).execute()
            return True
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("GoogleCalendarSync failed gracefully: %s", exc)
            return False


class AgendaStore:
    def __init__(
        self,
        db_path: str | Path = ":memory:",
        calendar_sync: GoogleCalendarSync | None = None,
    ) -> None:
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.calendar_sync = calendar_sync
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
        event = AgendaEvent(id=cur.lastrowid or 0, title=title, when=when, notes=notes)
        if self.calendar_sync is not None:
            self.calendar_sync.sync_event(event)
        return event

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
