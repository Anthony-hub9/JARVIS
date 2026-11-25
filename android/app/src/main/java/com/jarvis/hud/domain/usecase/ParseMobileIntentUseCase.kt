package com.jarvis.hud.domain.usecase

import com.jarvis.hud.domain.model.MobileIntent

/**
 * Pure-Kotlin parser that extracts a [MobileIntent] from a `tool_result` JSON payload
 * returned by the JARVIS Hub when targeting the S24+ device.
 */
class ParseMobileIntentUseCase {

    operator fun invoke(toolResultJson: String?): MobileIntent? {
        if (toolResultJson.isNullOrBlank()) return null

        val packageName = extractStringField(toolResultJson, "package").orEmpty()
        val intentUrl = extractStringField(toolResultJson, "intent_url").orEmpty()
        val appName = extractStringField(toolResultJson, "app_name").orEmpty()
        val device = extractStringField(toolResultJson, "device").orEmpty()
        val requiresNativeBridge = extractBooleanField(toolResultJson, "requires_native_bridge")

        val isMobileTarget = device.equals("s24_plus", ignoreCase = true) ||
            device.equals("s24-plus", ignoreCase = true) ||
            packageName.isNotEmpty() ||
            intentUrl.isNotEmpty()

        if (!isMobileTarget || (packageName.isEmpty() && intentUrl.isEmpty())) {
            return null
        }

        return MobileIntent(
            appName = appName.ifEmpty { packageName },
            packageName = packageName,
            intentUrl = intentUrl,
            requiresNativeBridge = requiresNativeBridge
        )
    }

    private fun extractStringField(json: String, key: String): String? {
        val pattern = Regex(""""${Regex.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)"""")
        val match = pattern.find(json) ?: return null
        return match.groupValues[1]
            .replace("\\\"", "\"")
            .replace("\\\\", "\\")
            .replace("\\/", "/")
            .trim()
    }

    private fun extractBooleanField(json: String, key: String): Boolean {
        val pattern = Regex(""""${Regex.escape(key)}"\s*:\s*(true|false)""", RegexOption.IGNORE_CASE)
        return pattern.find(json)?.groupValues?.get(1)?.equals("true", ignoreCase = true) ?: false
    }
}
