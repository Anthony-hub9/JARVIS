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

    @Test
    fun `detects common Spanish STT phonetic variants of jarvis`() {
        assertEquals(WakeWordResult.Command("qué hora es"), matcher.match("yarvis qué hora es"))
        assertEquals(WakeWordResult.Command("abre Spotify"), matcher.match("Oye jarbis, abre Spotify"))
        assertEquals(WakeWordResult.Command("pon música"), matcher.match("harvis pon música"))
        assertEquals(WakeWordResult.BareWakeWord, matcher.match("garvis"))
        assertEquals(WakeWordResult.BareWakeWord, matcher.match("charvis"))
        assertEquals(WakeWordResult.Command("dime el clima"), matcher.match("yarbis, dime el clima"))
    }

    @Test
    fun `selectBestMatch prefers wake word candidate in wake-word mode`() {
        val matches = listOf("oye travis abre whatsapp", "oye yarvis abre whatsapp", "oye jarbis")
        assertEquals(
            "oye yarvis abre whatsapp",
            matcher.selectBestMatch(matches, isWakeWordMode = true)
        )
        assertEquals(
            "oye travis abre whatsapp",
            matcher.selectBestMatch(matches, isWakeWordMode = false)
        )
    }

    @Test
    fun `selectBestMatch falls back cleanly when no wake word or empty list`() {
        assertEquals(
            "primera opción",
            matcher.selectBestMatch(listOf("primera opción", "segunda opción"), isWakeWordMode = true)
        )
        assertEquals("", matcher.selectBestMatch(emptyList(), isWakeWordMode = true))
        assertEquals("", matcher.selectBestMatch(listOf("   "), isWakeWordMode = false))
    }
}
