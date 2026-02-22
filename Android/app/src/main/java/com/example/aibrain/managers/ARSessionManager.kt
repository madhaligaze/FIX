package com.example.aibrain.managers

import android.content.Context
import android.os.Build
import android.util.Log
import com.google.ar.core.Anchor
import com.google.ar.core.CameraConfigFilter
import com.google.ar.core.Config
import com.google.ar.core.LightEstimate
import com.google.ar.core.Session
import com.google.ar.sceneform.AnchorNode
import com.google.ar.sceneform.ArSceneView

class ARSessionManager(
    private val context: Context,
    private val sceneView: ArSceneView,
) {
    private var currentAnchorNode: AnchorNode? = null
    var depthMode: Config.DepthMode = Config.DepthMode.DISABLED
        private set

    fun setupSession(): Boolean {
        // Жесткая защита от падений на API 27 (Android 8.1) и ниже.
        // На этих версиях в некоторых связках ARCore/Camera2 возможны NoSuchFieldError и нативные краши.
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) {
            Log.e(TAG, "AR disabled: SDK_INT=${Build.VERSION.SDK_INT} < 28")
            return false
        }

        val existingSession = sceneView.session
        if (existingSession != null) {
            applyConfig(existingSession)
            sceneView.planeRenderer.isVisible = true
            Log.d(TAG, "Re-configured existing session. depthMode=$depthMode")
            return true
        }

        val session = try {
            Session(context)
        } catch (t: Throwable) {
            // Важно: ловим Throwable, т.к. NoSuchFieldError/UnsatisfiedLinkError и т.п. не являются Exception.
            Log.e(TAG, "Failed to create ARCore Session: ${t.message}", t)
            return false
        }

        try {
            val filter = CameraConfigFilter(session)
            val configs = session.getSupportedCameraConfigs(filter)
            val best = configs.firstOrNull { it.fpsRange.upper >= 30 } ?: configs.firstOrNull()
            if (best != null) {
                session.cameraConfig = best
                Log.d(TAG, "CameraConfig: ${best.imageSize} @ ${best.fpsRange} FPS")
            }
        } catch (t: Throwable) {
            Log.w(TAG, "CameraConfig selection failed (non-fatal): ${t.message}")
        }

        applyConfig(session)

        return try {
            sceneView.session = session
            sceneView.planeRenderer.isVisible = true
            Log.i(TAG, "ARCore Session created. depthMode=$depthMode")
            true
        } catch (t: Throwable) {
            Log.e(TAG, "sceneView.session assignment failed: ${t.message}", t)
            session.close()
            false
        }
    }

    private fun applyConfig(session: Session) {
        depthMode = when {
            session.isDepthModeSupported(Config.DepthMode.RAW_DEPTH_ONLY) -> Config.DepthMode.RAW_DEPTH_ONLY
            session.isDepthModeSupported(Config.DepthMode.AUTOMATIC) -> Config.DepthMode.AUTOMATIC
            else -> Config.DepthMode.DISABLED
        }

        val config = Config(session).apply {
            focusMode = Config.FocusMode.AUTO
            // Sceneform 1.23.0 ожидает LightEstimate.acquireEnvironmentalHdrCubeMap(): ArImage[].
            // На некоторых версиях ARCore/Play Services for AR сигнатура другая (Image[]) и будет NoSuchMethodError.
            // Поэтому включаем ENVIRONMENTAL_HDR только если метод есть и возвращает именно ArImage[].
            lightEstimationMode = if (supportsSceneformEnvironmentalHdr()) {
                Config.LightEstimationMode.ENVIRONMENTAL_HDR
            } else {
                Config.LightEstimationMode.AMBIENT_INTENSITY
            }
            planeFindingMode = Config.PlaneFindingMode.HORIZONTAL_AND_VERTICAL
            updateMode = Config.UpdateMode.LATEST_CAMERA_IMAGE
            this.depthMode = this@ARSessionManager.depthMode
        }

        Log.i(TAG, "LightEstimationMode=${config.lightEstimationMode} (depthMode=$depthMode)")

        try {
            session.configure(config)
        } catch (t: Throwable) {
            Log.e(TAG, "session.configure() failed: ${t.message}", t)
        }
    }

    private fun supportsSceneformEnvironmentalHdr(): Boolean {
        return try {
            val m = LightEstimate::class.java.methods.firstOrNull {
                it.name == "acquireEnvironmentalHdrCubeMap" && it.parameterTypes.isEmpty()
            } ?: return false

            // Важно: проверяем именно тип возврата ArImage[] (а не Image[]), иначе Sceneform упадёт.
            m.returnType.isArray && m.returnType.componentType?.name == "com.google.ar.core.ArImage"
        } catch (_: Throwable) {
            false
        }
    }

    fun addAnchor(anchor: Anchor): AnchorNode {
        currentAnchorNode?.setParent(null)
        val anchorNode = AnchorNode(anchor).also { it.setParent(sceneView.scene) }
        currentAnchorNode = anchorNode
        return anchorNode
    }

    fun clearScene() {
        currentAnchorNode?.setParent(null)
        currentAnchorNode = null
    }

    private companion object {
        const val TAG = "ARSessionManager"
    }
}
