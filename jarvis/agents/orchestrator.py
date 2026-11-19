from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from jarvis.config import settings
from jarvis.tools.agenda import AgendaStore
from jarvis.tools.app_control import AppController, build_mobile_intent

MOBILE_DEVICE_IDS = {"s24", "s24_plus", "mobile", "android"}
_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


class AgentBackend(Protocol):
    async def generate(self, model: str, prompt: str, images: list[str] | None = None) -> str: ...


class OllamaBackend:
    def __init__(self, base_url: str = settings.ollama_base_url, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def generate(self, model: str, prompt: str, images: list[str] | None = None) -> str:
        import httpx

        payload: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
        if images:
            payload["images"] = images

        async with httpx.AsyncClient(timeout=self.timeout) as client:
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
    ) -> None:
        self.backend: AgentBackend = backend or OllamaBackend()
        self.executor_model = executor_model
        self.supervisor_model = supervisor_model
        self.vision_model = vision_model
        self.max_retries = max_retries
        self.agenda_store = agenda_store
        self.app_controller = app_controller or AppController()

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

        for attempt in range(1, self.max_retries + 2):
            attempts = attempt
            exec_prompt = self._build_executor_prompt(effective_input, device_id, feedback, has_images=bool(images))
            if images:
                candidate = await self.backend.generate(self.vision_model, exec_prompt, images=images)
            else:
                candidate = await self.backend.generate(self.executor_model, exec_prompt)

            sup_prompt = self._build_supervisor_prompt(effective_input, device_id, candidate)
            verdict = (await self.backend.generate(self.supervisor_model, sup_prompt)).strip()

            if verdict.upper().startswith("APPROVED"):
                tool_call = _parse_tool_call(candidate)
                if tool_call is not None:
                    response_text, tool_result = self._execute_tool(tool_call, device_id)
                    return OrchestratorResult(
                        response=response_text,
                        approved=True,
                        attempts=attempts,
                        tool_result=tool_result,
                    )
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

    def _execute_tool(self, tool_call: dict[str, Any], device_id: str) -> tuple[str, dict[str, Any]]:
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
                if device_id.strip().lower() in MOBILE_DEVICE_IDS:
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
            except ValueError as exc:
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

        return (
            f"Herramienta desconocida: '{tool_name}'.",
            {"tool": tool_name, "error": "Unknown tool"},
        )

    @staticmethod
    def _build_executor_prompt(
        user_input: str,
        device_id: str,
        feedback: str,
        has_images: bool = False,
    ) -> str:
        if has_images:
            base = (
                "Eres el módulo de visión táctica de JARVIS (100% local en Ollama).\n"
                "Analiza la captura adjunta y da una respuesta breve, clara y accionable "
                "(advierte sobre munición baja, salud baja, enemigos o consejos tácticos).\n\n"
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
                "Si es una conversación o pregunta general, responde directamente en texto natural.\n\n"
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
