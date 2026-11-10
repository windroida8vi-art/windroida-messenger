package ir.windroida.app.net

import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager

/** HTTP(S) to the Windroida server with the pinned certificate (media, avatars, uploads). Blocking: call from a background thread. */
class Http(private val cfg: ServerCfg) {
    private val ctx: SSLContext? = if (cfg.tls && cfg.pin.isNotEmpty()) SSLContext.getInstance("TLS").also { it.init(null, arrayOf<TrustManager>(PinTrust(cfg.pin)), null) } else null

    /** session cookie (Ghab uses a cookie login; the messenger uses a key in the URL) */
    @Volatile var cookie: String? = null

    /** one-time sign-in link of Ghab/Cloud Drive: follows nothing, just keeps the session cookie from the answer. */
    fun signIn(path: String): Boolean {
        val c = open(path, "GET")
        try {
            c.responseCode
            val set = c.headerFields?.get("Set-Cookie") ?: return false
            val ck = set.map { it.substringBefore(';') }.filter { it.contains('=') }.joinToString("; ")
            if (ck.isEmpty()) return false
            cookie = ck; return true
        } finally { c.disconnect() }
    }

    /** JSON request with the session cookie; returns (HTTP code, parsed JSON or null). [body] = JSON object text. */
    fun json(method: String, path: String, body: String? = null): Pair<Int, Any?> {
        val c = open(path, method)
        try {
            if (body != null) {
                c.doOutput = true
                val b = body.toByteArray(Charsets.UTF_8)
                c.setFixedLengthStreamingMode(b.size); c.setRequestProperty("Content-Type", "application/json")
                c.outputStream.use { it.write(b) }
            } else if (method == "POST") { c.doOutput = true; c.setFixedLengthStreamingMode(0); c.outputStream.close() }
            val code = c.responseCode
            val text = (if (code in 200..299) c.inputStream else c.errorStream)?.use { String(readAll(it, 8 shl 20), Charsets.UTF_8) } ?: ""
            return code to (try { Json.parse(text) } catch (_: Exception) { null })
        } finally { c.disconnect() }
    }

    /** one part of a multipart upload: either [data] (small, in memory) or a stream of known [length] */
    class Part(val field: String, val name: String?, val mime: String?, val length: Long, val data: ByteArray? = null, val open: (() -> InputStream)? = null)

    /** multipart/form-data POST (Ghab posts and stories). The total size is announced up front (Content-Length): Ghab's server refuses chunked request bodies. */
    fun multipart(path: String, fields: Map<String, String>, parts: List<Part>, progress: ((Long, Long) -> Unit)? = null): Pair<Int, Any?> {
        val c = open(path, "POST")
        val bnd = "----wd" + System.nanoTime()
        try {
            val heads = ArrayList<ByteArray>()
            for ((k, v) in fields) heads.add(("--$bnd\r\nContent-Disposition: form-data; name=\"$k\"\r\n\r\n$v\r\n").toByteArray(Charsets.UTF_8))
            val partHeads = parts.map { p ->
                val fn = (p.name ?: "").replace("\"", "_").replace("\r", "").replace("\n", "")
                ("--$bnd\r\nContent-Disposition: form-data; name=\"${p.field}\"" + (if (p.name != null) "; filename=\"$fn\"" else "") +
                    (if (p.mime != null) "\r\nContent-Type: ${p.mime}" else "") + "\r\n\r\n").toByteArray(Charsets.UTF_8)
            }
            val tail = "--$bnd--\r\n".toByteArray(Charsets.UTF_8)
            val crlf = "\r\n".toByteArray(Charsets.UTF_8)
            val total = heads.sumOf { it.size.toLong() } + parts.indices.sumOf { partHeads[it].size + parts[it].length + crlf.size } + tail.size
            val fileTotal = parts.sumOf { it.length }
            c.doOutput = true; c.readTimeout = 300000
            c.setFixedLengthStreamingMode(total)
            c.setRequestProperty("Content-Type", "multipart/form-data; boundary=$bnd")
            var done = 0L
            c.outputStream.use { os ->
                for (h in heads) os.write(h)
                val buf = ByteArray(64 * 1024)
                for ((i, p) in parts.withIndex()) {
                    os.write(partHeads[i])
                    if (p.data != null) { os.write(p.data); done += p.data.size; progress?.invoke(done, fileTotal) }
                    else p.open?.invoke()?.use { ins ->
                        while (true) { val n = ins.read(buf); if (n < 0) break; os.write(buf, 0, n); done += n; progress?.invoke(done, fileTotal) }
                    }
                    os.write(crlf)
                }
                os.write(tail)
            }
            val code = c.responseCode
            val text = (if (code in 200..299) c.inputStream else c.errorStream)?.use { String(readAll(it, 1 shl 20), Charsets.UTF_8) } ?: ""
            return code to (try { Json.parse(text) } catch (_: Exception) { null })
        } finally { c.disconnect() }
    }

    fun q(vararg kv: Pair<String, Any?>): String =
        kv.filter { it.second != null }.joinToString("&") { URLEncoder.encode(it.first, "UTF-8") + "=" + URLEncoder.encode(it.second.toString(), "UTF-8") }

    fun url(path: String): String = cfg.base + path

    private fun open(path: String, method: String): HttpURLConnection {
        if (cfg.tls && ctx == null) throw IOException("certificate not confirmed yet")
        val c = URL(url(path)).openConnection() as HttpURLConnection
        if (c is HttpsURLConnection) {
            c.sslSocketFactory = ctx!!.socketFactory
            c.hostnameVerifier = HostnameVerifier { _, _ -> true }      // identity = the pinned fingerprint
        }
        c.requestMethod = method
        cookie?.let { c.setRequestProperty("Cookie", it) }
        c.connectTimeout = 10000
        c.readTimeout = 30000
        c.instanceFollowRedirects = false
        return c
    }

    fun get(path: String, maxBytes: Int = 32 * 1024 * 1024): ByteArray {
        val c = open(path, "GET")
        try {
            if (c.responseCode != 200) throw IOException("HTTP " + c.responseCode)
            val len = c.contentLength
            if (len > maxBytes) throw IOException("too big")
            return c.inputStream.use { readAll(it, maxBytes) }
        } finally { c.disconnect() }
    }

    /** Streams the answer into [dest] (written to a temp name first, then renamed) and reports (done, total). */
    fun download(path: String, dest: File, progress: ((Long, Long) -> Unit)? = null, cancelled: () -> Boolean = { false }) {
        val tmp = File(dest.path + ".part")
        val c = open(path, "GET")
        try {
            if (c.responseCode != 200) throw IOException("HTTP " + c.responseCode)
            val total = c.contentLengthLong
            c.inputStream.use { ins ->
                FileOutputStream(tmp).use { os ->
                    val buf = ByteArray(64 * 1024)
                    var done = 0L
                    while (true) {
                        if (cancelled()) throw IOException("cancelled")
                        val n = ins.read(buf)
                        if (n < 0) break
                        os.write(buf, 0, n); done += n
                        progress?.invoke(done, total)
                    }
                    if (total >= 0 && done != total) throw IOException("incomplete download")
                }
            }
            if (!tmp.renameTo(dest)) throw IOException("cannot save")
        } catch (e: Exception) {
            tmp.delete(); throw e
        } finally { c.disconnect() }
    }

    /** POST a raw body (the file) to /upload?...; returns the parsed JSON answer. [length] must be exact. */
    fun upload(path: String, body: InputStream, length: Long, progress: ((Long, Long) -> Unit)? = null, cancelled: () -> Boolean = { false }, stallMs: Long = 0): Map<String, Any?> {
        val c = open(path, "POST")
        val tick = java.util.concurrent.atomic.AtomicLong(System.currentTimeMillis())
        val finished = java.util.concurrent.atomic.AtomicBoolean(false)
        if (stallMs > 0) Thread {            // a dead connection can block a write for minutes: cut it so the caller can wait for the net and continue
            while (!finished.get()) { try { Thread.sleep(1500) } catch (_: InterruptedException) {}; if (!finished.get() && System.currentTimeMillis() - tick.get() > stallMs) { try { c.disconnect() } catch (_: Exception) {}; break } }
        }.also { it.isDaemon = true }.start()
        try {
            c.doOutput = true
            c.readTimeout = 120000
            c.setFixedLengthStreamingMode(length)
            c.setRequestProperty("Content-Type", "application/octet-stream")
            c.outputStream.use { os ->
                val buf = ByteArray(64 * 1024)
                var sent = 0L
                while (true) {
                    if (cancelled()) throw IOException("cancelled")
                    val n = body.read(buf)
                    if (n < 0) break
                    os.write(buf, 0, n); sent += n; tick.set(System.currentTimeMillis())
                    progress?.invoke(sent, length)
                }
                if (sent != length) throw IOException("file changed while uploading")
            }
            tick.set(System.currentTimeMillis())
            val code = c.responseCode
            val stream = if (code in 200..299) c.inputStream else c.errorStream
            val text = stream?.use { String(readAll(it, 1 shl 20), Charsets.UTF_8) } ?: ""
            val j = Json.obj(text) ?: throw IOException("bad answer (HTTP $code)")
            if (!j.bool("ok")) throw ApiError(j.str("error", "ارسال ناموفق بود"), true)
            return j
        } finally { finished.set(true); c.disconnect() }
    }

    /**
     * Upload that survives a lost connection: the server keeps what it already got (rid), after a cut we wait
     * (up to [graceMs], default 5 minutes) for the internet to come back, ask how much arrived and send only the rest.
     * [state] is told "waiting" (true) / "sending" (false) so the UI can show "منتظر اینترنت…".
     */
    fun uploadResumable(path: String, open: () -> InputStream, length: Long, progress: ((Long, Long) -> Unit)? = null, cancelled: () -> Boolean = { false },
                        graceMs: Long = 300_000, state: ((Boolean) -> Unit)? = null): Map<String, Any?> {
        val rid = java.util.UUID.randomUUID().toString().replace("-", "")
        val sep = if (path.contains('?')) "&" else "?"
        var downSince = -1L
        var offset = 0L
        var attempt = 0
        while (true) {
            if (cancelled()) throw IOException("cancelled")
            try {
                if (attempt > 0) {
                    val st = Json.obj(String(get("/upload-status?" + path.substringAfter('?') + "&rid=" + rid, 4096), Charsets.UTF_8))
                    offset = (st?.get("have") as? Number)?.toLong() ?: 0L
                    if (offset > length) offset = 0L
                }
                attempt++
                state?.invoke(false)
                val base = offset
                open().use { ins ->
                    var skipped = 0L
                    while (skipped < base) { val k = ins.skip(base - skipped); if (k <= 0) throw IOException("file changed while uploading"); skipped += k }
                    return upload(path + sep + "rid=" + rid + "&offset=" + base + "&total=" + length, ins, length - base,
                        { d, _ -> downSince = -1L; progress?.invoke(base + d, length) }, cancelled, 25_000)
                }
            } catch (e: ApiError) {
                if (e.message == "resume mismatch" && attempt < 6) continue      // the server's count differs: ask again and send from there
                throw e
            } catch (e: IOException) {
                if (cancelled() || e.message == "cancelled" || e.message == "file changed while uploading") throw e
                val now = System.currentTimeMillis()
                if (downSince < 0) downSince = now
                if (now - downSince > graceMs) throw IOException("اینترنت بیشتر از ۵ دقیقه قطع بود؛ دوباره بفرست")
                state?.invoke(true)
                var w = 0
                while (w < 50) { if (cancelled()) throw IOException("cancelled"); try { Thread.sleep(100) } catch (_: InterruptedException) {}; w++ }   // 5 s between tries
            }
        }
    }

    private fun readAll(ins: InputStream, max: Int): ByteArray {
        val out = java.io.ByteArrayOutputStream()
        val buf = ByteArray(32 * 1024)
        while (true) {
            val n = ins.read(buf)
            if (n < 0) break
            out.write(buf, 0, n)
            if (out.size() > max) throw IOException("too big")
        }
        return out.toByteArray()
    }
}
