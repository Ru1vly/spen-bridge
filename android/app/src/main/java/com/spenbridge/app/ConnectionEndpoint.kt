package com.spenbridge.app

import java.net.IDN
import java.net.Inet6Address
import java.net.InetAddress

/** Immutable endpoint snapshots prevent mixed host/port/pairing generations. */
data class ConnectionEndpoint(val host: String, val port: Int, val fingerprint: String, val code: String) {
    override fun toString(): String = "ConnectionEndpoint(host=$host, port=$port, paired=${isPaired()})"
    fun isPaired(): Boolean = PairingProtocol.validFingerprint(fingerprint) && PairingProtocol.validCode(code)
    fun isLoopback(): Boolean = host in listOf("127.0.0.1", "::1", "localhost")

    companion object {
        fun validHost(value: String): Boolean {
            if (value.isBlank() || value.length > 253 || value.any { it.isWhitespace() || it in "/\\?#@" }) return false
            if (':' in value) return try { InetAddress.getByName(value) is Inet6Address } catch (_: Exception) { false }
            if (value.all { it.isDigit() || it == '.' }) {
                val parts = value.split('.')
                return parts.size == 4 && parts.all { part ->
                    part.isNotEmpty() && part.length <= 3 && part.toIntOrNull() in 0..255 &&
                        (part.length == 1 || part[0] != '0')
                }
            }
            return try {
                val ascii = IDN.toASCII(value.removeSuffix("."), IDN.USE_STD3_ASCII_RULES)
                ascii.isNotEmpty() && ascii.length <= 253 && ascii.split('.').all { it.length in 1..63 }
            } catch (_: IllegalArgumentException) { false }
        }
    }
}
