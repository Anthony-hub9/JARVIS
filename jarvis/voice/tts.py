"""100% free Spanish Text-to-Speech synthesis using Edge Neural TTS with Windows SAPI5 fallback."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

try:
    import edge_tts
except ImportError:  # pragma: no cover - optional runtime fallback
    edge_tts = None  # type: ignore[assignment]


VOICE_PROFILES: dict[str, dict[str, str]] = {
    "jarvis": {
        "voice": "es-MX-JorgeNeural",
        "rate": "-4%",
        "pitch": "-6Hz",
    },
    "albedo": {
        "voice": "es-MX-DaliaNeural",
        "rate": "-5%",
        "pitch": "+2Hz",
    },
}


class TTSError(RuntimeError):
    """Raised when local TTS synthesis is unavailable or fails."""


_POWERSHELL_TTS_SCRIPT = (
    "Add-Type -AssemblyName System.Speech; "
    "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "try { "
    "$esVoice = $synth.GetInstalledVoices() | "
    "Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'es*' } | "
    "Select-Object -First 1; "
    "if ($esVoice) { $synth.SelectVoice($esVoice.VoiceInfo.Name) }; "
    "$synth.SetOutputToWaveFile($env:JARVIS_TTS_OUT); "
    "$synth.Speak($env:JARVIS_TTS_TEXT) "
    "} finally { $synth.Dispose() }"
)


class LocalTTSEngine:
    """Synthesizes Spanish text to WAV bytes locally on Windows via PowerShell System.Speech."""

    def __init__(
        self,
        max_length: int = 800,
        timeout: float = 20.0,
        powershell_exe: str | None = None,
    ) -> None:
        self.max_length = max_length
        self.timeout = timeout
        self.powershell_exe = powershell_exe

    def _resolve_powershell(self) -> str:
        if sys.platform != "win32" and self.powershell_exe is None:
            raise TTSError("LocalTTSEngine solo está disponible en Windows.")
        exe = self.powershell_exe or shutil.which("powershell") or shutil.which("pwsh")
        if not exe:
            raise TTSError("PowerShell no está disponible para síntesis de voz local.")
        return exe

    def validate_text(self, text: str) -> str:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("El texto para síntesis de voz no puede estar vacío.")
        cleaned = text.strip()
        if len(cleaned) > self.max_length:
            raise ValueError(
                f"El texto excede el límite máximo de {self.max_length} caracteres."
            )
        return cleaned

    async def synthesize_wav(self, text: str) -> bytes:
        """Synthesize *text* into WAV audio bytes asynchronously."""
        cleaned = self.validate_text(text)
        ps_exe = self._resolve_powershell()

        tmp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = Path(tmp_file.name)
        tmp_file.close()

        env = os.environ.copy()
        env["JARVIS_TTS_TEXT"] = cleaned
        env["JARVIS_TTS_OUT"] = str(tmp_path)

        try:
            proc = await asyncio.create_subprocess_exec(
                ps_exe,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                _POWERSHELL_TTS_SCRIPT,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            try:
                _, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )
            except asyncio.TimeoutError as exc:
                proc.kill()
                await proc.wait()
                raise TTSError("Tiempo de espera agotado al sintetizar voz.") from exc

            if proc.returncode != 0:
                err_msg = stderr.decode("utf-8", errors="replace").strip()
                raise TTSError(
                    f"Error en SpeechSynthesizer (código {proc.returncode}): {err_msg}"
                )

            if not tmp_path.is_file():
                raise TTSError("No se generó el archivo WAV de salida.")

            wav_bytes = tmp_path.read_bytes()
            if not wav_bytes:
                raise TTSError("El archivo WAV generado está vacío.")
            return wav_bytes
        finally:
            tmp_path.unlink(missing_ok=True)

    async def synthesize_audio(
        self, text: str, profile: str = "jarvis"
    ) -> tuple[bytes, str]:
        """Synthesize *text* using Edge Neural TTS, falling back to local SAPI5 WAV."""
        cleaned = self.validate_text(text)
        profile_key = (profile or "jarvis").strip().lower()
        selected = VOICE_PROFILES.get(profile_key, VOICE_PROFILES["jarvis"])

        if edge_tts is not None:
            try:
                communicate = edge_tts.Communicate(
                    cleaned,
                    voice=selected["voice"],
                    rate=selected["rate"],
                    pitch=selected["pitch"],
                )
                chunks: list[bytes] = []
                async for chunk in communicate.stream():
                    if chunk.get("type") == "audio" and chunk.get("data"):
                        chunks.append(chunk["data"])
                mp3_bytes = b"".join(chunks)
                if mp3_bytes:
                    return mp3_bytes, "audio/mpeg"
            except Exception:
                pass

        wav_bytes = await self.synthesize_wav(cleaned)
        return wav_bytes, "audio/wav"
