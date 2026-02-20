package com.example.aibrain.offline

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import com.example.aibrain.AnchorPayload
import com.example.aibrain.ApiService
import com.example.aibrain.LockPayload
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Small offline queue for critical user actions:
 * - anchors push
 * - lock/export request
 *
 * Design:
 * - per session: keep only latest anchors payload (dedupe by key)
 * - per session: keep only latest lock request
 */
class OfflineQueue(
    context: Context,
    prefsName: String = "offline_queue"
) {
    private val prefs: SharedPreferences = context.getSharedPreferences(prefsName, Context.MODE_PRIVATE)
    private val gson = Gson()

    data class QueueItem(
        val key: String,
        val type: String,
        val session_id: String,
        val created_at_ms: Long,
        val payload_json: String
    )

    private fun loadAll(): MutableMap<String, QueueItem> {
        val raw = prefs.getString("queue_map", null) ?: return mutableMapOf()
        return try {
            val t = object : TypeToken<MutableMap<String, QueueItem>>() {}.type
            gson.fromJson(raw, t) ?: mutableMapOf()
        } catch (_: Exception) {
            mutableMapOf()
        }
    }

    private fun saveAll(map: MutableMap<String, QueueItem>) {
        prefs.edit().putString("queue_map", gson.toJson(map)).apply()
    }

    fun enqueueAnchors(sessionId: String, payload: AnchorPayload) {
        val map = loadAll()
        val key = "ANCHORS:$sessionId"
        val item = QueueItem(
            key = key,
            type = "ANCHORS",
            session_id = sessionId,
            created_at_ms = System.currentTimeMillis(),
            payload_json = gson.toJson(payload)
        )
        map[key] = item
        saveAll(map)
    }

    fun enqueueLock(sessionId: String, payload: LockPayload) {
        val map = loadAll()
        val key = "LOCK:$sessionId"
        val item = QueueItem(
            key = key,
            type = "LOCK",
            session_id = sessionId,
            created_at_ms = System.currentTimeMillis(),
            payload_json = gson.toJson(payload)
        )
        map[key] = item
        saveAll(map)
    }

    suspend fun flushForSession(api: ApiService, sessionId: String): FlushResult = withContext(Dispatchers.IO) {
        val map = loadAll()
        var anchorsOk = true
        var lockOk = true

        val anchorsKey = "ANCHORS:$sessionId"
        val lockKey = "LOCK:$sessionId"

        map[anchorsKey]?.let { item ->
            try {
                val payload = gson.fromJson(item.payload_json, AnchorPayload::class.java)
                val r = api.postAnchors(payload)
                if (r.isSuccessful) {
                    map.remove(anchorsKey)
                } else {
                    anchorsOk = false
                }
            } catch (e: Exception) {
                anchorsOk = false
                Log.w("OfflineQueue", "flush anchors failed: ${e.message}")
            }
        }

        map[lockKey]?.let { item ->
            try {
                val payload = gson.fromJson(item.payload_json, LockPayload::class.java)
                val r = api.lockSession(payload)
                if (r.isSuccessful) {
                    map.remove(lockKey)
                } else {
                    lockOk = false
                }
            } catch (e: Exception) {
                lockOk = false
                Log.w("OfflineQueue", "flush lock failed: ${e.message}")
            }
        }

        saveAll(map)
        FlushResult(anchorsOk = anchorsOk, lockOk = lockOk)
    }

    data class FlushResult(
        val anchorsOk: Boolean,
        val lockOk: Boolean
    )
}
