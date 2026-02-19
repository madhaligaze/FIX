package com.example.aibrain

/**
 * Единый источник правды по состоянию соединения (для UI и логики).
 */
enum class ConnectionStatus {
    UNKNOWN,
    ONLINE,
    RECONNECTING,
    OFFLINE
}

data class ConnectionState(
    val status: ConnectionStatus = ConnectionStatus.UNKNOWN,
    val detail: String = ""
)
