"""100% free Spanish Text-to-Speech synthesis using Edge Neural TTS with Windows SAPI5 fallback."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

try:
    import edge_tts
except ImportError:  # pragma: no cover - optional runtime fallback
    edge_tts = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_ALBEDO_MODEL_PATH = Path("models/voices/albedo/albedo.pth")
_ALBEDO_INDEX_PATH = Path("models/voices/albedo/albedo.index")
_rvc_lock = threading.Lock()
_rvc_loader: Any = None


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


def _ensure_scripts_in_path() -> None:
    """Ensure the Python Scripts directory (containing ffmpeg.exe) is on PATH."""
    exe_dir = Path(sys.executable).resolve().parent
    scripts_dir = exe_dir if exe_dir.name.lower() == "scripts" else exe_dir / "Scripts"
    if not scripts_dir.is_dir():
        return
    current_path = os.environ.get("PATH", "")
    path_entries = current_path.split(os.pathsep) if current_path else []
    scripts_str = str(scripts_dir)
    if scripts_str not in path_entries:
        os.environ["PATH"] = (
            f"{scripts_str}{os.pathsep}{current_path}" if current_path else scripts_str
        )


def _get_rvc_loader(model_path: Path, index_path: Path) -> Any:
    """Return a cached infer_rvc_python.BaseLoader configured for the Albedo voice."""
    global _rvc_loader
    if _rvc_loader is not None:
        return _rvc_loader

    import torch
    from infer_rvc_python import BaseLoader

    use_cuda = torch.cuda.is_available()
    pitch_algo = "rmvpe" if use_cuda else "pm"
    loader = BaseLoader(only_cpu=not use_cuda)
    loader.apply_conf(
        tag="albedo",
        file_model=str(model_path),
        pitch_algo=pitch_algo,
        file_index=str(index_path) if index_path.is_file() else "",
    )
    _rvc_loader = loader
    return _rvc_loader


def preload_albedo_rvc() -> bool:
    """Preload the Albedo RVC model into memory if available; never raises."""
    if not _ALBEDO_MODEL_PATH.is_file():
        logger.debug(
            "Modelo RVC Albedo no encontrado en %s; omitiendo precarga.",
            _ALBEDO_MODEL_PATH,
        )
        return False
    try:
        with _rvc_lock:
            _ensure_scripts_in_path()
            _get_rvc_loader(_ALBEDO_MODEL_PATH, _ALBEDO_INDEX_PATH)
        logger.info("Modelo RVC Albedo precargado correctamente.")
        return True
    except Exception as exc:
        logger.warning("No se pudo precargar el modelo RVC Albedo: %s", exc)
        return False


def _convert_mp3_to_rvc_wav(
    mp3_bytes: bytes,
    model_path: Path,
    index_path: Path,
) -> bytes:
    """Convert base MP3 bytes to WAV bytes using the local RVC Albedo model."""
    _ensure_scripts_in_path()
    tmp_dir = Path(tempfile.mkdtemp(prefix="jarvis_rvc_"))
    input_path = tmp_dir / "input.mp3"
    output_files: list[str] = []
    try:
        input_path.write_bytes(mp3_bytes)
        with _rvc_lock:
            loader = _get_rvc_loader(model_path, index_path)
            output_files = loader(
                str(input_path),
                tag_list=["albedo"],
                overwrite=True,
                type_output="wav",
                show_progress=False,
            )

        if not output_files:
            raise TTSError("La conversión RVC no generó ningún archivo de salida.")

        output_path = Path(output_files[0])
        if not output_path.is_file():
            raise TTSError(f"No se encontró el archivo WAV de salida RVC: {output_path}")

        wav_bytes = output_path.read_bytes()
        if not wav_bytes:
            raise TTSError("El archivo WAV generado por RVC está vacío.")
        return wav_bytes
    finally:
        for out_file in output_files:
            Path(out_file).unlink(missing_ok=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)


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
                    if profile_key == "albedo":
                        if _ALBEDO_MODEL_PATH.is_file():
                            try:
                                wav_bytes = await asyncio.to_thread(
                                    _convert_mp3_to_rvc_wav,
                                    mp3_bytes,
                                    _ALBEDO_MODEL_PATH,
                                    _ALBEDO_INDEX_PATH,
                                )
                                return wav_bytes, "audio/wav"
                            except Exception as exc:
                                logger.warning(
                                    "Error en conversión RVC para 'albedo'; usando audio base edge-tts: %s",
                                    exc,
                                )
                        else:
                            logger.warning(
                                "Modelo RVC no encontrado en %s; usando audio base edge-tts para 'albedo'.",
                                _ALBEDO_MODEL_PATH,
                            )
                    return mp3_bytes, "audio/mpeg"
            except Exception:
                pass

        wav_bytes = await self.synthesize_wav(cleaned)
        return wav_bytes, "audio/wav"
