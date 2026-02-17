package com.example.aibrain

import android.content.Context
import android.media.AudioAttributes
import android.media.SoundPool

/**
 * Менеджер звуковых эффектов.
 */
class SoundManager(context: Context) {

    private val soundPool: SoundPool
    private val sounds = mutableMapOf<SoundType, Int>()

    init {
        val audioAttributes = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_GAME)
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .build()

        soundPool = SoundPool.Builder()
            .setMaxStreams(5)
            .setAudioAttributes(audioAttributes)
            .build()

        // Загрузить звуки (нужно добавить файлы в res/raw/)
        // sounds[SoundType.COLLAPSE] = soundPool.load(context, R.raw.metal_crash, 1)
        // sounds[SoundType.PLACE] = soundPool.load(context, R.raw.metal_click, 1)
        // sounds[SoundType.REMOVE] = soundPool.load(context, R.raw.metal_cut, 1)
    }

    fun play(soundType: SoundType, volume: Float = 1.0f) {
        sounds[soundType]?.let { soundId ->
            soundPool.play(soundId, volume, volume, 1, 0, 1.0f)
        }
    }

    fun release() {
        soundPool.release()
    }
}

enum class SoundType {
    COLLAPSE,
    PLACE,
    REMOVE
}
