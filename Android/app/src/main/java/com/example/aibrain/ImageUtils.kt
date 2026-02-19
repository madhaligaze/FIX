package com.example.aibrain

import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import android.media.Image
import android.util.Base64
import java.io.ByteArrayOutputStream

object ImageUtils {
    data class Nv21Frame(
        val data: ByteArray,
        val width: Int,
        val height: Int
    )

    fun imageToBase64(image: Image): String = convertYuvToJpegBase64(image)

    fun yuv420ToNv21(image: Image, swapUv: Boolean = false): Nv21Frame {
        require(image.format == ImageFormat.YUV_420_888) { "Expected YUV_420_888 image" }

        val width = image.width
        val height = image.height
        val out = ByteArray(width * height + (width * height / 2))

        val yPlane = image.planes[0]
        val uPlane = image.planes[1]
        val vPlane = image.planes[2]

        val yBuffer = yPlane.buffer.duplicate()
        val uBuffer = uPlane.buffer.duplicate()
        val vBuffer = vPlane.buffer.duplicate()
        val yBase = yBuffer.position()
        val uBase = uBuffer.position()
        val vBase = vBuffer.position()

        var dst = 0

        if (yPlane.pixelStride == 1 && yPlane.rowStride == width) {
            yBuffer.position(yBase)
            yBuffer.get(out, 0, width * height)
            dst = width * height
        } else {
            for (row in 0 until height) {
                val rowOffset = row * yPlane.rowStride
                for (col in 0 until width) {
                    out[dst++] = yBuffer.get(yBase + rowOffset + col * yPlane.pixelStride)
                }
            }
        }

        val uvHeight = height / 2
        val uvWidth = width / 2
        val useSwapped = swapUv

        for (row in 0 until uvHeight) {
            val uRowOffset = row * uPlane.rowStride
            val vRowOffset = row * vPlane.rowStride
            for (col in 0 until uvWidth) {
                val u = uBuffer.get(uBase + uRowOffset + col * uPlane.pixelStride)
                val v = vBuffer.get(vBase + vRowOffset + col * vPlane.pixelStride)
                if (useSwapped) {
                    out[dst++] = u
                    out[dst++] = v
                } else {
                    out[dst++] = v
                    out[dst++] = u
                }
            }
        }

        return Nv21Frame(data = out, width = width, height = height)
    }

    fun copyToNv21(image: Image): Nv21Frame = yuv420ToNv21(image)

    fun nv21ToJpegBase64(nv21: ByteArray, width: Int, height: Int, quality: Int = 75): String {
        val yuvImage = YuvImage(nv21, ImageFormat.NV21, width, height, null)
        val out = ByteArrayOutputStream()
        yuvImage.compressToJpeg(Rect(0, 0, width, height), quality.coerceIn(1, 100), out)

        return Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
    }

    fun convertYuvToJpegBase64(image: Image): String {
        val frame = yuv420ToNv21(image)
        return nv21ToJpegBase64(frame.data, frame.width, frame.height, 75)
    }
}
