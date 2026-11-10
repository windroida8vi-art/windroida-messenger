package ir.windroida.app.ui

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.webkit.MimeTypeMap
import ir.windroida.app.net.Http
import java.io.File
import java.util.concurrent.Executors

/**
 * Downloaded chat files (images/videos/voice/documents): kept in [filesDir], like Telegram's own "downloaded media" —
 * not [cacheDir], which Android can purge on its own the moment storage runs low, silently losing files the user
 * never asked to delete. A size cap (see [trim], set from Settings) is how the user controls growth instead.
 */
class Downloads(private val ctx: Context, private val http: () -> Http?, private val key: () -> String) {
    private val main = Handler(Looper.getMainLooper())
    private val pool = Executors.newFixedThreadPool(2)
    private val active = HashMap<Long, Boolean>()          // message id -> cancelled flag (true = cancel)
    private val dir = File(ctx.filesDir, "media").also { it.mkdirs(); migrateFromCache(ctx, it) }

    fun cached(id: Long, name: String): File = File(dir, id.toString() + "_" + safe(name))

    private fun safe(n: String): String = n.replace(Regex("[^A-Za-z0-9._\\-\\u0600-\\u06FF]"), "_").takeLast(80).ifEmpty { "file" }

    fun isBusy(id: Long) = active.containsKey(id)

    fun cancel(id: Long) { if (active.containsKey(id)) active[id] = true }

    /** Brings the file of message [id] into the persistent downloads folder (does nothing if it is already there). Callbacks on the UI thread. */
    fun fetch(id: Long, name: String, progress: (Long, Long) -> Unit, done: (File?, String?) -> Unit) {
        val f = cached(id, name)
        if (f.isFile && f.length() > 0) { f.setLastModified(System.currentTimeMillis()); done(f, null); return }
        val h = http() ?: run { done(null, "به سرور وصل نیستی"); return }
        active[id] = false
        pool.execute {
            var err: String? = null
            try {
                h.download("/media/$id?k=" + java.net.URLEncoder.encode(key(), "UTF-8"), f, { d, t -> main.post { progress(d, t) } }, { active[id] == true })
            } catch (e: Exception) { err = if (active[id] == true) "لغو شد" else (e.message ?: "دانلود ناموفق بود") }
            main.post { active.remove(id); done(if (err == null) f else null, err); if (err == null) pool.execute { trim() } }
        }
    }

    /** Total size + file count of everything downloaded so far (Settings' storage screen). */
    fun stats(): Pair<Long, Int> { val fs = dir.listFiles() ?: return 0L to 0; return fs.sumOf { it.length() } to fs.size }

    /** Deletes the oldest-touched files (by last access, bumped on every re-open) until under the saved limit, 0 = unlimited. */
    private fun trim() {
        val limit = ir.windroida.app.Prefs.downloadLimitMb(ctx).toLong() * 1024 * 1024
        if (limit <= 0) return
        val fs = (dir.listFiles() ?: return).sortedBy { it.lastModified() }
        var total = fs.sumOf { it.length() }
        for (f in fs) { if (total <= limit) break; total -= f.length(); f.delete() }
    }

    /** Copies a cached file into the phone's public Downloads folder (no storage permission needed on Android 10+). */
    fun saveToDownloads(f: File, displayName: String): Uri? {
        return try {
            val mime = mimeOf(displayName)
            val v = ContentValues()
            v.put(MediaStore.Downloads.DISPLAY_NAME, displayName)
            v.put(MediaStore.Downloads.MIME_TYPE, mime)
            v.put(MediaStore.Downloads.RELATIVE_PATH, "Download/Windroida")
            val uri = ctx.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v) ?: return null
            ctx.contentResolver.openOutputStream(uri)?.use { os -> f.inputStream().use { it.copyTo(os) } }
            uri
        } catch (e: Exception) { null }
    }

    fun mimeOf(name: String): String {
        val ext = name.substringAfterLast('.', "").lowercase()
        return MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext) ?: "application/octet-stream"
    }

    fun open(uri: Uri, name: String): Boolean = try {
        val i = Intent(Intent.ACTION_VIEW).setDataAndType(uri, mimeOf(name)).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        ctx.startActivity(i); true
    } catch (e: Exception) { false }

    fun clearCache() { dir.listFiles()?.forEach { it.delete() } }
}

/** One-time move of files from an old cacheDir-based location into the new, persistent [to] folder (an earlier build kept
 * downloads in the cache, where Android could silently wipe them; this recovers whatever is still there on first run after
 * updating). Safe to call every launch: it's a no-op once the old folder is gone or empty. */
internal fun migrateFromCache(ctx: Context, to: File, sub: String = "media") {
    try {
        val old = File(ctx.cacheDir, sub)
        val fs = old.listFiles() ?: return
        for (f in fs) { val dst = File(to, f.name); if (!dst.exists()) f.renameTo(dst) else f.delete() }
        old.delete()
    } catch (_: Exception) {}
}

/** One voice message plays at a time; progress is reported to whoever started it. */
/**
 * The one audio player of the app (process-wide, so music keeps playing when the screen is closed and the notification / lock-screen
 * buttons can control it). Voice messages play from a file; songs are streamed (see RangeSource) and live in a queue.
 */
class VoicePlayer(private val main: Handler) {
    companion object {
        @Volatile private var inst: VoicePlayer? = null
        fun shared(main: Handler): VoicePlayer = inst ?: synchronized(this) { inst ?: VoicePlayer(main).also { inst = it } }
        fun peek(): VoicePlayer? = inst
        const val REPEAT_OFF = 0; const val REPEAT_ALL = 1; const val REPEAT_ONE = 2
    }
    private var mp: MediaPlayer? = null
    private var source: RangeSource? = null
    private var gen = 0                         // bumps on every start/stop: late callbacks of an old track are ignored
    var playingId = 0L
        private set
    var title = ""                 // shown in the mini player (name of the song / "voice message")
    var subtitle = ""
    var queue: List<Track> = emptyList(); private set
    var qIndex = -1; private set
    var repeat = REPEAT_OFF
    var shuffle = false
    var loading = false; private set
    /** where the next song should start (0..1); set by a scrub on a song that is not playing yet */
    var startFrac = 0f
    private var cfg: StreamCfg? = null
    val isPlaying: Boolean get() = try { mp?.isPlaying == true } catch (_: Exception) { false }
    val durationMs: Int get() = try { if (mp != null && !loading) mp!!.duration else 0 } catch (_: Exception) { 0 }
    val positionMs: Int get() = try { if (mp != null && !loading) mp!!.currentPosition else 0 } catch (_: Exception) { 0 }
    private val stateListeners = ArrayList<() -> Unit>()
    fun addStateListener(l: () -> Unit) { if (!stateListeners.contains(l)) stateListeners.add(l) }
    fun removeStateListener(l: () -> Unit) { stateListeners.remove(l) }
    private fun changed() { for (l in ArrayList(stateListeners)) try { l() } catch (_: Exception) {} }
    private fun frac(p: MediaPlayer) = p.currentPosition.toFloat() / Math.max(1, p.duration)

    /** pause / resume the current one (mini player button, notification, lock screen) */
    fun toggleCurrent() {
        val p = mp ?: return
        if (loading) return
        try {
            if (p.isPlaying) { p.pause(); listener?.invoke(playingId, frac(p), false) }
            else { p.start(); main.post(ticker); listener?.invoke(playingId, frac(p), true) }
        } catch (_: Exception) {}
        changed()
    }

    fun seek(frac: Float) {
        val p = mp ?: return
        if (loading) return
        try { p.seekTo((p.duration * frac.coerceIn(0f, 1f)).toInt()); listener?.invoke(playingId, frac.coerceIn(0f, 1f), p.isPlaying) } catch (_: Exception) {}
        changed()
    }
    fun seekMs(ms: Long) { val p = mp ?: return; if (!loading) { try { p.seekTo(ms.toInt().coerceIn(0, Math.max(0, p.duration))) } catch (_: Exception) {}; changed() } }
    private var listener: ((Long, Float, Boolean) -> Unit)? = null     // (message id, 0..1, playing)
    private val ticker = object : Runnable {
        override fun run() {
            val p = mp ?: return
            try { if (p.isPlaying) { listener?.invoke(playingId, frac(p), true); main.postDelayed(this, 100) } } catch (_: Exception) {}
        }
    }

    fun onProgress(l: (Long, Float, Boolean) -> Unit) { listener = l }

    /** a voice message / an already downloaded file: plays it, or pauses / resumes if it is the current one */
    fun toggle(id: Long, file: File) {
        if (playingId == id && mp != null && !loading) { toggleCurrent(); return }
        stop()                                   // (tells the old bubble it stopped)
        queue = emptyList(); qIndex = -1
        val g = ++gen
        try {
            val p = MediaPlayer()
            p.setDataSource(file.absolutePath)
            p.setOnCompletionListener { if (g == gen) { val old = playingId; stop(); listener?.invoke(old, 0f, false) } }
            p.setOnErrorListener { _, _, _ -> if (g == gen) { val old = playingId; stop(); listener?.invoke(old, 0f, false) }; true }
            p.prepare(); p.start()
            mp = p; playingId = id
            listener?.invoke(id, 0f, true)
            main.post(ticker)
            changed()
        } catch (e: Exception) { stop() }
    }

    // ------------------------------------------------------------------ songs: queue + streaming
    /** plays [tracks] starting at [index]; the first bytes are heard after the first 256 KB arrive, not after the whole file */
    fun playQueue(tracks: List<Track>, index: Int, c: StreamCfg) {
        if (tracks.isEmpty() || index !in tracks.indices) return
        cfg = c; queue = tracks
        start(index)
    }

    /** the full list of the chat's songs arrived from the server: swap it in WITHOUT restarting the song that is playing (next / previous then follow the real order) */
    fun replaceQueue(tracks: List<Track>) {
        val cur = playingId
        val i = tracks.indexOfFirst { it.id == cur }
        if (i < 0 || tracks.isEmpty()) return
        queue = tracks; qIndex = i
        changed()
    }

    fun playAt(index: Int) { if (index in queue.indices) start(index) }

    /** called (on the UI thread) when a song could not be played at all; the text is shown to the user */
    var onFailure: ((String) -> Unit)? = null
    private val prepTimeout = Runnable { fallback() }
    private var fallbackIndex = -1

    private fun start(index: Int, file: File? = null) {
        val c = cfg ?: return
        val t = queue[index]
        releaseEngine()
        qIndex = index
        val prev = playingId
        if (prev != 0L && prev != t.id) listener?.invoke(prev, 0f, false)      // the row of the song that was playing shows "play" again
        playingId = t.id; title = t.title; subtitle = t.artist
        loading = true
        val g = ++gen
        try {
            val p = MediaPlayer()
            try { p.setAudioAttributes(android.media.AudioAttributes.Builder().setUsage(android.media.AudioAttributes.USAGE_MEDIA).setContentType(android.media.AudioAttributes.CONTENT_TYPE_MUSIC).build()) } catch (_: Exception) {}
            val saved = file ?: c.saved(t)
            if (saved.isFile && saved.length() > 0) p.setDataSource(saved.absolutePath)
            else { val rs = RangeSource(t, c); source = rs; p.setDataSource(rs) }
            p.setOnPreparedListener {
                if (g != gen) return@setOnPreparedListener
                main.removeCallbacks(prepTimeout)
                loading = false
                val sf = startFrac; startFrac = 0f
                if (sf > 0.01f) try { it.seekTo((it.duration * sf.coerceAtMost(0.99f)).toInt()) } catch (_: Exception) {}
                try { it.start() } catch (_: Exception) {}
                listener?.invoke(playingId, sf, true); main.post(ticker); changed()
            }
            p.setOnCompletionListener { if (g == gen) onEnded() }
            p.setOnErrorListener { _, _, _ ->
                if (g == gen) main.post { if (g == gen) fallback() }
                true
            }
            mp = p
            fallbackIndex = if (file != null) index else -1
            if (file == null) main.postDelayed(prepTimeout, 15000)
            p.prepareAsync()
        } catch (e: Exception) { main.post { if (g == gen) fallback() } }
        listener?.invoke(playingId, 0f, false)
        changed()
    }

    /** streaming did not work (error or too slow): download the whole song and play the file; if that fails too, say why */
    private fun fallback() {
        main.removeCallbacks(prepTimeout)
        val c = cfg ?: return
        if (qIndex !in queue.indices) return
        val idx = qIndex
        val t = queue[idx]
        if (fallbackIndex == idx) { giveUp("آهنگ پخش نشد (فایل خراب یا ناشناخته است)", idx); return }   // the file itself failed
        val g = ++gen
        releaseEngine(); loading = true; changed()
        c.fallback(t) { f, err ->
            if (g != gen) return@fallback
            if (f != null) start(idx, f) else giveUp(err ?: "آهنگ دانلود نشد", idx)
        }
    }

    private fun giveUp(msg: String, failed: Int) {
        loading = false
        onFailure?.invoke(msg)
        if (queue.size > 1 && failed + 1 < queue.size) start(failed + 1) else { val old = playingId; stop(); listener?.invoke(old, 0f, false) }
    }

    private fun onEnded() {
        if (repeat == REPEAT_ONE) { start(qIndex); return }
        val n = nextIndex()
        if (n >= 0) start(n) else { val old = playingId; stop(); listener?.invoke(old, 0f, false) }
    }

    private fun nextIndex(): Int {
        if (queue.isEmpty()) return -1
        if (shuffle && queue.size > 1) { var r: Int; do { r = (Math.random() * queue.size).toInt() } while (r == qIndex); return r }
        val n = qIndex + 1
        return if (n < queue.size) n else if (repeat == REPEAT_ALL) 0 else -1
    }

    fun next() { if (queue.isEmpty()) return; val n = nextIndex().let { if (it < 0 && queue.size > 1) 0 else it }; if (n >= 0) start(n) }
    fun prev() {
        if (queue.isEmpty()) return
        if (positionMs > 3000) { seekMs(0); return }
        start(if (qIndex > 0) qIndex - 1 else queue.size - 1)
    }
    fun cycleRepeat() { repeat = (repeat + 1) % 3; changed() }
    fun toggleShuffle() { shuffle = !shuffle; changed() }

    private fun releaseEngine() {
        main.removeCallbacks(ticker); main.removeCallbacks(prepTimeout)
        try { mp?.release() } catch (_: Exception) {}
        mp = null
        try { source?.close() } catch (_: Exception) {}
        source = null
    }

    fun stop() {
        gen++
        releaseEngine()
        val old = playingId
        playingId = 0L; loading = false
        if (old != 0L) listener?.invoke(old, 0f, false)
        queue = emptyList(); qIndex = -1
        changed()
    }
}

/** Records a voice message as AAC (m4a), mono, 24 kbps: small enough for a slow upload link. */
class VoiceRecorder(private val ctx: Context) {
    private var rec: MediaRecorder? = null
    private var file: File? = null
    private var t0 = 0L
    private val levels = ArrayList<Int>()
    val running: Boolean get() = rec != null

    fun start(): Boolean {
        stopQuiet()
        return try {
            val f = File(ctx.cacheDir, "rec_" + System.currentTimeMillis() + ".m4a")
            val r = if (Build.VERSION.SDK_INT >= 31) MediaRecorder(ctx) else @Suppress("DEPRECATION") MediaRecorder()
            r.setAudioSource(MediaRecorder.AudioSource.MIC)
            r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            r.setAudioChannels(1); r.setAudioSamplingRate(24000); r.setAudioEncodingBitRate(24000)
            r.setOutputFile(f.absolutePath)
            r.prepare(); r.start()
            rec = r; file = f; t0 = System.currentTimeMillis(); levels.clear()
            true
        } catch (e: Exception) { stopQuiet(); false }
    }

    /** call about every 100 ms while recording; returns the current level 0..31 */
    fun sample(): Int {
        val r = rec ?: return 0
        val a = try { r.maxAmplitude } catch (_: Exception) { 0 }
        val lv = Math.min(31, Math.round(Math.sqrt(a / 32767.0) * 31).toInt())
        levels.add(lv)
        return lv
    }

    fun seconds(): Double = (System.currentTimeMillis() - t0) / 1000.0

    class Result(val file: File, val dur: Double, val wave: List<Int>)

    /** Stops and returns the recording; null when it was cancelled, failed or shorter than a second. */
    fun finish(cancel: Boolean): Result? {
        val r = rec ?: return null
        val f = file
        val dur = seconds()
        rec = null; file = null
        try { r.stop() } catch (_: Exception) { try { r.release() } catch (_: Exception) {}; f?.delete(); return null }
        try { r.release() } catch (_: Exception) {}
        if (cancel || f == null || dur < 1.0 || !f.isFile || f.length() < 200) { f?.delete(); return null }
        val n = 40
        val wave = ArrayList<Int>()
        for (i in 0 until n) {
            val a = i * levels.size / n; val b = Math.max(a + 1, (i + 1) * levels.size / n)
            var mx = 0
            for (j in a until b) if (j < levels.size) mx = Math.max(mx, levels[j])
            wave.add(mx)
        }
        return Result(f, Math.round(dur * 10) / 10.0, wave)
    }

    private fun stopQuiet() { try { rec?.stop() } catch (_: Exception) {}; try { rec?.release() } catch (_: Exception) {}; rec = null; file?.delete(); file = null }
    fun release() = stopQuiet()
}
