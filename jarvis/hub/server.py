from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from jarvis.agents.orchestrator import DualAgentOrchestrator, GeminiBackend
from jarvis.config import settings

app = FastAPI(title="JARVIS Hub Central", version="0.1.0")


def get_orchestrator() -> DualAgentOrchestrator:
    backend = GeminiBackend(api_key=settings.gemini_api_key)
    return DualAgentOrchestrator(backend=backend)


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "executor": settings.executor_model,
        "supervisor": settings.supervisor_model,
    }


@app.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str) -> None:
    await websocket.accept()
    orchestrator = get_orchestrator()
    try:
        while True:
            user_text = await websocket.receive_text()
            result = await orchestrator.run(user_text, device_id=device_id)
            await websocket.send_json(
                {
                    "device_id": device_id,
                    "response": result.response,
                    "approved": result.approved,
                    "attempts": result.attempts,
                    "circuit_broken": result.circuit_broken,
                }
            )
    except WebSocketDisconnect:
        pass
