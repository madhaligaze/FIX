package com.example.aibrain.diagnostics

import android.content.Context
import android.os.Build
import android.util.Log
import com.example.aibrain.ApiService
import com.example.aibrain.ClientErrorItem
import com.example.aibrain.ClientReportEnvelope
import com.example.aibrain.LogDeviceInfo
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.ArrayDeque

class CrashReporter(private val context: Context) {

    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    private val errors = ArrayDeque<ClientErrorItem>(MAX_ERRORS)

    @Volatile
    private var lastExportRevId: String? = null

    fun setLastExportRev(revId: String?) {
        lastExportRevId = revId
    }

    fun recordError(tag: String, message: String, stack: String? = null) {
        val item = ClientErrorItem(
            timestamp_ms = System.currentTimeMillis(),
            tag = tag.take(64),
            message = message.take(512),
            stack = stack?.take(8000)
        )
        while (errors.size >= MAX_ERRORS) errors.removeFirst()
        errors.addLast(item)
        persistTail()
    }

    fun recordException(tag: String, t: Throwable) {
        recordError(tag, t.message ?: t.javaClass.simpleName, Log.getStackTraceString(t))
    }

    private fun persistTail() {
        try {
            val gson = com.google.gson.Gson()
            prefs.edit().putString(KEY_ERRORS_JSON, gson.toJson(errors.toList())).apply()
        } catch (_: Exception) {
        }
    }

    private fun loadTailIfNeeded() {
        if (errors.isNotEmpty()) return
        val raw = prefs.getString(KEY_ERRORS_JSON, null) ?: return
        try {
            val gson = com.google.gson.Gson()
            val t = com.google.gson.reflect.TypeToken.getParameterized(List::class.java, ClientErrorItem::class.java).type
            val list: List<ClientErrorItem> = gson.fromJson(raw, t) ?: emptyList()
            for (e in list.takeLast(MAX_ERRORS)) errors.addLast(e)
        } catch (_: Exception) {
        }
    }

    fun getLastSentMs(): Long = prefs.getLong(KEY_LAST_SENT_MS, 0L)

    suspend fun sendNow(
        api: ApiService,
        sessionId: String?,
        clientStats: Map<String, Any>,
        queuedActions: Map<String, Any>
    ): Boolean = withContext(Dispatchers.IO) {
        loadTailIfNeeded()

        val payload = ClientReportEnvelope(
            session_id = sessionId,
            timestamp_ms = System.currentTimeMillis(),
            client_stats = clientStats,
            last_export_rev = lastExportRevId,
            queued_actions = queuedActions,
            last_errors = errors.toList(),
            device = LogDeviceInfo(
                model = Build.MODEL ?: "unknown",
                manufacturer = Build.MANUFACTURER ?: "unknown",
                sdk = Build.VERSION.SDK_INT
            )
        )

        return@withContext try {
            val resp = api.postClientReport(payload)
            if (resp.isSuccessful) {
                prefs.edit().putLong(KEY_LAST_SENT_MS, System.currentTimeMillis()).apply()
                true
            } else {
                false
            }
        } catch (e: Exception) {
            false
        }
    }

    companion object {
        private const val PREFS = "crash_reporter"
        private const val KEY_ERRORS_JSON = "errors_json"
        private const val KEY_LAST_SENT_MS = "last_sent_ms"
        private const val MAX_ERRORS = 12
    }
}
