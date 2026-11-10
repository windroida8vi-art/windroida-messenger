package ir.windroida.app

import android.content.Context
import android.webkit.CookieManager
import android.webkit.WebResourceResponse
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.io.FilterInputStream
import java.io.IOException
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.HttpsURLConnection

/**
 * Instagram-style disk cache for the web Ghab screen (SiteActivity), so it opens and plays WITHOUT internet:
 *  - photos / videos (/media/…): cache-first. A video that is played is saved while it streams (nothing is downloaded twice);
 *    next time (and offline) it plays from the phone, with seeking. Everything media together stays under the limit (400 MB by default, changeable in Settings → Storage), the least recently used go first.
 *  - the page itself and the JSON of the feed / stories / profiles: network-first, the last good answer is kept and shown when there is no internet.
 * Only GET requests to the site's own origin are touched; the one-time /sso sign-in and everything else go the normal way.
 */
class WebCache(private val ctx: Context, private val origin: String) {
    private val dir = File(ctx.filesDir, "web-cache").also { it.mkdirs() }
    private val cap = capBytes(ctx)

    init { cleanup(dir) }

    private fun key(url: String): String = java.security.MessageDigest.getInstance("SHA-1").digest(url.toByteArray()).joinToString("") { "%02x".format(it) }
    private fun body(k: String) = File(dir, "$k.bin")
    private fun meta(k: String) = File(dir, "$k.meta")

    private fun isMedia(path: String) = path.startsWith("/media/") || path.startsWith("/thumb/") || path.startsWith("/avatar/")

    /** null = let the WebView handle the request itself */
    fun handle(url: String, method: String, reqHeaders: Map<String, String>): WebResourceResponse? {
        if (method != "GET" || !url.startsWith(origin)) return null
        val path = try { URL(url).path ?: "/" } catch (_: Exception) { return null }
        if (path.startsWith("/sso") || path.startsWith("/logout") || path.startsWith("/api/reels/watch")) return null
        val media = isMedia(path)
        val k = key(url)
        val range = reqHeaders.entries.firstOrNull { it.key.equals("Range", true) }?.value
        if (media) {
            cached(k, range)?.let { return it }
            return fetch(url, k, range, reqHeaders, true) ?: null
        }
        // page / api: network first, offline falls back to the last answer
        val live = try { fetch(url, k, null, reqHeaders, false) } catch (_: Exception) { null }
        return live ?: cached(k, null)
    }

    /** serve a saved file (with Range support so the video can seek) */
    private fun cached(k: String, range: String?): WebResourceResponse? {
        val b = body(k); val m = meta(k)
        if (!b.isFile || !m.isFile) return null
        val mime = try { m.readText().trim() } catch (_: Exception) { return null }
        val total = b.length()
        if (total <= 0) return null
        b.setLastModified(System.currentTimeMillis())
        var start = 0L; var end = total - 1
        var partial = false
        if (range != null) {
            val mm = Regex("bytes=(\\d*)-(\\d*)").find(range)
            if (mm != null) {
                val a = mm.groupValues[1]; val z = mm.groupValues[2]
                if (a.isEmpty() && z.isNotEmpty()) { start = (total - z.toLong()).coerceAtLeast(0); partial = true }
                else if (a.isNotEmpty()) { start = a.toLong(); if (z.isNotEmpty()) end = minOf(z.toLong(), total - 1); partial = true }
                if (start >= total) return resp(416, "Range Not Satisfiable", mime, emptyMap<String, String>() + ("Content-Range" to "bytes */$total"), java.io.ByteArrayInputStream(ByteArray(0)))
            }
        }
        val ins = FileInputStream(b); var sk = 0L
        while (sk < start) { val n = ins.skip(start - sk); if (n <= 0) break; sk += n }
        val len = end - start + 1
        val h = HashMap<String, String>()
        h["Accept-Ranges"] = "bytes"; h["Content-Length"] = len.toString()
        if (partial) h["Content-Range"] = "bytes $start-$end/$total"
        return resp(if (partial) 206 else 200, if (partial) "Partial Content" else "OK", mime, h, Limited(ins, len))
    }

    private fun resp(code: Int, reason: String, mime: String, headers: Map<String, String>, ins: InputStream): WebResourceResponse {
        val ct = mime.substringBefore(';').trim().ifEmpty { "application/octet-stream" }
        val cs = if (mime.contains("charset=")) mime.substringAfter("charset=").trim() else null
        return WebResourceResponse(ct, cs, code, reason, headers, ins)
    }

    private class Limited(ins: InputStream, private var left: Long) : FilterInputStream(ins) {
        override fun read(): Int { if (left <= 0) return -1; val r = super.read(); if (r >= 0) left--; return r }
        override fun read(b: ByteArray, off: Int, len: Int): Int { if (left <= 0) return -1; val r = super.read(b, off, minOf(len.toLong(), left).toInt()); if (r > 0) left -= r; return r }
    }

    /** asks the server (pinned certificate + the page's login cookie); saves complete answers; hands back what the WebView asked for */
    private fun fetch(url: String, k: String, range: String?, req: Map<String, String>, media: Boolean): WebResourceResponse? {
        val c = URL(url).openConnection() as HttpURLConnection
        if (c is HttpsURLConnection) {
            c.sslSocketFactory = Trust.pinnedContext(Prefs.pin(ctx)).socketFactory
            c.hostnameVerifier = HostnameVerifier { _, _ -> true }          // identity = the pinned fingerprint
        }
        c.instanceFollowRedirects = false
        c.connectTimeout = 8000; c.readTimeout = 30000
        CookieManager.getInstance().getCookie(url)?.let { c.setRequestProperty("Cookie", it) }
        for ((n, v) in req) if (n.equals("Accept", true) || n.equals("Accept-Language", true) || n.equals("User-Agent", true)) c.setRequestProperty(n, v)
        if (range != null) c.setRequestProperty("Range", range)
        val code = c.responseCode
        c.headerFields?.get("Set-Cookie")?.forEach { CookieManager.getInstance().setCookie(url, it) }
        val mime = c.contentType ?: "application/octet-stream"
        val h = HashMap<String, String>()
        for ((n, v) in c.headerFields ?: emptyMap()) if (n != null && v != null && v.isNotEmpty() && !n.equals("Set-Cookie", true) && !n.equals("Transfer-Encoding", true) && !n.equals("Content-Type", true)) h[n] = v.last()
        val reason = c.responseMessage ?: ""
        val stream: InputStream = (if (code >= 400) c.errorStream else c.inputStream) ?: java.io.ByteArrayInputStream(ByteArray(0))
        val total = c.contentLengthLong
        // what may be saved: a complete answer (200, or a 206 that starts at 0 and reaches the end)
        var saveTotal = -1L
        if (code == 200 && total > 0) saveTotal = total
        else if (code == 206) {
            val cr = c.getHeaderField("Content-Range") ?: ""                       // bytes 0-999/5000
            val m = Regex("bytes (\\d+)-(\\d+)/(\\d+)").find(cr)
            if (m != null && m.groupValues[1] == "0" && m.groupValues[2].toLong() + 1 == m.groupValues[3].toLong()) saveTotal = m.groupValues[3].toLong()
        }
        val limit = if (media) cap else 4L * 1024 * 1024
        if (saveTotal in 1..limit && (code == 200 || code == 206) && claim(k)) {
            val part = File(dir, k + "." + System.nanoTime() + ".part")
            val out = try { FileOutputStream(part) } catch (_: Exception) { release(k); return resp(code, reason, mime, h, stream) }
            return resp(code, reason, mime, h, Tee(stream, out, part, saveTotal, k, mime, c))
        }
        if (!media && code == 200 && total <= 0) {          // gzip / chunked page or JSON: no length known, so read it (max 4 MB) and keep it for offline
            val bo = java.io.ByteArrayOutputStream(); val buf = ByteArray(32 * 1024); var big = false
            stream.use { ins -> while (true) { val n = ins.read(buf); if (n < 0) break; bo.write(buf, 0, n); if (bo.size() > 4 * 1024 * 1024) { big = true; break } } }
            if (big) return null
            val bytes = bo.toByteArray()
            try { body(k).writeBytes(bytes); meta(k).writeText(mime) } catch (_: Exception) {}
            h.remove("Content-Length"); h.remove("Content-Encoding")
            return resp(code, reason, mime, h, java.io.ByteArrayInputStream(bytes))
        }
        return resp(code, reason, mime, h, stream)
    }

    // shared by every WebCache instance (Ghab + Drive screens): one download per file at a time; a claim older than 5 min is stale (the page never closed its stream)
    private fun claim(k: String): Boolean = synchronized(LOCK) {
        val t = inflight[k]
        if (t != null && System.currentTimeMillis() - t < 300_000) false else { inflight[k] = System.currentTimeMillis(); true }
    }
    private fun release(k: String) { synchronized(LOCK) { inflight.remove(k) } }

    /** passes bytes to the WebView and into a temp file; if the whole thing arrived, it becomes the saved copy */
    private inner class Tee(ins: InputStream, private val out: FileOutputStream, private val part: File, private val total: Long, private val k: String, private val mime: String, private val c: HttpURLConnection) : FilterInputStream(ins) {
        private var got = 0L; private var done = false; private var broken = false
        private fun w(b: ByteArray, off: Int, n: Int) { if (!broken) try { out.write(b, off, n) } catch (_: IOException) { broken = true } }
        override fun read(): Int { val r = super.read(); if (r >= 0) { got++; w(byteArrayOf(r.toByte()), 0, 1) } else finish(); return r }
        override fun read(b: ByteArray, off: Int, len: Int): Int { val r = try { super.read(b, off, len) } catch (e: IOException) { finish(); throw e }; if (r > 0) { got += r; w(b, off, r) } else if (r < 0) finish(); return r }
        private fun finish() {
            if (done) return; done = true
            try { out.close() } catch (_: Exception) {}
            var ok = !broken && got == total
            if (ok) {
                try {
                    val b = body(k)
                    if (!part.renameTo(b)) { part.copyTo(b, true); part.delete() }
                    meta(k).writeText(mime)
                    trim(b)
                } catch (_: Exception) { ok = false }
            }
            if (!ok) part.delete()
            release(k)
        }
        override fun close() { try { super.close() } finally { finish(); try { c.disconnect() } catch (_: Exception) {} } }
    }

    /** everything over the limit: the least recently watched copies are removed (never the one just saved). Half-written parts count too. */
    private fun trim(keep: File) = synchronized(LOCK) {
        val all = dir.listFiles() ?: return@synchronized
        val bins = all.filter { it.name.endsWith(".bin") }
        var total = all.filter { it.name.endsWith(".bin") || it.name.endsWith(".part") }.sumOf { it.length() }
        if (total <= cap) return@synchronized
        for (f in bins.sortedBy { it.lastModified() }) {
            if (total <= cap * 9 / 10) break
            if (f == keep) continue
            total -= f.length(); f.delete(); File(f.path.removeSuffix(".bin") + ".meta").delete()
        }
    }

    companion object {
        const val DEFAULT_MB = 400
        private val LOCK = Any()
        private val inflight = HashMap<String, Long>()
        private var cleaned = false

        fun capBytes(ctx: Context): Long = ctx.getSharedPreferences("wd", Context.MODE_PRIVATE).getInt("webcache_mb", DEFAULT_MB).coerceIn(50, 8192) * 1024L * 1024L
        fun setLimitMb(ctx: Context, mb: Int) { ctx.getSharedPreferences("wd", Context.MODE_PRIVATE).edit().putInt("webcache_mb", mb).apply() }
        fun limitMb(ctx: Context): Int = (capBytes(ctx) / (1024 * 1024)).toInt()

        private fun dirOf(ctx: Context) = File(ctx.filesDir, "web-cache").also { it.mkdirs() }

        /** (bytes, files) of the saved copies (photos, videos, pages) */
        fun stats(ctx: Context): Pair<Long, Int> {
            val bins = dirOf(ctx).listFiles()?.filter { it.name.endsWith(".bin") } ?: return 0L to 0
            return bins.sumOf { it.length() } to bins.size
        }

        /** removes every saved copy (and leftovers) */
        fun clear(ctx: Context) { synchronized(LOCK) { dirOf(ctx).listFiles()?.forEach { it.delete() }; inflight.clear() } }

        /** leftovers: half-written .part files from a killed app are removed once per start (and ones older than 10 min always); a lowered limit is applied */
        private fun cleanup(dir: File) {
            synchronized(LOCK) {
                val now = System.currentTimeMillis()
                dir.listFiles()?.forEach { f ->
                    if (f.name.endsWith(".part") && (!cleaned || now - f.lastModified() > 600_000)) f.delete()
                    if (f.name.endsWith(".meta") && !File(f.path.removeSuffix(".meta") + ".bin").isFile) f.delete()     // orphan description
                    if (f.name.endsWith(".bin") && !File(f.path.removeSuffix(".bin") + ".meta").isFile) f.delete()      // orphan body (never served)
                }
                cleaned = true
            }
        }
    }
}
