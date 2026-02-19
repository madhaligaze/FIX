package com.example.aibrain

import android.media.Image
import android.util.Base64
import com.google.ar.core.Frame

object DepthUtils {
    data class DepthFrame(
        val bytes: ByteArray,
        val width: Int,
        val height: Int,
        val scaleMPerUnit: Float = 0.001f,
    )

    fun tryAcquireDepth16(frame: Frame): Image? {
        return runCatching { frame.acquireRawDepthImage16Bits() }.getOrNull()
            ?: runCatching { frame.acquireDepthImage16Bits() }.getOrNull()
    }

    fun copyDepth16(image: Image): DepthFrame {
        val plane = image.planes[0]
        val width = image.width
        val height = image.height
        val rowStride = plane.rowStride
        val pixelStride = plane.pixelStride
        val src = plane.buffer.duplicate()
        val base = src.position()
        if (rowStride < width * pixelStride) {
            throw IllegalStateException("Invalid DEPTH16 strides: rowStride=$rowStride, width=$width, pixelStride=$pixelStride")
        }
        val out = ByteArray(width * height * 2)

        if (pixelStride == 2) {
            var dst = 0
            val rowBytes = width * 2
            for (y in 0 until height) {
                src.position(base + y * rowStride)
                src.get(out, dst, rowBytes)
                dst += rowBytes
            }
        } else {
            var dst = 0
            for (y in 0 until height) {
                val rowBase = y * rowStride
                for (x in 0 until width) {
                    val idx = base + rowBase + x * pixelStride
                    out[dst] = src.get(idx)
                    out[dst + 1] = src.get(idx + 1)
                    dst += 2
                }
            }
        }

        return DepthFrame(bytes = out, width = width, height = height)
    }

    fun depthBytesToBase64(bytes: ByteArray): String = Base64.encodeToString(bytes, Base64.NO_WRAP)
}
