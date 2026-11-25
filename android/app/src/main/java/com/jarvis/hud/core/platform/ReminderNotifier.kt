package com.jarvis.hud.core.platform

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.jarvis.hud.R
import com.jarvis.hud.domain.model.AgendaItem

class ReminderNotifier(
    private val context: Context
) {
    private val channelId = context.getString(R.string.notification_channel_id)

    init {
        ensureChannel()
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val channel = NotificationChannel(
                channelId,
                context.getString(R.string.notification_channel_name),
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Alertas de recordatorios enviadas desde el Hub de JARVIS"
                enableVibration(true)
            }
            manager.createNotificationChannel(channel)
        }
    }

    fun showReminder(item: AgendaItem, message: String) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            val granted = ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.POST_NOTIFICATIONS
            ) == PackageManager.PERMISSION_GRANTED
            if (!granted) return
        }

        val subtitle = buildString {
            if (item.whenText.isNotBlank()) append(item.whenText)
            if (item.notes.isNotBlank()) {
                if (isNotEmpty()) append(" • ")
                append(item.notes)
            }
        }.ifEmpty { message }

        val notification = NotificationCompat.Builder(context, channelId)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("JARVIS • ${item.title}")
            .setContentText(subtitle)
            .setStyle(NotificationCompat.BigTextStyle().bigText(subtitle))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .build()

        val id = (item.id.hashCode().takeIf { it != 0 } ?: System.currentTimeMillis().toInt())
        NotificationManagerCompat.from(context).notify(id, notification)
    }
}
