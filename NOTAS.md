# NOTAS — Estado del Proyecto JARVIS

**Última actualización:** 2026-11-19 (commit `11391da` en `origin/main`)

## Lo hecho en esta sesión
- **Arquitectura Laptop-Hub (100% Ollama local y gratuito):** Hub Central en la Laptop (`DESKTOP-ANNU1GG`, GTX 1650 Ti 4 GB VRAM) sin API keys de Gemini en runtime (`docs/ARQUITECTURA_JARVIS.md`, `jarvis/config.py`).
- **Optimización de velocidad (Punto 1):** `executor_model` y `supervisor_model` unificados en `qwen2.5:1.5b` + `fast_supervisor=True` (1 llamada Ollama para chat, agenda y `app_launch`; 2 llamadas solo para `app_close`). Timeout `180s` + `keep_alive: "15m"` y manejo de errores WebSocket.
- **Control dinámico de aplicaciones:** `jarvis/tools/app_control.py` descubre apps de Windows (Menú Inicio `.lnk`, `Program Files`, Registro, Microsoft Store/UWP via `Get-StartApps`), soporta búsqueda parcial/natural (ej. `"riot"` -> `"riot client"`) y cierre seguro protegiendo procesos críticos. También soporta `intent_url` para apps del **Galaxy S24+** (`calculadora`, `cámara`, `reloj`, etc.).
- **Interfaz HUD + Voz neuronal + Escucha continua:** `jarvis/hub/static/index.html` con diseño HUD futurista, pestañas Chat/Agenda/Apps, modo **Escucha continua: Jarvis** (`WAKE_WORD_REGEX`), botón directo de `intent://` en S24+ y selector de voz (**JARVIS** / **Albedo** vía `edge-tts` gratis en `jarvis/voice/tts.py` con respaldo offline SAPI5).
- **Agenda + Visión base:** `AgendaStore` SQLite + `GoogleCalendarSync` opcional (`jarvis/tools/agenda.py`) y soporte `game_frame` (`moondream`) en `jarvis/hub/server.py` y `jarvis/clients/pc_game_satellite.py`.
- **Pruebas:** `.\.venv\Scripts\pytest.exe -q` -> **60 passed**.

## Lo pendiente
1. **Conectar la PC Gamer** por Tailscale (`git pull` de `Anthony-hub9/JARVIS`) y probar `pc_game_satellite.py` con videojuegos (ej. API local `127.0.0.1:2999` para League of Legends + recortes ligeros `mss` para CoD/Helldivers).
2. **Voz / App nativa en segundo plano (Fase 2):** Empaquetado en bandeja del sistema (System Tray) en Windows y app Android Kotlin (`ForegroundService`) o `tailscale serve --bg 8000` (HTTPS) para usar micrófono continuo desde el S24+.
3. **Google Calendar OAuth:** Agregar `credentials.json` si se desea sincronización real con Google Calendar.

## Ficheros clave
- `jarvis/hub/server.py` — Servidor FastAPI, WebSocket `/ws/{device_id}`, `/api/tts`, `/api/agenda`, `/api/apps`
- `jarvis/hub/static/index.html` — Interfaz HUD web, Wake Word `"Jarvis"`, selector de voz y lanzador `intent://`
- `jarvis/agents/orchestrator.py` — `OllamaBackend` y `DualAgentOrchestrator` (`fast_supervisor`)
- `jarvis/tools/app_control.py` — Descubrimiento/apertura/cierre dinámico en Windows + paquetes S24+
- `jarvis/voice/tts.py` — `LocalTTSEngine` (`edge-tts` JARVIS/Albedo + fallback SAPI5)
- `jarvis/tools/agenda.py` — `AgendaStore` SQLite + `GoogleCalendarSync`
- `jarvis/clients/pc_game_satellite.py` — Satélite ligero para PC Gamer

## Estado de Graphify
- **Código Python:** Actualizado (`graphify update .` -> `245 nodes, 556 edges, 11 communities` en `graphify-out/`).
- **Documentación (`docs/ARQUITECTURA_JARVIS.md`):** Pendiente de re-extracción semántica con `/graphify --update` si se desea incluir los cambios recientes de `.md` en el grafo (requiere tokens LLM).
