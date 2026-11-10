package ir.windroida.app.net

import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.Base64
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSocket
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/** SHA-256 fingerprint of a certificate as AA:BB:... (the same text the server window prints and Prefs.pin stores). */
fun certFingerprint(c: X509Certificate): String =
    MessageDigest.getInstance("SHA-256").digest(c.encoded).joinToString(":") { "%02X".format(it) }

/** Trust only the certificate whose fingerprint equals [pin]. No system CA store is involved. */
class PinTrust(private val pin: String) : X509TrustManager {
    override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
    override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
        if (chain.isEmpty() || !certFingerprint(chain[0]).equals(pin, ignoreCase = true)) throw CertificateException("certificate does not match the pinned fingerprint")
    }
    override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
}

/** Reads the fingerprint of the server's certificate without trusting it (used once, to ask the user to confirm). */
fun fetchFingerprint(host: String, port: Int, timeoutMs: Int = 8000): String {
    var got = ""
    val tm = object : X509TrustManager {
        override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
        override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) { if (chain.isNotEmpty()) got = certFingerprint(chain[0]) }
        override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
    }
    val ctx = SSLContext.getInstance("TLS")
    ctx.init(null, arrayOf<TrustManager>(tm), null)
    val raw = Socket()
    try {
        raw.connect(InetSocketAddress(host, port), timeoutMs)
        raw.soTimeout = timeoutMs
        val s = ctx.socketFactory.createSocket(raw, host, port, true) as SSLSocket
        s.startHandshake()
        s.close()
    } finally { try { raw.close() } catch (_: Exception) {} }
    if (got.isEmpty()) throw IOException("no certificate")
    return got
}

/** A minimal RFC 6455 client (text frames, ping/pong, fragmentation). The server only needs /ws and JSON text. */
class WsClient(private val host: String, private val port: Int, private val tls: Boolean, private val pin: String, private val path: String = "/ws") {
    interface Listener {
        fun onText(s: String)
        fun onClosed(reason: String)
    }

    companion object { const val MAX_MESSAGE = 16 * 1024 * 1024 }

    @Volatile private var sock: Socket? = null
    @Volatile private var out: OutputStream? = null
    @Volatile var open = false
        private set
    private val sendLock = Any()
    private val rnd = SecureRandom()

    fun connect(l: Listener, timeoutMs: Int = 8000) {
        val raw = Socket()
        try {
            raw.connect(InetSocketAddress(host, port), timeoutMs)
            raw.tcpNoDelay = true
            raw.soTimeout = timeoutMs
            val s: Socket = if (tls) {
                if (pin.isEmpty()) throw IOException("certificate not confirmed yet")
                val ctx = SSLContext.getInstance("TLS")
                ctx.init(null, arrayOf<TrustManager>(PinTrust(pin)), null)
                val ss = ctx.socketFactory.createSocket(raw, host, port, true) as SSLSocket
                ss.startHandshake()
                ss
            } else raw
            val ins = s.getInputStream()
            val os = s.getOutputStream()
            val keyBytes = ByteArray(16); rnd.nextBytes(keyBytes)
            val key = Base64.getEncoder().encodeToString(keyBytes)
            os.write(("GET $path HTTP/1.1\r\nHost: $host:$port\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n" +
                "Sec-WebSocket-Key: $key\r\nSec-WebSocket-Version: 13\r\n\r\n").toByteArray(Charsets.ISO_8859_1))
            os.flush()
            val head = readHead(ins)
            val lines = head.split("\r\n")
            if (lines.isEmpty() || !lines[0].contains(" 101")) throw IOException("server refused the WebSocket: " + (lines.firstOrNull() ?: ""))
            val want = Base64.getEncoder().encodeToString(MessageDigest.getInstance("SHA-1").digest((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").toByteArray()))
            val got = lines.firstOrNull { it.startsWith("sec-websocket-accept:", ignoreCase = true) }?.substringAfter(":")?.trim()
            if (got != want) throw IOException("bad handshake answer")
            s.soTimeout = 45000        // the caller pings every ~12 s; 45 s of silence means a dead link
            sock = s; out = os; open = true
            val t = Thread { readLoop(s, ins, l) }
            t.isDaemon = true
            t.name = "wd-ws-reader"
            t.start()
        } catch (e: Exception) {
            try { raw.close() } catch (_: Exception) {}
            throw e
        }
    }

    private fun readHead(ins: InputStream): String {
        val sb = StringBuilder()
        while (sb.length < 16384) {
            val b = ins.read()
            if (b < 0) throw IOException("closed during handshake")
            sb.append(b.toChar())
            if (sb.endsWith("\r\n\r\n")) return sb.toString()
        }
        throw IOException("handshake header too long")
    }

    private fun readFully(ins: InputStream, n: Int): ByteArray {
        val b = ByteArray(n)
        var o = 0
        while (o < n) {
            val r = ins.read(b, o, n - o)
            if (r < 0) throw IOException("connection closed")
            o += r
        }
        return b
    }

    private fun readLoop(s: Socket, ins: InputStream, l: Listener) {
        var reason = "closed"
        val msg = ByteArrayOutputStream()
        var curOp = 1
        try {
            while (true) {
                val b0 = ins.read()
                if (b0 < 0) break
                val fin = (b0 and 0x80) != 0
                val op = b0 and 0x0f
                val b1 = ins.read()
                if (b1 < 0) break
                var len = (b1 and 0x7f).toLong()
                if (len == 126L) { val x = readFully(ins, 2); len = (((x[0].toInt() and 0xff) shl 8) or (x[1].toInt() and 0xff)).toLong() }
                else if (len == 127L) { val x = readFully(ins, 8); len = 0; for (k in 0 until 8) len = (len shl 8) or (x[k].toLong() and 0xff) }
                if (len < 0 || len > MAX_MESSAGE) { reason = "message too big"; break }
                val mask = if ((b1 and 0x80) != 0) readFully(ins, 4) else null
                val p = readFully(ins, len.toInt())
                if (mask != null) for (k in p.indices) p[k] = (p[k].toInt() xor mask[k and 3].toInt()).toByte()
                when (op) {
                    0, 1, 2 -> {
                        if (op != 0) curOp = op
                        msg.write(p)
                        if (msg.size() > MAX_MESSAGE) { reason = "message too big"; break }
                        if (fin) {
                            val text = msg.toString("UTF-8"); msg.reset()
                            if (curOp == 1) try { l.onText(text) } catch (_: Exception) {}
                        }
                    }
                    8 -> { reason = "server closed"; break }
                    9 -> sendFrame(10, p)
                    else -> {}
                }
            }
        } catch (e: Exception) {
            reason = e.message ?: e.javaClass.simpleName
        } finally {
            open = false
            try { s.close() } catch (_: Exception) {}
            l.onClosed(reason)
        }
    }

    private fun sendFrame(op: Int, payload: ByteArray) {
        val os = out ?: throw IOException("not connected")
        val n = payload.size
        val hdr = ByteArrayOutputStream()
        hdr.write(0x80 or op)
        when {
            n < 126 -> hdr.write(0x80 or n)
            n < 65536 -> { hdr.write(0x80 or 126); hdr.write(n shr 8); hdr.write(n and 0xff) }
            else -> { hdr.write(0x80 or 127); for (k in 7 downTo 0) hdr.write(((n.toLong() shr (8 * k)) and 0xff).toInt()) }
        }
        val mask = ByteArray(4); rnd.nextBytes(mask)
        hdr.write(mask)
        val body = ByteArray(n) { (payload[it].toInt() xor mask[it and 3].toInt()).toByte() }
        synchronized(sendLock) {
            os.write(hdr.toByteArray()); os.write(body); os.flush()
        }
    }

    fun send(text: String) {
        if (!open) throw IOException("not connected")
        sendFrame(1, text.toByteArray(Charsets.UTF_8))
    }

    fun close() {
        open = false
        try { if (out != null) sendFrame(8, ByteArray(0)) } catch (_: Exception) {}
        try { sock?.close() } catch (_: Exception) {}
    }
}
