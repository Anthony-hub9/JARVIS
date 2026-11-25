from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import jarvis.voice.tts as tts_mod
from jarvis.voice.tts import LocalTTSEngine


def _make_fake_communicate(audio_chunks: list[bytes]):
    class FakeCommunicate:
        def __init__(self, text: str, voice: str, *, rate: str, pitch: str) -> None:
            self.text = text
            self.voice = voice
            self.rate = rate
            self.pitch = pitch

        async def stream(self):
            for chunk in audio_chunks:
                yield {"type": "audio", "data": chunk}

    return FakeCommunicate


@pytest.fixture(autouse=True)
def _reset_rvc_singleton():
    tts_mod._rvc_loader = None
    yield
    tts_mod._rvc_loader = None


@pytest.mark.asyncio
async def test_albedo_rvc_conversion_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pth_file = tmp_path / "albedo.pth"
    pth_file.write_bytes(b"fake-pth")
    index_file = tmp_path / "albedo.index"
    index_file.write_bytes(b"fake-index")

    monkeypatch.setattr(tts_mod, "_ALBEDO_MODEL_PATH", pth_file)
    monkeypatch.setattr(tts_mod, "_ALBEDO_INDEX_PATH", index_file)

    fake_wav = b"RIFF\x24\x00\x00\x00WAVEfmt RVC"
    calls: list[dict[str, object]] = []
    created_outputs: list[Path] = []
    created_inputs: list[Path] = []

    class FakeBaseLoader:
        def __init__(self, only_cpu: bool = False, **kwargs) -> None:
            calls.append({"init_only_cpu": only_cpu})

        def apply_conf(self, **kwargs) -> str:
            calls.append({"apply_conf": kwargs})
            return "OK"

        def __call__(self, audio_files, **kwargs):
            in_path = Path(audio_files)
            created_inputs.append(in_path)
            assert in_path.read_bytes() == b"BASE_MP3"
            out_path = in_path.with_name("albedo_out.wav")
            out_path.write_bytes(fake_wav)
            created_outputs.append(out_path)
            calls.append({"call_kwargs": kwargs})
            return [str(out_path)]

    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    fake_rvc_pkg = SimpleNamespace(BaseLoader=FakeBaseLoader)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "infer_rvc_python", fake_rvc_pkg)

    engine = LocalTTSEngine(powershell_exe="powershell.exe")
    with patch(
        "jarvis.voice.tts.edge_tts.Communicate",
        _make_fake_communicate([b"BASE_", b"MP3"]),
    ):
        audio_bytes, media_type = await engine.synthesize_audio(
            "Hola señor", profile="albedo"
        )

    assert audio_bytes == fake_wav
    assert media_type == "audio/wav"
    assert calls[0] == {"init_only_cpu": True}
    assert calls[1] == {
        "apply_conf": {
            "tag": "albedo",
            "file_model": str(pth_file),
            "pitch_algo": "pm",
            "file_index": str(index_file),
        }
    }
    assert tts_mod._rvc_loader is not None
    assert not created_inputs[0].exists()
    assert not created_outputs[0].exists()

    scripts_dir = str(Path(sys.executable).resolve().parent)
    if Path(scripts_dir).name.lower() == "scripts":
        assert scripts_dir in os.environ.get("PATH", "").split(os.pathsep)


@pytest.mark.asyncio
async def test_albedo_rvc_uses_rmvpe_on_cuda(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pth_file = tmp_path / "albedo.pth"
    pth_file.write_bytes(b"fake-pth")
    missing_index = tmp_path / "missing.index"

    monkeypatch.setattr(tts_mod, "_ALBEDO_MODEL_PATH", pth_file)
    monkeypatch.setattr(tts_mod, "_ALBEDO_INDEX_PATH", missing_index)

    recorded_conf: dict[str, object] = {}

    class FakeBaseLoader:
        def __init__(self, only_cpu: bool = False, **kwargs) -> None:
            recorded_conf["only_cpu"] = only_cpu

        def apply_conf(self, **kwargs) -> str:
            recorded_conf.update(kwargs)
            return "OK"

        def __call__(self, audio_files, **kwargs):
            out_path = Path(audio_files).with_suffix(".wav")
            out_path.write_bytes(b"RIFFWAVE")
            return [str(out_path)]

    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True))
    fake_rvc_pkg = SimpleNamespace(BaseLoader=FakeBaseLoader)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "infer_rvc_python", fake_rvc_pkg)

    engine = LocalTTSEngine(powershell_exe="powershell.exe")
    with patch(
        "jarvis.voice.tts.edge_tts.Communicate",
        _make_fake_communicate([b"MP3"]),
    ):
        audio_bytes, media_type = await engine.synthesize_audio("Prueba", profile="albedo")

    assert audio_bytes == b"RIFFWAVE"
    assert media_type == "audio/wav"
    assert recorded_conf["only_cpu"] is False
    assert recorded_conf["pitch_algo"] == "rmvpe"
    assert recorded_conf["file_index"] == ""


@pytest.mark.asyncio
async def test_albedo_falls_back_when_model_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    missing_pth = tmp_path / "does_not_exist.pth"
    monkeypatch.setattr(tts_mod, "_ALBEDO_MODEL_PATH", missing_pth)

    engine = LocalTTSEngine(powershell_exe="powershell.exe")
    with (
        caplog.at_level(logging.WARNING, logger="jarvis.voice.tts"),
        patch(
            "jarvis.voice.tts.edge_tts.Communicate",
            _make_fake_communicate([b"BASE_MP3"]),
        ),
    ):
        audio_bytes, media_type = await engine.synthesize_audio(
            "Sin modelo", profile="albedo"
        )

    assert audio_bytes == b"BASE_MP3"
    assert media_type == "audio/mpeg"
    assert any("no encontrado" in rec.message.lower() for rec in caplog.records)


@pytest.mark.asyncio
async def test_albedo_falls_back_when_rvc_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    pth_file = tmp_path / "albedo.pth"
    pth_file.write_bytes(b"fake-pth")
    monkeypatch.setattr(tts_mod, "_ALBEDO_MODEL_PATH", pth_file)
    monkeypatch.setattr(tts_mod, "_ALBEDO_INDEX_PATH", tmp_path / "albedo.index")

    class FailingBaseLoader:
        def __init__(self, **kwargs) -> None:
            pass

        def apply_conf(self, **kwargs) -> str:
            return "OK"

        def __call__(self, audio_files, **kwargs):
            raise RuntimeError("RVC boom")

    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    fake_rvc_pkg = SimpleNamespace(BaseLoader=FailingBaseLoader)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "infer_rvc_python", fake_rvc_pkg)

    engine = LocalTTSEngine(powershell_exe="powershell.exe")
    with (
        caplog.at_level(logging.WARNING, logger="jarvis.voice.tts"),
        patch(
            "jarvis.voice.tts.edge_tts.Communicate",
            _make_fake_communicate([b"BASE_MP3"]),
        ),
    ):
        audio_bytes, media_type = await engine.synthesize_audio(
            "Fallo RVC", profile="albedo"
        )

    assert audio_bytes == b"BASE_MP3"
    assert media_type == "audio/mpeg"
    assert any("RVC boom" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_jarvis_profile_skips_rvc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pth_file = tmp_path / "albedo.pth"
    pth_file.write_bytes(b"fake-pth")
    monkeypatch.setattr(tts_mod, "_ALBEDO_MODEL_PATH", pth_file)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("RVC should not run for jarvis profile")

    monkeypatch.setattr(tts_mod, "_convert_audio_to_rvc_wav", fail_if_called)

    engine = LocalTTSEngine(powershell_exe="powershell.exe")
    with patch(
        "jarvis.voice.tts.edge_tts.Communicate",
        _make_fake_communicate([b"JARVIS_MP3"]),
    ):
        audio_bytes, media_type = await engine.synthesize_audio(
            "Buenos días", profile="jarvis"
        )

    assert audio_bytes == b"JARVIS_MP3"
    assert media_type == "audio/mpeg"


def test_preload_albedo_rvc_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pth_file = tmp_path / "albedo.pth"
    pth_file.write_bytes(b"fake-pth")
    index_file = tmp_path / "albedo.index"
    index_file.write_bytes(b"fake-index")

    monkeypatch.setattr(tts_mod, "_ALBEDO_MODEL_PATH", pth_file)
    monkeypatch.setattr(tts_mod, "_ALBEDO_INDEX_PATH", index_file)

    class FakeBaseLoader:
        def __init__(self, only_cpu: bool = False, **kwargs) -> None:
            self.only_cpu = only_cpu

        def apply_conf(self, **kwargs) -> str:
            return "OK"

    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    fake_rvc_pkg = SimpleNamespace(BaseLoader=FakeBaseLoader)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "infer_rvc_python", fake_rvc_pkg)

    assert tts_mod.preload_albedo_rvc() is True
    assert tts_mod._rvc_loader is not None


def test_preload_albedo_rvc_missing_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tts_mod, "_ALBEDO_MODEL_PATH", tmp_path / "missing.pth")

    assert tts_mod.preload_albedo_rvc() is False
    assert tts_mod._rvc_loader is None


def test_preload_albedo_rvc_handles_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    pth_file = tmp_path / "albedo.pth"
    pth_file.write_bytes(b"fake-pth")
    monkeypatch.setattr(tts_mod, "_ALBEDO_MODEL_PATH", pth_file)
    monkeypatch.setattr(tts_mod, "_ALBEDO_INDEX_PATH", tmp_path / "missing.index")

    class BrokenBaseLoader:
        def __init__(self, **kwargs) -> None:
            raise RuntimeError("preload boom")

    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    fake_rvc_pkg = SimpleNamespace(BaseLoader=BrokenBaseLoader)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "infer_rvc_python", fake_rvc_pkg)

    with caplog.at_level(logging.WARNING, logger="jarvis.voice.tts"):
        assert tts_mod.preload_albedo_rvc() is False

    assert tts_mod._rvc_loader is None
    assert any("preload boom" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_albedo_offline_sapi5_runs_rvc_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pth_file = tmp_path / "albedo.pth"
    pth_file.write_bytes(b"fake-pth")
    index_file = tmp_path / "albedo.index"
    index_file.write_bytes(b"fake-index")

    monkeypatch.setattr(tts_mod, "_ALBEDO_MODEL_PATH", pth_file)
    monkeypatch.setattr(tts_mod, "_ALBEDO_INDEX_PATH", index_file)

    seen_suffixes: list[str] = []

    class FakeBaseLoader:
        def __init__(self, **kwargs) -> None:
            pass

        def apply_conf(self, **kwargs) -> str:
            return "OK"

        def __call__(self, audio_files, **kwargs):
            in_path = Path(audio_files)
            seen_suffixes.append(in_path.suffix)
            assert in_path.read_bytes() == b"SAPI5_WAV"
            out_path = in_path.with_name("albedo_offline.wav")
            out_path.write_bytes(b"RVC_OFFLINE_WAV")
            return [str(out_path)]

    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    fake_rvc_pkg = SimpleNamespace(BaseLoader=FakeBaseLoader)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "infer_rvc_python", fake_rvc_pkg)

    engine = LocalTTSEngine(powershell_exe="powershell.exe")

    async def fake_sapi5(_text: str) -> bytes:
        return b"SAPI5_WAV"

    monkeypatch.setattr(engine, "synthesize_wav", fake_sapi5)

    with patch(
        "jarvis.voice.tts.edge_tts.Communicate",
        side_effect=RuntimeError("offline"),
    ):
        audio_bytes, media_type = await engine.synthesize_audio(
            "Modo offline", profile="albedo"
        )

    assert audio_bytes == b"RVC_OFFLINE_WAV"
    assert media_type == "audio/wav"
    assert seen_suffixes == [".wav"]


@pytest.mark.asyncio
async def test_albedo_offline_sapi5_falls_back_to_plain_wav_when_rvc_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    pth_file = tmp_path / "albedo.pth"
    pth_file.write_bytes(b"fake-pth")
    monkeypatch.setattr(tts_mod, "_ALBEDO_MODEL_PATH", pth_file)
    monkeypatch.setattr(tts_mod, "_ALBEDO_INDEX_PATH", tmp_path / "albedo.index")

    class FailingBaseLoader:
        def __init__(self, **kwargs) -> None:
            pass

        def apply_conf(self, **kwargs) -> str:
            return "OK"

        def __call__(self, audio_files, **kwargs):
            raise RuntimeError("RVC offline boom")

    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    fake_rvc_pkg = SimpleNamespace(BaseLoader=FailingBaseLoader)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "infer_rvc_python", fake_rvc_pkg)

    engine = LocalTTSEngine(powershell_exe="powershell.exe")

    async def fake_sapi5(_text: str) -> bytes:
        return b"SAPI5_WAV"

    monkeypatch.setattr(engine, "synthesize_wav", fake_sapi5)

    with (
        caplog.at_level(logging.WARNING, logger="jarvis.voice.tts"),
        patch(
            "jarvis.voice.tts.edge_tts.Communicate",
            side_effect=RuntimeError("offline"),
        ),
    ):
        audio_bytes, media_type = await engine.synthesize_audio(
            "Sin RVC offline", profile="albedo"
        )

    assert audio_bytes == b"SAPI5_WAV"
    assert media_type == "audio/wav"
    assert any("RVC offline boom" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_audio_cache_hit_avoids_edge_tts_and_rvc_second_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pth_file = tmp_path / "albedo.pth"
    pth_file.write_bytes(b"fake-pth")
    monkeypatch.setattr(tts_mod, "_ALBEDO_MODEL_PATH", pth_file)
    monkeypatch.setattr(tts_mod, "_ALBEDO_INDEX_PATH", tmp_path / "albedo.index")

    edge_calls = 0
    rvc_calls = 0

    class CountingCommunicate:
        def __init__(self, text: str, voice: str, *, rate: str, pitch: str) -> None:
            nonlocal edge_calls
            edge_calls += 1

        async def stream(self):
            yield {"type": "audio", "data": b"MP3_DATA"}

    class CountingBaseLoader:
        def __init__(self, **kwargs) -> None:
            pass

        def apply_conf(self, **kwargs) -> str:
            return "OK"

        def __call__(self, audio_files, **kwargs):
            nonlocal rvc_calls
            rvc_calls += 1
            out_path = Path(audio_files).with_suffix(".wav")
            out_path.write_bytes(b"RVC_CACHED_WAV")
            return [str(out_path)]

    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    fake_rvc_pkg = SimpleNamespace(BaseLoader=CountingBaseLoader)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "infer_rvc_python", fake_rvc_pkg)

    engine = LocalTTSEngine(powershell_exe="powershell.exe")
    with patch("jarvis.voice.tts.edge_tts.Communicate", CountingCommunicate):
        first = await engine.synthesize_audio("  Hola señor  ", profile="albedo")
        second = await engine.synthesize_audio("Hola señor", profile="albedo")

    assert first == (b"RVC_CACHED_WAV", "audio/wav")
    assert second == first
    assert edge_calls == 1
    assert rvc_calls == 1

    # Long text (> max_cached_chars=220) must not be cached
    long_text = "x" * 221
    with patch("jarvis.voice.tts.edge_tts.Communicate", CountingCommunicate):
        await engine.synthesize_audio(long_text, profile="jarvis")
        await engine.synthesize_audio(long_text, profile="jarvis")

    assert edge_calls == 3
