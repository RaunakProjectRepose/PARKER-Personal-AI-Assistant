package com.raunakprojectrepose.parker

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

enum class Status(val label: String) {
    Connecting("CONNECTING"), Ready("READY"), Listening("LISTENING"),
    Thinking("THINKING"), Speaking("SPEAKING"), Offline("OFFLINE"),
}

class ParkerViewModel(app: Application) : AndroidViewModel(app) {
    var pairing by mutableStateOf(Pairing.load(app))
        private set
    var status by mutableStateOf(Status.Connecting)
        private set
    var today by mutableStateOf<Today?>(null)
        private set
    var confirmation by mutableStateOf<Confirmation?>(null)
        private set
    var problem by mutableStateOf<String?>(null)
        private set
    var speakReplies by mutableStateOf(true)
    val messages = mutableStateListOf<ChatMessage>()

    private var client: ParkerClient? = pairing?.let { ParkerClient(it) }

    /** Set by the activity: returns true if the microphone may be used (asks if not). */
    var micGate: () -> Boolean = { true }
    private val recorder = Recorder()
    private val player = Player(app)

    init {
        if (client != null) connect()
    }

    /** From a scanned QR code. Returns false if it wasn't a PARKER code. */
    fun pair(scanned: String): Boolean {
        val parsed = Pairing.parse(scanned) ?: return false
        Pairing.save(getApplication(), parsed)
        pairing = parsed
        client = ParkerClient(parsed)
        messages.clear()
        connect()
        return true
    }

    fun unpair() {
        Pairing.save(getApplication(), null)
        pairing = null
        client = null
        messages.clear()
        today = null
    }

    fun connect() = work(Status.Connecting) { c ->
        c.connect()
        val t = c.today()
        withContext(Dispatchers.Main) {
            today = t
            if (messages.isEmpty()) messages += ChatMessage("parker", t.greeting)
        }
    }

    fun refreshToday() = work(null) { c ->
        val t = c.today()
        withContext(Dispatchers.Main) { today = t }
    }

    fun send(text: String) {
        val clean = text.trim()
        if (clean.isEmpty()) return
        messages += ChatMessage("user", clean, fromMe = true)
        work(Status.Thinking) { c -> show(c.message(clean)) }
    }

    fun toggleTalking() {
        when (status) {
            Status.Listening -> {
                val wav = recorder.stop()
                work(Status.Thinking) { c ->
                    val reply = c.voice(wav)
                    withContext(Dispatchers.Main) {
                        if (reply.heard.isNotBlank()) messages += ChatMessage("user", reply.heard, fromMe = true)
                    }
                    show(reply)
                }
            }
            Status.Speaking -> stopSpeaking()
            else -> {
                if (!micGate()) return
                player.stop()
                recorder.start()
                status = Status.Listening
            }
        }
    }

    fun stopSpeaking() {
        player.stop()
        if (status == Status.Speaking) status = Status.Ready
    }

    fun answer(yes: Boolean) {
        val pending = confirmation ?: return
        confirmation = null
        work(Status.Thinking) { c -> show(c.confirm(pending.id, yes)) }
    }

    fun dismissProblem() {
        problem = null
    }

    // ---- helpers ---------------------------------------------------------------
    private suspend fun show(reply: Reply) {
        withContext(Dispatchers.Main) {
            messages += reply.messages
            confirmation = reply.confirm
        }
        val spoken = reply.messages.filter { it.kind == "parker" }.joinToString(" ") { it.text }
        if (speakReplies && spoken.isNotBlank()) {
            val audio = client?.speak(spoken) ?: return
            withContext(Dispatchers.Main) {
                status = Status.Speaking
                player.play(audio) { if (status == Status.Speaking) status = Status.Ready }
            }
        }
    }

    /** Runs network work off the main thread and turns failures into a readable message. */
    private fun work(busy: Status?, block: suspend (ParkerClient) -> Unit) {
        val c = client ?: return
        if (busy != null) status = busy
        viewModelScope.launch(Dispatchers.IO) {
            val failure = runCatching { block(c) }.exceptionOrNull()
            withContext(Dispatchers.Main) {
                if (failure != null) {
                    problem = failure.message ?: "Something went wrong."
                    status = if (busy == Status.Connecting) Status.Offline else Status.Ready
                } else if (status != Status.Speaking && busy != null) {
                    status = Status.Ready
                }
            }
        }
    }

    override fun onCleared() {
        player.stop()
        if (recorder.isRecording) recorder.stop()
    }
}
