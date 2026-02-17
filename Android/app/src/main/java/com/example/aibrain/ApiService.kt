package com.example.aibrain

import retrofit2.Response
import retrofit2.http.*
import com.google.gson.annotations.SerializedName

/**
 * API-интерфейс для связи с Python-сервером.
 *
 * ИСПРАВЛЕНО: модели ответов теперь совпадают с реальными ответами сервера.
 *
 * Сервер /session/stream возвращает:
 *   {"status": "RECEIVING", "ai_hints": {"instructions": [...], "warnings": [...], "quality_score": 85}}
 *
 * Раньше в Android было:
 *   data class HintResponse(val hints: Map<String, List<String>>)  ← НЕВЕРНО
 */

interface ApiService {

    @POST("/session/start")
    suspend fun startSession(): Response<SessionResponse>

    @POST("/session/stream/{session_id}")
    suspend fun streamData(
        @Path("session_id") sessionId: String,
        @Body body: Map<String, @JvmSuppressWildcards Any>
    ): Response<StreamResponse>

    @POST("/session/model/{session_id}")
    suspend fun startModeling(
        @Path("session_id") sessionId: String
    ): Response<ModelingResponse>

    @GET("/health")
    suspend fun healthCheck(): Response<HealthResponse>
}

// ── Ответ /session/start ──────────────────────────────────────────────────────
data class SessionResponse(
    val session_id: String,
    val status: String
)

// ── Ответ /session/stream ─────────────────────────────────────────────────────
data class StreamResponse(
    val status: String,
    val ai_hints: AiHints?
)

data class AiHints(
    val instructions: List<String>?,   // ["📏 Отойдите на 2 метра", ...]
    val warnings: List<String>?,        // ["⚠️ Мало AR-точек", ...]
    val quality_score: Double?,         // 0.0–100.0
    val is_ready: Boolean?              // true = можно моделировать
)

// ── Ответ /session/model ──────────────────────────────────────────────────────
data class ModelingResponse(
    val status: String,
    val options: List<ScaffoldOption>?
)

data class ScaffoldOption(
    @SerializedName(value = "variant_name", alternate = ["name"])
    val variant_name: String = "Option",
    val material_info: String = "",
    val safety_score: Int = 0,           // 0–100, выше = безопаснее
    val ai_critique: List<String>?,  // самокритика ИИ
    val elements: List<ScaffoldElement>? = null,
    val full_structure: List<ScaffoldElement>? = null,
    val stats: ScaffoldStats?,
    val physics: PhysicsResult?
)

data class ScaffoldElement(
    val id: String,
    val type: String,
    val start: ElementPoint,
    val end: ElementPoint,
    val stress_color: String? = null,
    val load_ratio: Double? = null
)

data class ElementPoint(
    val x: Float,
    val y: Float,
    val z: Float
)

data class ScaffoldStats(
    val total_nodes: Int,
    val total_beams: Int,
    val total_weight_kg: Int,
    val collisions_fixed: Int?
)

data class PhysicsResult(
    val status: String    // "OK" | "COLLAPSE" | "ERROR"
)

// ── Ответ /health ─────────────────────────────────────────────────────────────
data class HealthResponse(
    val status: String,
    val version: String,
    val modules: Map<String, Boolean>?
)
