package com.jarvis.hud.data.repository

import com.jarvis.hud.data.local.SettingsPrefs
import com.jarvis.hud.data.network.JarvisApiClient
import com.jarvis.hud.domain.model.AgendaItem
import com.jarvis.hud.domain.model.HubEvent
import com.jarvis.hud.domain.model.HubHealth
import com.jarvis.hud.domain.model.VoiceProfile
import com.jarvis.hud.domain.repository.JarvisRepository
import kotlinx.coroutines.flow.Flow

class JarvisRepositoryImpl(
    private val apiClient: JarvisApiClient,
    private val prefs: SettingsPrefs
) : JarvisRepository {

    override val hubEvents: Flow<HubEvent> = apiClient.hubEvents

    override fun connectWebSocket() = apiClient.connectWebSocket()

    override fun disconnectWebSocket() = apiClient.disconnectWebSocket()

    override suspend fun sendCommand(text: String): Result<Unit> = apiClient.sendCommand(text)

    override suspend fun sendImageCommand(prompt: String, imageBase64: String): Result<Unit> =
        apiClient.sendImageCommand(prompt, imageBase64)

    override suspend fun fetchHealth(): Result<HubHealth> = apiClient.fetchHealth()

    override suspend fun fetchAgenda(upcomingOnly: Boolean): Result<List<AgendaItem>> =
        apiClient.fetchAgenda(upcomingOnly)

    override suspend fun createAgenda(
        title: String,
        whenText: String,
        notes: String
    ): Result<AgendaItem> = apiClient.createAgenda(title, whenText, notes)

    override suspend fun fetchApps(): Result<List<String>> = apiClient.fetchApps()

    override suspend fun openDesktopApp(appName: String): Result<Unit> =
        apiClient.openDesktopApp(appName)

    override suspend fun synthesizeTts(text: String, voice: VoiceProfile): Result<ByteArray> =
        apiClient.synthesizeTts(text, voice)

    override fun getHubUrl(): String = prefs.getHubUrl()

    override fun setHubUrl(url: String) {
        val previous = prefs.getHubUrl()
        prefs.setHubUrl(url)
        if (prefs.getHubUrl() != previous) {
            apiClient.connectWebSocket()
        }
    }

    override fun getVoiceProfile(): VoiceProfile = prefs.getVoiceProfile()

    override fun setVoiceProfile(profile: VoiceProfile) {
        prefs.setVoiceProfile(profile)
    }
}
