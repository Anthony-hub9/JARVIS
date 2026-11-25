package com.jarvis.hud.domain.usecase

import com.jarvis.hud.domain.repository.JarvisRepository

/**
 * Validates and dispatches a user command to the JARVIS Hub over WebSocket.
 */
class SendCommandUseCase(
    private val repository: JarvisRepository
) {
    suspend operator fun invoke(rawText: String): Result<Unit> {
        val cleaned = rawText.trim()
        if (cleaned.isEmpty()) {
            return Result.failure(IllegalArgumentException("El comando no puede estar vacío."))
        }
        return repository.sendCommand(cleaned)
    }
}
