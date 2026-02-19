package com.example.aibrain.managers

import android.content.Context
import com.google.ar.core.Anchor
import com.google.ar.core.Config
import com.google.ar.sceneform.AnchorNode
import com.google.ar.sceneform.ArSceneView

class ARSessionManager(
    private val context: Context,
    private val sceneView: ArSceneView
 ) {
    private var currentAnchorNode: AnchorNode? = null
    private var sessionConfigured: Boolean = false

    fun setupSession() {
        sceneView.planeRenderer.isVisible = true

        sceneView.scene.addOnUpdateListener {
            val session = sceneView.session ?: return@addOnUpdateListener
            if (sessionConfigured) return@addOnUpdateListener

            val rawDepthMode = enumValues<Config.DepthMode>().firstOrNull { it.name == "RAW_DEPTH_ONLY" }
            val selectedDepthMode = when {
                rawDepthMode != null && session.isDepthModeSupported(rawDepthMode) -> rawDepthMode
                session.isDepthModeSupported(Config.DepthMode.AUTOMATIC) -> Config.DepthMode.AUTOMATIC
                else -> Config.DepthMode.DISABLED
            }

            val config = Config(session).apply {
                focusMode = Config.FocusMode.AUTO
                lightEstimationMode = Config.LightEstimationMode.ENVIRONMENTAL_HDR
                planeFindingMode = Config.PlaneFindingMode.HORIZONTAL_AND_VERTICAL
                depthMode = selectedDepthMode
            }

            session.configure(config)
            sessionConfigured = true
        }
    }

    fun addAnchor(anchor: Anchor): AnchorNode {
        currentAnchorNode?.let { it.setParent(null) }
        val anchorNode = AnchorNode(anchor)
        anchorNode.setParent(sceneView.scene)
        currentAnchorNode = anchorNode
        return anchorNode
    }

    fun renderModel(modelUrl: String, scale: Float = 1.0f) {
        // Model rendering is handled directly in MainActivity/SceneBuilder.
    }

    fun clearScene() {
        currentAnchorNode?.let { it.setParent(null) }
        currentAnchorNode = null
    }
}
