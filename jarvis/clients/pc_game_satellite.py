"""Lightweight PC Game Satellite client for screen capture and Hub WebSocket streaming."""

from __future__ import annotations

import base64
import json
from typing import Any


def capture_screen_base64(monitor_index: int = 1) -> str:
    """Capture the primary (or specified) monitor and return a base64-encoded PNG.

    `mss` is imported lazily so importing this module in headless/test
    environments without a display does not fail.
    """
    import mss
    import mss.tools

    with mss.mss() as sct:
        monitor = sct.monitors[monitor_index]
        screenshot = sct.grab(monitor)
        png_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)
        return base64.b64encode(png_bytes).decode("ascii")


async def _send_ws_payload(hub_ws_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    import websockets

    async with websockets.connect(hub_ws_url) as ws:
        await ws.send(json.dumps(payload))
        response = await ws.recv()
        if isinstance(response, bytes):
            response = response.decode("utf-8")
        return json.loads(response)


async def send_game_frame(
    hub_ws_url: str,
    prompt: str = "",
    *,
    monitor_index: int = 1,
    image_base64: str | None = None,
) -> dict[str, Any]:
    """Send a `game_frame` screenshot payload to the Laptop Hub for vision analysis."""
    encoded_image = image_base64 if image_base64 is not None else capture_screen_base64(monitor_index)
    payload = {
        "type": "game_frame",
        "prompt": prompt,
        "image_base64": encoded_image,
    }
    return await _send_ws_payload(hub_ws_url, payload)


async def send_screen_prompt(
    hub_ws_url: str,
    prompt: str,
    *,
    monitor_index: int = 1,
    image_base64: str | None = None,
) -> dict[str, Any]:
    """Send a screenshot + prompt payload to the JARVIS Hub over WebSocket."""
    encoded_image = image_base64 if image_base64 is not None else capture_screen_base64(monitor_index)
    payload = {
        "type": "pc_game_satellite",
        "prompt": prompt,
        "image_base64": encoded_image,
    }
    return await _send_ws_payload(hub_ws_url, payload)
