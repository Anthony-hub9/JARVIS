package com.jarvis.hud.core.platform

import android.content.Context
import android.content.Intent
import android.net.Uri
import com.jarvis.hud.domain.model.MobileIntent

class AndroidAppLauncher(
    private val context: Context
) {
    fun launch(mobileIntent: MobileIntent): Result<Unit> {
        if (mobileIntent.packageName.isNotBlank()) {
            val packageIntent = context.packageManager
                .getLaunchIntentForPackage(mobileIntent.packageName)
                ?.apply { addFlags(Intent.FLAG_ACTIVITY_NEW_TASK) }

            if (packageIntent != null) {
                return runCatching { context.startActivity(packageIntent) }
            }
        }

        if (mobileIntent.intentUrl.isNotBlank()) {
            val viewIntent = Intent(Intent.ACTION_VIEW, Uri.parse(mobileIntent.intentUrl)).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            return runCatching { context.startActivity(viewIntent) }
        }

        return Result.failure(
            IllegalStateException("No se encontró ${mobileIntent.appName} en este dispositivo.")
        )
    }
}
