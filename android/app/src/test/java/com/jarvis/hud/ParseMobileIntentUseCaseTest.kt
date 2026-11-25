package com.jarvis.hud

import com.jarvis.hud.domain.model.MobileIntent
import com.jarvis.hud.domain.usecase.ParseMobileIntentUseCase
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ParseMobileIntentUseCaseTest {

    private val parser = ParseMobileIntentUseCase()

    @Test
    fun `parses valid s24_plus tool_result json`() {
        val json = """
            {
              "device": "s24_plus",
              "action": "android.intent.action.MAIN",
              "category": "android.intent.category.LAUNCHER",
              "package": "com.whatsapp",
              "app_name": "whatsapp",
              "intent_url": "whatsapp://",
              "requires_native_bridge": false
            }
        """.trimIndent()

        val result = parser(json)

        assertEquals(
            MobileIntent(
                appName = "whatsapp",
                packageName = "com.whatsapp",
                intentUrl = "whatsapp://",
                requiresNativeBridge = false
            ),
            result
        )
    }

    @Test
    fun `parses native bridge app without intent_url`() {
        val json = """
            {
              "device": "s24_plus",
              "package": "com.sec.android.app.popupcalculator",
              "app_name": "calculadora",
              "intent_url": "",
              "requires_native_bridge": true
            }
        """.trimIndent()

        val result = parser(json)

        assertEquals(
            MobileIntent(
                appName = "calculadora",
                packageName = "com.sec.android.app.popupcalculator",
                intentUrl = "",
                requiresNativeBridge = true
            ),
            result
        )
    }

    @Test
    fun `returns null for blank or non-mobile tool_result`() {
        assertNull(parser(null))
        assertNull(parser("   "))
        assertNull(parser("""{"status": "opened", "app": "chrome", "pid": 1234}"""))
    }
}
