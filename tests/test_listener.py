from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
import speech_recognition as sr

from jarvis.voice.listener import WAKE_WORD_REGEX, BackgroundVoiceListener


def test_wake_word_regex_matches_variants_and_ignores_unrelated() -> None:
    assert WAKE_WORD_REGEX.search("Jarvis, ¿qué hora es?")
    assert WAKE_WORD_REGEX.search("oye yarvis abre chrome")
    assert WAKE_WORD_REGEX.search("Harvis por favor")
    assert WAKE_WORD_REGEX.search("garviz status")
    assert WAKE_WORD_REGEX.search("jarbis")
    assert not WAKE_WORD_REGEX.search("hola mundo")
    assert not WAKE_WORD_REGEX.search("jardinero")


def test_record_utterance_detects_speech_and_stops_on_silence() -> None:
    listener = BackgroundVoiceListener(
        sample_rate=16000,
        chunk_duration=0.1,
        energy_threshold=400.0,
        silence_duration=0.3,
        max_utterance_seconds=5.0,
    )
    chunk_samples = 1600
    silent = np.zeros((chunk_samples, 1), dtype=np.int16)
    loud = np.full((chunk_samples, 1), 2000, dtype=np.int16)

    chunks = [(silent, False), (silent, False), (loud, False), (loud, False)] + [
        (silent, False)
    ] * 3
    stream = MagicMock()
    stream.read.side_effect = chunks

    audio = listener.record_utterance(stream)

    assert isinstance(audio, sr.AudioData)
    assert audio.sample_rate == 16000
    assert audio.sample_width == 2
    # 2 loud + 3 trailing silent chunks = 5 chunks
    assert len(audio.get_raw_data()) == 5 * chunk_samples * 2


def test_record_utterance_stops_at_max_duration() -> None:
    listener = BackgroundVoiceListener(
        sample_rate=16000,
        chunk_duration=0.1,
        energy_threshold=400.0,
        silence_duration=0.9,
        max_utterance_seconds=0.4,
    )
    chunk_samples = 1600
    loud = np.full((chunk_samples, 1), 2000, dtype=np.int16)

    stream = MagicMock()
    stream.read.return_value = (loud, False)

    audio = listener.record_utterance(stream)

    assert isinstance(audio, sr.AudioData)
    assert len(audio.get_raw_data()) == 4 * chunk_samples * 2


@pytest.mark.parametrize(
    ("side_effect", "expected"),
    [
        ("Jarvis abre notepad", "Jarvis abre notepad"),
        (sr.UnknownValueError(), None),
        (sr.RequestError("offline"), None),
    ],
)
def test_transcribe_handles_google_responses_and_errors(side_effect, expected) -> None:
    recognizer = MagicMock()
    if isinstance(side_effect, Exception):
        recognizer.recognize_google.side_effect = side_effect
    else:
        recognizer.recognize_google.return_value = side_effect

    listener = BackgroundVoiceListener(recognizer=recognizer)
    audio = sr.AudioData(b"\x00\x00" * 1600, 16000, 2)

    assert listener.transcribe(audio) == expected


def test_process_transcript_ignores_without_wake_word() -> None:
    orchestrator = MagicMock()
    orchestrator.run = AsyncMock()
    tts = MagicMock()
    tts.synthesize_audio = AsyncMock()

    listener = BackgroundVoiceListener(orchestrator=orchestrator, tts_engine=tts)
    handled = listener.process_transcript("hola qué tal")

    assert handled is False
    orchestrator.run.assert_not_called()
    tts.synthesize_audio.assert_not_called()


def test_process_transcript_runs_orchestrator_and_plays_mp3() -> None:
    orchestrator = MagicMock()
    orchestrator.run = AsyncMock(return_value=SimpleNamespace(response="Son las diez."))
    tts = MagicMock()
    tts.synthesize_audio = AsyncMock(return_value=(b"mp3-bytes", "audio/mpeg"))

    listener = BackgroundVoiceListener(
        orchestrator=orchestrator,
        tts_engine=tts,
        voice_profile="albedo",
    )

    with (
        patch("jarvis.voice.listener.pygame.mixer.get_init", return_value=False),
        patch("jarvis.voice.listener.pygame.mixer.init") as mock_init,
        patch("jarvis.voice.listener.pygame.mixer.music.load") as mock_load,
        patch("jarvis.voice.listener.pygame.mixer.music.play") as mock_play,
        patch("jarvis.voice.listener.pygame.mixer.music.get_busy", return_value=False),
    ):
        handled = listener.process_transcript("Jarvis qué hora es")

    assert handled is True
    orchestrator.run.assert_awaited_once_with("Jarvis qué hora es", device_id="laptop")
    tts.synthesize_audio.assert_awaited_once_with("Son las diez.", profile="albedo")
    mock_init.assert_called_once_with()
    mock_load.assert_called_once()
    mock_play.assert_called_once_with()
    assert listener.is_speaking is False


def test_play_audio_wav_uses_winsound_and_pauses_capture() -> None:
    listener = BackgroundVoiceListener()
    seen_speaking: list[bool] = []

    def fake_playsound(_data: bytes, _flags: int) -> None:
        seen_speaking.append(listener.is_speaking)

    mock_winsound = MagicMock()
    mock_winsound.SND_MEMORY = 4
    mock_winsound.PlaySound.side_effect = fake_playsound

    with patch("jarvis.voice.listener.winsound", mock_winsound):
        listener.play_audio(b"RIFF....WAVE", "audio/wav")

    assert seen_speaking == [True]
    assert listener.is_speaking is False


def test_listen_loop_handles_missing_microphone_gracefully() -> None:
    listener = BackgroundVoiceListener()
    listener._running = True

    with patch("jarvis.voice.listener.sd.InputStream", side_effect=OSError("No mic")):
        listener._listen_loop()

    assert listener.is_running is False
