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

    /**
     * Legacy API (kept): converts a YUV_420_888 camera Image to a JPEG base64 string.
     * Note: heavy; prefer [copyToNv21] + [nv21ToJpegBase64] off the main thread.
     */
    fun imageToBase64(image: Image): String = convertYuvToJpegBase64(image)

    /**
     * Copy Image planes to an NV21 byte array.
     * This is safe to do quickly on the main thread, then close the Image.
     */
    fun copyToNv21(image: Image): Nv21Frame {
        val yBuffer = image.planes[0].buffer
        val uBuffer = image.planes[1].buffer
        val vBuffer = image.planes[2].buffer

        val ySize = yBuffer.remaining()
        val uSize = uBuffer.remaining()
        val vSize = vBuffer.remaining()

        val nv21 = ByteArray(ySize + uSize + vSize)

        // NV21 format: Y + V + U
        yBuffer.get(nv21, 0, ySize)
        vBuffer.get(nv21, ySize, vSize)
        uBuffer.get(nv21, ySize + vSize, uSize)

        return Nv21Frame(
            data = nv21,
            width = image.width,
            height = image.height
        )
    }

    /**
     * Compress an NV21 buffer to JPEG base64.
     * Run this off the main thread.
     */
    fun nv21ToJpegBase64(nv21: ByteArray, width: Int, height: Int, quality: Int = 75): String {
        val yuvImage = YuvImage(nv21, ImageFormat.NV21, width, height, null)
        val out = ByteArrayOutputStream()
        yuvImage.compressToJpeg(Rect(0, 0, width, height), quality.coerceIn(1, 100), out)

        val imageBytes = out.toByteArray()
        return Base64.encodeToString(imageBytes, Base64.NO_WRAP)
    }

    fun convertYuvToJpegBase64(image: Image): String {
        val frame = copyToNv21(image)
        return nv21ToJpegBase64(frame.data, frame.width, frame.height, 75)
    }
}
