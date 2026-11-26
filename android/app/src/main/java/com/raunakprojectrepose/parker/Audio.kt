package com.raunakprojectrepose.parker

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaPlayer
import android.media.MediaRecorder
import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

const val SAMPLE_RATE = 16_000
private const val MAX_SECONDS = 30

/** 16-bit mono PCM -> a complete WAV file (what the laptop's /api/voice expects). */
fun pcmToWav(pcm: ByteArray, sampleRate: Int = SAMPLE_RATE): ByteArray {
    val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN).apply {
        put("RIFF".toByteArray()); putInt(36 + pcm.size); put("WAVE".toByteArray())
        put("fmt ".toByteArray()); putInt(16); putShort(1); putShort(1)
        putInt(sampleRate); putInt(sampleRate * 2); putShort(2); putShort(16)
        put("data".toByteArray()); putInt(pcm.size)
    }
    return header.array() + pcm
}

/** Push-to-talk recorder: start(), then stop() returns the recording as WAV. */
class Recorder {
    @Volatile private var recording = false
    private var thread: Thread? = null
    private val buffer = ByteArrayOutputStream()

    val isRecording get() = recording

    @SuppressLint("MissingPermission") // checked by MainActivity before starting
    fun start() {
        if (recording) return
        val minSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val record = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION, SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, minSize * 4,
        )
        buffer.reset()
        recording = true
        record.startRecording()
        thread = Thread {
            val chunk = ByteArray(minSize)
            val limit = SAMPLE_RATE * 2 * MAX_SECONDS
            while (recording && buffer.size() < limit) {
                val n = record.read(chunk, 0, chunk.size)
                if (n > 0) buffer.write(chunk, 0, n)
            }
            record.stop()
            record.release()
        }.apply { start() }
    }

    fun stop(): ByteArray {
        recording = false
        thread?.join(2000)
        thread = null
        return pcmToWav(buffer.toByteArray())
    }
}

/** Plays PARKER's spoken replies (WAV from the laptop). */
class Player(private val context: Context) {
    private var player: MediaPlayer? = null

    fun play(wav: ByteArray, onDone: () -> Unit = {}) {
        stop()
        val file = File(context.cacheDir, "parker-reply.wav").apply { writeBytes(wav) }
        player = MediaPlayer().apply {
            setDataSource(file.path)
            setOnCompletionListener { onDone() }
            prepare()
            start()
        }
    }

    fun stop() {
        player?.runCatching { stop(); release() }
        player = null
    }
}
