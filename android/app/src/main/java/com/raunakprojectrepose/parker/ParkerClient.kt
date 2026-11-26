package com.raunakprojectrepose.parker

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

/**
 * Trusts exactly one certificate: the one made on the paired laptop, whose
 * SHA-256 fingerprint came in the QR code. Any other server is refused, so
 * another device on the Wi-Fi can't read the traffic or pretend to be PARKER.
 */
class PinnedTrustManager(fingerprintHex: String) : X509TrustManager {
    private val expected = fingerprintHex.chunked(2).map { it.toInt(16).toByte() }.toByteArray()

    override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
        val leaf = chain?.firstOrNull() ?: throw CertificateException("No certificate")
        val actual = MessageDigest.getInstance("SHA-256").digest(leaf.encoded)
        if (!MessageDigest.isEqual(actual, expected)) {
            throw CertificateException("This isn't your paired PARKER")
        }
    }

    override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) =
        throw CertificateException("Not used")

    override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
}

fun pinnedHttpClient(fingerprintHex: String, readTimeoutSeconds: Long = 120): OkHttpClient {
    val trust = PinnedTrustManager(fingerprintHex)
    val tls = SSLContext.getInstance("TLS").apply { init(null, arrayOf(trust), null) }
    return OkHttpClient.Builder()
        .sslSocketFactory(tls.socketFactory, trust)
        // The laptop is reached by IP address; its identity is proven by the
        // pinned certificate above, not by a hostname.
        .hostnameVerifier { _, _ -> true }
        .connectTimeout(4, TimeUnit.SECONDS)
        .readTimeout(readTimeoutSeconds, TimeUnit.SECONDS)
        .build()
}

data class ChatMessage(val kind: String, val text: String, val fromMe: Boolean = false)
data class Confirmation(val id: String, val question: String)
data class Reply(val messages: List<ChatMessage>, val heard: String = "", val confirm: Confirmation? = null)
data class TodayItem(val text: String, val whenText: String, val source: String = "")
data class Today(
    val greeting: String,
    val plans: List<String>,
    val events: List<TodayItem>,
    val reminders: List<TodayItem>,
    val memories: List<String>,
)

class ParkerException(message: String) : IOException(message)

/** Talks to the PARKER running on the paired laptop. Call from a background thread. */
class ParkerClient(private val pairing: Pairing, private val http: OkHttpClient = pinnedHttpClient(pairing.fingerprint)) {
    @Volatile var baseUrl: String? = null
        private set

    /** Finds which of the laptop's addresses answers (Wi-Fi first, then Tailscale). */
    fun connect(): String {
        val errors = mutableListOf<String>()
        for (host in pairing.hosts) {
            val url = "https://$host:${pairing.port}"
            try {
                call(Request.Builder().url("$url/api/status"), url)
                baseUrl = url
                return url
            } catch (e: IOException) {
                errors += "$host: ${e.message}"
            }
        }
        throw ParkerException(
            "Can't reach PARKER on the laptop. Is it running with Phone companion on, " +
                "and is the phone on the same Wi-Fi? (${errors.joinToString("; ")})"
        )
    }

    fun today(): Today {
        val j = JSONObject(get("/api/today"))
        fun items(name: String) = j.getJSONArray(name).let { a ->
            (0 until a.length()).map { a.getJSONObject(it) }
                .map { TodayItem(it.getString("text"), it.getString("when"), it.optString("source")) }
        }
        fun strings(name: String) = j.getJSONArray(name).let { a -> (0 until a.length()).map { a.getString(it) } }
        return Today(j.getString("greeting"), strings("plans"), items("events"), items("reminders"), strings("memories"))
    }

    fun message(text: String): Reply = parseReply(post("/api/message", JSONObject().put("text", text).toString()))

    fun confirm(id: String, yes: Boolean): Reply =
        parseReply(post("/api/confirm", JSONObject().put("id", id).put("yes", yes).toString()))

    fun voice(wav: ByteArray): Reply = parseReply(post("/api/voice", wav, "audio/wav"))

    fun speak(text: String): ByteArray = postBytes("/api/speak", JSONObject().put("text", text).toString())

    // ---- plumbing ------------------------------------------------------------
    private fun url(path: String) = (baseUrl ?: connect()) + path

    private fun get(path: String): String = call(Request.Builder().url(url(path))).decodeToString()

    private fun post(path: String, body: String) = post(path, body.toByteArray(), "application/json")

    private fun post(path: String, body: ByteArray, type: String): String =
        call(Request.Builder().url(url(path)).post(body.toRequestBody(type.toMediaType()))).decodeToString()

    private fun postBytes(path: String, body: String): ByteArray =
        call(Request.Builder().url(url(path)).post(body.toRequestBody("application/json".toMediaType())))

    private fun call(builder: Request.Builder, base: String? = null): ByteArray {
        val request = builder.header("Authorization", "Bearer ${pairing.token}").build()
        http.newCall(request).execute().use { response ->
            if (response.code == 401) throw ParkerException("This phone isn't paired with PARKER any more. Pair again.")
            if (!response.isSuccessful) {
                val detail = runCatching { JSONObject(response.body!!.string()).optString("detail") }.getOrNull()
                throw ParkerException(detail?.takeIf { it.isNotBlank() } ?: "PARKER replied with error ${response.code}")
            }
            return response.body!!.bytes()
        }
    }

    companion object {
        fun parseReply(body: String): Reply {
            val j = JSONObject(body)
            val list = j.optJSONArray("messages")
            val messages = if (list == null) emptyList() else (0 until list.length()).map {
                val m = list.getJSONObject(it)
                ChatMessage(m.getString("kind"), m.getString("text"))
            }
            val confirm = j.optJSONObject("confirm")?.let { Confirmation(it.getString("id"), it.getString("question")) }
            return Reply(messages, j.optString("heard", ""), confirm)
        }
    }
}
