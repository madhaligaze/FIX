package com.example.aibrain.measurement

import android.content.Context
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.io.File

class MeasurementStore(private val context: Context) {

    private val gson = Gson()
    private val file: File = File(context.filesDir, "measurements.json")
    private val lock = Any()

    data class Point3(val x: Float, val y: Float, val z: Float)

    data class MeasurementRecord(
        val id: String,
        val type: String,
        val label: String,
        val timestamp: Long,
        val distance_m: Float? = null,
        val height_m: Float? = null,
        val area_m2: Float? = null,
        val perimeter_m: Float? = null,
        val points: List<Point3>
    )

    fun append(measurement: Measurement) {
        synchronized(lock) {
            val list = loadInternal().toMutableList()
            list.add(toRecord(measurement))
            saveInternal(list)
        }
    }

    fun clear() {
        synchronized(lock) {
            if (file.exists()) file.delete()
        }
    }

    fun exportJson(): String {
        synchronized(lock) {
            return if (file.exists()) {
                try {
                    file.readText()
                } catch (_: Exception) {
                    ""
                }
            } else {
                "[]"
            }
        }
    }

    private fun toRecord(m: Measurement): MeasurementRecord {
        val pts = m.points.map { p -> Point3(p.pose.tx(), p.pose.ty(), p.pose.tz()) }
        return MeasurementRecord(
            id = m.id,
            type = m.type.name,
            label = m.label,
            timestamp = m.timestamp,
            distance_m = if (m.type == MeasurementType.LINEAR) m.distance else null,
            height_m = m.height,
            area_m2 = m.area,
            perimeter_m = m.perimeter,
            points = pts
        )
    }

    private fun loadInternal(): List<MeasurementRecord> {
        if (!file.exists()) return emptyList()
        return try {
            val type = object : TypeToken<List<MeasurementRecord>>() {}.type
            gson.fromJson<List<MeasurementRecord>>(file.readText(), type) ?: emptyList()
        } catch (_: Exception) {
            emptyList()
        }
    }

    private fun saveInternal(list: List<MeasurementRecord>) {
        try {
            file.writeText(gson.toJson(list))
        } catch (_: Exception) {
            // ignore
        }
    }
}
