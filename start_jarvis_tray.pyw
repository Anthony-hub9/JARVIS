from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
os.chdir(ROOT_DIR)

from jarvis.clients.tray_app import _ensure_stdio, main  # noqa: E402

if __name__ == "__main__":
    _ensure_stdio(ROOT_DIR / "jarvis_tray.log")
    main()
