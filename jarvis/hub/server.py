from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from jarvis.agents.orchestrator import DualAgentOrchestrator, OllamaBackend
from jarvis.config import settings
from jarvis.tools.agenda import AgendaEvent, AgendaStore, GoogleCalendarSync
from jarvis.tools.app_control import AppController
from jarvis.tools.memory import MemoryStore
from jarvis.tools.web_search import WebSearchTool
from jarvis.voice.tts import LocalTTSEngine, TTSError

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def broadcast_json(self, payload: dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_json(payload)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self._connections.discard(ws)


manager = ConnectionManager()


async def check_and_dispatch_reminders(
    store: AgendaStore | None = None,
    conn_manager: ConnectionManager | None = None,
    ntfy_topic: str | None = None,
    now: str | None = None,
) -> list[AgendaEvent]:
    agenda = store or get_agenda_store()
    ws_manager = conn_manager or manager
    topic = (settings.ntfy_topic if ntfy_topic is None else ntfy_topic).strip()

    due = agenda.due_unnotified(now=now)
    for ev in due:
        agenda.mark_notified(ev.id)
        payload: dict[str, Any] = {
            "type": "reminder_alert",
            "device_id": "hub",
            "response": f"Recordatorio: {ev.title}",
            "approved": True,
            "event": {
                "id": ev.id,
                "title": ev.title,
                "when": ev.when,
                "notes": ev.notes,
            },
        }
        await ws_manager.broadcast_json(payload)
        if topic:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(
                        f"https://ntfy.sh/{topic}",
                        content=ev.title.encode("utf-8"),
                        headers={"Title": "JARVIS Recordatorio"},
                    )
            except Exception as exc:
                logger.warning("ntfy.sh push failed: %s", exc)
    return due


async def _reminder_loop() -> None:
    while True:
        try:
            await check_and_dispatch_reminders()
        except Exception as exc:
            logger.warning("Reminder scheduler error: %s", exc)
        await asyncio.sleep(max(1.0, float(settings.reminder_poll_seconds)))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(_reminder_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="JARVIS Hub Central", version="0.1.0", lifespan=lifespan)

STATIC_DIR = Path(__file__).resolve().parent / "static"

_agenda_store: AgendaStore | None = None
_app_controller: AppController | None = None
_memory_store: MemoryStore | None = None
_web_search: WebSearchTool | None = None
_tts_engine: LocalTTSEngine | None = None


class TTSRequest(BaseModel):
    text: str
    voice: str = "jarvis"


class AgendaCreateRequest(BaseModel):
    title: str
    when: str
    notes: str = ""


class AppActionRequest(BaseModel):
    app_name: str


def get_agenda_store() -> AgendaStore:
    global _agenda_store
    if _agenda_store is None:
        calendar_sync = GoogleCalendarSync(
            credentials_path=settings.google_credentials_path,
            token_path=settings.google_token_path,
        )
        _agenda_store = AgendaStore(settings.agenda_db_path, calendar_sync=calendar_sync)
    return _agenda_store


def get_app_controller() -> AppController:
    global _app_controller
    if _app_controller is None:
        _app_controller = AppController()
    return _app_controller


def get_memory_store() -> MemoryStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore(settings.memory_db_path)
    return _memory_store


def get_web_search() -> WebSearchTool:
    global _web_search
    if _web_search is None:
        _web_search = WebSearchTool()
    return _web_search


def get_tts_engine() -> LocalTTSEngine:
    global _tts_engine
    if _tts_engine is None:
        _tts_engine = LocalTTSEngine()
    return _tts_engine


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
        memory_store=get_memory_store(),
        web_search=get_web_search(),
        fast_supervisor=settings.fast_supervisor,
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


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "backend": "ollama",
        "executor": settings.executor_model,
        "supervisor": settings.supervisor_model,
        "vision": settings.vision_model,
    }


@app.post("/api/tts")
async def synthesize_tts(payload: TTSRequest) -> Response:
    engine = get_tts_engine()
    try:
        audio_bytes, media_type = await engine.synthesize_audio(
            payload.text, profile=payload.voice
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except (TTSError, Exception) as exc:
        return JSONResponse(status_code=503, content={"detail": str(exc)})
    return Response(content=audio_bytes, media_type=media_type)


@app.get("/api/agenda")
async def list_agenda(upcoming: bool = False) -> dict[str, Any]:
    store = get_agenda_store()
    events = store.upcoming_reminders() if upcoming else store.list_events()
    return {
        "events": [
            {"id": ev.id, "title": ev.title, "when": ev.when, "notes": ev.notes}
            for ev in events
        ]
    }


@app.post("/api/agenda")
async def create_agenda_event(payload: AgendaCreateRequest) -> JSONResponse:
    title = payload.title.strip()
    when = payload.when.strip()
    if not title or not when:
        return JSONResponse(
            status_code=400,
            content={"detail": "Los campos 'title' y 'when' son obligatorios."},
        )
    event = get_agenda_store().add_event(title=title, when=when, notes=payload.notes.strip())
    return JSONResponse(
        status_code=201,
        content={
            "event": {
                "id": event.id,
                "title": event.title,
                "when": event.when,
                "notes": event.notes,
            }
        },
    )


@app.get("/api/calendar/status")
async def calendar_status() -> dict[str, Any]:
    credentials_path = Path(settings.google_credentials_path)
    token_path = Path(settings.google_token_path)
    return {
        "configured": credentials_path.is_file(),
        "authenticated": token_path.is_file(),
        "credentials_path": str(settings.google_credentials_path),
        "token_path": str(settings.google_token_path),
    }


@app.get("/api/apps")
async def list_apps() -> dict[str, list[str]]:
    apps = get_app_controller().list_available_apps()
    return {"apps": apps}


@app.post("/api/apps/open")
async def open_app_endpoint(payload: AppActionRequest) -> JSONResponse:
    try:
        proc = get_app_controller().launch_app(payload.app_name)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    return JSONResponse(
        status_code=200,
        content={"status": "opened", "app": payload.app_name, "pid": getattr(proc, "pid", None)},
    )


@app.post("/api/apps/close")
async def close_app_endpoint(payload: AppActionRequest) -> JSONResponse:
    try:
        result = get_app_controller().close_app(payload.app_name)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    return JSONResponse(status_code=200, content={"status": "closed", **result})


@app.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str) -> None:
    await manager.connect(websocket)
    orchestrator = get_orchestrator()
    try:
        while True:
            raw_text = await websocket.receive_text()
            user_text, images = _parse_ws_message(raw_text)
            try:
                if images:
                    result = await orchestrator.run(user_text, device_id=device_id, images=images)
                else:
                    result = await orchestrator.run(user_text, device_id=device_id)
            except Exception as exc:
                await websocket.send_json(
                    {
                        "device_id": device_id,
                        "response": f"Error al procesar con Ollama: {type(exc).__name__}: {exc}",
                        "approved": False,
                        "attempts": 0,
                        "circuit_broken": False,
                    }
                )
                continue
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
    finally:
        manager.disconnect(websocket)
