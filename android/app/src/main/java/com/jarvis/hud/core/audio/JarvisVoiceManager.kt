package com.jarvis.hud.core.audio

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import androidx.core.content.ContextCompat
import java.io.File
import java.util.Locale

class JarvisVoiceManager(
    private val context: Context,
    private val onTranscript: (text: String, isWakeWordMode: Boolean) -> Unit,
    private val onListeningChanged: (Boolean) -> Unit,
    private val onSpeakingChanged: (Boolean) -> Unit,
    private val onError: (String) -> Unit
) {
    private val mainHandler = Handler(Looper.getMainLooper())
    private var speechRecognizer: SpeechRecognizer? = null
    private var mediaPlayer: MediaPlayer? = null
    private var currentTempAudioFile: File? = null
    private var androidTts: TextToSpeech? = null
    private var ttsReady = false

    @Volatile
    private var wakeWordEnabled = false

    @Volatile
    private var isSpeaking = false

    @Volatile
    private var isListening = false

    @Volatile
    private var awaitingActiveCommand = false

    private var lastErrorReportMs = 0L

    init {
        initAndroidTts()
    }

    private fun initAndroidTts() {
        androidTts = TextToSpeech(context.applicationContext) { status ->
            if (status == TextToSpeech.SUCCESS) {
                val locale = Locale("es", "MX")
                val result = androidTts?.setLanguage(locale)
                ttsReady = result != TextToSpeech.LANG_MISSING_DATA &&
                    result != TextToSpeech.LANG_NOT_SUPPORTED
                androidTts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) = Unit
                    override fun onDone(utteranceId: String?) = finishSpeaking()
                    @Deprecated("Deprecated in Java")
                    override fun onError(utteranceId: String?) = finishSpeaking()
                })
            }
        }
    }

    fun startSingleShot(activeFollowUp: Boolean = false) {
        mainHandler.post {
            awaitingActiveCommand = activeFollowUp
            if (isSpeaking) stopSpeakingInternal()
            startRecognizerInternal()
        }
    }

    fun setWakeWordEnabled(enabled: Boolean) {
        wakeWordEnabled = enabled
        mainHandler.post {
            if (enabled) {
                if (!isSpeaking && !isListening) {
                    awaitingActiveCommand = false
                    startRecognizerInternal()
                }
            } else {
                awaitingActiveCommand = false
                stopRecognizerInternal()
            }
        }
    }

    fun stopListening() {
        wakeWordEnabled = false
        awaitingActiveCommand = false
        mainHandler.post { stopRecognizerInternal() }
    }

    fun speak(text: String, audioBytes: ByteArray?) {
        if (text.isBlank() && audioBytes == null) return
        Log.d(TAG, "speak: textLength=${text.length}, hasAudioBytes=${audioBytes != null && audioBytes.isNotEmpty()}")
        mainHandler.post {
            isSpeaking = true
            onSpeakingChanged(true)
            stopRecognizerInternal()

            if (audioBytes != null && audioBytes.isNotEmpty()) {
                val played = playAudioBytes(audioBytes)
                if (played) return@post
            }
            speakWithAndroidTts(text)
        }
    }

    private fun playAudioBytes(bytes: ByteArray): Boolean {
        return try {
            releaseMediaPlayer()
            val tempFile = File.createTempFile("jarvis_tts_", ".mp3", context.cacheDir)
            currentTempAudioFile = tempFile
            tempFile.writeBytes(bytes)

            mediaPlayer = MediaPlayer().apply {
                setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ASSISTANT)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                setDataSource(tempFile.absolutePath)
                setOnCompletionListener {
                    releaseMediaPlayer()
                    finishSpeaking()
                }
                setOnErrorListener { _, _, _ ->
                    releaseMediaPlayer()
                    false
                }
                prepare()
                start()
            }
            true
        } catch (_: Exception) {
            releaseMediaPlayer()
            false
        }
    }

    private fun speakWithAndroidTts(text: String) {
        if (ttsReady && androidTts != null) {
            androidTts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "jarvis_utterance")
        } else {
            finishSpeaking()
        }
    }

    private fun finishSpeaking() {
        mainHandler.post {
            isSpeaking = false
            onSpeakingChanged(false)
            if (wakeWordEnabled && !isListening) {
                scheduleWakeWordRestart(250L)
            }
        }
    }

    private fun stopSpeakingInternal() {
        releaseMediaPlayer()
        androidTts?.stop()
        isSpeaking = false
        onSpeakingChanged(false)
    }

    private fun startRecognizerInternal() {
        Log.d(
            TAG,
            "startRecognizerInternal: wakeWord=$wakeWordEnabled, awaitingActive=$awaitingActiveCommand, isSpeaking=$isSpeaking"
        )
        val hasAudioPermission = ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED
        if (!hasAudioPermission) {
            Log.d(TAG, "startRecognizerInternal: missing RECORD_AUDIO permission")
            isListening = false
            onListeningChanged(false)
            onError("Falta permiso de micrófono.")
            return
        }
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            Log.d(TAG, "startRecognizerInternal: recognition unavailable")
            onError("Reconocimiento de voz no disponible en este dispositivo.")
            return
        }
        if (isSpeaking) return

        recreateRecognizer()
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "es-MX")
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "es-MX")
            putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, context.packageName)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        }
        isListening = true
        onListeningChanged(true)
        runCatching {
            speechRecognizer?.startListening(intent)
        }.onFailure { err ->
            Log.d(TAG, "startRecognizerInternal: startListening failed: ${err.message}")
            isListening = false
            onListeningChanged(false)
            onError(err.message ?: "No se pudo iniciar el micrófono.")
        }
    }

    private fun stopRecognizerInternal() {
        isListening = false
        onListeningChanged(false)
        runCatching { speechRecognizer?.cancel() }
    }

    private fun recreateRecognizer() {
        runCatching { speechRecognizer?.destroy() }
        speechRecognizer = null
        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(context).apply {
            setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) {
                    Log.d(TAG, "onReadyForSpeech")
                }
                override fun onBeginningOfSpeech() = Unit
                override fun onRmsChanged(rmsdB: Float) = Unit
                override fun onBufferReceived(buffer: ByteArray?) = Unit
                override fun onEndOfSpeech() {
                    isListening = false
                    onListeningChanged(false)
                }

                override fun onError(error: Int) {
                    Log.d(
                        TAG,
                        "onError: code=$error, wakeWord=$wakeWordEnabled, awaitingActive=$awaitingActiveCommand"
                    )
                    isListening = false
                    onListeningChanged(false)
                    val isNoMatchOrTimeout = error == SpeechRecognizer.ERROR_NO_MATCH ||
                        error == SpeechRecognizer.ERROR_SPEECH_TIMEOUT
                    if (!(wakeWordEnabled && isNoMatchOrTimeout)) {
                        reportErrorThrottled(mapSpeechError(error))
                    }
                    if (wakeWordEnabled && !isSpeaking) {
                        scheduleWakeWordRestart(450L)
                    }
                }

                override fun onResults(results: Bundle?) {
                    isListening = false
                    onListeningChanged(false)
                    val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    val text = matches?.firstOrNull()?.trim().orEmpty()
                    val isWakeLoop = wakeWordEnabled && !awaitingActiveCommand
                    awaitingActiveCommand = false
                    Log.d(
                        TAG,
                        "onResults: matches=${matches?.size ?: 0}, textLength=${text.length}, isWakeLoop=$isWakeLoop"
                    )

                    if (text.isNotEmpty()) {
                        onTranscript(text, isWakeLoop)
                    } else if (wakeWordEnabled && !isSpeaking) {
                        scheduleWakeWordRestart(300L)
                    }
                }

                override fun onPartialResults(partialResults: Bundle?) = Unit
                override fun onEvent(eventType: Int, params: Bundle?) = Unit
            })
        }
    }

    private fun reportErrorThrottled(message: String) {
        val now = SystemClock.elapsedRealtime()
        if (!wakeWordEnabled || now - lastErrorReportMs >= ERROR_THROTTLE_MS) {
            lastErrorReportMs = now
            onError(message)
        }
    }

    private fun mapSpeechError(error: Int): String = when (error) {
        SpeechRecognizer.ERROR_NETWORK,
        SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "Error de red en el reconocimiento de voz."
        SpeechRecognizer.ERROR_AUDIO -> "Error de audio en el micrófono."
        SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Falta permiso de micrófono."
        SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "El reconocedor de voz está ocupado."
        SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE -> "Idioma de voz no disponible en el dispositivo."
        SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED -> "Idioma de voz no compatible en este dispositivo."
        SpeechRecognizer.ERROR_NO_MATCH -> "No se entendió lo que dijiste."
        SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "No se detectó voz a tiempo."
        else -> "Error de voz ($error)."
    }

    private fun scheduleWakeWordRestart(delayMs: Long) {
        mainHandler.postDelayed({
            if (wakeWordEnabled && !isSpeaking && !isListening) {
                startRecognizerInternal()
            }
        }, delayMs)
    }

    private fun releaseMediaPlayer() {
        runCatching {
            mediaPlayer?.stop()
            mediaPlayer?.release()
        }
        mediaPlayer = null
        runCatching { currentTempAudioFile?.delete() }
        currentTempAudioFile = null
    }

    fun release() {
        wakeWordEnabled = false
        mainHandler.removeCallbacksAndMessages(null)
        mainHandler.post {
            runCatching { speechRecognizer?.destroy() }
            speechRecognizer = null
            releaseMediaPlayer()
            androidTts?.shutdown()
            androidTts = null
        }
    }

    companion object {
        private const val TAG = "JarvisVoice"
        private const val ERROR_THROTTLE_MS = 4000L
    }
}
