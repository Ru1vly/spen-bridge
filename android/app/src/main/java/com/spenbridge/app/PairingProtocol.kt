package com.spenbridge.app

import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSocketFactory
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/** Pure JVM pairing primitives, also tested against Python protocol fixtures. */
object PairingProtocol {
    val VERSION = byteArrayOf('S'.code.toByte(), 'P'.code.toByte(), 'B'.code.toByte(), '2'.code.toByte())
    private val codePattern = Regex("[A-Za-z0-9_-]{43}")
    private val pinPattern = Regex("[0-9a-f]{64}")

    fun normalizeFingerprint(value: String): String = value.filterNot { it.isWhitespace() || it == ':' }.lowercase()
    fun validCode(value: String): Boolean = codePattern.matches(value)
    fun validFingerprint(value: String): Boolean = pinPattern.matches(normalizeFingerprint(value))

    fun proof(code: String, nonce: ByteArray, role: String): ByteArray {
        require(validCode(code) && nonce.size == 32 && role in listOf("client", "server")) { "Invalid pairing parameters" }
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(code.toByteArray(Charsets.US_ASCII), "HmacSHA256"))
        return VERSION + mac.doFinal(VERSION + role.toByteArray(Charsets.US_ASCII) + byteArrayOf(0) + nonce)
    }

    fun verifyProof(code: String, nonce: ByteArray, role: String, received: ByteArray): Boolean =
        MessageDigest.isEqual(proof(code, nonce, role), received)

    fun verifyCertificate(chain: Array<X509Certificate>, fingerprint: String) {
        if (!validFingerprint(fingerprint) || chain.isEmpty()) throw CertificateException("Desktop pairing is missing")
        chain[0].checkValidity()
        val digest = MessageDigest.getInstance("SHA-256").digest(chain[0].encoded)
        val expected = normalizeFingerprint(fingerprint).chunked(2).map { it.toInt(16).toByte() }.toByteArray()
        if (!MessageDigest.isEqual(digest, expected)) throw CertificateException("Desktop certificate does not match pairing")
    }

    // Trust is the exact paired leaf certificate plus its validity period; never the network CA set.
    @android.annotation.SuppressLint("CustomX509TrustManager")
    fun socketFactory(fingerprint: String): SSLSocketFactory {
        require(validFingerprint(fingerprint)) { "Desktop fingerprint is missing or invalid" }
        val trust = object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {
                throw CertificateException("Client certificates are not used")
            }
            override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
                verifyCertificate(chain, fingerprint)
            }
            override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
        }
        return SSLContext.getInstance("TLS").apply {
            init(null, arrayOf<TrustManager>(trust), null)
        }.socketFactory
    }
}
