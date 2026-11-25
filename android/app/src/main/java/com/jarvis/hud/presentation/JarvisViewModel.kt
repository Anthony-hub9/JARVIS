package com.jarvis.hud.presentation

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.jarvis.hud.core.audio.JarvisVoiceManager
import com.jarvis.hud.core.platform.AndroidAppLauncher
import com.jarvis.hud.core.platform.ContactAndMessageHelper
import com.jarvis.hud.core.platform.DeviceHardwareController
import com.jarvis.hud.core.platform.JarvisForegroundService
import com.jarvis.hud.core.platform.NotificationCache
import com.jarvis.hud.core.platform.PhoneCallController
import com.jarvis.hud.core.platform.ReminderNotifier
import com.jarvis.hud.data.local.SettingsPrefs
import com.jarvis.hud.data.network.JarvisApiClient
import com.jarvis.hud.data.repository.JarvisRepositoryImpl
import com.jarvis.hud.domain.model.AgendaItem
import com.jarvis.hud.domain.model.ChatMessage
import com.jarvis.hud.domain.model.ConnectionStatus
import com.jarvis.hud.domain.model.HubEvent
import com.jarvis.hud.domain.model.HubHealth
import com.jarvis.hud.domain.model.MobileAction
import com.jarvis.hud.domain.model.MobileIntent
import com.jarvis.hud.domain.model.OrbState
import com.jarvis.hud.domain.model.VoiceProfile
import com.jarvis.hud.domain.repository.JarvisRepository
import com.jarvis.hud.domain.usecase.ParseMobileActionUseCase
import com.jarvis.hud.domain.usecase.ParseMobileIntentUseCase
import com.jarvis.hud.domain.usecase.SendCommandUseCase
import com.jarvis.hud.domain.usecase.WakeWordMatcher
import com.jarvis.hud.domain.usecase.WakeWordResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID

data class JarvisUiState(
    val orbState: OrbState = OrbState.IDLE,
    val connectionStatus: ConnectionStatus = ConnectionStatus.DISCONNECTED,
    val messages: List<ChatMessage> = emptyList(),
    val inputText: String = "",
    val ttsEnabled: Boolean = true,
    val wakeWordEnabled: Boolean = false,
    val voiceProfile: VoiceProfile = VoiceProfile.JARVIS,
    val hubUrl: String = SettingsPrefs.DEFAULT_HUB_URL,
    val health: HubHealth? = null,
    val agendaItems: List<AgendaItem> = emptyList(),
    val isAgendaLoading: Boolean = false,
    val laptopApps: List<String> = emptyList(),
    val appSearchQuery: String = "",
    val isAppsLoading: Boolean = false,
    val notificationAccessEnabled: Boolean = false,
    val backgroundServiceEnabled: Boolean = false,
    val statusBanner: String? = null
)

class JarvisViewModel(
    private val repository: JarvisRepository,
    private val sendCommandUseCase: SendCommandUseCase,
    private val parseMobileIntentUseCase: ParseMobileIntentUseCase,
    private val parseMobileActionUseCase: ParseMobileActionUseCase,
    private val wakeWordMatcher: WakeWordMatcher,
    private val appLauncher: AndroidAppLauncher,
    private val phoneCallController: PhoneCallController,
    private val contactAndMessageHelper: ContactAndMessageHelper,
    private val deviceHardwareController: DeviceHardwareController,
    private val reminderNotifier: ReminderNotifier,
    private val appContext: Context
) : ViewModel() {

    private val _uiState = MutableStateFlow(
        JarvisUiState(
            voiceProfile = repository.getVoiceProfile(),
            hubUrl = repository.getHubUrl()
        )
    )
    val uiState: StateFlow<JarvisUiState> = _uiState.asStateFlow()

    private val voiceManager = JarvisVoiceManager(
        context = appContext,
        onTranscript = ::handleVoiceTranscript,
        onListeningChanged = { listening ->
            _uiState.update { state ->
                val nextOrb = when {
                    listening -> OrbState.LISTENING
                    state.orbState == OrbState.LISTENING -> OrbState.IDLE
                    else -> state.orbState
                }
                state.copy(orbState = nextOrb)
            }
        },
        onSpeakingChanged = { speaking ->
            _uiState.update { state ->
                val nextOrb = when {
                    speaking -> OrbState.SPEAKING
                    state.orbState == OrbState.SPEAKING -> OrbState.IDLE
                    else -> state.orbState
                }
                state.copy(orbState = nextOrb)
            }
        },
        onError = { msg -> showBanner(msg) }
    )

    init {
        observeHubEvents()
        repository.connectWebSocket()
        refreshNotificationAccess()
        refreshHealth()
        refreshAgenda()
        refreshApps()
    }

    private fun observeHubEvents() {
        viewModelScope.launch {
            repository.hubEvents.collect { event ->
                when (event) {
                    is HubEvent.ConnectionChanged -> {
                        _uiState.update { it.copy(connectionStatus = event.status) }
                    }

                    is HubEvent.AssistantReply -> {
                        val mobileIntent = parseMobileIntentUseCase(event.toolResultJson)
                        val mobileAction = parseMobileActionUseCase(event.toolResultJson)
                        val displayResponse = if (mobileAction != null) {
                            executeMobileAction(mobileAction, event.response)
                        } else {
                            event.response
                        }
                        val msg = ChatMessage(
                            id = UUID.randomUUID().toString(),
                            text = displayResponse,
                            isFromUser = false,
                            approved = event.approved,
                            attempts = event.attempts,
                            circuitBroken = event.circuitBroken,
                            mobileIntent = mobileIntent
                        )
                        _uiState.update { state ->
                            state.copy(
                                orbState = OrbState.IDLE,
                                messages = state.messages + msg
                            )
                        }
                        if (mobileIntent != null) {
                            launchMobileApp(mobileIntent)
                        }
                        if (_uiState.value.ttsEnabled) {
                            speakResponse(displayResponse)
                        }
                    }

                    is HubEvent.ReminderAlert -> {
                        reminderNotifier.showReminder(event.item, event.message)
                        val msg = ChatMessage(
                            id = UUID.randomUUID().toString(),
                            text = event.message,
                            isFromUser = false,
                            isReminder = true
                        )
                        _uiState.update { it.copy(messages = it.messages + msg) }
                        if (_uiState.value.ttsEnabled) {
                            speakResponse(event.message)
                        }
                        refreshAgenda()
                    }

                    is HubEvent.ErrorEvent -> {
                        _uiState.update { state ->
                            val nextOrb = if (state.orbState == OrbState.THINKING) {
                                OrbState.IDLE
                            } else {
                                state.orbState
                            }
                            state.copy(orbState = nextOrb, statusBanner = event.message)
                        }
                    }
                }
            }
        }
    }

    fun onInputTextChanged(value: String) {
        _uiState.update { it.copy(inputText = value) }
    }

    fun sendCurrentInput() {
        val text = _uiState.value.inputText
        if (text.isBlank()) return
        _uiState.update { it.copy(inputText = "") }
        sendCommand(text)
    }

    fun sendCommand(rawText: String) {
        val cleaned = rawText.trim()
        if (cleaned.isEmpty()) return

        val userMsg = ChatMessage(
            id = UUID.randomUUID().toString(),
            text = cleaned,
            isFromUser = true
        )
        _uiState.update {
            it.copy(
                orbState = OrbState.THINKING,
                messages = it.messages + userMsg,
                statusBanner = null
            )
        }

        viewModelScope.launch {
            sendCommandUseCase(cleaned).onFailure { err ->
                _uiState.update {
                    it.copy(
                        orbState = OrbState.IDLE,
                        statusBanner = err.message ?: "Error al enviar comando"
                    )
                }
            }
        }
    }

    fun onOrbOrMicClicked() {
        when (_uiState.value.orbState) {
            OrbState.LISTENING -> voiceManager.stopListening()
            else -> voiceManager.startSingleShot(activeFollowUp = false)
        }
    }

    fun toggleWakeWord(enabled: Boolean) {
        _uiState.update { it.copy(wakeWordEnabled = enabled) }
        voiceManager.setWakeWordEnabled(enabled)
        if (enabled) {
            showBanner("Escucha continua activa: di \"Jarvis\" seguido de tu comando.")
        }
    }

    fun toggleTts(enabled: Boolean) {
        _uiState.update { it.copy(ttsEnabled = enabled) }
    }

    fun toggleBackgroundService(enabled: Boolean) {
        _uiState.update { it.copy(backgroundServiceEnabled = enabled) }
        if (enabled) {
            JarvisForegroundService.start(appContext)
            showBanner("J.A.R.V.I.S. activo en segundo plano.")
        } else {
            JarvisForegroundService.stop(appContext)
            showBanner("Servicio en segundo plano detenido.")
        }
    }

    fun sendVisionBitmap(
        imageBase64: String,
        prompt: String = "Describe esta foto"
    ) {
        if (imageBase64.isBlank()) return
        val userMsg = ChatMessage(
            id = UUID.randomUUID().toString(),
            text = "📷 $prompt",
            isFromUser = true
        )
        _uiState.update {
            it.copy(
                orbState = OrbState.THINKING,
                messages = it.messages + userMsg,
                statusBanner = null
            )
        }
        viewModelScope.launch {
            repository.sendImageCommand(prompt, imageBase64).onFailure { err ->
                _uiState.update {
                    it.copy(
                        orbState = OrbState.IDLE,
                        statusBanner = err.message ?: "Error al enviar imagen"
                    )
                }
            }
        }
    }

    fun launchMobileApp(intent: MobileIntent) {
        appLauncher.launch(intent).onFailure { err ->
            showBanner(err.message ?: "No se pudo abrir ${intent.appName}")
        }
    }

    private fun handleVoiceTranscript(transcript: String, isWakeWordMode: Boolean) {
        if (!isWakeWordMode) {
            sendCommand(transcript)
            return
        }

        when (val result = wakeWordMatcher.match(transcript)) {
            is WakeWordResult.Command -> sendCommand(result.commandText)
            WakeWordResult.BareWakeWord -> {
                showBanner("Te escucho, dime tu comando...")
                voiceManager.startSingleShot(activeFollowUp = true)
            }
            WakeWordResult.NotDetected -> {
                if (_uiState.value.wakeWordEnabled) {
                    voiceManager.setWakeWordEnabled(true)
                }
            }
        }
    }

    private fun speakResponse(text: String) {
        viewModelScope.launch {
            val audioBytes = repository.synthesizeTts(text, _uiState.value.voiceProfile).getOrNull()
            voiceManager.speak(text, audioBytes)
        }
    }

    fun refreshHealth() {
        viewModelScope.launch {
            repository.fetchHealth()
                .onSuccess { health -> _uiState.update { it.copy(health = health) } }
                .onFailure { _uiState.update { it.copy(health = null) } }
        }
    }

    fun refreshAgenda() {
        _uiState.update { it.copy(isAgendaLoading = true) }
        viewModelScope.launch {
            repository.fetchAgenda(upcomingOnly = false)
                .onSuccess { items ->
                    _uiState.update { it.copy(agendaItems = items, isAgendaLoading = false) }
                }
                .onFailure { err ->
                    _uiState.update {
                        it.copy(
                            isAgendaLoading = false,
                            statusBanner = err.message ?: "No se pudo cargar la agenda"
                        )
                    }
                }
        }
    }

    fun createAgendaItem(title: String, whenText: String, notes: String) {
        viewModelScope.launch {
            repository.createAgenda(title, whenText, notes)
                .onSuccess {
                    showBanner("Recordatorio guardado: $title")
                    refreshAgenda()
                }
                .onFailure { err ->
                    showBanner(err.message ?: "Error al crear recordatorio")
                }
        }
    }

    fun refreshApps() {
        _uiState.update { it.copy(isAppsLoading = true) }
        viewModelScope.launch {
            repository.fetchApps()
                .onSuccess { apps ->
                    _uiState.update { it.copy(laptopApps = apps, isAppsLoading = false) }
                }
                .onFailure { err ->
                    _uiState.update {
                        it.copy(
                            isAppsLoading = false,
                            statusBanner = err.message ?: "No se pudieron cargar las apps"
                        )
                    }
                }
        }
    }

    fun onAppSearchChanged(query: String) {
        _uiState.update { it.copy(appSearchQuery = query) }
    }

    fun openLaptopApp(appName: String) {
        viewModelScope.launch {
            repository.openDesktopApp(appName)
                .onSuccess { showBanner("Abriendo $appName en la Laptop") }
                .onFailure { err -> showBanner(err.message ?: "Error al abrir $appName") }
        }
    }

    fun updateHubUrl(url: String) {
        repository.setHubUrl(url)
        _uiState.update { it.copy(hubUrl = repository.getHubUrl()) }
        refreshHealth()
        refreshAgenda()
        refreshApps()
        showBanner("Hub actualizado: ${repository.getHubUrl()}")
    }

    fun updateVoiceProfile(profile: VoiceProfile) {
        repository.setVoiceProfile(profile)
        _uiState.update { it.copy(voiceProfile = profile) }
    }

    fun reconnectHub() {
        repository.connectWebSocket()
        refreshHealth()
    }

    fun refreshNotificationAccess() {
        val enabled = NotificationCache.isEnabled(appContext)
        _uiState.update { it.copy(notificationAccessEnabled = enabled) }
    }

    private fun executeMobileAction(action: MobileAction, fallbackResponse: String): String {
        return when (action) {
            is MobileAction.CallControl -> {
                val res = if (action.action == "answer") {
                    phoneCallController.answerCall()
                } else {
                    phoneCallController.rejectCall()
                }
                res.fold(
                    onSuccess = { fallbackResponse },
                    onFailure = { err ->
                        val msg = err.message ?: "No se pudo controlar la llamada."
                        showBanner(msg)
                        msg
                    }
                )
            }

            MobileAction.ReadNotifications -> {
                if (!NotificationCache.isEnabled(appContext)) {
                    "Activa el acceso a notificaciones en la pestaña Control para leer tus mensajes."
                } else {
                    val recent = NotificationCache.recent(limit = 5)
                    if (recent.isEmpty()) {
                        "No tienes mensajes recientes en caché."
                    } else {
                        val summary = recent.joinToString(". ") { item ->
                            "${item.appName} de ${item.sender}: ${item.text}"
                        }
                        "Tienes ${recent.size} mensajes recientes. $summary"
                    }
                }
            }

            is MobileAction.ReplyNotification -> {
                NotificationCache.reply(appContext, action.sender, action.message).fold(
                    onSuccess = { target ->
                        "Respuesta enviada a ${target.sender} por ${target.appName}."
                    },
                    onFailure = { err ->
                        val msg = err.message ?: "No se pudo responder al mensaje."
                        showBanner(msg)
                        msg
                    }
                )
            }

            is MobileAction.SendMessage -> {
                val res = if (action.channel == "sms") {
                    contactAndMessageHelper.sendSms(action.recipient, action.message)
                } else {
                    contactAndMessageHelper.openWhatsApp(action.recipient, action.message)
                }
                res.fold(
                    onSuccess = {
                        if (action.channel == "sms") {
                            showBanner("SMS enviado a ${action.recipient}")
                        }
                        fallbackResponse
                    },
                    onFailure = { err ->
                        val msg = err.message ?: "No se pudo enviar el mensaje."
                        showBanner(msg)
                        msg
                    }
                )
            }

            is MobileAction.DeviceControl -> {
                deviceHardwareController.execute(action).fold(
                    onSuccess = { fallbackResponse },
                    onFailure = { err ->
                        val msg = err.message ?: "No se pudo ejecutar el control del dispositivo."
                        showBanner(msg)
                        msg
                    }
                )
            }
        }
    }

    fun clearBanner() {
        _uiState.update { it.copy(statusBanner = null) }
    }

    private fun showBanner(message: String) {
        _uiState.update { it.copy(statusBanner = message) }
    }

    override fun onCleared() {
        super.onCleared()
        voiceManager.release()
        repository.disconnectWebSocket()
    }

    class Factory(private val context: Context) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            val appCtx = context.applicationContext
            val prefs = SettingsPrefs(appCtx)
            val apiClient = JarvisApiClient { prefs.getHubUrl() }
            val repository = JarvisRepositoryImpl(apiClient, prefs)
            return JarvisViewModel(
                repository = repository,
                sendCommandUseCase = SendCommandUseCase(repository),
                parseMobileIntentUseCase = ParseMobileIntentUseCase(),
                parseMobileActionUseCase = ParseMobileActionUseCase(),
                wakeWordMatcher = WakeWordMatcher(),
                appLauncher = AndroidAppLauncher(appCtx),
                phoneCallController = PhoneCallController(appCtx),
                contactAndMessageHelper = ContactAndMessageHelper(appCtx),
                deviceHardwareController = DeviceHardwareController(appCtx),
                reminderNotifier = ReminderNotifier(appCtx),
                appContext = appCtx
            ) as T
        }
    }
}
