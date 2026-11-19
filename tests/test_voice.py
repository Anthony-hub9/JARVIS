from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.voice.tts import VOICE_PROFILES, LocalTTSEngine, TTSError


@pytest.mark.asyncio
async def test_synthesize_wav_rejects_empty_text() -> None:
    engine = LocalTTSEngine(powershell_exe="powershell.exe")
    with pytest.raises(ValueError, match="vacío"):
        await engine.synthesize_wav("   ")


@pytest.mark.asyncio
async def test_synthesize_wav_rejects_too_long_text() -> None:
    engine = LocalTTSEngine(max_length=20, powershell_exe="powershell.exe")
    with pytest.raises(ValueError, match="20"):
        await engine.synthesize_wav("a" * 21)


@pytest.mark.asyncio
async def test_synthesize_wav_unavailable_on_non_windows() -> None:
    engine = LocalTTSEngine()
    with patch("jarvis.voice.tts.sys.platform", "linux"):
        with pytest.raises(TTSError, match="Windows"):
            await engine.synthesize_wav("Hola mundo")


@pytest.mark.asyncio
async def test_synthesize_wav_success_and_cleanup() -> None:
    engine = LocalTTSEngine(powershell_exe="powershell.exe")
    created_paths: list[Path] = []
    fake_wav = b"RIFF\x24\x00\x00\x00WAVEfmt "

    async def fake_exec(*args, **kwargs):
        env = kwargs["env"]
        assert env["JARVIS_TTS_TEXT"] == "Hola JARVIS"
        out_path = Path(env["JARVIS_TTS_OUT"])
        created_paths.append(out_path)
        out_path.write_bytes(fake_wav)

        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        return proc

    with patch("jarvis.voice.tts.asyncio.create_subprocess_exec", side_effect=fake_exec):
        result = await engine.synthesize_wav("  Hola JARVIS  ")

    assert result == fake_wav
    assert len(created_paths) == 1
    assert not created_paths[0].exists()


@pytest.mark.asyncio
async def test_synthesize_wav_nonzero_exit_raises_and_cleans_up() -> None:
    engine = LocalTTSEngine(powershell_exe="powershell.exe")
    created_paths: list[Path] = []

    async def fake_exec(*args, **kwargs):
        out_path = Path(kwargs["env"]["JARVIS_TTS_OUT"])
        created_paths.append(out_path)

        proc = MagicMock()
        proc.returncode = 1
        proc.communicate = AsyncMock(return_value=(b"", b"Synth failed"))
        return proc

    with patch("jarvis.voice.tts.asyncio.create_subprocess_exec", side_effect=fake_exec):
        with pytest.raises(TTSError, match="Synth failed"):
            await engine.synthesize_wav("Prueba de error")

    assert len(created_paths) == 1
    assert not created_paths[0].exists()


@pytest.mark.asyncio
async def test_synthesize_wav_timeout_kills_process() -> None:
    engine = LocalTTSEngine(timeout=0.05, powershell_exe="powershell.exe")
    proc = MagicMock()
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=None)

    async def slow_communicate():
        await asyncio.sleep(1.0)
        return b"", b""

    proc.communicate = slow_communicate

    with patch(
        "jarvis.voice.tts.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=proc),
    ):
        with pytest.raises(TTSError, match="Tiempo de espera"):
            await engine.synthesize_wav("Hola")

    proc.kill.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile", "expected_voice", "expected_rate", "expected_pitch"),
    [
        ("jarvis", "es-MX-JorgeNeural", "-4%", "-6Hz"),
        ("albedo", "es-MX-DaliaNeural", "-5%", "+2Hz"),
    ],
)
async def test_synthesize_audio_neural_profiles(
    profile: str,
    expected_voice: str,
    expected_rate: str,
    expected_pitch: str,
) -> None:
    engine = LocalTTSEngine(powershell_exe="powershell.exe")
    captured: dict[str, object] = {}

    class FakeCommunicate:
        def __init__(self, text: str, voice: str, *, rate: str, pitch: str) -> None:
            captured["text"] = text
            captured["voice"] = voice
            captured["rate"] = rate
            captured["pitch"] = pitch

        async def stream(self):
            yield {"type": "WordBoundary", "data": None}
            yield {"type": "audio", "data": b"ID3"}
            yield {"type": "audio", "data": b"\x00\x01MP3"}

    assert profile in VOICE_PROFILES
    with patch("jarvis.voice.tts.edge_tts.Communicate", FakeCommunicate):
        audio_bytes, media_type = await engine.synthesize_audio(
            "  Buenos días señor  ", profile=profile
        )

    assert audio_bytes == b"ID3\x00\x01MP3"
    assert media_type == "audio/mpeg"
    assert captured == {
        "text": "Buenos días señor",
        "voice": expected_voice,
        "rate": expected_rate,
        "pitch": expected_pitch,
    }


@pytest.mark.asyncio
async def test_synthesize_audio_falls_back_to_sapi5_on_edge_tts_error() -> None:
    engine = LocalTTSEngine(powershell_exe="powershell.exe")
    fake_wav = b"RIFF\x24\x00\x00\x00WAVEfmt "

    class FailingCommunicate:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def stream(self):
            raise RuntimeError("offline")
            yield  # pragma: no cover

    with (
        patch("jarvis.voice.tts.edge_tts.Communicate", FailingCommunicate),
        patch.object(
            engine, "synthesize_wav", new=AsyncMock(return_value=fake_wav)
        ) as wav_mock,
    ):
        audio_bytes, media_type = await engine.synthesize_audio(
            "Modo sin conexión", profile="albedo"
        )

    assert audio_bytes == fake_wav
    assert media_type == "audio/wav"
    wav_mock.assert_awaited_once_with("Modo sin conexión")
