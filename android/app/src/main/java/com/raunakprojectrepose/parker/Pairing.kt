package com.raunakprojectrepose.parker

import android.content.Context
import org.json.JSONObject

/** What the laptop's "Pair phone" QR code contains. */
data class Pairing(
    val hosts: List<String>,
    val port: Int,
    val token: String,
    val fingerprint: String,
    val name: String,
) {
    fun toJson(): String = JSONObject()
        .put("app", "parker").put("v", 1).put("hosts", org.json.JSONArray(hosts))
        .put("port", port).put("token", token).put("fp", fingerprint).put("name", name)
        .toString()

    companion object {
        /** Parses a scanned QR code; returns null if it isn't a PARKER pairing code. */
        fun parse(text: String): Pairing? = try {
            val json = JSONObject(text)
            val hostsJson = json.getJSONArray("hosts")
            val hosts = (0 until hostsJson.length()).map { hostsJson.getString(it) }
            val fp = json.getString("fp").lowercase()
            val token = json.getString("token")
            if (json.optString("app") != "parker" || hosts.isEmpty() || token.length < 20 ||
                !Regex("^[0-9a-f]{64}$").matches(fp)
            ) null
            else Pairing(hosts, json.optInt("port", 8765), token, fp, json.optString("name", ""))
        } catch (e: Exception) {
            null
        }

        private const val PREFS = "parker"
        private const val KEY = "pairing"

        /** Kept in the app's private storage, which other apps can't read. */
        fun load(context: Context): Pairing? =
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY, null)?.let(::parse)

        fun save(context: Context, pairing: Pairing?) {
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().apply {
                if (pairing == null) remove(KEY) else putString(KEY, pairing.toJson())
            }.apply()
        }
    }
}
