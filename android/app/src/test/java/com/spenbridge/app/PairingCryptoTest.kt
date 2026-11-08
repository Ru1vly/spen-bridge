package com.spenbridge.app

import org.junit.Assert.*
import org.junit.Test
import javax.crypto.KeyAgreement

class PairingCryptoTest {
    @Test fun pythonGoldenVerificationNumber() {
        assertEquals("487673", PairingCrypto.verificationNumber(ByteArray(32) { it.toByte() }, "ab".repeat(32),
            "client-public".toByteArray(), ByteArray(32) { 'c'.code.toByte() },
            "server-public".toByteArray(), ByteArray(32) { 's'.code.toByte() }))
    }
    @Test fun bothEphemeralKeysDeriveTheSameNumber() {
        val client = PairingCrypto.createKey();val server = PairingCrypto.createKey()
        val cn = PairingCrypto.nonce();val sn = PairingCrypto.nonce()
        fun secret(own: java.security.KeyPair, peer: java.security.KeyPair) = KeyAgreement.getInstance("ECDH").apply {
            init(own.private);doPhase(peer.public, true)
        }.generateSecret()
        val first = PairingCrypto.verificationNumber(secret(client, server), "ab".repeat(32), client.public.encoded, cn, server.public.encoded, sn)
        val second = PairingCrypto.verificationNumber(secret(server, client), "ab".repeat(32), client.public.encoded, cn, server.public.encoded, sn)
        assertEquals(first, second);assertTrue(first.matches(Regex("[0-9]{6}")))
    }
    @Test fun commitmentBindsRoleKeyAndNonce() {
        val key = byteArrayOf(1, 2, 3);val nonce = ByteArray(32) { 7 }
        val original = PairingCrypto.commitment("client", key, nonce)
        assertFalse(original.contentEquals(PairingCrypto.commitment("server", key, nonce)))
        assertFalse(original.contentEquals(PairingCrypto.commitment("client", byteArrayOf(4), nonce)))
        assertFalse(original.contentEquals(PairingCrypto.commitment("client", key, ByteArray(32) { 8 })))
    }
    @Test fun desktopCertificateChangesVerificationNumber() {
        fun number(fp: String) = PairingCrypto.verificationNumber(ByteArray(32) { 7 }, fp, byteArrayOf(1), ByteArray(32) { 2 }, byteArrayOf(3), ByteArray(32) { 4 })
        assertNotEquals(number("01".repeat(32)), number("02".repeat(32)))
    }
    @Test fun hexRoundTripAndBounds() {
        val value = ByteArray(256) { it.toByte() }
        assertArrayEquals(value, PairingCrypto.unhex(PairingCrypto.hex(value), maximum = 256))
        for (invalid in listOf("xx", "1", "a".repeat(402))) {
            try { PairingCrypto.unhex(invalid);fail("Invalid hex accepted") } catch (_: IllegalArgumentException) { }
        }
    }
}
