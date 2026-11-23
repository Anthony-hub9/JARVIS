from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from jarvis.config import settings
from jarvis.tools.agenda import AgendaStore, parse_spanish_reminder
from jarvis.tools.app_control import AppController, build_mobile_intent
from jarvis.tools.memory import MemoryStore, MemoryTurn
from jarvis.tools.system_control import SystemController
from jarvis.tools.web_search import WebSearchTool

MOBILE_DEVICE_IDS = {"s24", "s24_plus", "s24-plus", "mobile", "android", "phone", "galaxy-s24", "galaxy_s24"}
SAFE_FAST_TOOLS = {
    "agenda_add",
    "agenda_list",
    "agenda_upcoming",
    "app_launch",
    "memory_save",
    "memory_search",
    "system_media",
    "system_open_target",
    "system_status",
    "system_time",
    "web_search",
}
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
            "options": {"num_predict": 140, "num_ctx": 2048},
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

    for pattern, action in _DIRECT_MEDIA_PATTERNS:
        if pattern.match(text):
            return {"tool": "system_media", "action": action}

    for pattern, action in _DIRECT_POWER_PATTERNS:
        if pattern.match(text):
            return {"tool": "system_power", "action": action}

    reminder = parse_spanish_reminder(text)
    if reminder is not None:
        return {
            "tool": "agenda_add",
            "title": reminder["title"],
            "when": reminder["when"],
            "notes": "",
        }

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
            else:
                exec_prompt = self._build_executor_prompt(
                    effective_input,
                    device_id,
                    feedback,
                    has_images=bool(images),
                    recent_turns=recent_turns,
                )
                if images:
                    candidate = await self.backend.generate(self.vision_model, exec_prompt, images=images)
                else:
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
                    if self.memory_store is not None:
                        self.memory_store.add_turn(device_id, "user", effective_input)
                        self.memory_store.add_turn(device_id, "assistant", response_text)
                    return OrchestratorResult(
                        response=response_text,
                        approved=True,
                        attempts=attempts,
                        tool_result=tool_result,
                    )
                if self.memory_store is not None:
                    self.memory_store.add_turn(device_id, "user", effective_input)
                    self.memory_store.add_turn(device_id, "assistant", candidate)
                return OrchestratorResult(
                    response=candidate,
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
                msg = self.system_controller.media_action(action)
                return msg, {"tool": tool_name, "action": action.lower()}
            except ValueError as exc:
                return f"No se pudo ejecutar la acción multimedia: {exc}", {"tool": tool_name, "error": str(exc)}

        if tool_name == "system_open_target":
            target = str(tool_call.get("target", "")).strip()
            if not target:
                return (
                    "Falta el destino a abrir ('target').",
                    {"tool": tool_name, "error": "Missing target"},
                )
            try:
                msg = self.system_controller.open_target(target)
                return msg, {"tool": tool_name, "target": target.lower()}
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

        return (
            f"Herramienta desconocida: '{tool_name}'.",
            {"tool": tool_name, "error": "Unknown tool"},
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
            lines = [f"- [{t.device_id}] {t.role}: {t.content}" for t in recent_turns]
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
            base = (
                "Eres el módulo de visión táctica de JARVIS (100% local en Ollama).\n"
                "Analiza la captura adjunta y da una respuesta breve, clara y accionable "
                "(advierte sobre munición baja, salud baja, enemigos o consejos tácticos).\n\n"
                f"{facts_block}"
                f"{history_block}"
                f"[Dispositivo: {device_id}]\nSolicitud: {user_input}"
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
                '- {"tool": "memory_save", "key": "...", "value": "..."}\n'
                '- {"tool": "memory_search", "query": "..."}\n'
                '- {"tool": "system_time"}\n'
                '- {"tool": "system_status"}\n'
                '- {"tool": "system_media", "action": "volume_up|volume_down|mute|play_pause|next_track|prev_track"}\n'
                '- {"tool": "system_open_target", "target": "descargas|documentos|escritorio|youtube|google|github|..."}\n'
                '- {"tool": "system_power", "action": "lock|sleep"}\n'
                '- {"tool": "web_search", "query": "..."}\n'
                "Si es una conversación o pregunta general, responde directamente en texto natural.\n\n"
                f"{facts_block}"
                f"{history_block}"
                f"[Dispositivo: {device_id}]\nUsuario: {user_input}"
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
