package com.example.aibrain.scene

import android.content.Context
import android.net.Uri
import android.util.Log
import com.google.ar.sceneform.AnchorNode
import com.google.ar.sceneform.ArSceneView
import com.google.ar.sceneform.Node
import com.google.ar.sceneform.NodeParent
import com.google.ar.sceneform.rendering.ModelRenderable
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit
import java.util.zip.CRC32
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

class LayerGlbManager(
    private val context: Context,
    private val sceneView: ArSceneView,
    private val baseUrl: String,
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()
    private val nodesByLayerId = mutableMapOf<String, Node>()
    private var layersRoot: AnchorNode? = null

    fun setLayersRoot(anchor: AnchorNode?) {
        layersRoot = anchor
        val parent: NodeParent = anchor ?: sceneView.scene
        val parent = anchor ?: sceneView.scene
        nodesByLayerId.values.forEach { it.setParent(parent) }
    }

    suspend fun loadLayer(layerId: String, relativePath: String): Node {
        val cached = withContext(Dispatchers.IO) { downloadToCache(layerId, relativePath) }
        val renderable = withContext(Dispatchers.Main) {
            ModelRenderable.builder()
                .setSource(context, Uri.fromFile(cached.file))
                .setRegistryId("${cached.file.absolutePath}:${cached.contentTag}")
                .build()
                .await()
        }

        return withContext(Dispatchers.Main) {
            nodesByLayerId[layerId]?.setParent(null)
            val nodeParent: NodeParent = layersRoot ?: sceneView.scene
            val node = Node().apply {
                this.renderable = renderable
                this.isEnabled = true
                setParent(nodeParent)
                setParent(layersRoot ?: sceneView.scene)
            }
            nodesByLayerId[layerId] = node
            node
        }
    }

    fun setVisible(layerId: String, visible: Boolean) {
        nodesByLayerId[layerId]?.isEnabled = visible
    }

    fun clearAll() {
        nodesByLayerId.values.forEach { it.setParent(null) }
        nodesByLayerId.clear()
    }

    private data class CachedLayerFile(val file: File, val contentTag: String)

    private fun downloadToCache(layerId: String, relativePath: String): CachedLayerFile {
        val cleanPath = relativePath.removePrefix("/")
        val full = baseUrl.trimEnd('/') + "/" + cleanPath
        Log.i("LayerGlbManager", "Downloading layer $layerId from $full")
        val req = Request.Builder().url(full).build()
        client.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) {
                throw IllegalStateException("Failed to download layer=$layerId url=$full: HTTP ${resp.code}")
            }
            val bytes = resp.body?.bytes() ?: throw IllegalStateException("Empty response body for layer=$layerId url=$full")
            val crc = CRC32().apply { update(bytes) }.value.toString(16)
            val out = File(context.cacheDir, "layer_${layerId}_$crc.glb")
            out.writeBytes(bytes)
            return CachedLayerFile(file = out, contentTag = crc)
        }
    }
}

private suspend fun <T> CompletableFuture<T>.await(): T = suspendCancellableCoroutine { cont ->
    whenComplete { value, error ->
        if (error != null) cont.resumeWithException(error)
        else cont.resume(value)
    }
    cont.invokeOnCancellation { cancel(true) }
}
