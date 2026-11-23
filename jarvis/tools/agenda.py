from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_REMINDER_PREFIX_RE = re.compile(r"^(?:jarvis[,\s]+)?", re.IGNORECASE)
_RELATIVE_REMINDER_RE = re.compile(
    r"^(?:recu[eé]rdame|remind\s+me)\s+(?:en|in)\s+(\d+)\s+"
    r"(minutos?|mins?|horas?|hrs?|h|minutes?|hours?)\s+(?:de\s+|que\s+|to\s+)?(.+)$",
    re.IGNORECASE,
)
_ABS_TIME_FIRST_RE = re.compile(
    r"^(?:recu[eé]rdame|remind\s+me|ag[eé]ndame|agenda)\s+"
    r"(?:(hoy|ma[ñn]ana|today|tomorrow)\s+)?"
    r"(?:a\s+las?|at)\s+(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?\s+(.+)$",
    re.IGNORECASE,
)
_ABS_TITLE_FIRST_RE = re.compile(
    r"^(?:recu[eé]rdame|remind\s+me|ag[eé]ndame|agenda)\s+(.+?)\s+"
    r"(?:(hoy|ma[ñn]ana|today|tomorrow)\s+)?"
    r"(?:a\s+las?|at)\s+(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?$",
    re.IGNORECASE,
)


def _resolve_absolute_when(
    ref_now: datetime,
    day_word: str | None,
    hour_str: str,
    minute_str: str | None,
    meridiem: str | None,
) -> datetime | None:
    hour = int(hour_str)
    minute = int(minute_str) if minute_str is not None else 0
    if minute > 59:
        return None

    mer = meridiem.lower().replace(".", "") if meridiem else None
    if mer in {"am", "pm"}:
        if hour < 1 or hour > 12:
            return None
        if mer == "pm" and hour < 12:
            hour += 12
        elif mer == "am" and hour == 12:
            hour = 0
    elif hour > 23:
        return None

    day_norm = day_word.lower() if day_word else None
    day_offset = 1 if day_norm in {"mañana", "manana", "tomorrow"} else 0
    target = ref_now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(
        days=day_offset
    )
    if day_norm is None and target <= ref_now:
        target += timedelta(days=1)
    return target


def parse_spanish_reminder(
    text: str, now: datetime | None = None
) -> dict[str, str] | None:
    """Parse common Spanish/English reminder commands into {'title', 'when'}."""
    clean = _REMINDER_PREFIX_RE.sub("", text.strip().lstrip("¿¡")).strip()
    clean = clean.rstrip(".!?").strip()
    if not clean:
        return None

    ref_now = (now or datetime.now()).replace(tzinfo=None, microsecond=0)

    rel_match = _RELATIVE_REMINDER_RE.match(clean)
    if rel_match:
        amount = int(rel_match.group(1))
        unit = rel_match.group(2).lower()
        title = rel_match.group(3).strip(" .!?")
        if amount <= 0 or not title:
            return None
        delta = (
            timedelta(hours=amount)
            if unit.startswith(("h", "hour"))
            else timedelta(minutes=amount)
        )
        target = ref_now + delta
        return {"title": title, "when": target.strftime("%Y-%m-%dT%H:%M:%S")}

    abs_first = _ABS_TIME_FIRST_RE.match(clean)
    if abs_first:
        day_word, hour_s, min_s, mer, raw_title = abs_first.groups()
        title = raw_title.strip(" .!?")
        if title:
            target = _resolve_absolute_when(ref_now, day_word, hour_s, min_s, mer)
            if target is not None:
                return {"title": title, "when": target.strftime("%Y-%m-%dT%H:%M:%S")}

    abs_title = _ABS_TITLE_FIRST_RE.match(clean)
    if abs_title:
        raw_title, day_word, hour_s, min_s, mer = abs_title.groups()
        title = raw_title.strip(" .!?")
        if title:
            target = _resolve_absolute_when(ref_now, day_word, hour_s, min_s, mer)
            if target is not None:
                return {"title": title, "when": target.strftime("%Y-%m-%dT%H:%M:%S")}

    return None


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
                notes TEXT NOT NULL DEFAULT '',
                notified INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        cols = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(events)").fetchall()
        }
        if "notified" not in cols:
            self._conn.execute(
                "ALTER TABLE events ADD COLUMN notified INTEGER NOT NULL DEFAULT 0"
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

    def due_unnotified(self, now: str | None = None) -> list[AgendaEvent]:
        cutoff = now or datetime.now().replace(microsecond=0).isoformat()
        rows = self._conn.execute(
            "SELECT id, title, event_when, notes FROM events WHERE notified = 0 AND event_when <= ? ORDER BY event_when ASC",
            (cutoff,),
        ).fetchall()
        return [
            AgendaEvent(id=r["id"], title=r["title"], when=r["event_when"], notes=r["notes"])
            for r in rows
        ]

    def mark_notified(self, event_id: int) -> None:
        self._conn.execute(
            "UPDATE events SET notified = 1 WHERE id = ?",
            (event_id,),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
