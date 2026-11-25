package com.jarvis.hud.data.local

import android.content.Context
import android.content.SharedPreferences
import com.jarvis.hud.domain.model.VoiceProfile

class SettingsPrefs(context: Context) {

    private val prefs: SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun getHubUrl(): String =
        normalizeUrl(prefs.getString(KEY_HUB_URL, DEFAULT_HUB_URL) ?: DEFAULT_HUB_URL)

    fun setHubUrl(url: String) {
        prefs.edit().putString(KEY_HUB_URL, normalizeUrl(url)).apply()
    }

    fun getVoiceProfile(): VoiceProfile =
        VoiceProfile.fromId(prefs.getString(KEY_VOICE_PROFILE, VoiceProfile.JARVIS.id))

    fun setVoiceProfile(profile: VoiceProfile) {
        prefs.edit().putString(KEY_VOICE_PROFILE, profile.id).apply()
    }

    private fun normalizeUrl(raw: String): String {
        val trimmed = raw.trim().trimEnd('/')
        return trimmed.ifEmpty { DEFAULT_HUB_URL }
    }

    companion object {
        private const val PREFS_NAME = "jarvis_hud_prefs"
        private const val KEY_HUB_URL = "hub_url"
        private const val KEY_VOICE_PROFILE = "voice_profile"
        const val DEFAULT_HUB_URL = "http://100.72.40.20:8000"
    }
}
