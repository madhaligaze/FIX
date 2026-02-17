package com.example.aibrain.scene

import com.example.aibrain.ElementPoint
import com.example.aibrain.HeatmapItem
import com.example.aibrain.ScaffoldElement
import com.example.aibrain.materials.MaterialManager
import com.example.aibrain.models.LayherModels
import com.google.ar.sceneform.Node
import com.google.ar.sceneform.Scene
import com.google.ar.sceneform.math.Quaternion
import com.google.ar.sceneform.math.Vector3
import com.google.ar.sceneform.rendering.ModelRenderable
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlin.math.sqrt

class SceneBuilder(private val scene: Scene) {

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private val materialManager = MaterialManager(scene.view.context)
    private var isInitialized = false

    private val renderableCache = mutableMapOf<String, ModelRenderable>()
    private val sceneNodes = mutableListOf<Node>()
    private val elementNodes = mutableMapOf<String, ElementNode>()
    private val allElements = mutableListOf<ScaffoldElement>()

    fun preloadModels(onReady: (() -> Unit)? = null) {
        if (isInitialized) {
            onReady?.invoke()
            return
        }

        scope.launch {
            materialManager.init()
            isInitialized = true
            onReady?.invoke()
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
        allElements.clear()
    }

    fun getAllElements(): List<ScaffoldElement> = allElements.toList()

    fun updateColors(heatmap: List<Map<String, Any>>) {
        val colorById = heatmap.associate {
            val id = it["id"] as? String ?: ""
            val loadRatio = when (val color = it["color"] as? String ?: "gray") {
                "red" -> 1.0
                "orange", "yellow" -> 0.7
                else -> 0.2
            }
            id to loadRatio
        }
        colorById.forEach { (id, loadRatio) -> updateElementColor(id, loadRatio) }
    }

    fun findNodeById(elementId: String): Node? = elementNodes[elementId]?.node

    fun removeElement(elementId: String) {
        elementNodes[elementId]?.let { elementNode ->
            elementNode.node.setParent(null)
            sceneNodes.remove(elementNode.node)
            elementNodes.remove(elementId)
            allElements.removeAll { it.id == elementId }
        }
    }

    fun updateHeatmap(heatmap: List<HeatmapItem>) {
        heatmap.forEach { updateElementColor(it.id, it.load_ratio) }
    }

    private fun createElement(element: ScaffoldElement) {
        if (!isInitialized) {
            return
        }

        val renderable = getOrCreateRenderable(element).makeCopy()
        val elementLength = calculateLength(element.start, element.end)
        val loadRatio = element.load_ratio ?: 0.0

        val node = Node().apply {
            this.renderable = renderable

            val midPoint = Vector3(
                (element.start.x + element.end.x) / 2f,
                (element.start.y + element.end.y) / 2f,
                (element.start.z + element.end.z) / 2f
            )
            worldPosition = midPoint
            worldRotation = calculateRotation(element.start, element.end)
        }

        if (isVerticalElement(element.type)) {
            attachWedgeNodes(node, elementLength, loadRatio)
        }

        node.setParent(scene)
        sceneNodes.add(node)
        elementNodes[element.id] = ElementNode(node = node, element = element, renderable = renderable)
    }

    private fun getOrCreateRenderable(element: ScaffoldElement): ModelRenderable {
        val loadRatio = element.load_ratio ?: 0.0
        val length = calculateLength(element.start, element.end)
        val roundedLen = (length * 20).toInt()
        val cacheKey = "${element.type}_${(loadRatio * 10).toInt()}_$roundedLen"

        return renderableCache.getOrPut(cacheKey) {
            val material = materialManager.getMaterial(element.type, loadRatio)
            when (element.type) {
                "standard", "vertical" -> LayherModels.createStandard(scene.view.context, length, material)
                "ledger", "horizontal" -> LayherModels.createLedger(scene.view.context, length, material)
                "bracing", "diagonal" -> LayherModels.createBracing(scene.view.context, length, material)
                "deck", "platform" -> LayherModels.createDeck(scene.view.context, material)
                else -> LayherModels.createLedger(scene.view.context, length, material)
            }
        }
    }


    private fun attachWedgeNodes(parentNode: Node, height: Float, loadRatio: Double) {
        val wedgeRenderable = getWedgeRenderable(loadRatio)
        LayherModels.getWedgeOffsets(height).forEach { yOffset ->
            Node().apply {
                renderable = wedgeRenderable.makeCopy()
                localPosition = Vector3(0f, yOffset, 0f)
                setParent(parentNode)
            }
        }
    }

    private fun getWedgeRenderable(loadRatio: Double): ModelRenderable {
        val cacheKey = "wedge_${(loadRatio * 10).toInt()}"
        return renderableCache.getOrPut(cacheKey) {
            val wedgeMaterial = materialManager.getMaterial("vertical", loadRatio)
            LayherModels.createWedgeNode(scene.view.context, wedgeMaterial)
        }
    }

    private fun isVerticalElement(type: String): Boolean {
        return type == "standard" || type == "vertical"
    }

    fun updateElementColor(elementId: String, loadRatio: Double) {
        elementNodes[elementId]?.let { elementNode ->
            val material = materialManager.getMaterial(elementNode.element.type, loadRatio)
            elementNode.renderable.material = material
            if (isVerticalElement(elementNode.element.type)) {
                elementNode.node.children.forEach { child ->
                    child.renderable?.material = material
                }
            }
        }
    }

    private fun calculateLength(start: ElementPoint, end: ElementPoint): Float {
        val dx = end.x - start.x
        val dy = end.y - start.y
        val dz = end.z - start.z
        return sqrt(dx * dx + dy * dy + dz * dz).coerceAtLeast(0.05f)
    }

    private fun calculateRotation(start: ElementPoint, end: ElementPoint): Quaternion {
        val direction = Vector3(
            end.x - start.x,
            end.y - start.y,
            end.z - start.z
        ).normalized()

        if (direction.y > 0.98f) return Quaternion.identity()
        if (direction.y < -0.98f) return Quaternion.axisAngle(Vector3.right(), 180f)

        val up = Vector3.up()
        val angle = Math.acos(Vector3.dot(up, direction).toDouble()).toFloat()
        val axis = Vector3.cross(up, direction).normalized()
        return Quaternion.axisAngle(axis, Math.toDegrees(angle.toDouble()).toFloat())
    }

    private data class ElementNode(
        val node: Node,
        val element: ScaffoldElement,
        val renderable: ModelRenderable
    )
}
