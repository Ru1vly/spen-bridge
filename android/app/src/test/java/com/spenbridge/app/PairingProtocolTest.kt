package com.spenbridge.app

import org.junit.Assert.*
import org.junit.Test

class PairingProtocolTest {
    @Test fun proofUsesFreshChallengeAndSeparatesClientAndServerRoles() {
        val nonce = ByteArray(32) { it.toByte() }
        val client = PairingProtocol.proof("a".repeat(43), nonce, "client")
        assertEquals("53504232f362637d845b5bf0c27b8a750964fb5e0621837a6cf59a71c8255cef9e1a084a", client.joinToString("") { "%02x".format(it.toInt() and 255) })
        assertTrue(PairingProtocol.verifyProof("a".repeat(43), nonce, "client", client))
        assertFalse(PairingProtocol.verifyProof("a".repeat(43), nonce, "server", client))
        assertFalse(PairingProtocol.verifyProof("a".repeat(43), ByteArray(32), "client", client))
        assertFalse(PairingProtocol.verifyProof("b".repeat(43), nonce, "client", client))
    }

    private fun certificate(name: String): java.security.cert.X509Certificate =
        java.security.cert.CertificateFactory.getInstance("X.509").generateCertificate(
            javaClass.getResourceAsStream("/$name.der")
        ) as java.security.cert.X509Certificate

    private fun fingerprint(cert: java.security.cert.X509Certificate): String =
        java.security.MessageDigest.getInstance("SHA-256").digest(cert.encoded)
            .joinToString("") { "%02x".format(it.toInt() and 255) }

    @Test fun certificatePinRejectsWrongMissingAndExpiredIdentities() {
        val paired = certificate("paired")
        PairingProtocol.verifyCertificate(arrayOf(paired), fingerprint(paired))
        for ((chain, pin) in listOf(
            arrayOf(paired) to "00".repeat(32),
            emptyArray<java.security.cert.X509Certificate>() to fingerprint(paired),
            arrayOf(paired) to "",
            arrayOf(certificate("expired")) to fingerprint(certificate("expired"))
        )) {
            try {
                PairingProtocol.verifyCertificate(chain, pin)
                fail("Invalid certificate accepted")
            } catch (_: java.security.cert.CertificateException) { }
        }
    }

    @Test fun identityFieldsMustBeCompleteAndValid() {
        assertFalse(PairingProtocol.validCode(""))
        assertFalse(PairingProtocol.validCode("a".repeat(42)))
        assertFalse(PairingProtocol.validFingerprint("trust-any-server"))
        assertTrue(PairingProtocol.validFingerprint("AB:".repeat(31) + "AB"))
        assertEquals("ab".repeat(32), PairingProtocol.normalizeFingerprint(" AB:".repeat(31) + "AB "))
    }
}
