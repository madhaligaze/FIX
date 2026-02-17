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

    @POST("/session/update/{session_id}")
    suspend fun updateStructure(
        @Path("session_id") sessionId: String,
        @Body action: UpdateAction
    ): Response<UpdateResponse>

    @POST("/session/preview_remove/{session_id}")
    suspend fun previewRemove(
        @Path("session_id") sessionId: String,
        @Query("element_id") elementId: String
    ): Response<PreviewResponse>

    @GET("/health")
    suspend fun healthCheck(): Response<HealthResponse>

    @GET("/session/voxels/{session_id}")
    suspend fun getVoxels(
        @Path("session_id") sessionId: String
    ): Response<VoxelResponse>
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

// ── Запрос/ответ для /session/update ───────────────────────────────────────
data class UpdateAction(
    val action: String,
    val element_id: String? = null,
    val element_data: ScaffoldElement? = null
)

data class UpdateResponse(
    val status: String,
    val is_stable: Boolean,
    val physics_status: String,
    val heatmap: List<HeatmapItem>,
    val affected_elements: List<String>,
    val collapsed: CollapsedData,
    val processing_time_ms: Int
)

data class HeatmapItem(
    val id: String,
    val color: String,
    val load_ratio: Double
)

data class CollapsedData(
    val nodes: List<String>,
    val elements: List<String>
)

// ── Ответ для /session/preview_remove ──────────────────────────────────────
data class PreviewResponse(
    val status: String,
    val element_id: String,
    val is_critical: Boolean,
    val would_collapse: List<String>,
    val collapse_count: Int,
    val warning: String
)


data class VoxelResponse(
    val status: String,
    val voxels: List<VoxelItem>,
    val bounds: Bounds,
    val resolution: Double,
    val total_count: Int
)

data class VoxelItem(
    val position: List<Float>,
    val type: String,
    val color: String,
    val alpha: Double,
    val radius: Float? = null
)

data class Bounds(
    val min: List<Float>,
    val max: List<Float>
)
