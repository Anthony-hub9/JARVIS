from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from jarvis.config import settings
from jarvis.tools.agenda import AgendaStore, parse_spanish_reminder
from jarvis.tools.app_control import AppController, build_mobile_intent
from jarvis.tools.desktop_context import read_clipboard_text, read_local_document
from jarvis.tools.laptop_vision import capture_screen_base64
from jarvis.tools.memory import MemoryStore, MemoryTurn
from jarvis.tools.mobile_comms import (
    build_mobile_call_intent,
    build_mobile_device_control_intent,
    build_mobile_message_intent,
    build_mobile_notifications_intent,
)
from jarvis.tools.system_control import SystemController
from jarvis.tools.web_search import WebSearchTool

MOBILE_DEVICE_IDS = {"s24", "s24_plus", "s24-plus", "mobile", "android", "phone", "galaxy-s24", "galaxy_s24"}
SAFE_FAST_TOOLS = {
    "agenda_add",
    "agenda_list",
    "agenda_upcoming",
    "app_launch",
    "clipboard_read",
    "document_read",
    "laptop_screen_vision",
    "memory_save",
    "memory_search",
    "mobile_call",
    "mobile_device_control",
    "mobile_message",
    "mobile_notifications",
    "system_media",
    "system_open_target",
    "system_status",
    "system_time",
    "web_search",
}
ALLOWED_TOOLS = SAFE_FAST_TOOLS
_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
_DIRECT_APP_LAUNCH_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:abre|abrir|inicia|iniciar|lanza|lanzar|open|launch)\s+(?:el|la|los|las|the)?\s*(.+?)[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_APP_CLOSE_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:cierra|cerrar|termina|terminar|mata|close|kill)\s+(?:el|la|los|las|the)?\s*(.+?)[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_AGENDA_LIST_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:ver|muestra|mostrar|lista|listar|dime)\s+(?:mi\s+)?(?:agenda|recordatorios)[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_SCREEN_VISION_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:(?:qu[eé])\s+(?:ves|hay|aparece|est[aá])\s+en\s+(?:(?:mi|la)\s+)?pantalla|"
    r"(?:puedes\s+ver|analiza|mira|revisa|describe|lee|ve)\s+(?:(?:mi|la)\s+)?pantalla|"
    r"ay[uú]dame\s+con\s+(?:este|el)\s+error\s+(?:en\s+|de\s+)?(?:la\s+)?pantalla)(?:[,:\s.!?]+.*)?$",
    re.IGNORECASE,
)
_DIRECT_CLIPBOARD_READ_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:(resume|analiza|lee)\s+(?:lo\s+que\s+copi[eé]|el\s+portapapeles)|"
    r"(?:qué|que)\s+(?:tengo\s+copiado|hay\s+en\s+el\s+portapapeles))[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_DOCUMENT_READ_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(resume|analiza|lee|abre\s+y\s+lee)\s+(?:el\s+)?(?:archivo|documento)\s+(.+?)[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_WEB_SEARCH_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:busca|buscar|b[uú]scame|investiga|investigar|googlea|search)\s+(?:en\s+(?:internet|la\s+web|google)\s+)?(.+?)[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_MEMORY_SAVE_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:recuerda\s+que|memoriza\s+que|guarda\s+(?:en\s+(?:tu\s+)?memoria\s+)?que|anota\s+que)\s+(.+?)[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_MEMORY_SEARCH_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:qu[eé]\s+recuerdas(?:\s+de|\s+sobre)?|qu[eé]\s+sabes(?:\s+de|\s+sobre)?|qu[eé]\s+te\s+dije(?:\s+de|\s+sobre)?)\s+(.+?)[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_SYSTEM_TIME_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:qu[eé]\s+hora\s+es|dime\s+la\s+hora|qu[eé]\s+d[ií]a\s+es(?:\s+hoy)?|qu[eé]\s+fecha\s+es(?:\s+hoy)?)[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_SYSTEM_STATUS_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:(?:dime\s+(?:la|el)\s+)?(?:bater[ií]a|estado\s+de\s+la\s+(?:laptop|pc|computadora)|estado\s+del\s+sistema|uso\s+de\s+cpu)|cu[aá]nta\s+ram(?:\s+.*)?)[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_SET_VOLUME_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:(?:sube|subir|baja|bajar|pon|poner|ajusta|ajustar|deja|dejar|cambia|cambiar|set)\s+)?(?:el\s+)?(?:volumen|volume)\s+(?:a|al|en|to)\s+(\d{1,3})\s*%?[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_FOLDER_OPEN_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:abre|abrir|muestra|mostrar|open)\s+(?:la\s+|el\s+)?(?:carpeta|folder|directorio)\s+(?:de\s+|del\s+)?(.+?)[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_MOBILE_CALL_ANSWER_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:contesta|contestar|responde|responder|atiende|atender|acepta|aceptar|coge)\s+(?:la\s+|esa\s+)?llamada[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_MOBILE_CALL_REJECT_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:cuelga|colgar|rechaza|rechazar|ignora|ignorar|corta|cortar|termina|terminar)\s+(?:la\s+|esa\s+)?llamada[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_MOBILE_NOTIF_READ_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:(?:lee|leer|revisa|revisar|dime|muestra|mostrar)\s+(?:mis\s+|las\s+)?(?:mensajes|notificaciones)|(?:qu[eé]\s+|cu[aá]les\s+son\s+mis\s+|tengo\s+)(?:mensajes|notificaciones)(?:\s+tengo|\s+nuevos|\s+pendientes)?)[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_MOBILE_NOTIF_REPLY_SENDER_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:resp[oó]ndele|responderle|cont[eé]stale|contestarle)\s+a\s+(.+?)\s+(?:y\s+dile|dile|dici[eé]ndole|diciendo|con|que)\s+(.+?)[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_MOBILE_NOTIF_REPLY_LAST_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:responde|responder|contesta|contestar)\s+(?:al\s+|a\s+la\s+)?(?:[uú]ltimo\s+)?(?:mensaje|notificaci[oó]n)\s+(?:y\s+dile|dile|dici[eé]ndole|diciendo|con|que)\s+(.+?)[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_MOBILE_MESSAGE_SEND_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:env[ií]a(?:le|me)?|enviar(?:le|me)?|m[aá]nda(?:le|me)?|mandar(?:le|me)?|escr[ií]be(?:le|me)?|escribir(?:le|me)?)\s+(?:(?:un|por)\s+)?(whatsapp|wasap|sms|mensaje(?:\s+(?:de|por|en)\s+(?:whatsapp|wasap|sms))?)\s+a\s+(.+?)\s+(?:y\s+dile|dile|dici[eé]ndole|diciendo|que|:)\s*(.+?)[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_MOBILE_FLASHLIGHT_ON_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:prende|prender|enciende|encender|activa|activar)\s+(?:la\s+)?linterna(?:\s+(?:del\s+)?(?:tel[eé]fono|celular|m[oó]vil|s24))?[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_MOBILE_FLASHLIGHT_OFF_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:apaga|apagar|desactiva|desactivar)\s+(?:la\s+)?linterna(?:\s+(?:del\s+)?(?:tel[eé]fono|celular|m[oó]vil|s24))?[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_MOBILE_ALARM_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:(?:pon|poner|programa|programar|crea|crear)\s+(?:una\s+)?alarma|despi[eé]rtame|despertarme)\s+(?:a\s+las\s+)(\d{1,2})(?::(\d{2}))?(?:\s+(?:con\s+(?:etiqueta|nombre)\s+|para\s+)(.+?))?[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_MOBILE_TIMER_RE = re.compile(
    r"^(?:jarvis[,\s]+)?(?:(?:pon|poner|inicia|iniciar|programa|programar)\s+(?:un\s+)?)?(?:temporizador|timer|cuenta\s+regresiva)\s+(?:de|para)\s+(\d+)\s*(minutos?|mins?|m|segundos?|segs?|s)\b(?:\s+(?:para\s+)(.+?))?[.!?\s]*$",
    re.IGNORECASE,
)
_MOBILE_DEVICE_REF = r"(?:tel[eé]fono|celular|m[oó]vil|s24(?:\s*\+)?)"
_DIRECT_MOBILE_VOLUME_SET_RE = re.compile(
    rf"^(?:jarvis[,\s]+)?(?:pon|poner|ajusta|ajustar|fija|fijar)\s+(?:el\s+)?volumen\s+(?:del\s+)?{_MOBILE_DEVICE_REF}\s+(?:a|al|en)\s+(\d{{1,3}})\s*%?[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_MOBILE_VOLUME_UP_RE = re.compile(
    rf"^(?:jarvis[,\s]+)?(?:sube|subir|aumenta|aumentar)\s+(?:el\s+)?volumen\s+(?:del\s+)?{_MOBILE_DEVICE_REF}[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_MOBILE_VOLUME_DOWN_RE = re.compile(
    rf"^(?:jarvis[,\s]+)?(?:baja|bajar|disminuye|disminuir)\s+(?:el\s+)?volumen\s+(?:del\s+)?{_MOBILE_DEVICE_REF}[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_MOBILE_MUTE_RE = re.compile(
    rf"^(?:jarvis[,\s]+)?(?:silencia|silenciar|mute|quita\s+el\s+sonido\s+de)\s+(?:el\s+|del\s+)?{_MOBILE_DEVICE_REF}[.!?\s]*$",
    re.IGNORECASE,
)
_DIRECT_MEDIA_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(?:jarvis[,\s]+)?(?:sube|subir|aumenta)\s+(?:el\s+)?volumen[.!?\s]*$", re.IGNORECASE), "volume_up"),
    (re.compile(r"^(?:jarvis[,\s]+)?(?:baja|bajar|disminuye)\s+(?:el\s+)?volumen[.!?\s]*$", re.IGNORECASE), "volume_down"),
    (re.compile(r"^(?:jarvis[,\s]+)?(?:silencia|silenciar|mute|quita\s+el\s+sonido)(?:\s+(?:el\s+)?(?:volumen|audio|sonido))?[.!?\s]*$", re.IGNORECASE), "mute"),
    (re.compile(r"^(?:jarvis[,\s]+)?(?:pon\s+pausa|pausa|pausar|reproduce|reproducir|reanuda|reanudar)(?:\s+(?:la\s+)?(?:m[uú]sica|canci[oó]n))?[.!?\s]*$", re.IGNORECASE), "play_pause"),
    (re.compile(r"^(?:jarvis[,\s]+)?(?:siguiente\s+canci[oó]n|siguiente\s+pista|cambia\s+de\s+canci[oó]n|next\s+track)[.!?\s]*$", re.IGNORECASE), "next_track"),
    (re.compile(r"^(?:jarvis[,\s]+)?(?:canci[oó]n\s+anterior|pista\s+anterior|anterior\s+canci[oó]n|prev(?:ious)?\s+track)[.!?\s]*$", re.IGNORECASE), "prev_track"),
)
_DIRECT_POWER_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(?:jarvis[,\s]+)?(?:bloquea|bloquear)\s+(?:la\s+)?(?:pantalla|laptop|pc|computadora|sesi[oó]n)[.!?\s]*$", re.IGNORECASE), "lock"),
    (re.compile(r"^(?:jarvis[,\s]+)?(?:suspende|suspender|duerme|dormir)\s+(?:la\s+)?(?:laptop|pc|computadora|equipo)[.!?\s]*$", re.IGNORECASE), "sleep"),
)
_SYSTEM_OPEN_TARGETS: frozenset[str] = frozenset(
    {
        "descargas",
        "downloads",
        "documentos",
        "documents",
        "escritorio",
        "desktop",
        "imagenes",
        "imágenes",
        "pictures",
        "musica",
        "música",
        "music",
        "videos",
        "youtube",
        "google",
        "github",
        "twitch",
        "netflix",
    }
)
_FACT_SEARCH_STOPWORDS = {
    "que",
    "qué",
    "con",
    "por",
    "para",
    "como",
    "cómo",
    "cual",
    "cuál",
    "sobre",
    "una",
    "uno",
    "unos",
    "unas",
    "los",
    "las",
    "del",
    "the",
    "and",
    "for",
    "with",
    "what",
    "who",
    "how",
    "dime",
    "algo",
    "sabes",
    "recuerdas",
    "jarvis",
}


class AgentBackend(Protocol):
    async def generate(self, model: str, prompt: str, images: list[str] | None = None) -> str: ...


class OllamaBackend:
    def __init__(self, base_url: str = settings.ollama_base_url, timeout: float = 180.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def generate(self, model: str, prompt: str, images: list[str] | None = None) -> str:
        import httpx

        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "15m",
            "options": {"num_predict": 512, "num_ctx": 8192, "repeat_penalty": 1.15},
        }
        if images:
            payload["images"] = images

        timeout_cfg = httpx.Timeout(self.timeout, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout_cfg) as client:
            resp = await client.post(
                f"{self.base_url}/api/generate",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")


@dataclass
class OrchestratorResult:
    response: str
    approved: bool
    attempts: int
    circuit_broken: bool = False
    supervisor_feedback: str = ""
    tool_result: dict[str, Any] | None = None


def _parse_tool_call(candidate: str) -> dict[str, Any] | None:
    """Extract a JSON tool-call object if the executor emitted one."""
    text = candidate.strip()
    match = _JSON_FENCE_RE.match(text)
    if match:
        text = match.group(1).strip()
    if not text.startswith("{"):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict) and isinstance(payload.get("tool"), str):
        return payload
    return None


def _route_direct_tool(user_input: str) -> dict[str, Any] | None:
    """Deterministically route unambiguous local commands to tool JSON without LLM."""
    text = user_input.strip().lstrip("¿¡").strip()
    if not text:
        return None

    if _DIRECT_AGENDA_LIST_RE.match(text):
        return {"tool": "agenda_list"}

    if _DIRECT_SYSTEM_TIME_RE.match(text):
        return {"tool": "system_time"}

    if _DIRECT_SYSTEM_STATUS_RE.match(text):
        return {"tool": "system_status"}

    if _DIRECT_SCREEN_VISION_RE.match(text):
        return {"tool": "laptop_screen_vision", "question": text}

    clip_match = _DIRECT_CLIPBOARD_READ_RE.match(text)
    if clip_match:
        verb = (clip_match.group(1) or "").strip().lower()
        return {"tool": "clipboard_read", "summarize": verb in {"resume", "analiza"}}

    doc_match = _DIRECT_DOCUMENT_READ_RE.match(text)
    if doc_match:
        verb = doc_match.group(1).strip().lower()
        target = doc_match.group(2).strip().strip("\"'")
        if target:
            return {
                "tool": "document_read",
                "target": target,
                "summarize": verb in {"resume", "analiza"},
            }

    if _DIRECT_MOBILE_FLASHLIGHT_ON_RE.match(text):
        return {"tool": "mobile_device_control", "action": "flashlight_on", "value": "", "label": ""}

    if _DIRECT_MOBILE_FLASHLIGHT_OFF_RE.match(text):
        return {"tool": "mobile_device_control", "action": "flashlight_off", "value": "", "label": ""}

    alarm_match = _DIRECT_MOBILE_ALARM_RE.match(text)
    if alarm_match:
        hour = int(alarm_match.group(1))
        minute = int(alarm_match.group(2) or "0")
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            label = (alarm_match.group(3) or "").strip()
            return {
                "tool": "mobile_device_control",
                "action": "set_alarm",
                "value": f"{hour:02d}:{minute:02d}",
                "label": label,
            }

    timer_match = _DIRECT_MOBILE_TIMER_RE.match(text)
    if timer_match:
        amount = int(timer_match.group(1))
        unit = timer_match.group(2).strip().lower()
        seconds = amount * 60 if unit.startswith("m") else amount
        label = (timer_match.group(3) or "").strip()
        if seconds > 0:
            return {
                "tool": "mobile_device_control",
                "action": "set_timer",
                "value": str(seconds),
                "label": label,
            }

    mobile_vol_set = _DIRECT_MOBILE_VOLUME_SET_RE.match(text)
    if mobile_vol_set:
        level = max(0, min(100, int(mobile_vol_set.group(1))))
        return {"tool": "mobile_device_control", "action": "volume_set", "value": str(level), "label": ""}

    if _DIRECT_MOBILE_VOLUME_UP_RE.match(text):
        return {"tool": "mobile_device_control", "action": "volume_up", "value": "", "label": ""}

    if _DIRECT_MOBILE_VOLUME_DOWN_RE.match(text):
        return {"tool": "mobile_device_control", "action": "volume_down", "value": "", "label": ""}

    if _DIRECT_MOBILE_MUTE_RE.match(text):
        return {"tool": "mobile_device_control", "action": "mute", "value": "", "label": ""}

    vol_match = _DIRECT_SET_VOLUME_RE.match(text)
    if vol_match:
        level = max(0, min(100, int(vol_match.group(1))))
        return {"tool": "system_media", "action": "set_volume", "level": level}

    for pattern, action in _DIRECT_MEDIA_PATTERNS:
        if pattern.match(text):
            return {"tool": "system_media", "action": action}

    for pattern, action in _DIRECT_POWER_PATTERNS:
        if pattern.match(text):
            return {"tool": "system_power", "action": action}

    if _DIRECT_MOBILE_CALL_ANSWER_RE.match(text):
        return {"tool": "mobile_call", "action": "answer"}

    if _DIRECT_MOBILE_CALL_REJECT_RE.match(text):
        return {"tool": "mobile_call", "action": "reject"}

    if _DIRECT_MOBILE_NOTIF_READ_RE.match(text):
        return {"tool": "mobile_notifications", "action": "read"}

    reply_sender_match = _DIRECT_MOBILE_NOTIF_REPLY_SENDER_RE.match(text)
    if reply_sender_match:
        sender = reply_sender_match.group(1).strip()
        message = reply_sender_match.group(2).strip()
        if sender and message:
            return {
                "tool": "mobile_notifications",
                "action": "reply",
                "sender": sender,
                "message": message,
            }

    reply_last_match = _DIRECT_MOBILE_NOTIF_REPLY_LAST_RE.match(text)
    if reply_last_match:
        message = reply_last_match.group(1).strip()
        if message:
            return {
                "tool": "mobile_notifications",
                "action": "reply",
                "sender": "",
                "message": message,
            }

    msg_send_match = _DIRECT_MOBILE_MESSAGE_SEND_RE.match(text)
    if msg_send_match:
        raw_channel = msg_send_match.group(1).strip().lower()
        recipient = msg_send_match.group(2).strip()
        message = msg_send_match.group(3).strip()
        channel = "sms" if "sms" in raw_channel else "whatsapp"
        if recipient and message:
            return {
                "tool": "mobile_message",
                "channel": channel,
                "recipient": recipient,
                "message": message,
            }

    reminder = parse_spanish_reminder(text)
    if reminder is not None:
        return {
            "tool": "agenda_add",
            "title": reminder["title"],
            "when": reminder["when"],
            "notes": "",
        }

    folder_match = _DIRECT_FOLDER_OPEN_RE.match(text)
    if folder_match:
        folder_name = folder_match.group(1).strip()
        if folder_name:
            return {"tool": "system_open_target", "target": folder_name, "kind": "folder"}

    launch_match = _DIRECT_APP_LAUNCH_RE.match(text)
    if launch_match:
        app_name = launch_match.group(1).strip()
        if app_name:
            lowered = app_name.lower()
            if lowered in _SYSTEM_OPEN_TARGETS or lowered.startswith(("https://", "http://")):
                return {"tool": "system_open_target", "target": app_name}
            return {"tool": "app_launch", "app_name": app_name}

    close_match = _DIRECT_APP_CLOSE_RE.match(text)
    if close_match:
        app_name = close_match.group(1).strip()
        if app_name:
            return {"tool": "app_close", "app_name": app_name}

    web_match = _DIRECT_WEB_SEARCH_RE.match(text)
    if web_match:
        query = web_match.group(1).strip()
        if query:
            return {"tool": "web_search", "query": query}

    save_match = _DIRECT_MEMORY_SAVE_RE.match(text)
    if save_match:
        value = save_match.group(1).strip()
        if value:
            key = " ".join(value.split()[:4])
            return {"tool": "memory_save", "key": key, "value": value}

    mem_search_match = _DIRECT_MEMORY_SEARCH_RE.match(text)
    if mem_search_match:
        query = mem_search_match.group(1).strip()
        if query:
            return {"tool": "memory_search", "query": query}

    return None


_DEVICE_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"\[Dispositivo:[^\]]*\]\s*[:-]?\s*"
    r"|Dispositivo\s+[^\s:\n]+(?:\s*[:-]\s*|\s+)"
    r"|(?:s24[-_]?plus|s24|galaxy[-_]?s24|assistant|jarvis)\s*:\s*"
    r")",
    re.IGNORECASE,
)

_CONVERSATIONAL_GREETING_RE = re.compile(
    r"^\s*[¡¿]?(?:jarvis[,\s]+)?(?:"
    r"hola(?:\s+jarvis)?|holi|hey|buenas|buen\s+d[ií]a|buenos\s+d[ií]as|"
    r"buenas\s+tardes|buenas\s+noches|qu[eé]\s+tal|c[oó]mo\s+est[aá]s|"
    r"c[oó]mo\s+te\s+va|c[oó]mo\s+andas|todo\s+bien|"
    r"(?:muchas\s+|mil\s+)?gracias|adi[oó]s|chao|hasta\s+luego|nos\s+vemos|bye|"
    r"jarvis"
    r")(?:[,\s]+jarvis)?[!?.¡¿\s]*$",
    re.IGNORECASE,
)


def _is_conversational_greeting(user_input: str) -> bool:
    """Return True when user_input is a pure greeting or small-talk phrase."""
    return bool(user_input.strip() and _CONVERSATIONAL_GREETING_RE.match(user_input))


def _looks_like_raw_tool_json(text: str) -> bool:
    """Return True when text looks like a raw or fenced JSON tool-call payload."""
    stripped = text.strip()
    match = _JSON_FENCE_RE.match(stripped)
    if match:
        stripped = match.group(1).strip()
    return stripped.startswith("{") and '"tool"' in stripped


def _sanitize_vision_description(text: str) -> str:
    """Strip non-printable/garbled characters and repetition loops from vision output."""
    # Keep printable Latin/ASCII/Spanish characters and common punctuation/whitespace
    filtered = re.sub(r"[^\x20-\x7EáéíóúüñÁÉÍÓÚÜÑ¿¡\s]", "", text)
    # Collapse repeated short substrings (e.g. 'ramarama...' or 'abababab')
    filtered = re.sub(r"(.{2,16}?)\1{3,}", r"\1", filtered)
    # Collapse repeated single characters (e.g. 'aaaaaa')
    filtered = re.sub(r"(.)\1{4,}", r"\1", filtered)
    return re.sub(r"\s+", " ", filtered).strip()


def _clean_assistant_response(text: str) -> str:
    """Strip accidental device-echo or role prefixes from model responses."""
    cleaned = text.strip()
    while True:
        updated = _DEVICE_PREFIX_RE.sub("", cleaned, count=1).strip()
        if updated == cleaned:
            return cleaned
        cleaned = updated


class DualAgentOrchestrator:
    def __init__(
        self,
        backend: AgentBackend | None = None,
        executor_model: str = settings.executor_model,
        supervisor_model: str = settings.supervisor_model,
        vision_model: str = settings.vision_model,
        max_retries: int = settings.max_supervisor_retries,
        agenda_store: AgendaStore | None = None,
        app_controller: AppController | None = None,
        memory_store: MemoryStore | None = None,
        system_controller: SystemController | None = None,
        web_search: WebSearchTool | None = None,
        fast_supervisor: bool = False,
    ) -> None:
        self.backend: AgentBackend = backend or OllamaBackend()
        self.executor_model = executor_model
        self.supervisor_model = supervisor_model
        self.vision_model = vision_model
        self.max_retries = max_retries
        self.agenda_store = agenda_store
        self.app_controller = app_controller or AppController()
        self.memory_store = memory_store
        self.system_controller = system_controller or SystemController()
        self.web_search = web_search or WebSearchTool()
        self.fast_supervisor = fast_supervisor

    async def run(
        self,
        user_input: str,
        device_id: str = "pc",
        images: list[str] | None = None,
    ) -> OrchestratorResult:
        feedback = ""
        attempts = 0
        effective_input = user_input.strip() or (
            "Analiza esta captura de juego y advierte brevemente sobre munición baja, "
            "salud, enemigos cercanos o consejos tácticos."
            if images
            else ""
        )

        recent_turns = self.memory_store.recent_turns(limit=8) if self.memory_store is not None else []

        for attempt in range(1, self.max_retries + 2):
            attempts = attempt
            direct_tool = (
                _route_direct_tool(effective_input)
                if (not images and not feedback and self.fast_supervisor)
                else None
            )
            if direct_tool is not None:
                tool_call = direct_tool
                candidate = json.dumps(direct_tool, ensure_ascii=False)
            elif images:
                candidate = await self._describe_image_in_spanish(effective_input, images)
                tool_call = None
            else:
                exec_prompt = self._build_executor_prompt(
                    effective_input,
                    device_id,
                    feedback,
                    has_images=False,
                    recent_turns=recent_turns,
                )
                candidate = await self.backend.generate(self.executor_model, exec_prompt)
                tool_call = _parse_tool_call(candidate)
            fast_approved = self.fast_supervisor and (
                tool_call is None or tool_call["tool"].strip().lower() in SAFE_FAST_TOOLS
            )
            if fast_approved:
                approved = True
                verdict = "APPROVED"
            else:
                sup_prompt = self._build_supervisor_prompt(effective_input, device_id, candidate)
                verdict = (await self.backend.generate(self.supervisor_model, sup_prompt)).strip()
                approved = verdict.upper().startswith("APPROVED")

            if approved:
                if tool_call is not None:
                    response_text, tool_result = await self._execute_tool(tool_call, device_id)
                    response_text = _clean_assistant_response(response_text)
                    if self.memory_store is not None:
                        self.memory_store.add_turn(device_id, "user", effective_input)
                        self.memory_store.add_turn(device_id, "assistant", response_text)
                    return OrchestratorResult(
                        response=response_text,
                        approved=True,
                        attempts=attempts,
                        tool_result=tool_result,
                    )
                cleaned_candidate = _clean_assistant_response(candidate)
                if _looks_like_raw_tool_json(cleaned_candidate):
                    cleaned_candidate = (
                        "Hola, ¿en qué puedo ayudarte?"
                        if _is_conversational_greeting(effective_input)
                        else "No entendí bien tu solicitud, ¿puedes decirme qué necesitas?"
                    )
                if self.memory_store is not None:
                    self.memory_store.add_turn(device_id, "user", effective_input)
                    self.memory_store.add_turn(device_id, "assistant", cleaned_candidate)
                return OrchestratorResult(
                    response=cleaned_candidate,
                    approved=True,
                    attempts=attempts,
                )

            feedback = verdict.removeprefix("REJECTED:").strip()

        return OrchestratorResult(
            response="Acción abortada por el Circuit Breaker de seguridad (supervisor).",
            approved=False,
            attempts=attempts,
            circuit_broken=True,
            supervisor_feedback=feedback,
        )

    async def _execute_tool(self, tool_call: dict[str, Any], device_id: str) -> tuple[str, dict[str, Any]]:
        tool_name = tool_call["tool"].strip().lower()

        if tool_name in {"agenda_add", "agenda_list", "agenda_upcoming"}:
            if self.agenda_store is None:
                return (
                    "La agenda local no está configurada en este momento.",
                    {"tool": tool_name, "error": "AgendaStore not configured"},
                )

            if tool_name == "agenda_add":
                title = str(tool_call.get("title", "")).strip()
                when = str(tool_call.get("when", "")).strip()
                notes = str(tool_call.get("notes", "")).strip()
                if not title or not when:
                    return (
                        "Faltan 'title' o 'when' para agendar el evento.",
                        {"tool": tool_name, "error": "Missing title or when"},
                    )
                event = self.agenda_store.add_event(title=title, when=when, notes=notes)
                return (
                    f"Evento agendado: {event.title} ({event.when}).",
                    {
                        "tool": tool_name,
                        "event": {
                            "id": event.id,
                            "title": event.title,
                            "when": event.when,
                            "notes": event.notes,
                        },
                    },
                )

            if tool_name == "agenda_list":
                events = self.agenda_store.list_events()
                items = [
                    {"id": e.id, "title": e.title, "when": e.when, "notes": e.notes}
                    for e in events
                ]
                summary = (
                    "No hay eventos en la agenda."
                    if not items
                    else "Eventos: " + "; ".join(f"{e['title']} ({e['when']})" for e in items)
                )
                return summary, {"tool": tool_name, "events": items}

            now = tool_call.get("now")
            events = self.agenda_store.upcoming_reminders(now=now)
            items = [
                {"id": e.id, "title": e.title, "when": e.when, "notes": e.notes}
                for e in events
            ]
            summary = (
                "No hay recordatorios próximos."
                if not items
                else "Próximos recordatorios: " + "; ".join(f"{e['title']} ({e['when']})" for e in items)
            )
            return summary, {"tool": tool_name, "events": items}

        if tool_name == "app_launch":
            app_name = str(tool_call.get("app_name", "")).strip()
            if not app_name:
                return (
                    "Falta el nombre de la aplicación ('app_name').",
                    {"tool": tool_name, "error": "Missing app_name"},
                )
            try:
                normalized_device = device_id.strip().lower().replace("-", "_")
                if normalized_device in MOBILE_DEVICE_IDS:
                    intent = build_mobile_intent(app_name)
                    return (
                        f"Intent generado para abrir {intent['app_name']} en {device_id}.",
                        {"tool": tool_name, "intent": intent},
                    )
                self.app_controller.launch_app(app_name)
                return (
                    f"Aplicación '{app_name.lower()}' iniciada en {device_id}.",
                    {"tool": tool_name, "app_name": app_name.lower(), "device": device_id},
                )
            except (ValueError, OSError) as exc:
                return (
                    f"No se pudo abrir '{app_name}': {exc}",
                    {"tool": tool_name, "error": str(exc)},
                )

        if tool_name == "app_close":
            app_name = str(tool_call.get("app_name", "")).strip()
            if not app_name:
                return (
                    "Falta el nombre de la aplicación ('app_name').",
                    {"tool": tool_name, "error": "Missing app_name"},
                )
            try:
                close_res = self.app_controller.close_app(app_name)
                if close_res["returncode"] == 0:
                    return (
                        f"Aplicación '{app_name.lower()}' cerrada en {device_id}.",
                        {
                            "tool": tool_name,
                            "app_name": app_name.lower(),
                            "process": close_res["process"],
                            "device": device_id,
                            "returncode": close_res["returncode"],
                        },
                    )
                detail = close_res["stderr"] or close_res["stdout"] or "proceso no encontrado"
                return (
                    f"No se pudo cerrar '{app_name.lower()}' ({close_res['process']}): {detail}",
                    {
                        "tool": tool_name,
                        "app_name": app_name.lower(),
                        "process": close_res["process"],
                        "device": device_id,
                        "returncode": close_res["returncode"],
                        "error": detail,
                    },
                )
            except ValueError as exc:
                return (
                    f"No se pudo cerrar '{app_name}': {exc}",
                    {"tool": tool_name, "error": str(exc)},
                )

        if tool_name == "memory_save":
            if self.memory_store is None:
                return (
                    "La memoria compartida no está configurada en este momento.",
                    {"tool": tool_name, "error": "MemoryStore not configured"},
                )
            key = str(tool_call.get("key", "")).strip()
            value = str(tool_call.get("value", "")).strip()
            if not key or not value:
                return (
                    "Faltan 'key' o 'value' para guardar en memoria.",
                    {"tool": tool_name, "error": "Missing key or value"},
                )
            fact = self.memory_store.save_fact(key=key, value=value)
            return (
                f"Guardado en memoria: {fact.key} = {fact.value}.",
                {
                    "tool": tool_name,
                    "fact": {
                        "id": fact.id,
                        "key": fact.key,
                        "value": fact.value,
                        "updated_at": fact.updated_at,
                    },
                },
            )

        if tool_name == "memory_search":
            if self.memory_store is None:
                return (
                    "La memoria compartida no está configurada en este momento.",
                    {"tool": tool_name, "error": "MemoryStore not configured"},
                )
            query = str(tool_call.get("query", "")).strip()
            raw_limit = tool_call.get("limit", 5)
            try:
                limit = max(1, int(raw_limit))
            except (TypeError, ValueError):
                limit = 5
            facts = self.memory_store.search_facts(query=query, limit=limit)
            items = [
                {"id": f.id, "key": f.key, "value": f.value, "updated_at": f.updated_at}
                for f in facts
            ]
            summary = (
                f"No encontré recuerdos relacionados con '{query}'."
                if not items
                else "Recuerdos encontrados: " + "; ".join(f"{f['key']}: {f['value']}" for f in items)
            )
            return summary, {"tool": tool_name, "query": query, "facts": items}

        if tool_name == "web_search":
            query = str(tool_call.get("query", "")).strip()
            if not query:
                return (
                    "Falta el término de búsqueda ('query').",
                    {"tool": tool_name, "error": "Missing query"},
                )
            raw_max = tool_call.get("max_results", 3)
            try:
                max_results = max(1, min(10, int(raw_max)))
            except (TypeError, ValueError):
                max_results = 3
            results = self.web_search.search(query, max_results=max_results)
            if not results:
                return (
                    f"No encontré resultados en la web para '{query}'.",
                    {"tool": tool_name, "query": query, "results": []},
                )
            formatted_results = "\n".join(
                f"- {r['title']}: {r['snippet']} ({r['url']})" for r in results
            )
            summary_prompt = (
                "Resume de forma breve, natural y directa para voz en español los siguientes "
                f"resultados de búsqueda para '{query}':\n{formatted_results}"
            )
            try:
                summary = (await self.backend.generate(self.executor_model, summary_prompt)).strip()
            except Exception:
                summary = ""
            if not summary:
                summary = WebSearchTool.format_spoken_summary(query, results)
            return summary, {"tool": tool_name, "query": query, "results": results}

        if tool_name == "system_time":
            info = self.system_controller.get_time_info()
            return info["formatted"], {"tool": tool_name, **info}

        if tool_name == "system_status":
            status = self.system_controller.get_system_status()
            return status["formatted"], {"tool": tool_name, **status}

        if tool_name == "system_media":
            action = str(tool_call.get("action", "")).strip()
            if not action:
                return (
                    "Falta la acción multimedia ('action').",
                    {"tool": tool_name, "error": "Missing action"},
                )
            try:
                if action.lower() == "set_volume":
                    raw_level = tool_call.get("level")
                    if raw_level is None:
                        return (
                            "Falta el nivel de volumen ('level').",
                            {"tool": tool_name, "error": "Missing level"},
                        )
                    level = max(0, min(100, int(raw_level)))
                    msg = self.system_controller.set_volume(level)
                    return msg, {"tool": tool_name, "action": "set_volume", "level": level}
                msg = self.system_controller.media_action(action)
                return msg, {"tool": tool_name, "action": action.lower()}
            except (ValueError, TypeError) as exc:
                return f"No se pudo ejecutar la acción multimedia: {exc}", {"tool": tool_name, "error": str(exc)}

        if tool_name == "system_open_target":
            target = str(tool_call.get("target", "")).strip()
            kind = tool_call.get("kind")
            kind_str = str(kind).strip().lower() if isinstance(kind, str) and kind.strip() else None
            if not target:
                return (
                    "Falta el destino a abrir ('target').",
                    {"tool": tool_name, "error": "Missing target"},
                )
            try:
                if kind_str is not None:
                    msg = self.system_controller.open_target(target, kind=kind_str)
                else:
                    msg = self.system_controller.open_target(target)
                result_payload: dict[str, Any] = {"tool": tool_name, "target": target.lower()}
                if kind_str is not None:
                    result_payload["kind"] = kind_str
                return msg, result_payload
            except (ValueError, OSError) as exc:
                return f"No se pudo abrir '{target}': {exc}", {"tool": tool_name, "error": str(exc)}

        if tool_name == "system_power":
            action = str(tool_call.get("action", "")).strip()
            if not action:
                return (
                    "Falta la acción de energía ('action').",
                    {"tool": tool_name, "error": "Missing action"},
                )
            try:
                msg = self.system_controller.power_action(action)
                return msg, {"tool": tool_name, "action": action.lower()}
            except (ValueError, OSError) as exc:
                return f"No se pudo ejecutar la acción de energía: {exc}", {"tool": tool_name, "error": str(exc)}

        if tool_name in {"mobile_call", "mobile_notifications", "mobile_message", "mobile_device_control"}:
            return self._execute_mobile_tool(tool_name, tool_call, device_id)

        if tool_name == "laptop_screen_vision":
            question = str(tool_call.get("question", "")).strip() or "Describe lo que ves en mi pantalla."
            try:
                b64 = capture_screen_base64()
                answer = await self._describe_image_in_spanish(question, [b64])
                return answer, {"tool": tool_name, "question": question, "image_b64_len": len(b64)}
            except Exception as exc:
                return (
                    f"No pude analizar la pantalla: {exc}",
                    {"tool": tool_name, "error": str(exc)},
                )

        if tool_name == "clipboard_read":
            summarize = bool(tool_call.get("summarize", False))
            try:
                content = read_clipboard_text()
            except (ValueError, OSError) as exc:
                return f"No pude leer el portapapeles: {exc}", {"tool": tool_name, "error": str(exc)}
            if summarize:
                summary = await self.backend.generate(
                    self.executor_model,
                    f"Resume brevemente en español el siguiente contenido del portapapeles:\n\n{content}",
                )
                return summary, {"tool": tool_name, "chars": len(content), "summarized": True}
            return (
                f"Portapapeles:\n{content}",
                {"tool": tool_name, "chars": len(content), "summarized": False, "content": content},
            )

        if tool_name == "document_read":
            target = str(tool_call.get("target", "")).strip()
            summarize = bool(tool_call.get("summarize", False))
            if not target:
                return (
                    "Falta indicar el archivo o documento ('target').",
                    {"tool": tool_name, "error": "Missing target"},
                )
            try:
                path, content = read_local_document(target)
            except (FileNotFoundError, ValueError, OSError) as exc:
                return f"No pude leer el documento '{target}': {exc}", {"tool": tool_name, "error": str(exc)}
            if summarize:
                summary = await self.backend.generate(
                    self.executor_model,
                    f"Resume brevemente en español el archivo '{path.name}':\n\n{content}",
                )
                return summary, {
                    "tool": tool_name,
                    "path": str(path),
                    "chars": len(content),
                    "summarized": True,
                }
            return (
                f"Contenido de {path.name}:\n{content}",
                {
                    "tool": tool_name,
                    "path": str(path),
                    "chars": len(content),
                    "summarized": False,
                    "content": content,
                },
            )

        return (
            f"Herramienta desconocida: '{tool_name}'.",
            {"tool": tool_name, "error": "Unknown tool"},
        )

    @staticmethod
    def _execute_mobile_tool(
        tool_name: str,
        tool_call: dict[str, Any],
        device_id: str,
    ) -> tuple[str, dict[str, Any]]:
        normalized_device = device_id.strip().lower().replace("-", "_")
        if normalized_device not in MOBILE_DEVICE_IDS:
            return (
                "Esta función móvil solo está disponible desde tu Samsung S24+.",
                {"tool": tool_name, "error": "Mobile device required", "device": device_id},
            )
        try:
            if tool_name == "mobile_call":
                action = str(tool_call.get("action", "")).strip()
                intent = build_mobile_call_intent(action)
                msg = (
                    "Contestando la llamada en tu S24+."
                    if intent["mobile_action"]["action"] == "answer"
                    else "Rechazando la llamada en tu S24+."
                )
                return msg, {"tool": tool_name, **intent}

            if tool_name == "mobile_notifications":
                action = str(tool_call.get("action", "")).strip()
                sender = str(tool_call.get("sender", "")).strip()
                message = str(tool_call.get("message", "")).strip()
                intent = build_mobile_notifications_intent(action, sender=sender, message=message)
                if intent["mobile_action"]["action"] == "read":
                    msg = "Leyendo tus mensajes recientes en tu S24+."
                elif sender:
                    msg = f"Respondiendo a {sender} en tu S24+."
                else:
                    msg = "Respondiendo al último mensaje en tu S24+."
                return msg, {"tool": tool_name, **intent}

            if tool_name == "mobile_device_control":
                action = str(tool_call.get("action", "")).strip()
                value = str(tool_call.get("value", "")).strip()
                label = str(tool_call.get("label", "")).strip()
                intent = build_mobile_device_control_intent(action, value=value, label=label)
                act = intent["mobile_action"]["action"]
                msg_map = {
                    "flashlight_on": "Encendiendo la linterna en tu S24+.",
                    "flashlight_off": "Apagando la linterna en tu S24+.",
                    "volume_up": "Subiendo el volumen de tu S24+.",
                    "volume_down": "Bajando el volumen de tu S24+.",
                    "volume_set": f"Ajustando el volumen de tu S24+ al {value}%.",
                    "mute": "Silenciando tu S24+.",
                    "set_alarm": f"Configurando alarma a las {value} en tu S24+.",
                    "set_timer": f"Iniciando temporizador de {value} segundos en tu S24+.",
                }
                return msg_map[act], {"tool": tool_name, **intent}

            channel = str(tool_call.get("channel", "")).strip()
            recipient = str(tool_call.get("recipient", "")).strip()
            message = str(tool_call.get("message", "")).strip()
            intent = build_mobile_message_intent(channel, recipient, message)
            ch = intent["mobile_action"]["channel"]
            msg = (
                f"Enviando SMS a {recipient} desde tu S24+."
                if ch == "sms"
                else f"Preparando WhatsApp para {recipient} en tu S24+."
            )
            return msg, {"tool": tool_name, **intent}
        except ValueError as exc:
            return f"No se pudo ejecutar la acción móvil: {exc}", {"tool": tool_name, "error": str(exc)}

    async def _describe_image_in_spanish(self, user_prompt: str, images: list[str]) -> str:
        """Describe images in English via vision_model, then translate/answer in Spanish via executor_model."""
        cleaned_prompt = user_prompt.strip() or "Describe what you see in this image."
        raw_desc = await self.backend.generate(
            self.vision_model,
            "Describe clearly and concisely in 2-3 English sentences what you see in this image. "
            "Focus on objects, text, or errors visible.",
            images=images,
        )
        vision_desc = _sanitize_vision_description(raw_desc)
        if len(vision_desc) < 5 or not any(ch.isalnum() for ch in vision_desc):
            return "No pude obtener una descripción clara de la imagen."

        tactical_note = (
            " Enfócate en munición baja, salud, enemigos cercanos o consejos tácticos."
            if "[modo juego" in cleaned_prompt.lower()
            else ""
        )
        return await self.backend.generate(
            self.executor_model,
            "Responde en español natural y breve (máximo 3 oraciones) a la solicitud del usuario "
            f"usando esta descripción visual:{tactical_note}\n"
            f"Solicitud: {cleaned_prompt}\n"
            f"Descripción visual: {vision_desc}",
        )

    def _build_executor_prompt(
        self,
        user_input: str,
        device_id: str,
        feedback: str,
        has_images: bool = False,
        recent_turns: list[MemoryTurn] | None = None,
    ) -> str:
        history_block = ""
        if recent_turns:
            lines = [
                f"- {'Tú' if t.role == 'user' else 'JARVIS'}: {t.content}"
                for t in recent_turns
            ]
            history_block = "Contexto reciente compartido (entre dispositivos):\n" + "\n".join(lines) + "\n\n"

        facts_block = ""
        if self.memory_store is not None and user_input.strip():
            facts = self.memory_store.search_facts(user_input, limit=3)
            if not facts:
                seen_ids: set[int] = set()
                words = re.findall(r"[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9]+", user_input.lower())
                for word in words:
                    if len(word) < 3 or word in _FACT_SEARCH_STOPWORDS:
                        continue
                    for fact in self.memory_store.search_facts(word, limit=3):
                        if fact.id not in seen_ids:
                            seen_ids.add(fact.id)
                            facts.append(fact)
                        if len(facts) >= 3:
                            break
                    if len(facts) >= 3:
                        break
            if facts:
                fact_lines = [f"- {f.key}: {f.value}" for f in facts]
                facts_block = "[Hechos guardados]\n" + "\n".join(fact_lines) + "\n\n"

        if has_images:
            is_game_mode = "[modo juego" in user_input.lower()
            vision_role = (
                "Eres el módulo de visión táctica de JARVIS (100% local en Ollama).\n"
                "Analiza la captura adjunta y da una respuesta breve, clara y accionable "
                "(advierte sobre munición baja, salud baja, enemigos o consejos tácticos).\n\n"
                if is_game_mode
                else "Eres el módulo de visión de JARVIS (100% local en Ollama).\n"
                "Analiza la imagen o captura adjunta y responde en español de forma clara, natural y útil.\n\n"
            )
            base = (
                f"{vision_role}"
                f"{facts_block}"
                f"{history_block}"
                f"Solicitud: {user_input}"
            )
        elif _is_conversational_greeting(user_input):
            base = (
                "Eres JARVIS, un asistente personal amable y eficiente.\n"
                "Responde en español natural y directo (1-2 oraciones), sin prefijos como 'Assistant:' o 'JARVIS:' "
                "y sin mencionar el nombre del dispositivo.\n\n"
                f"{facts_block}"
                f"{history_block}"
                f"Usuario: {user_input}"
            )
        else:
            base = (
                "Eres el agente ejecutor de JARVIS (100% local en Ollama).\n"
                "Herramientas disponibles (responde SOLO con un objeto JSON válido si necesitas usar una):\n"
                '- {"tool": "agenda_add", "title": "...", "when": "YYYY-MM-DDTHH:MM:SS", "notes": ""}\n'
                '- {"tool": "agenda_list"}\n'
                '- {"tool": "agenda_upcoming"}\n'
                '- {"tool": "app_launch", "app_name": "..."}\n'
                '- {"tool": "app_close", "app_name": "..."}\n'
                '- {"tool": "clipboard_read", "summarize": false}\n'
                '- {"tool": "document_read", "target": "...", "summarize": false}\n'
                '- {"tool": "laptop_screen_vision", "question": "..."}\n'
                '- {"tool": "memory_save", "key": "...", "value": "..."}\n'
                '- {"tool": "memory_search", "query": "..."}\n'
                '- {"tool": "mobile_call", "action": "answer|reject"}\n'
                '- {"tool": "mobile_notifications", "action": "read|reply", "sender": "", "message": ""}\n'
                '- {"tool": "mobile_message", "channel": "whatsapp|sms", "recipient": "...", "message": "..."}\n'
                '- {"tool": "system_time"}\n'
                '- {"tool": "system_status"}\n'
                '- {"tool": "system_media", "action": "volume_up|volume_down|mute|play_pause|next_track|prev_track"}\n'
                '- {"tool": "system_open_target", "target": "descargas|documentos|escritorio|youtube|google|github|..."}\n'
                '- {"tool": "system_power", "action": "lock|sleep"}\n'
                '- {"tool": "web_search", "query": "..."}\n'
                "Responde en español natural y directo, sin prefijos como 'Assistant:' o 'JARVIS:'. "
                'SOLO emite JSON {"tool": ...} si el usuario pidió explícitamente una acción.\n'
                "Responde directo sin mencionar el nombre del dispositivo.\n\n"
                f"{facts_block}"
                f"{history_block}"
                f"Usuario: {user_input}"
            )
        if feedback:
            base += f"\n\nCorrección obligatoria del supervisor: {feedback}"
        return base

    @staticmethod
    def _build_supervisor_prompt(user_input: str, device_id: str, candidate: str) -> str:
        return (
            "Eres el agente supervisor/gatekeeper de JARVIS. "
            "Evalúa si la respuesta o llamada a herramienta del ejecutor es segura, precisa y adecuada "
            f"para el dispositivo '{device_id}'.\n"
            f"Solicitud: {user_input}\n"
            f"Propuesta: {candidate}\n\n"
            "Responde exactamente 'APPROVED' si es válida, o 'REJECTED: <motivo>' si debe corregirse."
        )
