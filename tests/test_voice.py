from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.voice.tts import LocalTTSEngine, TTSError


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
