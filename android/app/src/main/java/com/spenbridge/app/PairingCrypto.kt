package com.spenbridge.app

import java.nio.ByteBuffer
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.spec.ECGenParameterSpec
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/** Enrollment-only commitments and verification number, shared with Python. */
object PairingCrypto {
    private val domain = "SPEN-PAIR-1\u0000".toByteArray(Charsets.US_ASCII)
    fun createKey(): KeyPair = KeyPairGenerator.getInstance("EC").apply {
        initialize(ECGenParameterSpec("secp256r1"), SecureRandom())
    }.generateKeyPair()
    fun nonce(): ByteArray = ByteArray(32).also { SecureRandom().nextBytes(it) }
    fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it.toInt() and 255) }
    fun unhex(value: String, size: Int? = null, maximum: Int = 200): ByteArray {
        require(value.length % 2 == 0 && value.length <= maximum * 2 && value.all { Character.digit(it, 16) >= 0 })
        return ByteArray(value.length / 2) { value.substring(it * 2, it * 2 + 2).toInt(16).toByte() }.also {
            require(size == null || it.size == size)
        }
    }
    fun commitment(role: String, publicKey: ByteArray, nonce: ByteArray): ByteArray {
        require(role in listOf("client", "server") && nonce.size == 32)
        return MessageDigest.getInstance("SHA-256").digest(domain + role.toByteArray(Charsets.US_ASCII) + byteArrayOf(0) + publicKey + nonce)
    }
    fun verificationNumber(secret: ByteArray, fingerprint: String, clientPublic: ByteArray,
                           clientNonce: ByteArray, serverPublic: ByteArray, serverNonce: ByteArray): String {
        val transcript = domain + unhex(fingerprint, 32) + clientPublic + clientNonce + serverPublic + serverNonce
        val mac = Mac.getInstance("HmacSHA256").apply { init(SecretKeySpec(secret, "HmacSHA256")) }.doFinal(transcript)
        val number = (ByteBuffer.wrap(mac).int.toLong() and 0xffffffffL) % 1_000_000L
        return String.format(java.util.Locale.ROOT, "%06d", number)
    }
}
