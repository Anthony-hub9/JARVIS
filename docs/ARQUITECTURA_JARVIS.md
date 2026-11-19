# Arquitectura de JARVIS

Documento de diseño técnico y hoja de ruta para el asistente personal distribuido **JARVIS**, 100% gratuito y local sobre **Ollama** (sin APIs externas de pago ni dependencias de nube), centrado en la **Laptop como Hub Central** con clientes ligeros conectados de forma segura mediante Tailscale.

---

## 1. Visión General y Topología

El sistema sigue una arquitectura **Hub-and-Spoke** donde todo el procesamiento de IA (LLM local en Ollama, visión, voz local, orquestación de agentes, agenda SQLite y automatizaciones) reside en la **Laptop (`DESKTOP-ANNU1GG`)**, de modo que el **PC Gaming** pierde **0 FPS** al ejecutar únicamente un cliente satélite ligero (`pc_game_satellite.py`). Los clientes prioritarios (**Laptop**, **PC Gaming** y **Galaxy S24+**) y los futuros clientes de Fase 3 (**Galaxy Watch 7** y **Android Auto**) se comunican por WebSockets sobre Tailscale.

```text
+-------------------+       +-------------------+       +-------------------+
|   Galaxy Watch 7  |       |   Android Auto    |       |    PC Gaming      |
| (Fase 3: Wear OS) |       | (Fase 3: BT vía   |       | (Satélite ligero: |
+---------+---------+       |       S24+)       |       | mss + app control)|
          |                 +---------+---------+       +---------+---------+
          +-------------+-------------+                           |
                        |                                         |
                        v                                         v
             +----------+----------+                   +----------+----------+
             |  Galaxy S24+ (Hub   |                   |     Red Mesh VPN    |
             |  móvil prioritario  +------------------>+     (Tailscale)     |
             |  ForegroundService) |   WebSockets      +----------+----------+
             +---------------------+                              |
                                                                  v
                                                       +----------+----------+
                                                       | HUB CENTRAL (Laptop |
                                                       |  DESKTOP-ANNU1GG)   |
                                                       | Ollama / FastAPI    |
                                                       +---------------------+
```

---

## 2. Hub Central (Laptop `DESKTOP-ANNU1GG`)

* **Hardware:** Intel Core i5-10300H, NVIDIA GTX 1650 Ti (4 GB VRAM), ~20 GB RAM, Windows.
* **Motor LLM y Visión 100% Local:** **Ollama** (`http://localhost:11434/api/generate`) vía `OllamaBackend`, completamente gratuito y offline (sin `GEMINI_API_KEY` ni `google-genai`), con modelos ajustados para **4 GB de VRAM**:
  * `EXECUTOR_MODEL=qwen2.5:3b`
  * `SUPERVISOR_MODEL=qwen2.5:1.5b`
  * `VISION_MODEL=moondream` (alternativa: `qwen2.5vl:3b`)
* **Runtime y Backend:** Python 3.12+ (`asyncio`), **FastAPI** + **WebSockets** (`/ws/{device_id}`, `/health`) bidireccionales en tiempo real.
* **Red y Seguridad:** Exposición privada exclusivamente sobre **Tailscale** (sin puertos públicos abiertos en el router).

---

## 3. Clientes Ligeros (Prioridad y Fases)

| Dispositivo | Prioridad | Rol y Mecanismo de Activación | Transporte |
| :--- | :--- | :--- | :--- |
| **Laptop (`DESKTOP-ANNU1GG`)** | **Prioritario (Fase 1 - Hub)** | Hub Central (Ollama, FastAPI/WebSockets, orquestador, visión, voz, SQLite) y cliente local de escritorio. | Local / Tailscale |
| **PC Gaming (Ryzen 5 7600X, RTX 4070 Super, 32 GB RAM)** | **Prioritario (Fase 1 - Satélite)** | Ejecuta únicamente el satélite ligero `pc_game_satellite.py` para captura de pantalla en CPU (`mss`) por hotkey y apertura/cierre remoto de apps (**0 FPS de pérdida** en juegos). | WebSocket sobre Tailscale |
| **Samsung Galaxy S24+** | **Prioritario (Fase 2)** | Cliente móvil principal. Integración con **One UI Rutinas**, `ForegroundService` persistente y launcher de apps mediante Android Intents (`build_mobile_intent`). | WebSocket sobre Tailscale |
| **Galaxy Watch 7** | **Fase 3** | **Wear OS 5**. Activación bajo demanda mediante **Tile** o **botón físico** (sin escucha pasiva para preservar batería). | Puente vía S24+ / Tailscale |
| **Android Auto** | **Fase 3** | Interacción manos libres en vehículo mediante puente **Bluetooth HFP/A2DP** gestionado desde el Galaxy S24+. | BT HFP/A2DP → S24+ → Hub |

---

## 4. Arquitectura de Doble Agente Local (Obligatoria)

Todas las acciones, invocaciones de herramientas y respuestas críticas pasan por un flujo de validación en dos etapas ejecutado **exclusivamente con modelos locales en Ollama** (configurables vía `.env`):

1. **Agente Ejecutor (`EXECUTOR_MODEL`, por defecto `qwen2.5:3b` / `VISION_MODEL`, por defecto `moondream` para frames):**
   * Interpreta la intención del usuario, decide si responder en lenguaje natural o emitir una llamada estructurada a herramienta (`agenda_add`, `agenda_list`, `agenda_upcoming`, `app_launch`, `app_close`) y analiza capturas `game_frame` mediante `OllamaBackend.generate(..., images=[...])`.
2. **Agente Supervisor / Gatekeeper (`SUPERVISOR_MODEL`, por defecto `qwen2.5:1.5b`):**
   * Audita la propuesta o llamada a herramienta del Ejecutor antes de ejecutar cualquier acción sensible (apertura/cierre de apps, cambios en agenda, intents móviles).
   * **Circuit Breaker:** Máximo **2 reintentos** (`MAX_SUPERVISOR_RETRIES=2`) ante fallos de validación. Si se supera el límite, el circuito se abre, se aborta la acción de forma segura y se informa al usuario.

---

## 5. Pipeline de Voz Local en Hub (Laptop)

Todo el procesamiento de audio se ejecuta localmente en la **Laptop (`DESKTOP-ANNU1GG`)** para preservar la privacidad y no consumir recursos del PC Gaming:

* **Detección de Wake Word y VAD:** `openWakeWord` + `Silero VAD` para detección de palabra clave y segmentación precisa de voz/silencio.
* **STT (Speech-to-Text):** `faster-whisper` acelerado por CUDA (GTX 1650 Ti 4 GB) o CPU según presupuesto de VRAM.
* **TTS (Text-to-Speech):** `Kokoro` / `Piper` en modo **streaming**, enviando fragmentos de audio al cliente correspondiente conforme se generan.

---

## 6. Sistema de Memoria y Herramientas Integradas

* **Memoria a Corto Plazo (Contexto activo):** Almacenada en **RAM / Redis** para mantener el estado de la conversación actual y sesiones activas por dispositivo.
* **Agenda Local (`AgendaStore` en SQLite + `GoogleCalendarSync` opcional):** Registro y consulta local de eventos y recordatorios (`jarvis_agenda.db`) 100% offline/gratis. Si existe `credentials.json` local de OAuth, `GoogleCalendarSync` sincroniza de forma opcional sin bloquear ni fallar cuando no está configurado.
* **Control Dinámico de Aplicaciones (`AppController`):** Descubrimiento dinámico en Windows (accesos directos `.lnk` del Menú Inicio, `shutil.which`, `Program Files` y Registro `App Paths`) para **abrir** (`app_launch`) y **cerrar** (`app_close` vía `taskkill`) aplicaciones con lista de protección de procesos críticos del sistema (`explorer.exe`, `csrss.exe`, `svchost.exe`, `lsass.exe`, `wininit.exe`, `dwm.exe`), además de intents Android (`build_mobile_intent`) para **Galaxy S24+**.
* **Memoria Vectorial (Fases posteriores):** **ChromaDB / Qdrant** para búsqueda semántica y recuperación de contexto (RAG).

---

## 7. Funciones v1 y Soporte Gaming con 0 Pérdida de FPS

* **Chat y Q&A por WebSocket:** Consultas generales validadas por el doble agente local en Ollama.
* **Agenda:** Gestión de eventos y recordatorios en **SQLite** local (`agenda_add`, `agenda_list`, `agenda_upcoming`) con sincronización opcional a Google Calendar.
* **Control de aplicaciones:** Apertura y cierre dinámico de apps en Windows (`app_launch`, `app_close`) e intents en Galaxy S24+.
* **Apoyo en videojuegos sin pérdida de FPS:**
  * El cliente `pc_game_satellite.py` en el PC Gaming se activa bajo demanda por **hotkey**, realiza una captura ultrarrápida en CPU con `mss` (sin *alt-tab* ni hooks invasivos) y envía un payload `game_frame` por WebSocket al Hub en la Laptop.
  * La Laptop ejecuta la inferencia de visión en Ollama (`moondream` / `qwen2.5vl:3b`) para advertir sobre munición baja, enemigos cercanos, salud o consejos tácticos, dejando el **100% de la RTX 4070 Super** libre para el juego.
* **Plática continua:** Modo conversacional fluido con detección de interrupciones mediante `Silero VAD`.

---

## 8. Roadmap de Implementación (4 Fases)

* **Fase 1: Hub en Laptop + Satélite PC Gaming (Prioritario)**
  * Servidor `asyncio` con FastAPI/WebSockets en Laptop (`DESKTOP-ANNU1GG`), `OllamaBackend` 4 GB VRAM (`qwen2.5:3b` + `qwen2.5:1.5b` + `moondream`) con Circuit Breaker, `AgendaStore`, `AppController` dinámico (`launch`/`close`) y `pc_game_satellite.py` con `game_frame` sin pérdida de FPS.
* **Fase 2: Galaxy S24+ (Prioritario)**
  * Conexión segura vía Tailscale y cliente móvil en **Galaxy S24+** con `ForegroundService`, One UI Rutinas y ejecución de intents.
* **Fase 3: Galaxy Watch 7 + Android Auto**
  * Cliente Wear OS 5 con Tile/botón físico (sin escucha pasiva) y puente Bluetooth HFP/A2DP desde el S24+ para uso en Android Auto.
* **Fase 4: Automatización Cruzada Avanzada**
  * Automatizaciones coordinadas entre Laptop, PC Gaming y Galaxy S24+ con memoria vectorial.
