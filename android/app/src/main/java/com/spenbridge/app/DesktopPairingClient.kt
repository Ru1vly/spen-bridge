package com.spenbridge.app

import org.json.JSONObject
import java.io.IOException
import java.net.InetSocketAddress
import java.net.Socket
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.KeyFactory
import java.security.MessageDigest
import java.security.cert.X509Certificate
import java.security.interfaces.ECPublicKey
import java.security.spec.X509EncodedKeySpec
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import javax.crypto.KeyAgreement
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSocket
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

data class PairedDesktop(val host: String, val port: Int, val fingerprint: String, val code: String, val name: String)

/** Bootstrap trust is established by matching committed verification numbers.
 * Unknown certificates are allowed ONLY in this user-approved enrollment path.
 * Normal pen connections continue to require exact pinning and mutual HMAC proof.
 */
object DesktopPairingClient {
    fun pair(desktop: NearbyDesktop, name: String, publish: (Socket) -> Boolean,
             verify: (String) -> Unit): PairedDesktop {
        val raw = Socket()
        val watchdog = Executors.newSingleThreadScheduledExecutor { runnable -> Thread(runnable, "Pairing deadline").apply { isDaemon = true } }
        var deadlineTask = watchdog.schedule({ try { raw.close() } catch (_: IOException) { } }, 10, TimeUnit.SECONDS)
        var tls: SSLSocket? = null
        try {
            if (!publish(raw)) throw IOException("Pairing cancelled")
            raw.tcpNoDelay = true
            raw.connect(InetSocketAddress(desktop.host, desktop.port), 3000)
            val bootstrapTrust = object : X509TrustManager {
                override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
                override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) { throw java.security.cert.CertificateException("Not a server") }
                override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
                    if (chain.isEmpty()) throw java.security.cert.CertificateException("Missing certificate")
                    chain[0].checkValidity()
                }
            }
            val context = SSLContext.getInstance("TLS").apply { init(null, arrayOf<TrustManager>(bootstrapTrust), null) }
            val channel = context.socketFactory.createSocket(raw, desktop.host, desktop.port, true) as SSLSocket
            tls = channel
            channel.enabledProtocols = channel.supportedProtocols.filter { it in listOf("TLSv1.2", "TLSv1.3") }.toTypedArray()
            channel.soTimeout = 5000
            channel.startHandshake()
            val certificate = channel.session.peerCertificates[0] as X509Certificate
            certificate.checkValidity()
            val fingerprint = PairingCrypto.hex(MessageDigest.getInstance("SHA-256").digest(certificate.encoded))
            val input = channel.inputStream
            val output = channel.outputStream
            var readDeadline = System.nanoTime() + 5_000_000_000L
            fun exact(size: Int): ByteArray {
                val bytes = ByteArray(size)
                var offset = 0
                while (offset < size) {
                    val remaining = TimeUnit.NANOSECONDS.toMillis(readDeadline - System.nanoTime())
                    if (remaining <= 0) throw java.net.SocketTimeoutException("Pairing timed out")
                    channel.soTimeout = remaining.coerceAtMost(65000).toInt()
                    val count = input.read(bytes, offset, size - offset)
                    if (count < 0) throw IOException("Desktop closed pairing. Open Pair tablet and try again.")
                    offset += count
                }
                return bytes
            }
            fun packet(kind: Byte, sequence: Int): ByteArray {
                val header = ByteBuffer.wrap(exact(Protocol.HEADER_SIZE)).order(ByteOrder.LITTLE_ENDIAN)
                val magic = ByteArray(4).also { header.get(it) }
                val actualKind = header.get()
                val seq = header.short.toInt() and 65535
                val size = header.short.toInt() and 65535
                if (!magic.contentEquals(Protocol.MAGIC) || actualKind != kind || seq != sequence || size !in 1..2048) throw IOException("Invalid pairing response")
                return exact(size)
            }
            fun send(sequence: Int, value: JSONObject) {
                val payload = value.toString().toByteArray(Charsets.UTF_8)
                require(payload.size <= 2048)
                output.write(Protocol.packPacket(Protocol.PKT_PAIRING, sequence.toShort(), payload));output.flush()
            }
            val hello = packet(Protocol.PKT_HANDSHAKE, 0)
            if (hello.size != 36 || !hello.copyOfRange(0, 4).contentEquals(PairingProtocol.VERSION)) throw IOException("Desktop needs an update")
            val key = PairingCrypto.createKey()
            val public = key.public.encoded
            val nonce = PairingCrypto.nonce()
            send(0, JSONObject().put("stage", "request").put("name", name.take(80))
                .put("commitment", PairingCrypto.hex(PairingCrypto.commitment("client", public, nonce))))
            val committed = JSONObject(String(packet(Protocol.PKT_PAIRING, 0), Charsets.UTF_8))
            if (committed.getString("stage") != "server_commit") throw IOException("Invalid pairing stage")
            val serverCommitment = PairingCrypto.unhex(committed.getString("commitment"), 32)
            send(1, JSONObject().put("stage", "client_reveal").put("public_key", PairingCrypto.hex(public)).put("nonce", PairingCrypto.hex(nonce)))
            val reveal = JSONObject(String(packet(Protocol.PKT_PAIRING, 1), Charsets.UTF_8))
            if (reveal.getString("stage") != "server_reveal") throw IOException("Invalid pairing stage")
            val serverPublic = PairingCrypto.unhex(reveal.getString("public_key"), maximum = 120)
            val serverNonce = PairingCrypto.unhex(reveal.getString("nonce"), 32)
            if (!MessageDigest.isEqual(serverCommitment, PairingCrypto.commitment("server", serverPublic, serverNonce))) throw IOException("Pairing verification changed. Try again.")
            val peer = KeyFactory.getInstance("EC").generatePublic(X509EncodedKeySpec(serverPublic)) as ECPublicKey
            val own = key.public as ECPublicKey
            if (peer.params.curve != own.params.curve || peer.params.generator != own.params.generator || peer.params.order != own.params.order || peer.params.cofactor != own.params.cofactor || MessageDigest.isEqual(serverPublic, public)) throw IOException("Unsupported pairing key")
            val agreement = KeyAgreement.getInstance("ECDH").apply { init(key.private);doPhase(peer, true) }
            val number = PairingCrypto.verificationNumber(agreement.generateSecret(), fingerprint, public, nonce, serverPublic, serverNonce)
            deadlineTask.cancel(false)
            deadlineTask = watchdog.schedule({ try { raw.close() } catch (_: IOException) { } }, 65, TimeUnit.SECONDS)
            readDeadline = System.nanoTime() + 65_000_000_000L
            verify(number)
            val result = JSONObject(String(packet(Protocol.PKT_PAIRING, 2), Charsets.UTF_8))
            if (result.getString("stage") != "result" || result.get("approved") != true) throw IOException("Pairing was declined on the desktop")
            if (result.getString("fingerprint") != fingerprint) throw IOException("Desktop identity changed")
            val code = result.getString("pairing_code")
            val port = result.getInt("port")
            val host = if (desktop.host == "127.0.0.1") result.optString("host") else desktop.host
            if (!PairingProtocol.validCode(code) || !PairingProtocol.validFingerprint(fingerprint) || port !in 1..65535 || (host.isNotEmpty() && (!ConnectionEndpoint.validHost(host) || ConnectionEndpoint(host, port, "", "").isLoopback()))) throw IOException("Desktop returned invalid connection settings")
            return PairedDesktop(host, port, fingerprint, code, result.optString("name", desktop.name).take(80))
        } finally {
            deadlineTask.cancel(false);watchdog.shutdownNow()
            try { raw.close() } catch (_: IOException) { }
            try { tls?.close() } catch (_: IOException) { }
        }
    }
}
