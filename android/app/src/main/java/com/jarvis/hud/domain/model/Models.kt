package com.jarvis.hud.domain.model

enum class OrbState {
    IDLE,
    LISTENING,
    THINKING,
    SPEAKING
}

enum class VoiceProfile(val id: String, val label: String) {
    JARVIS("jarvis", "JARVIS"),
    ALBEDO("albedo", "Albedo");

    companion object {
        fun fromId(id: String?): VoiceProfile =
            entries.firstOrNull { it.id.equals(id, ignoreCase = true) } ?: JARVIS
    }
}

enum class ConnectionStatus {
    DISCONNECTED,
    CONNECTING,
    CONNECTED,
    ERROR
}

data class MobileIntent(
    val appName: String,
    val packageName: String,
    val intentUrl: String,
    val requiresNativeBridge: Boolean = false
)

sealed interface MobileAction {
    data class CallControl(val action: String) : MobileAction
    data object ReadNotifications : MobileAction
    data class ReplyNotification(val sender: String, val message: String) : MobileAction
    data class SendMessage(
        val channel: String,
        val recipient: String,
        val message: String
    ) : MobileAction
    data class DeviceControl(
        val action: String,
        val value: String = "",
        val label: String = ""
    ) : MobileAction
}

data class ChatMessage(
    val id: String,
    val text: String,
    val isFromUser: Boolean,
    val approved: Boolean = true,
    val attempts: Int = 1,
    val circuitBroken: Boolean = false,
    val isReminder: Boolean = false,
    val mobileIntent: MobileIntent? = null,
    val timestampMs: Long = System.currentTimeMillis()
)

data class AgendaItem(
    val id: String,
    val title: String,
    val whenText: String,
    val notes: String = ""
)

data class HubHealth(
    val status: String,
    val backend: String,
    val executor: String,
    val supervisor: String,
    val vision: String
)

sealed interface HubEvent {
    data class ConnectionChanged(val status: ConnectionStatus) : HubEvent
    data class AssistantReply(
        val response: String,
        val approved: Boolean,
        val attempts: Int,
        val circuitBroken: Boolean,
        val toolResultJson: String? = null
    ) : HubEvent
    data class ReminderAlert(val message: String, val item: AgendaItem) : HubEvent
    data class ErrorEvent(val message: String) : HubEvent
}
