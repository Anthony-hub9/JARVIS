import pytest

from jarvis.agents.orchestrator import DualAgentOrchestrator


class MockBackend:
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)

    async def generate(self, model: str, prompt: str) -> str:
        return next(self._responses)


@pytest.mark.asyncio
async def test_orchestrator_approves_on_first_try() -> None:
    backend = MockBackend(["Hola, soy JARVIS.", "APPROVED"])
    orch = DualAgentOrchestrator(backend=backend, max_retries=2)

    result = await orch.run("Hola JARVIS", device_id="laptop")

    assert result.approved is True
    assert result.circuit_broken is False
    assert result.attempts == 1
    assert result.response == "Hola, soy JARVIS."


@pytest.mark.asyncio
async def test_orchestrator_retries_and_approves() -> None:
    backend = MockBackend(
        [
            "Borrando archivos...",
            "REJECTED: Acción peligrosa sin confirmación",
            "¿Confirmas que deseas continuar?",
            "APPROVED",
        ]
    )
    orch = DualAgentOrchestrator(backend=backend, max_retries=2)

    result = await orch.run("Limpia descargas", device_id="s24")

    assert result.approved is True
    assert result.circuit_broken is False
    assert result.attempts == 2
    assert result.response == "¿Confirmas que deseas continuar?"


@pytest.mark.asyncio
async def test_orchestrator_trips_circuit_breaker_after_max_retries() -> None:
    backend = MockBackend(
        [
            "Intento 1",
            "REJECTED: Falla 1",
            "Intento 2",
            "REJECTED: Falla 2",
            "Intento 3",
            "REJECTED: Falla 3",
        ]
    )
    orch = DualAgentOrchestrator(backend=backend, max_retries=2)

    result = await orch.run("Comando inválido", device_id="watch7")

    assert result.approved is False
    assert result.circuit_broken is True
    assert result.attempts == 3
    assert "Circuit Breaker" in result.response
