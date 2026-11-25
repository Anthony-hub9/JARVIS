package com.jarvis.hud.core.platform

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.telecom.TelecomManager
import androidx.core.content.ContextCompat

class PhoneCallController(private val context: Context) {

    @SuppressLint("MissingPermission")
    fun answerCall(): Result<Unit> {
        if (!hasCallPermission()) {
            return Result.failure(
                SecurityException("Falta el permiso para contestar llamadas en el S24+.")
            )
        }
        val telecomManager = context.getSystemService(TelecomManager::class.java)
            ?: return Result.failure(IllegalStateException("Servicio de llamadas no disponible."))
        return runCatching {
            telecomManager.acceptRingingCall()
        }
    }

    @SuppressLint("MissingPermission")
    @Suppress("DEPRECATION")
    fun rejectCall(): Result<Unit> {
        if (!hasCallPermission()) {
            return Result.failure(
                SecurityException("Falta el permiso para colgar o rechazar llamadas en el S24+.")
            )
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) {
            return Result.failure(
                UnsupportedOperationException("Rechazar llamadas requiere Android 9 o superior.")
            )
        }
        val telecomManager = context.getSystemService(TelecomManager::class.java)
            ?: return Result.failure(IllegalStateException("Servicio de llamadas no disponible."))
        return runCatching {
            val ended = telecomManager.endCall()
            if (!ended) {
                throw IllegalStateException("No hay ninguna llamada activa o entrante.")
            }
        }
    }

    private fun hasCallPermission(): Boolean =
        ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.ANSWER_PHONE_CALLS
        ) == PackageManager.PERMISSION_GRANTED
}
