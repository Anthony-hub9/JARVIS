# Arquitectura de JARVIS

Documento de diseño técnico y hoja de ruta para el asistente personal distribuido **JARVIS**, centrado en un Hub local de alto rendimiento con clientes ligeros conectados de forma segura mediante Tailscale.

---

## 1. Visión General y Topología

El sistema sigue una arquitectura **Hub-and-Spoke** donde todo el procesamiento pesado (voz local en GPU, orquestación de agentes, memoria y automatizaciones) reside en el PC principal, mientras que los dispositivos móviles y portátiles actúan como clientes ligeros de captura y reproducción.

```text
+-------------------+       +-------------------+       +-------------------+
|   Galaxy Watch 7  |       |   Android Auto    |       |      Laptop       |
| (Wear OS 5, Tile) |       | (BT HFP/A2DP via  |       |    (Tailscale)    |
+---------+---------+       |       S24+)       |       +---------+---------+
          |                 +---------+---------+                 |
          +-------------+-------------+                           |
                        |                                         |
                        v                                         v
             +----------+----------+                   +----------+----------+
             |  Galaxy S24+ (Hub   |                   |     Red Mesh VPN    |
             |  móvil / Rutinas /  +------------------>+     (Tailscale)     |
             |  ForegroundService) |   WebSockets      +----------+----------+
             +---------------------+                              |
                                                                  v
                                                       +----------+----------+
                                                       |   HUB CENTRAL (PC)  |
                                                       | Python 3.12+ / GPU  |
                                                       +---------------------+
```

---

## 2. Hub Central (PC Principal)

* **Hardware:** AMD Ryzen 5 7600X, NVIDIA RTX 4070 Super (12 GB VRAM), 32 GB RAM, Windows.
* **Runtime y Backend:** Python 3.12+ (`asyncio`), **FastAPI** + **WebSockets** bidireccionales en tiempo real.
* **Red y Seguridad:** Exposición privada exclusivamente sobre **Tailscale** (sin puertos públicos abiertos en el router).

---

## 3. Clientes Ligeros

| Dispositivo | Rol y Mecanismo de Activación | Transporte |
| :--- | :--- | :--- |
| **Laptop (`DESKTOP-ANNU1GG`)** | Windows, Intel Core i5-10300H @ 2.50GHz, ~20 GB RAM. Cliente ligero de escritorio para audio, texto y comandos remotos (con `openWakeWord` + `Silero VAD` opcional en CPU). | WebSocket sobre Tailscale |
| **Samsung Galaxy S24+** | Cliente móvil principal. Integración con **One UI Rutinas** y `ForegroundService` persistente para mantener la conexión y el puente de audio/notificaciones. | WebSocket sobre Tailscale |
| **Galaxy Watch 7** | **Wear OS 5**. Activación bajo demanda mediante **Tile** o **botón físico** (sin escucha pasiva para preservar batería). | Puente vía S24+ / Tailscale |
| **Android Auto** | Interacción manos libres en vehículo mediante puente **Bluetooth HFP/A2DP** gestionado desde el Galaxy S24+. | BT HFP/A2DP → S24+ → Hub |

---

## 4. Arquitectura de Doble Agente (Obligatoria)

Todas las acciones y respuestas críticas pasan por un flujo de validación en dos etapas para garantizar precisión y seguridad:

1. **Agente Ejecutor (`gemini-4-hydrogen-medium`):**
   * Interpreta la intención del usuario, planifica los pasos, consulta herramientas/memoria y genera la propuesta de acción o respuesta.
2. **Agente Supervisor / Gatekeeper (`gemini-4-argon-medium`):**
   * Audita el plan o la salida del Ejecutor antes de ejecutar acciones sensibles (mensajes, llamadas, automatizaciones, cambios en agenda).
   * **Circuit Breaker:** Máximo **2 reintentos** ante fallos de validación o errores de ejecución. Si se supera el límite, el circuito se abre, se aborta la acción de forma segura y se informa al usuario.

---

## 5. Pipeline de Voz Local en GPU

Todo el procesamiento de audio se ejecuta localmente en la **RTX 4070 Super (12 GB)** para minimizar la latencia y preservar la privacidad:

* **Detección de Wake Word y VAD:** `openWakeWord` + `Silero VAD` para detección de palabra clave y segmentación precisa de voz/silencio.
* **STT (Speech-to-Text):** `faster-whisper` con modelo `large-v3-turbo` acelerado por **CUDA**.
* **TTS (Text-to-Speech):** `Kokoro` / `Piper` en modo **streaming**, enviando fragmentos de audio al cliente correspondiente conforme se generan.

---

## 6. Sistema de Memoria

* **Memoria a Corto Plazo (Contexto activo):** Almacenada en **RAM / Redis** para mantener el estado de la conversación actual, sesiones activas por dispositivo y caché de baja latencia.
* **Memoria a Largo Plazo:**
  * **SQLite:** Datos estructurados, historial de interacciones, configuraciones y registro local de eventos.
  * **ChromaDB / Qdrant:** Base de datos vectorial para búsqueda semántica, recuerdos persistentes y recuperación de contexto relevante (RAG).

---

## 7. Funciones v1

* **Búsqueda web por voz:** Consultas rápidas en tiempo real con síntesis de respuesta hablada.
* **Mensajes y llamadas:** Envío de mensajes y realización de llamadas con **confirmación obligatoria** del supervisor `argon` antes de despachar.
* **Agenda:** Gestión de eventos y recordatorios sincronizados con **Google Calendar + SQLite** local.
* **Plática continua:** Modo conversacional fluido con detección de interrupciones mediante `Silero VAD`.
* **Apoyo en videojuegos:** Activación por **hotkey**, captura de pantalla ultrarrápida con `mss` y análisis mediante **Visión** sin necesidad de hacer *alt-tab*.

---

## 8. Roadmap de Implementación (4 Fases)

* **Fase 1: Núcleo PC + Doble Agente**
  * Servidor `asyncio` con FastAPI/WebSockets, pipeline de voz local (`openWakeWord`, `Silero VAD`, `faster-whisper`, `Kokoro`/`Piper`), memoria base y flujo Ejecutor (`hydrogen`) + Supervisor (`argon`) con Circuit Breaker.
* **Fase 2: Hub + Galaxy S24+**
  * Conexión segura vía Tailscale, cliente ligero en S24+ con `ForegroundService` y One UI Rutinas, además de funciones v1 de agenda, búsqueda web y mensajes/llamadas confirmadas.
* **Fase 3: Galaxy Watch 7 + Android Auto**
  * Cliente Wear OS 5 con Tile/botón físico (sin escucha pasiva) y puente Bluetooth HFP/A2DP desde el S24+ para uso en Android Auto.
* **Fase 4: Visión y Automatización Cruzada**
  * Apoyo en videojuegos (`hotkey` + `mss` + Visión sin *alt-tab*) y automatizaciones coordinadas entre PC, Laptop y dispositivos móviles.
