package com.jarvis.hud.domain.repository

import com.jarvis.hud.domain.model.AgendaItem
import com.jarvis.hud.domain.model.HubEvent
import com.jarvis.hud.domain.model.HubHealth
import com.jarvis.hud.domain.model.VoiceProfile
import kotlinx.coroutines.flow.Flow

interface JarvisRepository {
    val hubEvents: Flow<HubEvent>

    fun connectWebSocket()
    fun disconnectWebSocket()
    suspend fun sendCommand(text: String): Result<Unit>
    suspend fun sendImageCommand(prompt: String, imageBase64: String): Result<Unit>

    suspend fun fetchHealth(): Result<HubHealth>
    suspend fun fetchAgenda(upcomingOnly: Boolean = false): Result<List<AgendaItem>>
    suspend fun createAgenda(title: String, whenText: String, notes: String = ""): Result<AgendaItem>
    suspend fun fetchApps(): Result<List<String>>
    suspend fun openDesktopApp(appName: String): Result<Unit>
    suspend fun synthesizeTts(text: String, voice: VoiceProfile): Result<ByteArray>

    fun getHubUrl(): String
    fun setHubUrl(url: String)
    fun getVoiceProfile(): VoiceProfile
    fun setVoiceProfile(profile: VoiceProfile)
}
