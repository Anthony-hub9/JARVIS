package com.jarvis.hud.data.network

import android.util.Log
import com.jarvis.hud.domain.model.AgendaItem
import com.jarvis.hud.domain.model.ConnectionStatus
import com.jarvis.hud.domain.model.HubEvent
import com.jarvis.hud.domain.model.HubHealth
import com.jarvis.hud.domain.model.VoiceProfile
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class JarvisApiClient(
    private val baseUrlProvider: () -> String
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private val client = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private val _hubEvents = MutableSharedFlow<HubEvent>(extraBufferCapacity = 64)
    val hubEvents: Flow<HubEvent> = _hubEvents.asSharedFlow()

    @Volatile
    private var webSocket: WebSocket? = null

    @Volatile
    private var shouldReconnect = false

    private var reconnectJob: Job? = null

    fun connectWebSocket() {
        shouldReconnect = true
        reconnectJob?.cancel()
        openSocket()
    }

    fun disconnectWebSocket() {
        shouldReconnect = false
        reconnectJob?.cancel()
        webSocket?.close(1000, "Client disconnected")
        webSocket = null
        _hubEvents.tryEmit(HubEvent.ConnectionChanged(ConnectionStatus.DISCONNECTED))
    }

    private fun openSocket() {
        webSocket?.cancel()
        val wsUrl = toWebSocketUrl(baseUrlProvider()) + "/ws/$DEVICE_ID"
        _hubEvents.tryEmit(HubEvent.ConnectionChanged(ConnectionStatus.CONNECTING))

        val request = Request.Builder().url(wsUrl).build()
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.d(TAG, "onOpen: code=${response.code}")
                _hubEvents.tryEmit(HubEvent.ConnectionChanged(ConnectionStatus.CONNECTED))
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                Log.d(TAG, "onMessage: length=${text.length}")
                parseWsMessage(text)
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(1000, null)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                _hubEvents.tryEmit(HubEvent.ConnectionChanged(ConnectionStatus.DISCONNECTED))
                scheduleReconnect()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.d(TAG, "onFailure: code=${response?.code}, error=${t::class.simpleName}")
                _hubEvents.tryEmit(HubEvent.ConnectionChanged(ConnectionStatus.ERROR))
                _hubEvents.tryEmit(
                    HubEvent.ErrorEvent(t.message ?: "Error de conexión WebSocket con el Hub")
                )
                scheduleReconnect()
            }
        })
    }

    private fun scheduleReconnect() {
        if (!shouldReconnect) return
        reconnectJob?.cancel()
        reconnectJob = scope.launch {
            delay(RECONNECT_DELAY_MS)
            if (shouldReconnect) {
                openSocket()
            }
        }
    }

    private fun parseWsMessage(raw: String) {
        runCatching {
            val json = JSONObject(raw)
            if (json.optString("type") == "reminder_alert") {
                val ev = json.optJSONObject("event")
                val item = AgendaItem(
                    id = ev?.optString("id").orEmpty(),
                    title = ev?.optString("title").orEmpty().ifEmpty { "Recordatorio" },
                    whenText = ev?.optString("when").orEmpty(),
                    notes = ev?.optString("notes").orEmpty()
                )
                val msg = json.optString("response").ifEmpty { "Recordatorio: ${item.title}" }
                _hubEvents.tryEmit(HubEvent.ReminderAlert(message = msg, item = item))
                return
            }

            val toolResultObj = json.optJSONObject("tool_result")
            _hubEvents.tryEmit(
                HubEvent.AssistantReply(
                    response = json.optString("response"),
                    approved = json.optBoolean("approved", true),
                    attempts = json.optInt("attempts", 1),
                    circuitBroken = json.optBoolean("circuit_broken", false),
                    toolResultJson = toolResultObj?.toString()
                )
            )
        }.onFailure { err ->
            _hubEvents.tryEmit(HubEvent.ErrorEvent("Error al parsear respuesta: ${err.message}"))
        }
    }

    suspend fun sendCommand(text: String): Result<Unit> = withContext(Dispatchers.IO) {
        val socket = webSocket
        if (socket == null) {
            Log.d(TAG, "sendCommand: skipped, socket disconnected (length=${text.length})")
            return@withContext Result.failure(IllegalStateException("WebSocket desconectado"))
        }
        val sent = socket.send(text)
        Log.d(TAG, "sendCommand: sent=$sent, length=${text.length}")
        if (sent) {
            Result.success(Unit)
        } else {
            Result.failure(IOException("No se pudo enviar el comando por WebSocket"))
        }
    }

    suspend fun sendImageCommand(prompt: String, imageBase64: String): Result<Unit> {
        val payload = JSONObject()
            .put("prompt", prompt)
            .put("image_base64", imageBase64)
            .toString()
        return sendCommand(payload)
    }

    suspend fun fetchHealth(): Result<HubHealth> = executeJsonGet("/health") { json ->
        HubHealth(
            status = json.optString("status", "unknown"),
            backend = json.optString("backend", ""),
            executor = json.optString("executor", ""),
            supervisor = json.optString("supervisor", ""),
            vision = json.optString("vision", "")
        )
    }

    suspend fun fetchAgenda(upcomingOnly: Boolean): Result<List<AgendaItem>> =
        executeJsonGet("/api/agenda?upcoming=$upcomingOnly") { json ->
            val arr = json.optJSONArray("events") ?: return@executeJsonGet emptyList()
            buildList {
                for (i in 0 until arr.length()) {
                    val obj = arr.optJSONObject(i) ?: continue
                    add(obj.toAgendaItem())
                }
            }
        }

    suspend fun createAgenda(title: String, whenText: String, notes: String): Result<AgendaItem> {
        val body = JSONObject()
            .put("title", title)
            .put("when", whenText)
            .put("notes", notes)
        return executeJsonPost("/api/agenda", body) { json ->
            json.optJSONObject("event")?.toAgendaItem()
                ?: AgendaItem(id = "", title = title, whenText = whenText, notes = notes)
        }
    }

    suspend fun fetchApps(): Result<List<String>> = executeJsonGet("/api/apps") { json ->
        val arr = json.optJSONArray("apps") ?: return@executeJsonGet emptyList()
        buildList {
            for (i in 0 until arr.length()) {
                val app = arr.optString(i)
                if (app.isNotBlank()) add(app)
            }
        }
    }

    suspend fun openDesktopApp(appName: String): Result<Unit> {
        val body = JSONObject().put("app_name", appName)
        return executeJsonPost("/api/apps/open", body) { Unit }
    }

    suspend fun synthesizeTts(text: String, voice: VoiceProfile): Result<ByteArray> {
        val body = JSONObject()
            .put("text", text)
            .put("voice", voice.id)
        val request = Request.Builder()
            .url("${baseUrlProvider()}/api/tts")
            .post(body.toString().toRequestBody(JSON_MEDIA_TYPE))
            .build()
        return executeRaw(request)
    }

    private suspend fun <T> executeJsonGet(path: String, mapper: (JSONObject) -> T): Result<T> {
        val request = Request.Builder()
            .url("${baseUrlProvider()}$path")
            .get()
            .build()
        return executeRaw(request).mapCatching { bytes ->
            mapper(JSONObject(bytes.decodeToString()))
        }
    }

    private suspend fun <T> executeJsonPost(
        path: String,
        body: JSONObject,
        mapper: (JSONObject) -> T
    ): Result<T> {
        val request = Request.Builder()
            .url("${baseUrlProvider()}$path")
            .post(body.toString().toRequestBody(JSON_MEDIA_TYPE))
            .build()
        return executeRaw(request).mapCatching { bytes ->
            mapper(JSONObject(bytes.decodeToString()))
        }
    }

    private suspend fun executeRaw(request: Request): Result<ByteArray> = withContext(Dispatchers.IO) {
        runCatching {
            client.newCall(request).execute().use { response ->
                val bytes = response.body?.bytes() ?: ByteArray(0)
                if (!response.isSuccessful) {
                    val detail = runCatching {
                        JSONObject(bytes.decodeToString()).optString("detail")
                    }.getOrNull().orEmpty()
                    throw IOException(detail.ifEmpty { "HTTP ${response.code}" })
                }
                bytes
            }
        }
    }

    private fun JSONObject.toAgendaItem() = AgendaItem(
        id = optString("id"),
        title = optString("title"),
        whenText = optString("when"),
        notes = optString("notes")
    )

    private fun toWebSocketUrl(httpUrl: String): String = when {
        httpUrl.startsWith("https://", ignoreCase = true) ->
            "wss://" + httpUrl.removePrefix("https://")
        httpUrl.startsWith("http://", ignoreCase = true) ->
            "ws://" + httpUrl.removePrefix("http://")
        else -> "ws://$httpUrl"
    }

    companion object {
        const val DEVICE_ID = "s24-plus"
        private const val TAG = "JarvisApi"
        private const val RECONNECT_DELAY_MS = 3000L
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
    }
}
