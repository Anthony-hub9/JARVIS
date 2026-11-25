package com.jarvis.hud.core.platform

import android.app.Notification
import android.app.RemoteInput
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification

data class CachedNotification(
    val key: String,
    val packageName: String,
    val appName: String,
    val sender: String,
    val text: String,
    val timestampMs: Long,
    val replyAction: Notification.Action?,
    val remoteInput: RemoteInput?
)

object NotificationCache {
    private const val MAX_ITEMS = 25
    private val items = mutableListOf<CachedNotification>()
    private val lock = Any()

    fun put(notification: CachedNotification) {
        synchronized(lock) {
            items.removeAll { it.key == notification.key }
            items.add(0, notification)
            if (items.size > MAX_ITEMS) {
                items.subList(MAX_ITEMS, items.size).clear()
            }
        }
    }

    fun removeByKey(key: String) {
        synchronized(lock) {
            items.removeAll { it.key == key }
        }
    }

    fun recent(limit: Int = 5): List<CachedNotification> {
        synchronized(lock) {
            return items.take(limit.coerceAtLeast(1))
        }
    }

    fun reply(context: Context, senderQuery: String, message: String): Result<CachedNotification> {
        val target = synchronized(lock) {
            val cleanQuery = senderQuery.trim()
            val replyable = items.filter { it.replyAction != null && it.remoteInput != null }
            if (cleanQuery.isNotEmpty()) {
                replyable.firstOrNull { it.sender.contains(cleanQuery, ignoreCase = true) }
            } else {
                replyable.firstOrNull()
            }
        } ?: return Result.failure(
            IllegalStateException(
                if (senderQuery.isBlank()) {
                    "No hay notificaciones recientes con respuesta rápida disponible."
                } else {
                    "No encontré mensajes recientes de $senderQuery para responder."
                }
            )
        )

        val action = target.replyAction ?: return Result.failure(
            IllegalStateException("La notificación no admite respuesta directa.")
        )
        val remoteInput = target.remoteInput ?: return Result.failure(
            IllegalStateException("La notificación no tiene campo de respuesta.")
        )

        return runCatching {
            val intent = Intent()
            val bundle = Bundle().apply {
                putCharSequence(remoteInput.resultKey, message)
            }
            RemoteInput.addResultsToIntent(arrayOf(remoteInput), intent, bundle)
            action.actionIntent.send(context, 0, intent)
            target
        }
    }

    fun isEnabled(context: Context): Boolean {
        val enabled = Settings.Secure.getString(
            context.contentResolver,
            "enabled_notification_listeners"
        ).orEmpty()
        val component = ComponentName(context, JarvisNotificationListenerService::class.java)
        return enabled.split(':').any { entry ->
            entry.equals(component.flattenToString(), ignoreCase = true) ||
                entry.equals(component.flattenToShortString(), ignoreCase = true)
        }
    }
}

class JarvisNotificationListenerService : NotificationListenerService() {

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        val notification = sbn?.notification ?: return
        val pkg = sbn.packageName ?: return
        val appLabel = SUPPORTED_PACKAGES[pkg] ?: return

        if ((notification.flags and Notification.FLAG_GROUP_SUMMARY) != 0) {
            return
        }

        val extras = notification.extras ?: return
        val sender = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString()?.trim().orEmpty()
        val rawText = (extras.getCharSequence(Notification.EXTRA_BIG_TEXT)
            ?: extras.getCharSequence(Notification.EXTRA_TEXT))?.toString()?.trim().orEmpty()

        if (sender.isEmpty() && rawText.isEmpty()) return

        var foundAction: Notification.Action? = null
        var foundRemoteInput: RemoteInput? = null
        notification.actions?.forEach { action ->
            val remote = action.remoteInputs?.firstOrNull()
            if (remote != null && foundAction == null) {
                foundAction = action
                foundRemoteInput = remote
            }
        }

        NotificationCache.put(
            CachedNotification(
                key = sbn.key,
                packageName = pkg,
                appName = appLabel,
                sender = sender.ifEmpty { appLabel },
                text = rawText,
                timestampMs = sbn.postTime,
                replyAction = foundAction,
                remoteInput = foundRemoteInput
            )
        )
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification?) {
        val key = sbn?.key ?: return
        NotificationCache.removeByKey(key)
    }

    companion object {
        private val SUPPORTED_PACKAGES = mapOf(
            "com.whatsapp" to "WhatsApp",
            "com.whatsapp.w4b" to "WhatsApp Business",
            "com.google.android.apps.messaging" to "Mensajes",
            "com.samsung.android.messaging" to "Mensajes",
            "com.android.mms" to "SMS",
            "org.telegram.messenger" to "Telegram",
            "org.telegram.messenger.web" to "Telegram"
        )
    }
}
