from dataclasses import dataclass
from typing import Protocol

from jarvis.config import settings


class AgentBackend(Protocol):
    async def generate(self, model: str, prompt: str) -> str: ...


class GeminiBackend:
    def __init__(self, api_key: str) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)

    async def generate(self, model: str, prompt: str) -> str:
        response = await self._client.aio.models.generate_content(
            model=model,
            contents=prompt,
        )
        return response.text or ""


class OllamaBackend:
    def __init__(self, base_url: str = settings.ollama_base_url, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def generate(self, model: str, prompt: str) -> str:
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
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


class DualAgentOrchestrator:
    def __init__(
        self,
        backend: AgentBackend,
        executor_model: str = settings.executor_model,
        supervisor_model: str = settings.supervisor_model,
        max_retries: int = settings.max_supervisor_retries,
    ) -> None:
        self.backend = backend
        self.executor_model = executor_model
        self.supervisor_model = supervisor_model
        self.max_retries = max_retries

    async def run(self, user_input: str, device_id: str = "pc") -> OrchestratorResult:
        feedback = ""
        attempts = 0

        for attempt in range(1, self.max_retries + 2):
            attempts = attempt
            exec_prompt = self._build_executor_prompt(user_input, device_id, feedback)
            candidate = await self.backend.generate(self.executor_model, exec_prompt)

            sup_prompt = self._build_supervisor_prompt(user_input, device_id, candidate)
            verdict = (await self.backend.generate(self.supervisor_model, sup_prompt)).strip()

            if verdict.upper().startswith("APPROVED"):
                return OrchestratorResult(
                    response=candidate,
                    approved=True,
                    attempts=attempts,
                )

            feedback = verdict.removeprefix("REJECTED:").strip()

        return OrchestratorResult(
            response="Acción abortada por el Circuit Breaker de seguridad (argon).",
            approved=False,
            attempts=attempts,
            circuit_broken=True,
            supervisor_feedback=feedback,
        )

    @staticmethod
    def _build_executor_prompt(user_input: str, device_id: str, feedback: str) -> str:
        base = f"[Dispositivo: {device_id}]\nUsuario: {user_input}"
        if feedback:
            base += f"\n\nCorrección obligatoria del supervisor (argon): {feedback}"
        return base

    @staticmethod
    def _build_supervisor_prompt(user_input: str, device_id: str, candidate: str) -> str:
        return (
            "Eres argon, el supervisor/gatekeeper de JARVIS. "
            "Evalúa si la respuesta/plan del ejecutor (hydrogen) es segura, precisa y adecuada "
            f"para el dispositivo '{device_id}'.\n"
            f"Solicitud: {user_input}\n"
            f"Propuesta: {candidate}\n\n"
            "Responde exactamente 'APPROVED' si es válida, o 'REJECTED: <motivo>' si debe corregirse."
        )
