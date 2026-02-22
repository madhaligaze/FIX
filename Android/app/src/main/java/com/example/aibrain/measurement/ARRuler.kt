package com.example.aibrain.measurement

import android.graphics.Color
import android.widget.TextView
import com.google.ar.core.Anchor
import com.google.ar.core.HitResult
import com.google.ar.core.Plane
import com.google.ar.core.Pose
import com.google.ar.sceneform.AnchorNode
import com.google.ar.sceneform.ArSceneView
import com.google.ar.sceneform.Node
import com.google.ar.sceneform.math.Quaternion
import com.google.ar.sceneform.math.Vector3
import com.google.ar.sceneform.rendering.Material
import com.google.ar.sceneform.rendering.MaterialFactory
import com.google.ar.sceneform.rendering.ShapeFactory
import com.google.ar.sceneform.rendering.ViewRenderable
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlin.math.abs
import kotlin.math.max

data class MeasurementPoint(
    val anchor: Anchor,
    val pose: Pose,
    val node: AnchorNode,
    val timestamp: Long = System.currentTimeMillis()
) {
    fun getPosition(): Vector3 = Vector3(pose.tx(), pose.ty(), pose.tz())
}

data class Measurement(
    val id: String,
    val type: MeasurementType,
    val points: List<MeasurementPoint>,
    val distance: Float,
    val label: String,
    val timestamp: Long = System.currentTimeMillis(),
    val area: Float? = null,
    val perimeter: Float? = null,
    val height: Float? = null
)

enum class MeasurementType {
    LINEAR,
    HEIGHT,
    AREA
}

class ARRuler(
    private val sceneView: ArSceneView,
    private val scope: CoroutineScope
) {

    enum class Units { METRIC, IMPERIAL }

    var units: Units = Units.METRIC

    private var currentType: MeasurementType = MeasurementType.LINEAR
    private val currentPoints = mutableListOf<MeasurementPoint>()
    private val segmentNodes = mutableListOf<Node>()
    private var labelNode: Node? = null
    private var labelRenderable: ViewRenderable? = null
    private var labelTextView: TextView? = null
    private var updateListenerInstalled = false

    private var snapToSurface: Boolean = true
    private var showGrid: Boolean = true

    private val measurements = mutableListOf<Measurement>()

    var onMeasurementUpdate: ((Float, String) -> Unit)? = null
    var onMeasurementComplete: ((Measurement) -> Unit)? = null

    companion object {
        private const val POINT_RADIUS = 0.015f
        private const val LINE_THICKNESS = 0.0045f
        private const val MIN_DISTANCE = 0.01f
    }

    fun setSnapEnabled(enabled: Boolean) {
        snapToSurface = enabled
    }

    fun setGridEnabled(enabled: Boolean) {
        showGrid = enabled
    }

    fun startMeasurement(type: MeasurementType = MeasurementType.LINEAR) {
        currentType = type
        clearCurrentMeasurement()
        installBillboardUpdater()
    }

    fun getPointCount(): Int = currentPoints.size

    fun getCurrentValue(): Float {
        return when (currentType) {
            MeasurementType.LINEAR -> calculateTotalDistance()
            MeasurementType.HEIGHT -> calculateHeight()
            MeasurementType.AREA -> calculateArea()
        }
    }

    fun getCurrentLabel(): String {
        return when (currentType) {
            MeasurementType.LINEAR -> formatDistance(getCurrentValue())
            MeasurementType.HEIGHT -> formatDistance(getCurrentValue())
            MeasurementType.AREA -> formatArea(getCurrentValue())
        }
    }

    fun addMeasurementPoint(hitResult: HitResult): Boolean {
        val anchor = try {
            hitResult.createAnchor()
        } catch (_: Exception) {
            null
        } ?: return false

        val pose = anchor.pose
        val finalPose = if (snapToSurface && hitResult.trackable is Plane) {
            snapPoseToPlane(pose, hitResult.trackable as Plane)
        } else {
            pose
        }

        val anchorNode = createPointMarker(anchor)
        val point = MeasurementPoint(anchor, finalPose, anchorNode)
        currentPoints.add(point)

        when (currentType) {
            MeasurementType.LINEAR -> {
                if (currentPoints.size >= 2) {
                    updatePolyline(closed = false)
                    updateLabelForLinear()
                }
            }

            MeasurementType.HEIGHT -> {
                if (currentPoints.size >= 2) {
                    updateHeightVisual()
                    updateLabelForHeight()
                } else {
                    clearActiveLabel()
                    onMeasurementUpdate?.invoke(0f, "0.00 m")
                }
            }

            MeasurementType.AREA -> {
                if (currentPoints.size >= 2) {
                    updatePolyline(closed = false)
                }
                if (currentPoints.size >= 3) {
                    updateLabelForAreaPreview()
                } else {
                    clearActiveLabel()
                    onMeasurementUpdate?.invoke(0f, "0.00 m²")
                }
            }
        }
        return true
    }

    fun undoLastPoint() {
        if (currentPoints.isEmpty()) return
        val last = currentPoints.removeLast()
        try {
            last.anchor.detach()
        } catch (_: Exception) {
        }
        last.node.setParent(null)

        when (currentType) {
            MeasurementType.LINEAR -> {
                updatePolyline(closed = false)
                updateLabelForLinear()
            }

            MeasurementType.HEIGHT -> {
                updateHeightVisual()
                updateLabelForHeight()
            }

            MeasurementType.AREA -> {
                updatePolyline(closed = false)
                updateLabelForAreaPreview()
            }
        }
    }

    fun finishMeasurement(): Measurement? {
        val ok = when (currentType) {
            MeasurementType.LINEAR -> currentPoints.size >= 2
            MeasurementType.HEIGHT -> currentPoints.size >= 2
            MeasurementType.AREA -> currentPoints.size >= 3
        }
        if (!ok) return null

        val id = "meas_${System.currentTimeMillis()}"
        val now = System.currentTimeMillis()

        val measurement = when (currentType) {
            MeasurementType.LINEAR -> {
                val dist = calculateTotalDistance()
                Measurement(
                    id = id,
                    type = currentType,
                    points = currentPoints.toList(),
                    distance = dist,
                    label = formatDistance(dist),
                    timestamp = now
                )
            }

            MeasurementType.HEIGHT -> {
                val h = calculateHeight()
                Measurement(
                    id = id,
                    type = currentType,
                    points = currentPoints.toList(),
                    distance = h,
                    label = formatDistance(h),
                    timestamp = now,
                    height = h
                )
            }

            MeasurementType.AREA -> {
                val a = calculateArea()
                val p = calculatePerimeter()
                Measurement(
                    id = id,
                    type = currentType,
                    points = currentPoints.toList(),
                    distance = p,
                    label = formatArea(a),
                    timestamp = now,
                    area = a,
                    perimeter = p
                )
            }
        }

        measurements.add(measurement)
        try {
            MeasurementStore(sceneView.context).append(measurement)
        } catch (_: Exception) {
        }
        onMeasurementComplete?.invoke(measurement)

        // Keep visuals in scene; just drop active references
        currentPoints.clear()
        segmentNodes.clear()
        labelNode = null
        labelRenderable = null
        labelTextView = null

        return measurement
    }

    fun clearAll() {
        clearCurrentMeasurement()
        measurements.clear()
        try {
            MeasurementStore(sceneView.context).clear()
        } catch (_: Exception) {
        }
    }

    fun getSavedMeasurements(): List<Measurement> = measurements.toList()

    fun exportMeasurements(): String {
        return try {
            MeasurementStore(sceneView.context).exportJson()
        } catch (_: Exception) {
            ""
        }
    }

    private fun clearCurrentMeasurement() {
        currentPoints.forEach { p ->
            try {
                p.anchor.detach()
            } catch (_: Exception) {
            }
            p.node.setParent(null)
        }
        currentPoints.clear()

        segmentNodes.forEach { it.setParent(null) }
        segmentNodes.clear()
        clearActiveLabel()
    }

    private fun clearActiveLabel() {
        labelNode?.setParent(null)
        labelNode = null
        labelRenderable = null
        labelTextView = null
    }

    private fun createPointMarker(anchor: Anchor): AnchorNode {
        val anchorNode = AnchorNode(anchor)
        anchorNode.setParent(sceneView.scene)

        scope.launch(Dispatchers.Main) {
            MaterialFactory.makeOpaqueWithColor(
                sceneView.context,
                com.google.ar.sceneform.rendering.Color(0f, 0.96f, 1f)
            ).thenAccept { material ->
                val cube = ShapeFactory.makeCube(
                    Vector3(POINT_RADIUS * 2f, POINT_RADIUS * 2f, POINT_RADIUS * 2f),
                    Vector3.zero(),
                    material
                )
                val node = Node()
                node.renderable = cube
                node.setParent(anchorNode)
            }
        }

        return anchorNode
    }

    private fun updatePolyline(closed: Boolean) {
        segmentNodes.forEach { it.setParent(null) }
        segmentNodes.clear()
        if (currentPoints.size < 2) return

        scope.launch(Dispatchers.Main) {
            MaterialFactory.makeOpaqueWithColor(
                sceneView.context,
                com.google.ar.sceneform.rendering.Color(0f, 0.96f, 1f, 0.8f)
            ).thenAccept { material ->
                for (i in 0 until currentPoints.size - 1) {
                    val a = currentPoints[i].getPosition()
                    val b = currentPoints[i + 1].getPosition()
                    createSegment(a, b, material)
                }
                if (closed && currentPoints.size >= 3) {
                    val a = currentPoints.last().getPosition()
                    val b = currentPoints.first().getPosition()
                    createSegment(a, b, material)
                }
            }
        }
    }

    private fun createSegment(start: Vector3, end: Vector3, material: Material) {
        val dir = Vector3.subtract(end, start)
        val dist = dir.length()
        if (dist < MIN_DISTANCE) return

        val cylinder = ShapeFactory.makeCylinder(
            LINE_THICKNESS,
            dist,
            Vector3(0f, dist / 2f, 0f),
            material
        )

        val node = Node()
        node.renderable = cylinder

        val mid = Vector3.add(start, end).scaled(0.5f)
        node.worldPosition = mid
        node.worldRotation = Quaternion.lookRotation(dir.normalized(), Vector3.up())
        node.setParent(sceneView.scene)
        segmentNodes.add(node)
    }

    private fun updateHeightVisual() {
        segmentNodes.forEach { it.setParent(null) }
        segmentNodes.clear()
        if (currentPoints.size < 2) return

        val base = currentPoints.first().getPosition()
        val top = currentPoints.last().getPosition()
        val verticalTop = Vector3(base.x, top.y, base.z)

        scope.launch(Dispatchers.Main) {
            MaterialFactory.makeOpaqueWithColor(
                sceneView.context,
                com.google.ar.sceneform.rendering.Color(1f, 0.55f, 0.2f, 0.9f)
            ).thenAccept { material ->
                createSegment(base, verticalTop, material)
            }
        }
    }

    private fun updateLabelForLinear() {
        val value = calculateTotalDistance()
        if (currentPoints.size < 2) {
            clearActiveLabel()
            onMeasurementUpdate?.invoke(0f, formatDistance(0f))
            return
        }

        val a = currentPoints[currentPoints.size - 2].getPosition()
        val b = currentPoints.last().getPosition()
        val mid = Vector3.add(a, b).scaled(0.5f)
        createOrUpdateFloatingLabel(mid, formatDistance(value))
        onMeasurementUpdate?.invoke(value, formatDistance(value))
    }

    private fun updateLabelForHeight() {
        val h = calculateHeight()
        if (currentPoints.size < 2) {
            clearActiveLabel()
            onMeasurementUpdate?.invoke(0f, formatDistance(0f))
            return
        }

        val base = currentPoints.first().getPosition()
        val top = currentPoints.last().getPosition()
        val verticalTop = Vector3(base.x, top.y, base.z)
        val mid = Vector3.add(base, verticalTop).scaled(0.5f)
        createOrUpdateFloatingLabel(mid, formatDistance(h))
        onMeasurementUpdate?.invoke(h, formatDistance(h))
    }

    private fun updateLabelForAreaPreview() {
        if (currentPoints.size < 3) {
            clearActiveLabel()
            onMeasurementUpdate?.invoke(0f, "0.00 m²")
            return
        }

        val a = calculateArea()
        val centroid = calculateCentroidXZ()
        createOrUpdateFloatingLabel(centroid, formatArea(a))
        onMeasurementUpdate?.invoke(a, formatArea(a))
    }

    private fun createOrUpdateFloatingLabel(position: Vector3, text: String) {
        scope.launch(Dispatchers.Main) {
            if (labelNode == null) {
                val tv = TextView(sceneView.context).apply {
                    setTextColor(Color.WHITE)
                    setBackgroundColor(0xAA000000.toInt())
                    textSize = 14f
                    setPadding(16, 10, 16, 10)
                    this.text = text
                }

                ViewRenderable.builder()
                    .setView(sceneView.context, tv)
                    .build()
                    .thenAccept { renderable ->
                        labelRenderable = renderable
                        labelTextView = tv

                        val node = Node()
                        node.renderable = renderable
                        node.worldPosition = position
                        node.localScale = Vector3(0.7f, 0.7f, 0.7f)
                        node.setParent(sceneView.scene)
                        labelNode = node
                    }
            } else {
                labelNode?.worldPosition = position
                (labelRenderable?.view as? TextView)?.text = text
            }
        }
    }

    private fun installBillboardUpdater() {
        if (updateListenerInstalled) return
        updateListenerInstalled = true

        sceneView.scene.addOnUpdateListener {
            val node = labelNode ?: return@addOnUpdateListener
            val camPos = sceneView.scene.camera.worldPosition
            val dir = Vector3.subtract(camPos, node.worldPosition)
            if (dir.length() > 0.0001f) {
                node.worldRotation = Quaternion.lookRotation(dir.normalized(), Vector3.up())
            }
        }
    }

    private fun snapPoseToPlane(pose: Pose, plane: Plane): Pose {
        val center = plane.centerPose
        return Pose.makeTranslation(pose.tx(), center.ty(), pose.tz())
    }

    private fun calculateTotalDistance(): Float {
        if (currentPoints.size < 2) return 0f
        var total = 0f
        for (i in 0 until currentPoints.size - 1) {
            val a = currentPoints[i].getPosition()
            val b = currentPoints[i + 1].getPosition()
            total += Vector3.subtract(b, a).length()
        }
        return total
    }

    private fun calculateHeight(): Float {
        if (currentPoints.size < 2) return 0f
        val base = currentPoints.first().pose
        val top = currentPoints.last().pose
        return abs(top.ty() - base.ty())
    }

    private fun calculatePerimeter(): Float {
        if (currentPoints.size < 2) return 0f
        var total = 0f
        for (i in 0 until currentPoints.size - 1) {
            val a = currentPoints[i].getPosition()
            val b = currentPoints[i + 1].getPosition()
            total += Vector3.subtract(b, a).length()
        }
        if (currentPoints.size >= 3) {
            val a = currentPoints.last().getPosition()
            val b = currentPoints.first().getPosition()
            total += Vector3.subtract(b, a).length()
        }
        return total
    }

    private fun calculateArea(): Float {
        if (currentPoints.size < 3) return 0f
        var sum = 0f
        val pts = currentPoints.map { it.getPosition() }
        for (i in pts.indices) {
            val j = (i + 1) % pts.size
            sum += pts[i].x * pts[j].z - pts[j].x * pts[i].z
        }
        return abs(sum) * 0.5f
    }

    private fun calculateCentroidXZ(): Vector3 {
        val pts = currentPoints.map { it.getPosition() }
        if (pts.isEmpty()) return Vector3.zero()

        var sx = 0f
        var sy = 0f
        var sz = 0f
        for (p in pts) {
            sx += p.x
            sy += p.y
            sz += p.z
        }
        val n = max(1, pts.size)
        return Vector3(sx / n, sy / n, sz / n)
    }

    private fun formatDistance(meters: Float): String {
        val m = max(0f, meters)
        return when (units) {
            Units.METRIC -> {
                if (m >= 1f) String.format("%.2f m", m) else String.format("%.1f cm", m * 100f)
            }

            Units.IMPERIAL -> {
                val feet = m * 3.28084f
                if (feet >= 1f) String.format("%.2f ft", feet) else {
                    val inches = feet * 12f
                    String.format("%.1f in", inches)
                }
            }
        }
    }

    private fun formatArea(m2: Float): String {
        val a = max(0f, m2)
        return when (units) {
            Units.METRIC -> String.format("%.2f m²", a)
            Units.IMPERIAL -> {
                val ft2 = a * 10.7639104f
                String.format("%.2f ft²", ft2)
            }
        }
    }
}
