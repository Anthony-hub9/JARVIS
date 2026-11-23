from datetime import datetime
import sqlite3

from jarvis.tools.agenda import AgendaStore, GoogleCalendarSync, parse_spanish_reminder


def test_add_and_list_events(tmp_path):
    db_file = tmp_path / "agenda.db"
    store = AgendaStore(db_file)
    try:
        e1 = store.add_event("Standup", "2026-11-20T09:00:00+00:00", notes="Daily sync")
        e2 = store.add_event("Dentist", "2026-11-19T16:00:00+00:00")

        events = store.list_events()
        assert len(events) == 2
        assert events[0].id == e2.id
        assert events[0].title == "Dentist"
        assert events[1].id == e1.id
        assert events[1].notes == "Daily sync"
    finally:
        store.close()


def test_upcoming_reminders():
    store = AgendaStore(":memory:")
    try:
        store.add_event("Past", "2026-11-18T10:00:00+00:00")
        store.add_event("Future1", "2026-11-20T10:00:00+00:00")
        store.add_event("Future2", "2026-11-21T10:00:00+00:00")

        upcoming = store.upcoming_reminders(now="2026-11-19T12:00:00+00:00")
        assert [e.title for e in upcoming] == ["Future1", "Future2"]
    finally:
        store.close()


def test_google_calendar_sync_graceful_fallback_without_credentials(tmp_path):
    sync = GoogleCalendarSync(
        credentials_path=tmp_path / "missing_credentials.json",
        token_path=tmp_path / "token.json",
    )
    assert sync.is_configured() is False

    store = AgendaStore(tmp_path / "agenda.db", calendar_sync=sync)
    try:
        event = store.add_event("Offline Event", "2026-11-22T15:00:00+00:00", notes="Local only")
        assert sync.sync_event(event) is False
        events = store.list_events()
        assert len(events) == 1
        assert events[0].title == "Offline Event"
    finally:
        store.close()


def test_parse_spanish_reminder_variants() -> None:
    now = datetime(2026, 11, 23, 10, 0, 0)

    rel_min = parse_spanish_reminder("recuérdame en 15 minutos llamar a mamá", now=now)
    assert rel_min == {"title": "llamar a mamá", "when": "2026-11-23T10:15:00"}

    rel_hr = parse_spanish_reminder("recuerdame en 2 horas apagar la estufa", now=now)
    assert rel_hr == {"title": "apagar la estufa", "when": "2026-11-23T12:00:00"}

    hoy_pm = parse_spanish_reminder("recuérdame hoy a las 3:30 pm junta de equipo", now=now)
    assert hoy_pm == {"title": "junta de equipo", "when": "2026-11-23T15:30:00"}

    manana_am = parse_spanish_reminder("recuérdame mañana a las 8 am tomar pastilla", now=now)
    assert manana_am == {"title": "tomar pastilla", "when": "2026-11-24T08:00:00"}

    agenda_title_first = parse_spanish_reminder("agenda dentista mañana a las 6 pm", now=now)
    assert agenda_title_first == {"title": "dentista", "when": "2026-11-24T18:00:00"}

    recuerdame_title_first = parse_spanish_reminder("recuérdame sacar la basura hoy a las 9 pm", now=now)
    assert recuerdame_title_first == {"title": "sacar la basura", "when": "2026-11-23T21:00:00"}

    assert parse_spanish_reminder("hola jarvis cómo estás", now=now) is None


def test_due_unnotified_and_mark_notified_and_migration(tmp_path) -> None:
    db_file = tmp_path / "legacy_agenda.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, event_when TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '')"
    )
    conn.execute(
        "INSERT INTO events (title, event_when, notes) VALUES (?, ?, ?)",
        ("Legacy Due", "2026-11-23T09:50:00", ""),
    )
    conn.commit()
    conn.close()

    store = AgendaStore(db_file)
    try:
        future = store.add_event("Future", "2026-11-23T11:00:00")
        due_now = store.due_unnotified(now="2026-11-23T10:00:00")
        assert [e.title for e in due_now] == ["Legacy Due"]

        store.mark_notified(due_now[0].id)
        assert store.due_unnotified(now="2026-11-23T10:00:00") == []

        later = store.due_unnotified(now="2026-11-23T11:05:00")
        assert [e.id for e in later] == [future.id]
    finally:
        store.close()
