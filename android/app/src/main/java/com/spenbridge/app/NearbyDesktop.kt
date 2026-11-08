package com.spenbridge.app

import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.Inet4Address
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.NetworkInterface
import java.net.SocketTimeoutException

/** Discovery carries names and endpoints only. It never distributes credentials. */
data class NearbyDesktop(val host: String, val port: Int, val name: String)

object DesktopDiscovery {
    const val PORT = 40119
    fun search(publish: (DatagramSocket) -> Boolean, found: (NearbyDesktop) -> Unit) {
        DatagramSocket(null).use { socket ->
            if (!publish(socket)) return
            socket.broadcast = true
            socket.soTimeout = 250
            socket.bind(InetSocketAddress(0))
            val probe = PairingCrypto.hex(PairingCrypto.nonce().copyOf(16))
            val query = JSONObject().put("service", "spen-bridge").put("version", 1).put("probe", probe)
                .toString().toByteArray(Charsets.UTF_8)
            val addresses = mutableSetOf(InetAddress.getByName("255.255.255.255"))
            NetworkInterface.getNetworkInterfaces()?.toList()?.filter { it.isUp && !it.isLoopback }?.forEach { iface ->
                iface.interfaceAddresses.mapNotNull { it.broadcast }.filterIsInstance<Inet4Address>().forEach { addresses.add(it) }
            }
            val deadline = System.nanoTime() + 10_000_000_000L
            var nextSend = 0L
            val seen = mutableSetOf<String>()
            while (!socket.isClosed && System.nanoTime() < deadline) {
                if (System.nanoTime() >= nextSend) {
                    for (address in addresses) {
                        try { socket.send(DatagramPacket(query, query.size, address, PORT)) } catch (_: java.io.IOException) { }
                    }
                    nextSend = System.nanoTime() + 600_000_000L
                }
                val packet = DatagramPacket(ByteArray(513), 513)
                try { socket.receive(packet) } catch (_: SocketTimeoutException) { continue }
                if (packet.length > 512 || packet.address !is Inet4Address || packet.address.isLoopbackAddress) continue
                try {
                    val reply = JSONObject(String(packet.data, 0, packet.length, Charsets.UTF_8))
                    if (reply.optString("service") != "spen-bridge" || reply.optInt("version") != 1 || reply.optString("probe") != probe) continue
                    val port = reply.optInt("port")
                    val name = reply.optString("name").take(80)
                    val host = packet.address.hostAddress ?: continue
                    if (port !in 1..65535 || name.isBlank() || name.any { Character.isISOControl(it) }) continue
                    if (seen.size < 16 && seen.add("$host:$port")) found(NearbyDesktop(host, port, name))
                } catch (_: org.json.JSONException) { }
            }
        }
    }
}
