from __future__ import annotations

import base64
import io

from PIL import Image, ImageGrab


def capture_screen_base64(max_width: int = 1024) -> str:
    """Capture the primary screen, resize if wider than max_width, and return JPEG base64."""
    if max_width <= 0:
        raise ValueError("max_width debe ser mayor que 0.")

    image = ImageGrab.grab()
    if image.mode != "RGB":
        image = image.convert("RGB")

    width, height = image.size
    if width > max_width:
        new_height = max(1, round(height * (max_width / width)))
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        image = image.resize((max_width, new_height), resampling)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("ascii")
