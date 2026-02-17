package com.example.aibrain.scene

import com.example.aibrain.HeatmapItem
import com.example.aibrain.ScaffoldElement
import com.google.ar.sceneform.Node
import com.google.ar.sceneform.Scene
import com.google.ar.sceneform.math.Quaternion
import com.google.ar.sceneform.math.Vector3
import com.google.ar.sceneform.rendering.Color
import com.google.ar.sceneform.rendering.Material
import com.google.ar.sceneform.rendering.MaterialFactory
import com.google.ar.sceneform.rendering.ModelRenderable
import com.google.ar.sceneform.rendering.ShapeFactory

class SceneBuilder(private val scene: Scene) {

    private val modelCache = mutableMapOf<String, ModelRenderable>()
    private val sceneNodes = mutableListOf<Node>()
    private val elementNodes = mutableMapOf<String, Node>()
    private val allElements = mutableListOf<ScaffoldElement>()

    private val stressColors = mapOf(
        "green" to Color(0f, 0.8f, 0f),
        "yellow" to Color(1f, 1f, 0f),
        "orange" to Color(1f, 0.65f, 0f),
        "red" to Color(1f, 0f, 0f),
        "gray" to Color(0.6f, 0.6f, 0.6f)
    )

    fun preloadModels(onReady: (() -> Unit)? = null) {
        if (modelCache.isNotEmpty()) {
            onReady?.invoke()
            return
        }

        var remaining = 4
        fun done() {
            remaining--
            if (remaining <= 0) onReady?.invoke()
        }

        createPrimitiveModel("vertical", Vector3(0.06f, 1.035f, 0.06f), Color(0.7f, 0.7f, 0.7f), ::done)
        createPrimitiveModel("ledger", Vector3(1.035f, 0.04f, 0.04f), Color(0.75f, 0.75f, 0.75f), ::done)
        createPrimitiveModel("diagonal", Vector3(1.2f, 0.035f, 0.035f), Color(0.7f, 0.75f, 0.7f), ::done)
        createPrimitiveModel("deck", Vector3(1.035f, 0.03f, 0.32f), Color(0.45f, 0.45f, 0.45f), ::done)
    }

    private fun createPrimitiveModel(type: String, size: Vector3, color: Color, onReady: () -> Unit) {
        MaterialFactory.makeOpaqueWithColor(scene.view.context, color)
            .thenAccept { material: Material ->
                val cube = ShapeFactory.makeCube(size, Vector3.zero(), material)
                modelCache[type] = cube
                onReady()
            }
            .exceptionally {
                onReady()
                null
            }
    }

    fun buildScene(elements: List<ScaffoldElement>) {
        clearScene()
        allElements.clear()
        allElements.addAll(elements)
        elements.forEach { createElement(it) }
    }

    fun clearScene() {
        sceneNodes.forEach { it.setParent(null) }
        sceneNodes.clear()
        elementNodes.clear()
    }

    fun getAllElements(): List<ScaffoldElement> = allElements.toList()

    fun updateColors(heatmap: List<Map<String, Any>>) {
        val colorById = heatmap.associate {
            val id = it["id"] as? String ?: ""
            val color = it["color"] as? String ?: "gray"
            id to color
        }
        colorById.forEach { (id, color) -> elementNodes[id]?.let { applyStressColor(it, color) } }
    }

    /**
     * Найти Node по ID элемента.
     */
    fun findNodeById(elementId: String): Node? = elementNodes[elementId]

    /**
     * Удалить элемент из сцены.
     */
    fun removeElement(elementId: String) {
        elementNodes[elementId]?.let { node ->
            node.parent = null
            elementNodes.remove(elementId)
            sceneNodes.remove(node)
        }
    }

    /**
     * Обновить цвета элементов на основе heatmap.
     */
    fun updateHeatmap(heatmap: List<HeatmapItem>) {
        heatmap.forEach { item ->
            elementNodes[item.id]?.let { node ->
                applyStressColor(node, item.color)
            }
        }
    }

    private fun createElement(element: ScaffoldElement) {
        val baseModel = modelCache[element.type] ?: modelCache["ledger"] ?: return

        val start = Vector3(element.start.x, element.start.y, element.start.z)
        val end = Vector3(element.end.x, element.end.y, element.end.z)

        val node = Node().apply { renderable = baseModel.makeCopy() }
        val center = Vector3((start.x + end.x) / 2f, (start.y + end.y) / 2f, (start.z + end.z) / 2f)
        node.worldPosition = center

        val direction = Vector3.subtract(end, start)
        val length = direction.length().coerceAtLeast(0.01f)
        node.worldRotation = Quaternion.lookRotation(direction.normalized(), Vector3.up())
        node.localScale = Vector3(1f, (length / 2.07f).coerceAtLeast(0.05f), 1f)

        applyStressColor(node, element.stress_color ?: "gray")

        node.setParent(scene)
        sceneNodes.add(node)
        elementNodes[element.id] = node
    }

    private fun applyStressColor(node: Node, colorName: String) {
        val color = stressColors[colorName] ?: stressColors["gray"] ?: return
        val renderable = node.renderable as? ModelRenderable ?: return
        val material = renderable.material.makeCopy()
        material.setFloat4("baseColorTint", color)
        renderable.material = material
    }
}
