from jarvis.tools.agenda import AgendaStore


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
