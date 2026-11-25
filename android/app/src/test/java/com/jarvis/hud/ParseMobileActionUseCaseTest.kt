package com.jarvis.hud

import com.jarvis.hud.domain.model.MobileAction
import com.jarvis.hud.domain.usecase.ParseMobileActionUseCase
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ParseMobileActionUseCaseTest {

    private val parser = ParseMobileActionUseCase()

    @Test
    fun `parses call_control answer and reject`() {
        val answerJson = """
            {
              "tool": "mobile_call",
              "device": "s24_plus",
              "mobile_action": {
                "type": "call_control",
                "action": "answer"
              }
            }
        """.trimIndent()
        val rejectJson = """
            {
              "tool": "mobile_call",
              "device": "s24-plus",
              "mobile_action": {
                "type": "call_control",
                "action": "reject"
              }
            }
        """.trimIndent()

        assertEquals(MobileAction.CallControl("answer"), parser(answerJson))
        assertEquals(MobileAction.CallControl("reject"), parser(rejectJson))
    }

    @Test
    fun `parses read_notifications and reply_notification`() {
        val readJson = """
            {
              "tool": "mobile_notifications",
              "device": "s24_plus",
              "mobile_action": {
                "type": "read_notifications",
                "action": "read",
                "sender": "",
                "message": ""
              }
            }
        """.trimIndent()
        val replyJson = """
            {
              "tool": "mobile_notifications",
              "device": "s24_plus",
              "mobile_action": {
                "type": "reply_notification",
                "action": "reply",
                "sender": "Mamá",
                "message": "Llego en 10 minutos"
              }
            }
        """.trimIndent()

        assertEquals(MobileAction.ReadNotifications, parser(readJson))
        assertEquals(
            MobileAction.ReplyNotification(sender = "Mamá", message = "Llego en 10 minutos"),
            parser(replyJson)
        )
    }

    @Test
    fun `parses send_message for whatsapp and sms`() {
        val whatsappJson = """
            {
              "tool": "mobile_message",
              "device": "s24_plus",
              "mobile_action": {
                "type": "send_message",
                "channel": "whatsapp",
                "recipient": "Carlos",
                "message": "Nos vemos a las 8"
              }
            }
        """.trimIndent()
        val smsJson = """
            {
              "tool": "mobile_message",
              "device": "s24_plus",
              "mobile_action": {
                "type": "send_message",
                "channel": "sms",
                "recipient": "+525512345678",
                "message": "Hola"
              }
            }
        """.trimIndent()

        assertEquals(
            MobileAction.SendMessage("whatsapp", "Carlos", "Nos vemos a las 8"),
            parser(whatsappJson)
        )
        assertEquals(
            MobileAction.SendMessage("sms", "+525512345678", "Hola"),
            parser(smsJson)
        )
    }

    @Test
    fun `returns null for invalid, non-mobile, or unrelated payloads`() {
        assertNull(parser(null))
        assertNull(parser("   "))
        assertNull(parser("""{"tool": "app_launch", "device": "s24_plus"}"""))
        assertNull(
            parser(
                """{"device": "laptop", "mobile_action": {"type": "call_control", "action": "answer"}}"""
            )
        )
        assertNull(
            parser(
                """{"device": "s24_plus", "mobile_action": {"type": "reply_notification", "message": ""}}"""
            )
        )
    }

    @Test
    fun `parses device_control actions`() {
        val flashJson = """
            {
              "tool": "mobile_device_control",
              "device": "s24_plus",
              "mobile_action": {
                "type": "device_control",
                "action": "flashlight_on",
                "value": "",
                "label": ""
              }
            }
        """.trimIndent()
        val alarmJson = """
            {
              "tool": "mobile_device_control",
              "device": "s24_plus",
              "mobile_action": {
                "type": "device_control",
                "action": "set_alarm",
                "value": "07:30",
                "label": "Trabajo"
              }
            }
        """.trimIndent()
        val invalidJson = """
            {
              "tool": "mobile_device_control",
              "device": "s24_plus",
              "mobile_action": {
                "type": "device_control",
                "action": "unknown_hw_action"
              }
            }
        """.trimIndent()

        assertEquals(MobileAction.DeviceControl("flashlight_on", "", ""), parser(flashJson))
        assertEquals(MobileAction.DeviceControl("set_alarm", "07:30", "Trabajo"), parser(alarmJson))
        assertNull(parser(invalidJson))
    }
}
