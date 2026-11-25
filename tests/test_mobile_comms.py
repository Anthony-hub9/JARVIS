"""Unit tests for S24+ mobile communications helpers and orchestrator routing."""

from __future__ import annotations

import pytest

from jarvis.agents.orchestrator import DualAgentOrchestrator, _route_direct_tool
from jarvis.tools.mobile_comms import (
    build_mobile_call_intent,
    build_mobile_device_control_intent,
    build_mobile_message_intent,
    build_mobile_notifications_intent,
)


class _DummyBackend:
    async def generate(self, model: str, prompt: str, images: list[str] | None = None) -> str:
        raise AssertionError("LLM backend should not be called for deterministic mobile comms routing")


def test_build_mobile_call_intent() -> None:
    assert build_mobile_call_intent("answer") == {
        "device": "s24_plus",
        "mobile_action": {"type": "call_control", "action": "answer"},
    }
    assert build_mobile_call_intent("REJECT") == {
        "device": "s24_plus",
        "mobile_action": {"type": "call_control", "action": "reject"},
    }
    with pytest.raises(ValueError):
        build_mobile_call_intent("hold")


def test_build_mobile_notifications_intent() -> None:
    assert build_mobile_notifications_intent("read") == {
        "device": "s24_plus",
        "mobile_action": {
            "type": "read_notifications",
            "action": "read",
            "sender": "",
            "message": "",
        },
    }
    assert build_mobile_notifications_intent("reply", sender="Ana", message="Voy en camino") == {
        "device": "s24_plus",
        "mobile_action": {
            "type": "reply_notification",
            "action": "reply",
            "sender": "Ana",
            "message": "Voy en camino",
        },
    }
    with pytest.raises(ValueError):
        build_mobile_notifications_intent("reply", sender="Ana", message="   ")


def test_build_mobile_message_intent() -> None:
    assert build_mobile_message_intent("whatsapp", "Carlos", "Llego en 10") == {
        "device": "s24_plus",
        "mobile_action": {
            "type": "send_message",
            "channel": "whatsapp",
            "recipient": "Carlos",
            "message": "Llego en 10",
        },
    }
    assert build_mobile_message_intent("SMS", "+525512345678", "Hola") == {
        "device": "s24_plus",
        "mobile_action": {
            "type": "send_message",
            "channel": "sms",
            "recipient": "+525512345678",
            "message": "Hola",
        },
    }
    with pytest.raises(ValueError):
        build_mobile_message_intent("telegram", "Carlos", "Hola")


@pytest.mark.parametrize(
    ("utterance", "expected"),
    [
        ("Jarvis, contesta la llamada", {"tool": "mobile_call", "action": "answer"}),
        ("rechaza la llamada", {"tool": "mobile_call", "action": "reject"}),
        ("cuelga la llamada", {"tool": "mobile_call", "action": "reject"}),
        ("lee mis mensajes", {"tool": "mobile_notifications", "action": "read"}),
        ("¿qué mensajes tengo?", {"tool": "mobile_notifications", "action": "read"}),
        (
            "responde al mensaje diciendo ya voy para allá",
            {"tool": "mobile_notifications", "action": "reply", "sender": "", "message": "ya voy para allá"},
        ),
        (
            "respóndele a Mamá que llego en 5 minutos",
            {"tool": "mobile_notifications", "action": "reply", "sender": "Mamá", "message": "llego en 5 minutos"},
        ),
        (
            "envía un whatsapp a Carlos diciendo nos vemos a las 8",
            {"tool": "mobile_message", "channel": "whatsapp", "recipient": "Carlos", "message": "nos vemos a las 8"},
        ),
        (
            "manda un mensaje a Laura diciendo ya salí",
            {"tool": "mobile_message", "channel": "whatsapp", "recipient": "Laura", "message": "ya salí"},
        ),
        (
            "envía un sms a Pedro diciendo código 1234",
            {"tool": "mobile_message", "channel": "sms", "recipient": "Pedro", "message": "código 1234"},
        ),
        (
            "mándame un mensaje por WhatsApp a isai dile hola",
            {"tool": "mobile_message", "channel": "whatsapp", "recipient": "isai", "message": "hola"},
        ),
        (
            "envíale un mensaje de whatsapp a mamá y dile ya llegué",
            {"tool": "mobile_message", "channel": "whatsapp", "recipient": "mamá", "message": "ya llegué"},
        ),
        (
            "respóndele a isai dile ya voy",
            {"tool": "mobile_notifications", "action": "reply", "sender": "isai", "message": "ya voy"},
        ),
    ],
)
def test_route_direct_tool_mobile_comms(utterance: str, expected: dict[str, str]) -> None:
    assert _route_direct_tool(utterance) == expected


@pytest.mark.asyncio
async def test_orchestrator_executes_mobile_comms_on_s24_plus() -> None:
    orch = DualAgentOrchestrator(backend=_DummyBackend(), fast_supervisor=True)

    res_call = await orch.run("contesta la llamada", device_id="s24-plus")
    assert res_call.approved is True
    assert res_call.tool_result == {
        "tool": "mobile_call",
        "device": "s24_plus",
        "mobile_action": {"type": "call_control", "action": "answer"},
    }

    res_read = await orch.run("qué mensajes tengo", device_id="s24-plus")
    assert res_read.approved is True
    assert res_read.tool_result is not None
    assert res_read.tool_result["mobile_action"]["type"] == "read_notifications"

    res_msg = await orch.run("envía un sms a Juan diciendo hola", device_id="s24-plus")
    assert res_msg.approved is True
    assert res_msg.tool_result is not None
    assert res_msg.tool_result["mobile_action"] == {
        "type": "send_message",
        "channel": "sms",
        "recipient": "Juan",
        "message": "hola",
    }


@pytest.mark.asyncio
async def test_orchestrator_mobile_comms_non_mobile_fallback() -> None:
    orch = DualAgentOrchestrator(backend=_DummyBackend(), fast_supervisor=True)

    res = await orch.run("contesta la llamada", device_id="laptop")
    assert res.approved is True
    assert "Samsung S24+" in res.response
    assert res.tool_result == {
        "tool": "mobile_call",
        "error": "Mobile device required",
        "device": "laptop",
    }


def test_build_mobile_device_control_intent() -> None:
    assert build_mobile_device_control_intent("flashlight_on") == {
        "device": "s24_plus",
        "mobile_action": {
            "type": "device_control",
            "action": "flashlight_on",
            "value": "",
            "label": "",
        },
    }
    assert build_mobile_device_control_intent("set_alarm", value="07:30", label="Trabajo") == {
        "device": "s24_plus",
        "mobile_action": {
            "type": "device_control",
            "action": "set_alarm",
            "value": "07:30",
            "label": "Trabajo",
        },
    }
    with pytest.raises(ValueError):
        build_mobile_device_control_intent("invalid_action")
    with pytest.raises(ValueError):
        build_mobile_device_control_intent("set_timer", value="")


@pytest.mark.parametrize(
    ("utterance", "expected"),
    [
        ("prende la linterna", {"tool": "mobile_device_control", "action": "flashlight_on", "value": "", "label": ""}),
        ("enciende la linterna", {"tool": "mobile_device_control", "action": "flashlight_on", "value": "", "label": ""}),
        ("apaga la linterna", {"tool": "mobile_device_control", "action": "flashlight_off", "value": "", "label": ""}),
        ("pon una alarma a las 07:30", {"tool": "mobile_device_control", "action": "set_alarm", "value": "07:30", "label": ""}),
        ("despiértame a las 7", {"tool": "mobile_device_control", "action": "set_alarm", "value": "07:00", "label": ""}),
        ("pon un temporizador de 5 minutos", {"tool": "mobile_device_control", "action": "set_timer", "value": "300", "label": ""}),
        ("temporizador de 30 segundos", {"tool": "mobile_device_control", "action": "set_timer", "value": "30", "label": ""}),
        ("sube el volumen del teléfono", {"tool": "mobile_device_control", "action": "volume_up", "value": "", "label": ""}),
        ("baja el volumen del celular", {"tool": "mobile_device_control", "action": "volume_down", "value": "", "label": ""}),
        ("pon el volumen del teléfono en 50", {"tool": "mobile_device_control", "action": "volume_set", "value": "50", "label": ""}),
        ("silencia el teléfono", {"tool": "mobile_device_control", "action": "mute", "value": "", "label": ""}),
        ("sube el volumen", {"tool": "system_media", "action": "volume_up"}),
    ],
)
def test_route_direct_tool_device_control(utterance: str, expected: dict[str, str]) -> None:
    assert _route_direct_tool(utterance) == expected


@pytest.mark.asyncio
async def test_orchestrator_executes_device_control_on_s24_plus() -> None:
    orch = DualAgentOrchestrator(backend=_DummyBackend(), fast_supervisor=True)

    res_flash = await orch.run("enciende la linterna", device_id="s24-plus")
    assert res_flash.approved is True
    assert res_flash.tool_result == {
        "tool": "mobile_device_control",
        "device": "s24_plus",
        "mobile_action": {
            "type": "device_control",
            "action": "flashlight_on",
            "value": "",
            "label": "",
        },
    }

    res_timer = await orch.run("pon un temporizador de 2 minutos", device_id="s24-plus")
    assert res_timer.approved is True
    assert res_timer.tool_result is not None
    assert res_timer.tool_result["mobile_action"]["action"] == "set_timer"
    assert res_timer.tool_result["mobile_action"]["value"] == "120"

    res_laptop = await orch.run("prende la linterna", device_id="laptop")
    assert res_laptop.approved is True
    assert res_laptop.tool_result == {
        "tool": "mobile_device_control",
        "error": "Mobile device required",
        "device": "laptop",
    }
