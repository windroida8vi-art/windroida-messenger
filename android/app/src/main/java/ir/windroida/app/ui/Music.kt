package ir.windroida.app.ui

import android.media.MediaDataSource
import ir.windroida.app.Trust
import java.io.File
import java.io.IOException
import java.io.RandomAccessFile
import java.net.HttpURLConnection
import java.net.URL
import java.util.BitSet
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.HttpsURLConnection

/** One song of the play queue. [id] is the id of the chat message that carries the file. */
class Track(val id: Long, val name: String, val title: String, val artist: String)

/** Where and how to fetch songs (kept by the player itself so notification buttons keep working after the screen is gone). */
class StreamCfg(val base: String, val pin: String, val key: String, val cacheDir: File, val saved: (Track) -> File,
                val fallback: (Track, (File?, String?) -> Unit) -> Unit = { _, cb -> cb(null, null) })

/**
 * Plays a song WHILE it downloads (no waiting for the whole file): the player reads it through HTTP Range requests of 256 KB,
 * the pinned certificate is used (the phone's own certificate store is never involved), and a background thread keeps
 * fetching the rest in order. Every chunk is written into a temp file; when the last one arrives the file is moved to the
 * normal cache, so the next play (and playing without internet) is instant. Seeking works anywhere: that chunk is fetched first.
 */
class RangeSource(private val track: Track, private val cfg: StreamCfg) : MediaDataSource() {
    private val url = cfg.base + "/media/" + track.id + "?k=" + java.net.URLEncoder.encode(cfg.key, "UTF-8")
    private val part = File(cfg.cacheDir, "stream_" + track.id + "_" + System.nanoTime() + ".part").also {
        cfg.cacheDir.mkdirs()                          // a unique name: closing an old stream of the same song can never delete the new one's file
        try { cfg.cacheDir.listFiles()?.forEach { f -> if (f.name.endsWith(".part") && System.currentTimeMillis() - f.lastModified() > 3600_000L) f.delete() } } catch (_: Exception) {}
    }
    private val dest = cfg.saved(track)
    private var total = -1L
    private var raf: RandomAccessFile? = null
    private val have = BitSet()
    private val lock = Object()
    @Volatile private var closed = false
    @Volatile private var want = 0
    private var finished = false
    private var ahead: Thread? = null
    private val ssl by lazy { Trust.pinnedContext(cfg.pin).socketFactory }

    private fun open(range: String): HttpURLConnection {
        val c = URL(url).openConnection() as HttpURLConnection
        if (c is HttpsURLConnection) {
            if (cfg.pin.isEmpty()) throw IOException("certificate not confirmed")
            c.sslSocketFactory = ssl
            c.hostnameVerifier = HostnameVerifier { _, _ -> true }      // identity = the pinned fingerprint
        }
        c.connectTimeout = 10000; c.readTimeout = 20000
        c.setRequestProperty("Range", range)
        return c
    }

    private fun chunks(): Int = ((total + CHUNK - 1) / CHUNK).toInt()

    @Synchronized
    override fun getSize(): Long {
        if (total >= 0) return total
        val c = open("bytes=0-0")
        try {
            val code = c.responseCode
            if (code == 206) {
                val cr = c.getHeaderField("Content-Range") ?: ""          // bytes 0-0/12345
                total = cr.substringAfter('/').trim().toLongOrNull() ?: throw IOException("no size")
            } else if (code == 200) total = c.contentLengthLong
            else throw IOException("HTTP $code")
        } finally { c.disconnect() }
        if (total <= 0) throw IOException("empty")
        raf = RandomAccessFile(part, "rw").also { it.setLength(total) }
        ahead = Thread { prefetch() }.also { it.isDaemon = true; it.start() }
        return total
    }

    private val fetching = HashSet<Int>()

    /**
     * make sure chunk [i] is in the temp file. The download runs OUTSIDE the lock, so the player reading the part it needs is never
     * stuck behind the background prefetch of some other part; if both want the same chunk, one downloads and the other waits for it.
     */
    private fun ensure(i: Int) {
        while (true) {
            var mine = false
            synchronized(lock) {
                if (have.get(i)) return
                if (closed) throw IOException("closed")
                if (fetching.add(i)) mine = true else lock.wait(250)
            }
            if (!mine) continue
            try {
                val start = i.toLong() * CHUNK
                val end = minOf(total, start + CHUNK) - 1
                val c = open("bytes=$start-$end")
                val code = c.responseCode
                if (code != 206 && !(code == 200 && start == 0L)) { c.disconnect(); throw IOException("HTTP $code") }
                val buf = ByteArray((end - start + 1).toInt())
                var got = 0
                c.inputStream.use { st -> while (got < buf.size) { val n = st.read(buf, got, buf.size - got); if (n < 0) break; got += n } }
                if (got != buf.size) { c.disconnect(); throw IOException("short chunk") }     // (a fully read answer is NOT disconnected: the connection is reused for the next chunk)
                synchronized(lock) {
                    if (closed) throw IOException("closed")
                    val r = raf ?: throw IOException("closed")
                    r.seek(start); r.write(buf)
                    have.set(i)
                }
            } finally {
                synchronized(lock) { fetching.remove(i); lock.notifyAll() }
            }
            return
        }
    }

    override fun readAt(position: Long, buffer: ByteArray, offset: Int, size: Int): Int {
        if (size == 0) return 0
        if (position >= total) return -1
        var pos = position
        var out = 0
        val end = minOf(total, position + size)
        while (pos < end && !closed) {
            val i = (pos / CHUNK).toInt()
            want = i
            ensure(i)
            val inChunk = minOf(end, (i + 1L) * CHUNK) - pos
            synchronized(lock) {
                val r = raf ?: throw IOException("closed")
                r.seek(pos); r.readFully(buffer, offset + out, inChunk.toInt())
            }
            out += inChunk.toInt(); pos += inChunk
        }
        return if (out == 0) -1 else out
    }

    /** keeps fetching what comes after the part being played (and, later, what was skipped) until the whole file is here */
    private fun prefetch() {
        try {
            var fails = 0
            while (!closed) {
                var next = -1
                synchronized(lock) {
                    val n = chunks()
                    var i = want
                    while (i < n && have.get(i)) i++
                    if (i >= n) { i = 0; while (i < n && have.get(i)) i++ }
                    if (i < n) next = i
                }
                if (next < 0) { complete(); return }
                try { ensure(next); fails = 0 } catch (e: IOException) {
                    if (closed || ++fails > 6) return
                    try { Thread.sleep(1500L * fails) } catch (_: InterruptedException) { return }
                }
            }
        } catch (_: Exception) {}
    }

    private fun complete() {
        synchronized(lock) {
            if (finished || closed) return
            finished = true
            try { raf?.fd?.sync() } catch (_: Exception) {}
            try { raf?.close() } catch (_: Exception) {}
            raf = null
            try { dest.parentFile?.mkdirs(); if (!part.renameTo(dest)) part.copyTo(dest, true).also { part.delete() } } catch (_: Exception) {}
            // the player goes on reading from the moved file
            try { raf = RandomAccessFile(if (dest.isFile) dest else part, "r") } catch (_: Exception) {}
        }
    }

    override fun close() {
        closed = true
        ahead?.interrupt()
        Thread {                                     // never blocks the caller: an in-flight chunk may still hold the lock for a moment
            synchronized(lock) {
                try { raf?.close() } catch (_: Exception) {}
                raf = null
                if (!finished) part.delete()          // an unfinished download is never kept
            }
        }.also { it.isDaemon = true }.start()
    }

    // small pieces: the first sound starts after ~128 KB, a seek only waits for its own piece
    companion object { const val CHUNK = 128 * 1024 }
}
