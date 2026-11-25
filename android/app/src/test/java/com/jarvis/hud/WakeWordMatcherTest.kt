package com.jarvis.hud

import com.jarvis.hud.domain.usecase.WakeWordMatcher
import com.jarvis.hud.domain.usecase.WakeWordResult
import org.junit.Assert.assertEquals
import org.junit.Test

class WakeWordMatcherTest {

    private val matcher = WakeWordMatcher()

    @Test
    fun `detects command after jarvis wake word`() {
        val result = matcher.match("jarvis qué hora es")
        assertEquals(WakeWordResult.Command("qué hora es"), result)
    }

    @Test
    fun `normalizes accented jarvis and strips punctuation`() {
        val result = matcher.match("Oye Járvis, abre WhatsApp por favor")
        assertEquals(WakeWordResult.Command("abre WhatsApp por favor"), result)
    }

    @Test
    fun `returns BareWakeWord when only jarvis is spoken`() {
        assertEquals(WakeWordResult.BareWakeWord, matcher.match("  Jarvis! "))
        assertEquals(WakeWordResult.BareWakeWord, matcher.match("oye járvis"))
    }

    @Test
    fun `returns NotDetected when wake word is absent or partial`() {
        assertEquals(WakeWordResult.NotDetected, matcher.match("qué hora es"))
        assertEquals(WakeWordResult.NotDetected, matcher.match("jarvisito abre spotify"))
        assertEquals(WakeWordResult.NotDetected, matcher.match("   "))
    }
}
