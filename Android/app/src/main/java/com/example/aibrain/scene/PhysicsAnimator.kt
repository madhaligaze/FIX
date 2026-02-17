package com.example.aibrain.scene

import com.google.ar.sceneform.Node
import com.google.ar.sceneform.math.Vector3
import io.github.sceneview.ar.ArSceneView

/**
 * Простая визуальная анимация «падения» без полноценного physics engine.
 */
class PhysicsAnimator(private val sceneView: ArSceneView, private val sceneBuilder: SceneBuilder) {

    private val activeAnimations = mutableMapOf<String, FallingState>()

    fun animateFall(collapsedIds: List<String>) {
        collapsedIds.forEach { id ->
            val node = sceneBuilder.findNodeById(id) ?: return@forEach
            activeAnimations[id] = FallingState(node = node)
        }

        if (activeAnimations.isNotEmpty()) {
            sceneView.scene.addOnUpdateListener(::onUpdate)
        }
    }

    fun stopAll() {
        activeAnimations.clear()
        sceneView.scene.removeOnUpdateListener(::onUpdate)
    }

    private fun onUpdate(frameTime: com.google.ar.sceneform.FrameTime) {
        val delta = frameTime.deltaSeconds.coerceAtLeast(0.016f)
        val iterator = activeAnimations.iterator()

        while (iterator.hasNext()) {
            val state = iterator.next().value
            state.velocityY -= 9.81f * delta
            val p = state.node.worldPosition
            val nextY = p.y + state.velocityY * delta

            if (nextY <= groundY) {
                state.bouncesLeft--
                if (state.bouncesLeft <= 0) {
                    state.node.worldPosition = Vector3(p.x, groundY, p.z)
                    iterator.remove()
                    continue
                }
                state.velocityY = -state.velocityY * 0.35f
                state.node.worldPosition = Vector3(p.x, groundY, p.z)
            } else {
                state.node.worldPosition = Vector3(p.x, nextY, p.z)
            }
        }

        if (activeAnimations.isEmpty()) {
            sceneView.scene.removeOnUpdateListener(::onUpdate)
        }
    }

    private data class FallingState(
        val node: Node,
        var velocityY: Float = 0f,
        var bouncesLeft: Int = 2
    )

    private companion object {
        const val groundY = 0f
    }
}
