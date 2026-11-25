package com.jarvis.hud.core.platform

import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WhatsAppAutoSendArmerTest {

    @After
    fun tearDown() {
        WhatsAppAutoSendArmer.disarm()
    }

    @Test
    fun `never armed by default and consumes only once`() {
        WhatsAppAutoSendArmer.disarm()
        assertFalse(WhatsAppAutoSendArmer.isArmed())
        assertFalse(WhatsAppAutoSendArmer.consumeIfArmed())

        WhatsAppAutoSendArmer.arm(timeoutMs = 10_000L)
        assertTrue(WhatsAppAutoSendArmer.isArmed())
        assertTrue(WhatsAppAutoSendArmer.consumeIfArmed())
        assertFalse(WhatsAppAutoSendArmer.isArmed())
        assertFalse(WhatsAppAutoSendArmer.consumeIfArmed())
    }

    @Test
    fun `expired arming returns false`() {
        WhatsAppAutoSendArmer.arm(timeoutMs = 0L)
        Thread.sleep(5L)
        assertFalse(WhatsAppAutoSendArmer.isArmed())
        assertFalse(WhatsAppAutoSendArmer.consumeIfArmed())
    }
}
