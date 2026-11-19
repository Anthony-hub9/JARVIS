from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.tools.memory import MemoryStore


def test_memory_turns_shared_across_devices() -> None:
    store = MemoryStore(":memory:")
    try:
        store.add_turn("laptop", "user", "Hola JARVIS")
        store.add_turn("laptop", "assistant", "Hola, ¿en qué te ayudo?")
        store.add_turn("s24_plus", "user", "¿Qué quedamos?")
        store.add_turn("s24_plus", "assistant", "Seguimos con el proyecto.")

        recent = store.recent_turns(limit=3)
        assert len(recent) == 3
        assert [(t.device_id, t.role, t.content) for t in recent] == [
            ("laptop", "assistant", "Hola, ¿en qué te ayudo?"),
            ("s24_plus", "user", "¿Qué quedamos?"),
            ("s24_plus", "assistant", "Seguimos con el proyecto."),
        ]
        assert store.recent_turns(limit=0) == []
    finally:
        store.close()


def test_memory_facts_save_upsert_and_case_insensitive_search(tmp_path: Path) -> None:
    db_file = tmp_path / "jarvis_memory.db"
    store1 = MemoryStore(db_file)
    try:
        f1 = store1.save_fact("proyecto_actual", "JARVIS Hub Local")
        assert f1.key == "proyecto_actual"
        assert f1.value == "JARVIS Hub Local"

        # Upsert existing key
        f1_updated = store1.save_fact("proyecto_actual", "JARVIS Hub v2")
        assert f1_updated.value == "JARVIS Hub v2"

        store1.save_fact("gpu_laptop", "GTX 1650 Ti 4GB")
    finally:
        store1.close()

    # Re-open from disk to verify persistence
    store2 = MemoryStore(db_file)
    try:
        by_key = store2.search_facts("PROYECTO")
        assert len(by_key) == 1
        assert by_key[0].value == "JARVIS Hub v2"

        by_val = store2.search_facts("gtx 1650")
        assert len(by_val) == 1
        assert by_val[0].key == "gpu_laptop"

        all_facts = store2.search_facts("", limit=5)
        assert len(all_facts) == 2

        with pytest.raises(ValueError):
            store2.save_fact("   ", "algo")
    finally:
        store2.close()
