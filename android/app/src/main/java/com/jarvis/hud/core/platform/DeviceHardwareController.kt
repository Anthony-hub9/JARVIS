package com.jarvis.hud.core.platform

import android.content.Context
import android.content.Intent
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.media.AudioManager
import android.provider.AlarmClock
import com.jarvis.hud.domain.model.MobileAction
import kotlin.math.roundToInt

/**
 * Executes S24+ hardware and system actions: flashlight torch, media volume, alarms, and timers.
 */
class DeviceHardwareController(private val context: Context) {

    fun execute(action: MobileAction.DeviceControl): Result<Unit> = runCatching {
        when (action.action) {
            "flashlight_on" -> setFlashlight(enabled = true)
            "flashlight_off" -> setFlashlight(enabled = false)
            "volume_up" -> adjustVolume(AudioManager.ADJUST_RAISE)
            "volume_down" -> adjustVolume(AudioManager.ADJUST_LOWER)
            "mute" -> adjustVolume(AudioManager.ADJUST_MUTE)
            "volume_set" -> setVolumePercent(action.value.toIntOrNull() ?: error("Volumen inválido: ${action.value}"))
            "set_alarm" -> setAlarm(action.value, action.label)
            "set_timer" -> setTimer(action.value.toIntOrNull() ?: error("Duración inválida: ${action.value}"), action.label)
            else -> error("Acción de dispositivo no soportada: ${action.action}")
        }
    }

    private fun setFlashlight(enabled: Boolean) {
        val cameraManager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val cameraId = cameraManager.cameraIdList.firstOrNull { id ->
            val characteristics = cameraManager.getCameraCharacteristics(id)
            characteristics.get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true
        } ?: error("No se encontró cámara con flash disponible.")
        cameraManager.setTorchMode(cameraId, enabled)
    }

    private fun adjustVolume(direction: Int) {
        val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        audioManager.adjustStreamVolume(
            AudioManager.STREAM_MUSIC,
            direction,
            AudioManager.FLAG_SHOW_UI
        )
    }

    private fun setVolumePercent(percent: Int) {
        val clamped = percent.coerceIn(0, 100)
        val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val maxVolume = audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
        val target = ((clamped / 100f) * maxVolume).roundToInt().coerceIn(0, maxVolume)
        audioManager.setStreamVolume(
            AudioManager.STREAM_MUSIC,
            target,
            AudioManager.FLAG_SHOW_UI
        )
    }

    private fun setAlarm(timeValue: String, label: String) {
        val parts = timeValue.split(":")
        val hour = parts.getOrNull(0)?.toIntOrNull()
        val minutes = parts.getOrNull(1)?.toIntOrNull() ?: 0
        if (hour == null || hour !in 0..23 || minutes !in 0..59) {
            error("Hora de alarma inválida: $timeValue")
        }
        val intent = Intent(AlarmClock.ACTION_SET_ALARM).apply {
            putExtra(AlarmClock.EXTRA_HOUR, hour)
            putExtra(AlarmClock.EXTRA_MINUTES, minutes)
            putExtra(AlarmClock.EXTRA_SKIP_UI, true)
            if (label.isNotBlank()) {
                putExtra(AlarmClock.EXTRA_MESSAGE, label)
            }
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    }

    private fun setTimer(seconds: Int, label: String) {
        if (seconds <= 0) error("El temporizador debe ser mayor a 0 segundos.")
        val intent = Intent(AlarmClock.ACTION_SET_TIMER).apply {
            putExtra(AlarmClock.EXTRA_LENGTH, seconds)
            putExtra(AlarmClock.EXTRA_SKIP_UI, true)
            if (label.isNotBlank()) {
                putExtra(AlarmClock.EXTRA_MESSAGE, label)
            }
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    }
}
