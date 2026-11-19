from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from jarvis.agents.orchestrator import DualAgentOrchestrator, OllamaBackend
from jarvis.config import settings
from jarvis.tools.agenda import AgendaStore
from jarvis.tools.app_control import AppController

app = FastAPI(title="JARVIS Hub Central", version="0.1.0")

_agenda_store: AgendaStore | None = None
_app_controller: AppController | None = None


def get_agenda_store() -> AgendaStore:
    global _agenda_store
    if _agenda_store is None:
        _agenda_store = AgendaStore(settings.agenda_db_path)
    return _agenda_store


def get_app_controller() -> AppController:
    global _app_controller
    if _app_controller is None:
        _app_controller = AppController()
    return _app_controller


def get_orchestrator() -> DualAgentOrchestrator:
    backend = OllamaBackend(base_url=settings.ollama_base_url)
    return DualAgentOrchestrator(
        backend=backend,
        executor_model=settings.executor_model,
        supervisor_model=settings.supervisor_model,
        vision_model=settings.vision_model,
        max_retries=settings.max_supervisor_retries,
        agenda_store=get_agenda_store(),
        app_controller=get_app_controller(),
    )


def _parse_ws_message(raw_message: str) -> tuple[str, list[str] | None]:
    """Accept plain text or JSON payloads (game_frame, pc_game_satellite)."""
    stripped = raw_message.strip()
    if stripped.startswith("{"):
        try:
            payload: Any = json.loads(stripped)
            if isinstance(payload, dict):
                raw_image = payload.get("image_base64") or payload.get("frame_base64")
                images = [raw_image] if isinstance(raw_image, str) and raw_image.strip() else None
                msg_type = payload.get("type")
                raw_prompt = payload.get("prompt")
                prompt = raw_prompt.strip() if isinstance(raw_prompt, str) else ""

                if msg_type == "game_frame":
                    effective = prompt or (
                        "Analiza esta captura de juego y advierte brevemente sobre munición baja, "
                        "salud, enemigos o consejos tácticos."
                    )
                    return f"[Modo Juego / Frame] {effective}", images
                if msg_type == "pc_game_satellite":
                    return f"[Modo Juego / Satélite PC] {prompt}", images
                if isinstance(raw_prompt, str):
                    return prompt, images
        except json.JSONDecodeError:
            pass
    return raw_message, None


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "backend": "ollama",
        "executor": settings.executor_model,
        "supervisor": settings.supervisor_model,
        "vision": settings.vision_model,
    }


@app.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str) -> None:
    await websocket.accept()
    orchestrator = get_orchestrator()
    try:
        while True:
            raw_text = await websocket.receive_text()
            user_text, images = _parse_ws_message(raw_text)
            if images:
                result = await orchestrator.run(user_text, device_id=device_id, images=images)
            else:
                result = await orchestrator.run(user_text, device_id=device_id)
            await websocket.send_json(
                {
                    "device_id": device_id,
                    "response": result.response,
                    "approved": result.approved,
                    "attempts": result.attempts,
                    "circuit_broken": result.circuit_broken,
                    "tool_result": result.tool_result,
                }
            )
    except WebSocketDisconnect:
        pass
