"""Background microphone wake-word listener and TTS playback for laptop mode."""

from __future__ import annotations

import asyncio
import io
import logging
import re
import threading
import time
from collections.abc import Callable
from typing import Any

import numpy as np
import pygame
import sounddevice as sd
import speech_recognition as sr

from jarvis.voice.tts import LocalTTSEngine

try:
    import winsound
except ImportError:  # pragma: no cover - non-Windows fallback
    winsound = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

WAKE_WORD_REGEX = re.compile(r"\b[jyhg]ar[vb]i[sz]?\b", re.IGNORECASE)
VALID_VOICE_PROFILES = ("jarvis", "albedo")


class BackgroundVoiceListener:
    """Continuously listens for the JARVIS wake word and plays synthesized replies."""

    def __init__(
        self,
        orchestrator: Any | None = None,
        orchestrator_factory: Callable[[], Any] | None = None,
        tts_engine: LocalTTSEngine | None = None,
        recognizer: sr.Recognizer | None = None,
        voice_profile: str = "jarvis",
        language: str = "es-MX",
        sample_rate: int = 16000,
        chunk_duration: float = 0.1,
        energy_threshold: float = 250.0,
        silence_duration: float = 0.9,
        max_utterance_seconds: float = 10.0,
    ) -> None:
        self.orchestrator = orchestrator
        self._orchestrator_factory = orchestrator_factory
        self.tts_engine = tts_engine
        self.recognizer = recognizer or sr.Recognizer()
        self.voice_profile = voice_profile if voice_profile in VALID_VOICE_PROFILES else "jarvis"
        self.language = language
        self.sample_rate = sample_rate
        self.chunk_duration = chunk_duration
        self.energy_threshold = energy_threshold
        self.silence_duration = silence_duration
        self.max_utterance_seconds = max_utterance_seconds

        self.is_speaking = False
        self._running = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    def _get_orchestrator(self) -> Any:
        if self.orchestrator is not None:
            return self.orchestrator
        if self._orchestrator_factory is not None:
            self.orchestrator = self._orchestrator_factory()
            return self.orchestrator
        from jarvis.hub.server import get_orchestrator

        self.orchestrator = get_orchestrator()
        return self.orchestrator

    def _get_tts(self) -> LocalTTSEngine:
        if self.tts_engine is None:
            self.tts_engine = LocalTTSEngine()
        return self.tts_engine

    @staticmethod
    def _compute_rms(chunk: np.ndarray) -> float:
        arr = np.asarray(chunk, dtype=np.float32)
        if arr.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(arr * arr)))

    def record_utterance(self, stream: Any) -> sr.AudioData | None:
        """Wait for speech above threshold and record until ~0.9s silence or 10s max."""
        chunk_samples = max(1, int(self.sample_rate * self.chunk_duration))
        max_silence_chunks = max(1, int(round(self.silence_duration / self.chunk_duration)))
        max_utterance_chunks = max(1, int(round(self.max_utterance_seconds / self.chunk_duration)))

        frames: list[bytes] = []
        recording = False
        silence_chunks = 0

        while not self._stop_event.is_set():
            if self.is_speaking:
                frames.clear()
                recording = False
                silence_chunks = 0
                time.sleep(0.05)
                continue

            data, _overflowed = stream.read(chunk_samples)
            rms = self._compute_rms(data)

            if not recording:
                if rms >= self.energy_threshold:
                    recording = True
                    frames.append(np.asarray(data, dtype=np.int16).tobytes())
                    silence_chunks = 0
                continue

            frames.append(np.asarray(data, dtype=np.int16).tobytes())
            if rms < self.energy_threshold:
                silence_chunks += 1
            else:
                silence_chunks = 0

            if silence_chunks >= max_silence_chunks or len(frames) >= max_utterance_chunks:
                return sr.AudioData(b"".join(frames), self.sample_rate, 2)

        return None

    def transcribe(self, audio: sr.AudioData) -> str | None:
        """Transcribe recorded audio via Google Speech Recognition."""
        try:
            text = self.recognizer.recognize_google(audio, language=self.language)
            return text.strip() or None
        except (sr.UnknownValueError, sr.RequestError):
            return None
        except Exception as exc:
            logger.warning("Speech recognition error: %s", exc)
            return None

    def play_audio(self, audio_bytes: bytes, media_type: str) -> None:
        """Play synthesized audio while pausing microphone capture."""
        if not audio_bytes:
            return
        self.is_speaking = True
        try:
            if media_type in ("audio/mpeg", "audio/wav"):
                try:
                    if not pygame.mixer.get_init():
                        pygame.mixer.init()
                    pygame.mixer.music.load(io.BytesIO(audio_bytes))
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy() and not self._stop_event.is_set():
                        time.sleep(0.05)
                    return
                except Exception as exc:
                    if media_type != "audio/wav" or winsound is None:
                        raise
                    logger.warning("pygame WAV playback failed, falling back to winsound: %s", exc)
                    winsound.PlaySound(audio_bytes, winsound.SND_MEMORY)
        finally:
            self.is_speaking = False

    def process_transcript(self, transcript: str) -> bool:
        """Handle a recognized transcript if it contains the wake word."""
        if not transcript or not WAKE_WORD_REGEX.search(transcript):
            return False
        logger.info("Voice command received: %s", transcript)

        async def _handle() -> tuple[bytes, str] | None:
            result = await self._get_orchestrator().run(transcript, device_id="laptop")
            reply = (getattr(result, "response", "") or "").strip()
            if not reply:
                return None
            return await self._get_tts().synthesize_audio(reply[:2500], profile=self.voice_profile)

        synthesized = asyncio.run(_handle())
        if synthesized is not None:
            audio_bytes, media_type = synthesized
            self.play_audio(audio_bytes, media_type)
        return True

    def _listen_loop(self) -> None:
        chunk_samples = max(1, int(self.sample_rate * self.chunk_duration))
        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=chunk_samples,
            ) as stream:
                while not self._stop_event.is_set():
                    audio = self.record_utterance(stream)
                    if audio is None:
                        break
                    transcript = self.transcribe(audio)
                    if transcript:
                        try:
                            self.process_transcript(transcript)
                        except Exception as exc:
                            logger.warning("Error processing voice command: %s", exc)
        except Exception as exc:
            logger.warning("Microphone unavailable for background voice listener: %s", exc)
        finally:
            self._running = False

    def start(self) -> bool:
        """Start the background voice listener thread."""
        if self._running:
            return False
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop,
            name="jarvis-voice-listener",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop the background voice listener cleanly."""
        self._stop_event.set()
        self._running = False
        if self._thread is not None and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)
        self._thread = None
