package com.jarvis.hud.domain.usecase

import com.jarvis.hud.domain.model.MobileAction

/**
 * Pure-Kotlin parser that extracts a [MobileAction] from a `tool_result` JSON payload
 * returned by the JARVIS Hub for S24+ call, notification, and messaging commands.
 */
class ParseMobileActionUseCase {

    operator fun invoke(toolResultJson: String?): MobileAction? {
        if (toolResultJson.isNullOrBlank()) return null

        val device = extractStringField(toolResultJson, "device").orEmpty()
        val hasMobileDevice = device.equals("s24_plus", ignoreCase = true) ||
            device.equals("s24-plus", ignoreCase = true)

        val actionBlock = extractObjectBlock(toolResultJson, "mobile_action") ?: return null
        if (device.isNotEmpty() && !hasMobileDevice) return null

        return when (extractStringField(actionBlock, "type")?.lowercase()) {
            "call_control" -> {
                val action = extractStringField(actionBlock, "action")?.lowercase().orEmpty()
                if (action == "answer" || action == "reject") {
                    MobileAction.CallControl(action = action)
                } else {
                    null
                }
            }

            "read_notifications" -> MobileAction.ReadNotifications

            "reply_notification" -> {
                val message = extractStringField(actionBlock, "message").orEmpty()
                if (message.isEmpty()) return null
                val sender = extractStringField(actionBlock, "sender").orEmpty()
                MobileAction.ReplyNotification(sender = sender, message = message)
            }

            "send_message" -> {
                val channel = extractStringField(actionBlock, "channel")?.lowercase().orEmpty()
                val recipient = extractStringField(actionBlock, "recipient").orEmpty()
                val message = extractStringField(actionBlock, "message").orEmpty()
                if ((channel == "whatsapp" || channel == "sms") &&
                    recipient.isNotEmpty() &&
                    message.isNotEmpty()
                ) {
                    MobileAction.SendMessage(
                        channel = channel,
                        recipient = recipient,
                        message = message
                    )
                } else {
                    null
                }
            }

            "device_control" -> {
                val action = extractStringField(actionBlock, "action")?.lowercase().orEmpty()
                if (action in DEVICE_CONTROL_ACTIONS) {
                    MobileAction.DeviceControl(
                        action = action,
                        value = extractStringField(actionBlock, "value").orEmpty(),
                        label = extractStringField(actionBlock, "label").orEmpty()
                    )
                } else {
                    null
                }
            }

            else -> null
        }
    }

    private fun extractObjectBlock(json: String, key: String): String? {
        val keyRegex = Regex(""""${Regex.escape(key)}"\s*:\s*\{""")
        val match = keyRegex.find(json) ?: return null
        val startBrace = match.range.last
        var depth = 0
        var inString = false
        var escaped = false

        for (i in startBrace until json.length) {
            val ch = json[i]
            if (escaped) {
                escaped = false
                continue
            }
            if (ch == '\\' && inString) {
                escaped = true
                continue
            }
            if (ch == '"') {
                inString = !inString
                continue
            }
            if (!inString) {
                if (ch == '{') depth++
                else if (ch == '}') {
                    depth--
                    if (depth == 0) {
                        return json.substring(startBrace, i + 1)
                    }
                }
            }
        }
        return null
    }

    private fun extractStringField(json: String, key: String): String? {
        val pattern = Regex(""""${Regex.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)"""")
        val match = pattern.find(json) ?: return null
        return match.groupValues[1]
            .replace("\\\"", "\"")
            .replace("\\\\", "\\")
            .replace("\\/", "/")
            .replace("\\n", "\n")
            .trim()
    }

    private companion object {
        val DEVICE_CONTROL_ACTIONS = setOf(
            "flashlight_on",
            "flashlight_off",
            "volume_up",
            "volume_down",
            "volume_set",
            "mute",
            "set_alarm",
            "set_timer"
        )
    }
}
