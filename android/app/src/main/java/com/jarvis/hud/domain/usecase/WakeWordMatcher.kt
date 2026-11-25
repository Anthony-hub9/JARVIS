package com.jarvis.hud.domain.usecase

import java.text.Normalizer

sealed interface WakeWordResult {
    data object NotDetected : WakeWordResult
    data object BareWakeWord : WakeWordResult
    data class Command(val commandText: String) : WakeWordResult
}

/**
 * Normalizes Spanish diacritics and detects the "jarvis" wake word,
 * extracting any trailing command while preserving original accents/casing.
 */
class WakeWordMatcher {

    private val wakeWordRegex = Regex("""\bjarvis\b""", RegexOption.IGNORE_CASE)
    private val combiningMarksRegex = Regex("""\p{InCombiningDiacriticalMarks}+""")

    fun match(transcript: String): WakeWordResult {
        val trimmed = transcript.trim()
        if (trimmed.isEmpty()) return WakeWordResult.NotDetected

        val normalized = normalizeAccents(trimmed)
        val match = wakeWordRegex.find(normalized) ?: return WakeWordResult.NotDetected

        val afterIndex = (match.range.last + 1).coerceAtMost(trimmed.length)
        val remainder = trimmed.substring(afterIndex)
            .trimStart(' ', ',', ':', ';', '.', '!', '¡', '?', '¿', '-')
            .trim()

        return if (remainder.isEmpty()) {
            WakeWordResult.BareWakeWord
        } else {
            WakeWordResult.Command(remainder)
        }
    }

    fun normalizeAccents(input: String): String {
        val decomposed = Normalizer.normalize(input, Normalizer.Form.NFD)
        return combiningMarksRegex.replace(decomposed, "").lowercase()
    }
}
