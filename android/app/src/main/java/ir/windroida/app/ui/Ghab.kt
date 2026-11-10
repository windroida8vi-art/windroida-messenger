package ir.windroida.app.ui

import android.app.AlertDialog
import android.content.Intent
import android.graphics.Outline
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.view.ViewOutlineProvider
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import ir.windroida.app.NativeActivity
import ir.windroida.app.PlayerActivity
import ir.windroida.app.net.Http
import ir.windroida.app.net.ServerCfg
import ir.windroida.app.net.bool
import ir.windroida.app.net.lng
import ir.windroida.app.net.str
import java.io.File
import java.net.URLEncoder

/**
 * Ghab (قاب) inside the native app: one-time sign-in link from the messenger (same as the web), then the same JSON API as the web page.
 * Feed, stories, explore, reels, profiles, posts with likes / saves / comments, new posts and stories. Pictures are cached on the phone.
 */
class GhabClient(private val a: NativeActivity) {
    @Volatile var http: Http? = null
    @Volatile var img: Img? = null
    @Volatile var me: Map<String, Any?>? = null
    private var busy = false
    private val waiters = ArrayList<(Boolean) -> Unit>()

    private fun finish(ok: Boolean) { busy = false; val l = ArrayList(waiters); waiters.clear(); for (w in l) w(ok) }

    /** signs in once per app run (and again after the session ended) */
    @Suppress("UNCHECKED_CAST")
    fun ready(cb: (Boolean) -> Unit) {
        if (http != null && me != null) { cb(true); return }
        waiters.add(cb); if (busy) return
        busy = true
        a.rpc("ghab_token") { ok, r ->
            val cfg = a.api?.cfg
            if (!ok || cfg == null) { finish(false); return@rpc }
            port = r.lng("port").toInt()
            val h = Http(ServerCfg(cfg.host, port, cfg.tls, cfg.pin))
            Thread {
                var meJ: Map<String, Any?>? = null
                try {
                    if (h.signIn("/sso?t=" + URLEncoder.encode(r.str("token"), "UTF-8"))) {
                        val (code, j) = h.json("GET", "/api/me")
                        if (code == 200) meJ = j as? Map<String, Any?>
                    }
                } catch (_: Exception) {}
                a.main.post {
                    if (meJ != null) { http = h; me = meJ; img = Img(h, File(a.filesDir, "ghab-img")) }
                    finish(meJ != null)
                }
            }.start()
        }
    }

    /** one API call; [cb] gets the parsed JSON (Map / List) or null on a network error. The session is renewed on the next call after a 401. */
    fun api(method: String, path: String, body: String? = null, cb: (Any?) -> Unit) {
        ready { ok ->
            if (!ok) { cb(null); return@ready }
            val h = http ?: run { cb(null); return@ready }
            Thread {
                var res: Any? = null
                try { val (code, j) = h.json(method, path, body); if (code == 401) { http = null; me = null } else res = j } catch (_: Exception) {}
                a.main.post { cb(res) }
            }.start()
        }
    }

    fun path(name: String?): String? = if (name.isNullOrEmpty()) null else "/media/" + name.split("/").joinToString("/") { URLEncoder.encode(it, "UTF-8").replace("+", "%20") }

    @Volatile var port = 0
    // ---- videos kept inside the app (Ghab only): at most 550 MB, the least recently watched go first
    private val vdir by lazy { File(a.filesDir, "ghab-vid").also { it.mkdirs() } }
    private val pending = HashMap<String, MutableList<(File?) -> Unit>>()
    private fun sha(n: String): String = java.security.MessageDigest.getInstance("SHA-1").digest(n.toByteArray()).joinToString("") { "%02x".format(it) }
    private fun videoFile(name: String) = File(vdir, sha(name) + ".mp4")
    fun cachedVideo(name: String?): File? {
        if (name.isNullOrEmpty()) return null
        val f = videoFile(name)
        return if (f.isFile && f.length() > 0) f.also { it.setLastModified(System.currentTimeMillis()) } else null
    }
    private fun trimVideos(keep: File?) {
        val fs = (vdir.listFiles() ?: return).filter { it.name.endsWith(".mp4") }
        var total = fs.sumOf { it.length() }
        if (total <= VIDEO_CAP) return
        for (f in fs.sortedBy { it.lastModified() }) { if (total <= VIDEO_CAP * 9 / 10) break; if (f == keep) continue; total -= f.length(); f.delete() }
    }
    /** the saved copy of a video (downloaded now when missing); [progress] 0..1 on the main thread */
    fun fetchVideo(name: String?, progress: ((Float) -> Unit)? = null, cb: (File?) -> Unit) {
        if (name.isNullOrEmpty()) { cb(null); return }
        cachedVideo(name)?.let { cb(it); return }
        val list = pending[name]; if (list != null) { list.add(cb); return }
        pending[name] = arrayListOf(cb)
        ready { ok ->
            val h = http; val p = path(name)
            if (!ok || h == null || p == null) { pending.remove(name)?.forEach { it(null) }; return@ready }
            Thread {
                val dest = videoFile(name); var good = false
                try { h.download(p, dest, progress = { d, t -> if (t > 0 && progress != null) a.main.post { progress(d.toFloat() / t) } }); good = true } catch (_: Exception) {}
                if (good) trimVideos(dest)
                a.main.post { pending.remove(name)?.forEach { it(if (good) dest else null) } }
            }.start()
        }
    }

    // ---- live streaming (like Instagram / the web): the video starts playing while it downloads, what was loaded is kept on disk for next time
    private var streamCache: androidx.media3.datasource.cache.SimpleCache? = null
    @Synchronized
    fun streamSource(): androidx.media3.exoplayer.source.DefaultMediaSourceFactory {
        val pin = ir.windroida.app.Prefs.pin(a)
        val client = okhttp3.OkHttpClient.Builder()
            .sslSocketFactory(ir.windroida.app.Trust.pinnedContext(pin).socketFactory, ir.windroida.app.Trust.pinnedTm(pin))
            .hostnameVerifier { _, _ -> true }
            .connectTimeout(10, java.util.concurrent.TimeUnit.SECONDS).readTimeout(30, java.util.concurrent.TimeUnit.SECONDS).build()
        val ok = androidx.media3.datasource.okhttp.OkHttpDataSource.Factory(client)
        http?.cookie?.takeIf { it.isNotEmpty() }?.let { ok.setDefaultRequestProperties(mapOf("Cookie" to it)) }
        if (streamCache == null) streamCache = androidx.media3.datasource.cache.SimpleCache(File(a.filesDir, "ghab-stream"),
            androidx.media3.datasource.cache.LeastRecentlyUsedCacheEvictor(VIDEO_CAP), androidx.media3.database.StandaloneDatabaseProvider(a))
        val cds = androidx.media3.datasource.cache.CacheDataSource.Factory().setCache(streamCache!!)
            .setUpstreamDataSourceFactory(androidx.media3.datasource.DefaultDataSource.Factory(a, ok))
            .setCacheKeyFactory { it.uri.path ?: it.uri.toString() }
            .setFlags(androidx.media3.datasource.cache.CacheDataSource.FLAG_IGNORE_CACHE_ON_ERROR)
        return androidx.media3.exoplayer.source.DefaultMediaSourceFactory(cds)
    }

    /** a player that is ready to start: the saved copy when there is one, otherwise it streams at once. null when the server cannot be reached. */
    fun player(name: String?): androidx.media3.exoplayer.ExoPlayer? {
        val h = http ?: return null
        val p = path(name) ?: return null
        val saved = cachedVideo(name)
        val e = if (saved != null) androidx.media3.exoplayer.ExoPlayer.Builder(a).build() else androidx.media3.exoplayer.ExoPlayer.Builder(a).setMediaSourceFactory(streamSource()).build()
        e.setMediaItem(androidx.media3.common.MediaItem.fromUri(if (saved != null) android.net.Uri.fromFile(saved) else android.net.Uri.parse(h.url(p))))
        return e
    }

    /** full-screen player: the saved copy when there is one, otherwise it streams at once and a copy is saved in the background for next time */
    fun play(name: String?, title: String) {
        val h = http ?: return
        val p = path(name) ?: return
        val saved = cachedVideo(name)
        val i = Intent(a, PlayerActivity::class.java).putExtra("url", h.url(p)).putExtra("title", title).putExtra("cookie", h.cookie ?: "")
        if (saved != null) i.putExtra("file", saved.path) else fetchVideo(name) { }
        a.startActivity(i)
    }

    /** picks a picture / video from the phone and uploads it to [endpoint] ("/api/posts" or "/api/stories") with a percent ring */
    fun pickAndUpload(endpoint: String, caption: String, onDone: (Boolean) -> Unit) {
        a.pickResult(Intent(Intent.ACTION_GET_CONTENT).setType("*/*").putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("image/*", "video/*")).addCategory(Intent.CATEGORY_OPENABLE)) { res, data ->
            val u = data?.data
            if (res != android.app.Activity.RESULT_OK || u == null) { onDone(false); return@pickResult }
            a.hud("در حال آماده‌سازی…", -1f)
            ready { ok ->
                val h = http
                if (!ok || h == null) { a.hudHide(); a.toast("به قاب وصل نشد"); onDone(false); return@ready }
                Thread {
                    var good = false; var err = "ارسال نشد"
                    var tmp: File? = null
                    try {
                        val mime = a.contentResolver.getType(u) ?: "application/octet-stream"
                        val video = mime.startsWith("video")
                        var size = -1L
                        a.contentResolver.query(u, arrayOf(android.provider.OpenableColumns.SIZE), null, null, null)?.use { c -> if (c.moveToFirst() && !c.isNull(0)) size = c.getLong(0) }
                        if (size < 0) {                                   // the size must be known before sending: copy to a temporary file
                            tmp = File(a.cacheDir, "ghab-up.tmp"); a.contentResolver.openInputStream(u)!!.use { i -> tmp.outputStream().use { o -> i.copyTo(o) } }; size = tmp.length()
                        }
                        if (size > 600L * 1024 * 1024) throw java.io.IOException("فایل از ۶۰۰ مگابایت بزرگ‌تره")
                        val parts = ArrayList<Http.Part>()
                        val t0 = tmp
                        parts.add(Http.Part("file", if (video) "upload.mp4" else "upload.jpg", mime, size, null) { if (t0 != null) t0.inputStream() else a.contentResolver.openInputStream(u)!! })
                        if (video) posterOf(u)?.let { parts.add(Http.Part("poster", "poster.jpg", "image/jpeg", it.size.toLong(), it)) }
                        val total = parts.sumOf { it.length }
                        // internet cut: wait up to 5 minutes for it to come back, then send again (Ghab's server has no partial upload)
                        var downSince = -1L
                        var pair: Pair<Int, Any?>? = null
                        while (pair == null) {
                            try {
                                pair = h.multipart(endpoint, mapOf("caption" to caption), parts) { d, _ ->
                                    downSince = -1L
                                    val f = if (total > 0) d.toFloat() / total else -1f
                                    a.hud("در حال ارسال به قاب — " + Fmt.size(d) + " / " + Fmt.size(total), f)
                                }
                            } catch (e: java.io.IOException) {
                                val now = System.currentTimeMillis()
                                if (downSince < 0) downSince = now
                                if (now - downSince > 300_000) throw java.io.IOException("اینترنت بیشتر از ۵ دقیقه قطع بود؛ دوباره بفرست")
                                a.hud("منتظر اینترنت… (تا ۵ دقیقه)", -1f)
                                Thread.sleep(5000)
                            }
                        }
                        val (code, j) = pair!!
                        @Suppress("UNCHECKED_CAST") val m = j as? Map<String, Any?>
                        good = code in 200..299 && m?.get("error") == null
                        if (!good) err = m?.str("error", "ارسال نشد") ?: ("خطای سرور " + code)
                    } catch (e: Exception) { err = e.message ?: err } finally { tmp?.delete() }
                    a.hudHide()
                    a.main.post { if (!good) a.toast(err) else a.toast("ارسال شد"); onDone(good) }
                }.start()
            }
        }
    }

    /** a still frame of a video, as JPEG (the cover of the post) */
    private fun posterOf(u: android.net.Uri): ByteArray? = try {
        val r = android.media.MediaMetadataRetriever(); r.setDataSource(a, u)
        var bmp = r.getFrameAtTime(500_000, android.media.MediaMetadataRetriever.OPTION_CLOSEST_SYNC) ?: r.getFrameAtTime(0); r.release()
        if (bmp == null) null else {
            val k = Math.min(1f, 720f / Math.max(bmp.width, bmp.height))
            if (k < 1f) bmp = android.graphics.Bitmap.createScaledBitmap(bmp, Math.round(bmp.width * k), Math.round(bmp.height * k), true)
            val bo = java.io.ByteArrayOutputStream(); bmp.compress(android.graphics.Bitmap.CompressFormat.JPEG, 82, bo); bo.toByteArray()
        }
    } catch (_: Exception) { null }

    companion object { const val VIDEO_CAP = 550L * 1024 * 1024 }
}

// ---------------------------------------------------------------------------------------------------------------- small helpers
@Suppress("UNCHECKED_CAST")
private fun lm(v: Any?): List<Map<String, Any?>> = (v as? List<*>)?.mapNotNull { it as? Map<String, Any?> } ?: emptyList()
@Suppress("UNCHECKED_CAST")
private fun mm(v: Any?): Map<String, Any?>? = v as? Map<String, Any?>

private fun fmtT(ms: Long): String = Fmt.digits("${ms / 60000}:" + "%02d".format(ms / 1000 % 60))

private fun num(v: Any?): Double = (v as? Number)?.toDouble() ?: 0.0

private fun since(ts: Double): String {
    val s = (System.currentTimeMillis() / 1000.0 - ts).toLong().coerceAtLeast(0)
    val t = when { s < 60 -> "الان"; s < 3600 -> "${s / 60} دقیقه پیش"; s < 86400 -> "${s / 3600} ساعت پیش"; else -> "${s / 86400} روز پیش" }
    return Fmt.digits(t)
}

internal class GhabUi(val a: NativeActivity, val g: GhabClient) {
    val th = a.th

    fun load(iv: ImageView, name: String?, maxPx: Int) {
        iv.tag = name; iv.setImageDrawable(null)
        val p = g.path(name) ?: return
        g.img?.load(p, "", maxPx) { bmp -> if (iv.tag == name && bmp != null) iv.setImageBitmap(bmp) }
    }

    /** round avatar: first letter on a colour, the picture on top when there is one */
    fun avatar(username: String, file: String?, sizeDp: Int, ringColor: Int = 0): View {
        val box = FrameLayout(a)
        val pad = if (ringColor != 0) a.dp(3) else 0
        box.setPadding(pad, pad, pad, pad)
        if (ringColor != 0) box.background = GradientDrawable().also { it.shape = GradientDrawable.OVAL; it.setStroke(a.dp(2), ringColor) }
        val inner = FrameLayout(a)
        inner.background = GradientDrawable().also { it.shape = GradientDrawable.OVAL; it.setColor(Theme.AVATAR_COLORS[Math.abs(username.hashCode()) % Theme.AVATAR_COLORS.size]) }
        inner.clipToOutline = true
        inner.outlineProvider = object : ViewOutlineProvider() { override fun getOutline(v: View, o: Outline) { o.setOval(0, 0, v.width, v.height) } }
        inner.addView(label(a, username.take(1).uppercase(), sizeDp * 0.42f, 0xFFFFFFFF.toInt(), true).also { it.gravity = Gravity.CENTER }, FrameLayout.LayoutParams(MATCH, MATCH))
        val iv = ImageView(a); iv.scaleType = ImageView.ScaleType.CENTER_CROP
        inner.addView(iv, FrameLayout.LayoutParams(MATCH, MATCH))
        load(iv, file, 160)
        box.addView(inner, FrameLayout.LayoutParams(a.dp(sizeDp), a.dp(sizeDp)))
        return box
    }

    fun square(name: String?, isVideo: Boolean, onClick: () -> Unit): View {
        val f = FrameLayout(a); f.setBackgroundColor(th.field)
        val iv = ImageView(a); iv.scaleType = ImageView.ScaleType.CENTER_CROP
        f.addView(iv, FrameLayout.LayoutParams(MATCH, MATCH))
        load(iv, name, 400)
        if (isVideo) f.addView(label(a, "▶", 18f, 0xFFFFFFFF.toInt(), true), FrameLayout.LayoutParams(WRAP, WRAP, Gravity.END or Gravity.TOP).also { it.setMargins(a.dp(6), a.dp(4), a.dp(6), 0) })
        f.isClickable = true; f.setOnClickListener { onClick() }
        return f
    }

    /** rows of three squares */
    fun grid(posts: List<Map<String, Any?>>, open: (Map<String, Any?>) -> Unit): View {
        val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL
        val w = (a.resources.displayMetrics.widthPixels - a.dp(4)) / 3
        posts.chunked(3).forEach { row ->
            val r = LinearLayout(a)
            row.forEach { p ->
                val vid = p.str("kind") == "video"
                val v = square(if (vid) (p.str("poster").ifEmpty { null }) else (p.str("mid").ifEmpty { p.str("file") }), vid) { open(p) }
                r.addView(v, LinearLayout.LayoutParams(w, w).also { it.setMargins(a.dp(1), a.dp(1), a.dp(1), a.dp(1)) })
            }
            col.addView(r)
        }
        return col
    }

    // ---- feed videos play right inside their post (muted, looping) while they are mostly on screen, like Instagram; one at a time
    private class Slot(val frame: FrameLayout, val file: String, val playIcon: View)
    private val slots = ArrayList<Slot>()
    private var cur: Slot? = null
    private var curPlayer: androidx.media3.exoplayer.ExoPlayer? = null
    private var curView: androidx.media3.ui.PlayerView? = null
    private var curRing: RingView? = null

    fun stopInline() {
        curPlayer?.release(); curPlayer = null
        curView?.let { (it.parent as? android.view.ViewGroup)?.removeView(it) }; curView = null
        curRing?.let { (it.parent as? android.view.ViewGroup)?.removeView(it) }; curRing = null
        cur?.playIcon?.visibility = View.VISIBLE; cur = null
    }

    /** call after every scroll / after posts were added: starts the video that is most visible, stops the others */
    fun updateInline() {
        slots.removeAll { !it.frame.isAttachedToWindow }
        var best: Slot? = null; var bestFrac = 0.55f
        val r = android.graphics.Rect()
        for (s in slots) {
            if (s.frame.height <= 0 || !s.frame.getGlobalVisibleRect(r)) continue
            val f = r.height().toFloat() / s.frame.height
            if (f >= bestFrac) { best = s; bestFrac = f }
        }
        if (best === cur) return
        stopInline()
        val s = best ?: return
        cur = s
        g.ready { ok ->
            if (cur !== s || !ok) return@ready
            val e = g.player(s.file) ?: return@ready
            val v = androidx.media3.ui.PlayerView(a); v.useController = false; v.resizeMode = androidx.media3.ui.AspectRatioFrameLayout.RESIZE_MODE_ZOOM; v.setShutterBackgroundColor(0)
            v.player = e; e.volume = 0f; e.repeatMode = androidx.media3.common.Player.REPEAT_MODE_ONE
            val ring = RingView(a, 0x66000000); ring.progress = -1f
            e.addListener(object : androidx.media3.common.Player.Listener {
                override fun onRenderedFirstFrame() { ring.visibility = View.GONE; s.playIcon.visibility = View.GONE }
                override fun onPlaybackStateChanged(st: Int) { ring.visibility = if (st == androidx.media3.common.Player.STATE_BUFFERING) View.VISIBLE else View.GONE }
            })
            s.frame.addView(v, 1, FrameLayout.LayoutParams(MATCH, MATCH))
            s.frame.addView(ring, FrameLayout.LayoutParams(a.dp(44), a.dp(44), Gravity.CENTER))
            curPlayer = e; curView = v; curRing = ring
            e.prepare(); e.playWhenReady = true
        }
    }

    /** a post as in the feed. [onChange] lets the caller refresh when the post changed (like / save). */
    fun card(p0: Map<String, Any?>, openPost: ((Map<String, Any?>) -> Unit)?, openUser: (String) -> Unit): View {
        var p = p0
        val id = p.lng("id")
        val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL
        val user = mm(p["user"]) ?: emptyMap()
        val uname = user.str("username")
        val head = LinearLayout(a); head.gravity = Gravity.CENTER_VERTICAL; head.setPadding(a.dp(12), a.dp(8), a.dp(12), a.dp(8))
        head.addView(avatar(uname, user.str("avatar").ifEmpty { null }, 36))
        val nm = LinearLayout(a); nm.orientation = LinearLayout.VERTICAL; nm.setPadding(a.dp(10), 0, 0, 0)
        nm.addView(label(a, uname, 15f, th.text, true)); nm.addView(label(a, since(num(p["created"])), 11f, th.muted))
        head.addView(nm, lp(0, WRAP).weight(1f))
        head.isClickable = true; head.setOnClickListener { openUser(uname) }
        col.addView(head)
        // media
        val isVid = p.str("kind") == "video"
        val shown = if (isVid) p.str("poster").ifEmpty { null } else p.str("mid").ifEmpty { p.str("file") }
        val mf = FrameLayout(a); mf.setBackgroundColor(th.field)
        val iv = ImageView(a); iv.scaleType = ImageView.ScaleType.CENTER_CROP
        mf.addView(iv, FrameLayout.LayoutParams(MATCH, MATCH)); load(iv, shown, 1080)
        if (isVid) {
            val pi = label(a, "▶", 44f, 0xFFFFFFFF.toInt(), true)
            mf.addView(pi, FrameLayout.LayoutParams(WRAP, WRAP, Gravity.CENTER))
            slots.add(Slot(mf, p.str("file"), pi))
        }
        val n = p.lng("nmedia").toInt()
        if (n > 1) mf.addView(label(a, Fmt.digits("1/$n"), 12f, 0xFFFFFFFF.toInt(), true).also { it.background = rounded(0x99000000.toInt(), a.dpf(10f)); it.setPadding(a.dp(8), a.dp(2), a.dp(8), a.dp(2)) },
            FrameLayout.LayoutParams(WRAP, WRAP, Gravity.END or Gravity.TOP).also { it.setMargins(a.dp(8), a.dp(8), a.dp(8), 0) })
        mf.isClickable = true
        mf.setOnClickListener { if (isVid) g.play(p.str("file"), uname) else openPost?.invoke(p) }
        col.addView(mf, lp(MATCH, a.resources.displayMetrics.widthPixels))
        // actions
        val acts = LinearLayout(a); acts.gravity = Gravity.CENTER_VERTICAL; acts.setPadding(a.dp(10), a.dp(4), a.dp(10), 0)
        val like = label(a, "", 22f, th.text, true); val cm = label(a, "", 15f, th.text); val sv = label(a, "", 22f, th.text)
        val cap = label(a, "", 14f, th.text); val cmLink = label(a, "", 13f, th.muted)
        fun paint() {
            like.text = (if (p.bool("liked")) "♥ " else "♡ ") + Fmt.digits(p.lng("likes").toString()); like.setTextColor(if (p.bool("liked")) 0xFFE53950.toInt() else th.text)
            cm.text = "💬 " + Fmt.digits(p.lng("ncomments").toString()); sv.text = if (p.bool("saved")) "🔖" else "◻"
            sv.setTextColor(if (p.bool("saved")) th.accent else th.muted)
            cmLink.text = if (p.lng("ncomments") > 0) Fmt.digits("مشاهده ${p.lng("ncomments")} نظر") else ""
            cmLink.visibility = if (p.lng("ncomments") > 0 && openPost != null) View.VISIBLE else View.GONE
        }
        fun toggle(kind: String) { g.api("POST", "/api/posts/$id/$kind") { r -> mm(r)?.takeIf { it["error"] == null }?.let { p = it; paint() } } }
        like.setPadding(a.dp(6), a.dp(8), a.dp(14), a.dp(8)); like.isClickable = true; like.setOnClickListener { toggle("like") }
        cm.setPadding(a.dp(6), a.dp(8), a.dp(14), a.dp(8)); cm.isClickable = true; cm.setOnClickListener { openPost?.invoke(p) }
        sv.setPadding(a.dp(6), a.dp(6), a.dp(6), a.dp(6)); sv.isClickable = true; sv.setOnClickListener { toggle("save") }
        acts.addView(like); acts.addView(cm); acts.addView(View(a), lp(0, 1).weight(1f)); acts.addView(sv)
        col.addView(acts)
        val text = p.str("caption")
        if (text.isNotEmpty()) { cap.text = "$uname  $text"; cap.setPadding(a.dp(14), 0, a.dp(14), a.dp(2)); col.addView(cap) }
        cmLink.setPadding(a.dp(14), a.dp(2), a.dp(14), a.dp(6)); cmLink.isClickable = true; cmLink.setOnClickListener { openPost?.invoke(p) }
        col.addView(cmLink)
        paint()
        col.addView(View(a).also { it.setBackgroundColor(th.line) }, lp(MATCH, a.dp(6)))
        return col
    }

    /** full-screen story viewer: tap = next, tap on the left third = previous; images auto-advance */
    fun stories(groups: List<Map<String, Any?>>, start: Int) {
        val d = android.app.Dialog(a, android.R.style.Theme_Black_NoTitleBar_Fullscreen)
        val root = FrameLayout(a); root.setBackgroundColor(0xFF000000.toInt())
        val iv = ImageView(a); iv.scaleType = ImageView.ScaleType.FIT_CENTER
        root.addView(iv, FrameLayout.LayoutParams(MATCH, MATCH))
        val top = LinearLayout(a); top.gravity = Gravity.CENTER_VERTICAL; top.setPadding(a.dp(12), a.dp(28), a.dp(12), a.dp(8))
        val who = label(a, "", 15f, 0xFFFFFFFF.toInt(), true); val ago = label(a, "", 12f, 0xCCFFFFFF.toInt())
        val tl = LinearLayout(a); tl.orientation = LinearLayout.VERTICAL; tl.setPadding(a.dp(8), 0, 0, 0); tl.addView(who); tl.addView(ago)
        top.addView(tl, lp(0, WRAP).weight(1f))
        top.addView(label(a, "✕", 22f, 0xFFFFFFFF.toInt(), true).also { it.setPadding(a.dp(12), a.dp(4), a.dp(4), a.dp(4)); it.setOnClickListener { d.dismiss() } })
        root.addView(top, FrameLayout.LayoutParams(MATCH, WRAP, Gravity.TOP))
        var gi = start; var ii = 0
        var timer: Runnable? = null
        fun stop() { timer?.let { a.main.removeCallbacks(it) } }
        lateinit var show: () -> Unit
        fun next() { stop(); val items = lm(groups[gi]["items"]); if (ii + 1 < items.size) { ii++; show() } else if (gi + 1 < groups.size) { gi++; ii = 0; show() } else d.dismiss() }
        fun prev() { stop(); if (ii > 0) { ii--; show() } else if (gi > 0) { gi--; ii = 0; show() } else show() }
        show = {
            val grp = groups[gi]; val items = lm(grp["items"]); val s = items.getOrNull(ii)
            if (s == null) d.dismiss() else {
                who.text = grp.str("username"); ago.text = since(num(s["created"]))
                g.api("POST", "/api/stories/${s.lng("id")}/view") { }
                if (s.str("kind") == "video") { iv.setImageDrawable(null); g.play(s.str("file"), grp.str("username")); timer = Runnable { next() }; a.main.postDelayed(timer!!, 4000) }
                else {
                    iv.setImageDrawable(null); val nm = s.str("file")
                    g.path(nm)?.let { p -> g.img?.load(p, "", 1440) { b -> if (b != null) iv.setImageBitmap(b) } }
                    timer = Runnable { next() }; a.main.postDelayed(timer!!, 5000)
                }
            }
        }
        root.setOnTouchListener { v, e -> if (e.action == android.view.MotionEvent.ACTION_UP) { if (e.x < v.width / 3f) prev() else next() }; true }
        d.setContentView(root); d.setOnDismissListener { stop() }
        d.show(); show()
    }
}

// ---------------------------------------------------------------------------------------------------------------- screens
/** Reels like Instagram: one full-screen video at a time, swipe up / down for the next one, like / comment / share / save on the side. */
internal class ReelsView(private val a: NativeActivity, private val g: GhabClient, private val ui: GhabUi, private val openPost: (Long) -> Unit, private val openUser: (String) -> Unit) : FrameLayout(a) {
    private val th = a.th
    private val posts = ArrayList<Map<String, Any?>>()
    private val seen = HashSet<Long>()
    private var idx = 0
    private var page: Page? = null
    private var loading = false
    private val slop = android.view.ViewConfiguration.get(a).scaledTouchSlop
    private var busyAnim = false
    var muted = false
    fun toggleMute() { muted = !muted; page?.applyMute(muted) }
    // gesture state (same behaviour as the web reels)
    private var gx = 0f; private var gy = 0f; private var ix = 0f; private var iy = 0f; private var lastY = 0f
    private var gMode = ""; private var gFx = 0f; private var gWasPlaying = false; private var gT0 = 0L; private var gOn = false
    private var gHold: Runnable? = null
    private var lastTap = 0L; private var lastX = 0f; private var tapRun: Runnable? = null
    private fun fmt(ms: Long): String = Fmt.digits("${ms / 60000}:" + "%02d".format(ms / 1000 % 60))

    inner class Page(var p: Map<String, Any?>) {
        val view = FrameLayout(a)
        private var exo: androidx.media3.exoplayer.ExoPlayer? = null
        private var pv: androidx.media3.ui.PlayerView? = null
        private val ring = RingView(a, 0x99000000.toInt())
        private val like = label(a, "", 15f, 0xFFFFFFFF.toInt(), true); private val cm = label(a, "", 15f, 0xFFFFFFFF.toInt(), true); private val sv = label(a, "", 22f, 0xFFFFFFFF.toInt())
        private val pause = label(a, "▶", 64f, 0xCCFFFFFF.toInt(), true)
        private var released = false
        private val note = label(a, "", 16f, 0xFFFFFFFF.toInt(), true)
        private val heart = label(a, "♥", 110f, 0xFFFF3B5C.toInt(), true)
        private val progTrack = FrameLayout(a); private val progFill = View(a)
        private val muteBtn = label(a, "🔊", 20f, 0xFFFFFFFF.toInt())
        private val timeLbl = label(a, "", 12f, 0xFFFFFFFF.toInt(), true)
        private var ticker: Runnable? = null
        private var watched = 0f                 // seconds really watched: the ranking learns from this (like on the web)
        private var lastSec = -1L

        init {
            view.setBackgroundColor(0xFF000000.toInt())
            val poster = ImageView(a); poster.scaleType = ImageView.ScaleType.CENTER_CROP; view.addView(poster, FrameLayout.LayoutParams(MATCH, MATCH))
            ui.load(poster, p.str("poster").ifEmpty { null }, 1080)
            view.addView(ring, FrameLayout.LayoutParams(a.dp(56), a.dp(56), Gravity.CENTER)); ring.progress = -1f
            pause.visibility = View.GONE; pause.gravity = Gravity.CENTER; view.addView(pause, FrameLayout.LayoutParams(WRAP, WRAP, Gravity.CENTER))
            // right column
            val side = LinearLayout(a); side.orientation = LinearLayout.VERTICAL; side.gravity = Gravity.CENTER_HORIZONTAL
            fun cell(v: View) { v.setPadding(a.dp(10), a.dp(10), a.dp(10), a.dp(10)); (v as? TextView)?.gravity = Gravity.CENTER; v.isClickable = true; side.addView(v, lp(WRAP, WRAP)) }
            cell(like); cell(cm)
            val sh = label(a, "➤", 22f, 0xFFFFFFFF.toInt()); cell(sh); cell(sv)
            like.setOnClickListener { toggle("like") }; sv.setOnClickListener { toggle("save") }
            cm.setOnClickListener { openPost(p.lng("id")) }
            sh.setOnClickListener { share() }
            side.background = th.glass(a, 28, 0x33FFFFFF); side.setPadding(0, a.dp(4), 0, a.dp(4))
            view.addView(side, FrameLayout.LayoutParams(WRAP, WRAP, Gravity.END or Gravity.CENTER_VERTICAL).also { it.setMargins(0, 0, a.dp(8), a.dp(60)) })
            // bottom: who + follow + caption
            val u = mm(p["user"]) ?: emptyMap(); val uname = u.str("username")
            val bot = LinearLayout(a); bot.orientation = LinearLayout.VERTICAL; bot.setPadding(a.dp(14), 0, a.dp(70), a.dp(14))
            val who = LinearLayout(a); who.gravity = Gravity.CENTER_VERTICAL
            who.addView(ui.avatar(uname, u.str("avatar").ifEmpty { null }, 38, 0xFFE1306C.toInt()))
            who.addView(label(a, uname, 15f, 0xFFFFFFFF.toInt(), true).also { it.setPadding(a.dp(10), 0, a.dp(10), 0) })
            if (!p.bool("mine") && !p.bool("followed")) who.addView(label(a, "دنبال کن", 13f, 0xFFFFFFFF.toInt(), true).also { f ->
                f.setPadding(a.dp(12), a.dp(5), a.dp(12), a.dp(5)); f.background = th.glass(a, 10, 0x33FFFFFF); f.isClickable = true
                f.setOnClickListener { g.api("POST", "/api/user/" + URLEncoder.encode(uname, "UTF-8") + "/follow") { r -> if (mm(r) != null) f.visibility = View.GONE } } })
            who.isClickable = true; who.setOnClickListener { openUser(uname) }
            bot.addView(who)
            if (p.str("caption").isNotEmpty()) bot.addView(label(a, p.str("caption"), 14f, 0xFFFFFFFF.toInt()).also { it.maxLines = 2; it.ellipsize = android.text.TextUtils.TruncateAt.END; it.setPadding(0, a.dp(8), 0, 0) })
            bot.background = GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, intArrayOf(0x00000000, 0xB3000000.toInt())); bot.setPadding(a.dp(14), a.dp(40), a.dp(70), a.dp(18))
            view.addView(bot, FrameLayout.LayoutParams(MATCH, WRAP, Gravity.BOTTOM))
            timeLbl.background = th.glass(a, 12, 0x55000000); timeLbl.setPadding(a.dp(10), a.dp(3), a.dp(10), a.dp(3))
            view.addView(timeLbl, FrameLayout.LayoutParams(WRAP, WRAP, Gravity.END or Gravity.BOTTOM).also { it.setMargins(0, 0, a.dp(12), a.dp(8)) })
            // gesture feedback: note ("⏸", "⏩ ۲×", time), big heart, thin progress bar, mute
            note.visibility = View.GONE; note.background = rounded(0x99000000.toInt(), a.dpf(14f)); note.setPadding(a.dp(14), a.dp(6), a.dp(14), a.dp(6))
            view.addView(note, FrameLayout.LayoutParams(WRAP, WRAP, Gravity.CENTER_HORIZONTAL or Gravity.TOP).also { it.topMargin = a.dp(90) })
            heart.visibility = View.GONE; view.addView(heart, FrameLayout.LayoutParams(WRAP, WRAP, Gravity.CENTER))
            progTrack.layoutDirection = View.LAYOUT_DIRECTION_LTR; progTrack.setBackgroundColor(0x44FFFFFF)
            progFill.setBackgroundColor(0xFFFFFFFF.toInt()); progFill.pivotX = 0f; progFill.scaleX = 0f
            progTrack.addView(progFill, FrameLayout.LayoutParams(MATCH, MATCH)); view.addView(progTrack, FrameLayout.LayoutParams(MATCH, a.dp(3), Gravity.BOTTOM))
            muteBtn.background = th.glass(a, 20, 0x44000000); muteBtn.gravity = Gravity.CENTER; muteBtn.setPadding(a.dp(10), a.dp(8), a.dp(10), a.dp(8)); muteBtn.isClickable = true
            muteBtn.setOnClickListener { this@ReelsView.toggleMute() }
            view.addView(muteBtn, FrameLayout.LayoutParams(WRAP, WRAP, Gravity.END or Gravity.TOP).also { it.setMargins(0, a.dp(10), a.dp(8), 0) })
            applyMute(this@ReelsView.muted)
            paint()
        }

        fun pos(): Long = exo?.currentPosition ?: 0L
        fun dur(): Long = exo?.duration?.takeIf { it > 0 } ?: 0L
        fun seekTo(ms: Long) { exo?.seekTo(ms.coerceIn(0L, (dur() - 50).coerceAtLeast(0L))) }
        fun speed(f: Float) { exo?.setPlaybackSpeed(f) }
        fun playing(): Boolean = exo?.playWhenReady ?: false
        fun setPlaying(b: Boolean) { exo?.playWhenReady = b; pause.visibility = if (b) View.GONE else View.VISIBLE }
        fun showNote(t: String, auto: Boolean) { note.text = t; note.visibility = View.VISIBLE; if (auto) a.main.postDelayed({ note.visibility = View.GONE }, 750) }
        fun hideNote() { note.visibility = View.GONE }
        fun big(on: Boolean) { progTrack.layoutParams = (progTrack.layoutParams as FrameLayout.LayoutParams).also { it.height = a.dp(if (on) 8 else 3) }; progTrack.requestLayout() }
        fun applyMute(m: Boolean) { exo?.volume = if (m) 0f else 1f; muteBtn.text = if (m) "🔇" else "🔊" }
        /** double tap in the middle: a big heart pops up and the reel is liked (not un-liked) */
        fun likeIt() {
            heart.visibility = View.VISIBLE; heart.alpha = 1f; heart.scaleX = 0.3f; heart.scaleY = 0.3f
            heart.animate().scaleX(1.25f).scaleY(1.25f).setDuration(260).withEndAction { heart.animate().alpha(0f).setDuration(450).withEndAction { heart.visibility = View.GONE }.start() }.start()
            if (!p.bool("liked")) toggle("like")
        }

        private fun paint() {
            like.text = (if (p.bool("liked")) "♥\n" else "♡\n") + Fmt.digits(p.lng("likes").toString()); like.setTextColor(if (p.bool("liked")) 0xFFFF3B5C.toInt() else 0xFFFFFFFF.toInt())
            cm.text = "💬\n" + Fmt.digits(p.lng("ncomments").toString())
            sv.text = if (p.bool("saved")) "🔖" else "◻"
        }
        private fun toggle(kind: String) { g.api("POST", "/api/posts/${p.lng("id")}/$kind") { r -> mm(r)?.takeIf { it["error"] == null }?.let { p = it; paint() } } }
        private fun share() {
            val link = "https://" + (a.api?.cfg?.host ?: "") + ":" + g.port + "/p/" + p.lng("id")
            Dialogs.pickChats(a, "ارسال ریل به…") { ids -> for (id in ids) a.rpc("send", mapOf("chat_id" to id, "text" to link)); if (ids.isNotEmpty()) a.toast("ارسال شد") }
        }

        /** starts at once: streams the video live (or plays the saved copy); the ring only shows while it buffers */
        fun start() {
            g.ready { ok ->
                if (released) return@ready
                val e = if (ok) g.player(p.str("file")) else null
                if (e == null) { ring.visibility = View.GONE; a.toast("ویدیو بارگیری نشد"); return@ready }
                ring.progress = -1f; ring.visibility = View.VISIBLE
                val v = androidx.media3.ui.PlayerView(a); v.useController = false; v.resizeMode = androidx.media3.ui.AspectRatioFrameLayout.RESIZE_MODE_ZOOM; v.setShutterBackgroundColor(0)
                v.player = e
                e.prepare(); e.playWhenReady = true
                e.volume = if (this@ReelsView.muted) 0f else 1f
                e.repeatMode = androidx.media3.common.Player.REPEAT_MODE_OFF
                e.addListener(object : androidx.media3.common.Player.Listener {
                    override fun onRenderedFirstFrame() { ring.visibility = View.GONE }
                    override fun onPlaybackStateChanged(st: Int) {
                        if (released) return
                        ring.visibility = if (st == androidx.media3.common.Player.STATE_BUFFERING) View.VISIBLE else View.GONE
                        if (st == androidx.media3.common.Player.STATE_ENDED) this@ReelsView.endedOne(this@Page)
                    }
                    override fun onPlayerError(err: androidx.media3.common.PlaybackException) { ring.visibility = View.GONE; a.toast("ویدیو پخش نشد") }
                })
                exo = e; pv = v
                view.addView(v, 1, FrameLayout.LayoutParams(MATCH, MATCH))
                val tk = object : Runnable { override fun run() {
                    if (released) return
                    val d = dur(); val ps = pos()
                    if (d > 0) { progFill.scaleX = (ps.toFloat() / d).coerceIn(0f, 1f); if (ps / 1000 != lastSec) { lastSec = ps / 1000; timeLbl.text = fmtT(ps) + " / " + fmtT(d) } }
                    if (exo?.isPlaying == true) watched += 0.12f * (exo?.playbackParameters?.speed ?: 1f)
                    a.main.postDelayed(this, 120) } }
                ticker = tk; a.main.post(tk)
            }
        }
        fun toggle() { if (exo != null) setPlaying(!playing()) }
        fun pauseNow() { exo?.playWhenReady = false }
        fun resumeNow() { exo?.let { if (pause.visibility != View.VISIBLE) it.playWhenReady = true } }
        fun release() {
            if (!released) {
                val d = dur() / 1000.0
                if (watched >= 0.12f && d > 0) g.api("POST", "/api/reels/watch", org.json.JSONObject().put("post_id", p.lng("id")).put("secs", watched.toDouble()).put("dur", d).toString()) { }
            }
            released = true; ticker?.let { a.main.removeCallbacks(it) }; exo?.release(); exo = null
        }
        fun replay() { exo?.let { it.seekTo(0); it.playWhenReady = true; pause.visibility = View.GONE } }
    }

    private var tab = "all"
    private var done = false                 // the server has nothing more for this tab
    private var pendingNext = false
    private val loader = RingView(a, 0x66000000)
    private val tabs = LinearLayout(a)

    init {
        setBackgroundColor(0xFF000000.toInt())
        loader.progress = -1f; loader.visibility = View.GONE
        // top: "ریلز | دنبال‌شده‌ها" like the web
        tabs.gravity = Gravity.CENTER; tabs.background = th.glass(a, 22, 0x33000000); tabs.setPadding(a.dp(6), a.dp(4), a.dp(6), a.dp(4))
        drawTabs()
        load()
    }

    private fun drawTabs() {
        tabs.removeAllViews()
        for ((k, t) in listOf("all" to "ریلز", "following" to "دنبال‌شده‌ها")) {
            val on = tab == k
            tabs.addView(label(a, t, 15f, if (on) 0xFFFFFFFF.toInt() else 0xAAFFFFFF.toInt(), on).also { v ->
                v.setPadding(a.dp(14), a.dp(6), a.dp(14), a.dp(6)); v.isClickable = true
                if (on) v.background = rounded(0x33FFFFFF, a.dpf(16f))
                v.setOnClickListener { if (tab != k) switchTab(k) }
            })
        }
    }

    private fun switchTab(k: String) {
        page?.release(); page = null; posts.clear(); seen.clear(); idx = 0; done = false; pendingNext = false; loading = false
        removeAllViews(); tab = k; drawTabs(); load()
    }

    private fun chrome() {                  // the parts that stay on top of the pages
        if (tabs.parent != null) removeView(tabs)
        addView(tabs, FrameLayout.LayoutParams(WRAP, WRAP, Gravity.CENTER_HORIZONTAL or Gravity.TOP).also { it.topMargin = a.dp(10) })
        if (loader.parent != null) removeView(loader)
        addView(loader, FrameLayout.LayoutParams(a.dp(52), a.dp(52), Gravity.CENTER))
    }

    /** the same ranking as the web: ?tab=…&limit=8&exclude=<what was already shown> (so it never repeats), and what is watched is reported back */
    private fun load() {
        if (loading || done) return
        loading = true
        if (posts.isNotEmpty() || childCount == 0) { chrome(); loader.visibility = View.VISIBLE }
        val ex = if (seen.isEmpty()) "" else "&exclude=" + seen.joinToString(",")
        g.api("GET", "/api/reels?tab=$tab&limit=8$ex") { r ->
            loading = false; loader.visibility = View.GONE
            val fresh = lm(r).filter { seen.add(it.lng("id")) }
            if (r == null && posts.isEmpty()) { chrome(); addView(label(a, "به قاب وصل نشد. برای تلاش دوباره بزن.", 14f, 0xFFFFFFFF.toInt()).also { it.gravity = Gravity.CENTER; it.isClickable = true; it.setOnClickListener { _ -> removeAllViews(); load() } }, FrameLayout.LayoutParams(MATCH, MATCH)); return@api }
            if (r != null && fresh.isEmpty()) done = true
            if (fresh.isEmpty() && posts.isEmpty()) { chrome(); addView(label(a, if (tab == "following") "کسایی که دنبال می‌کنی هنوز ریلی نذاشتن" else "هنوز ریلی نیست", 14f, 0xFFFFFFFF.toInt()).also { it.gravity = Gravity.CENTER }, FrameLayout.LayoutParams(MATCH, MATCH)); return@api }
            val first = posts.isEmpty()
            posts.addAll(fresh)
            if (first) { show(0, 0); chrome() } else if (pendingNext && fresh.isNotEmpty()) { pendingNext = false; go(1) }
        }
    }

    /** the video ended: on to the next one (it loads with the ring); when there is nothing more it just plays again */
    fun endedOne(p: Page) {
        if (p !== page) return
        if (idx + 1 < posts.size) go(1)
        else if (!done) { pendingNext = true; load() }
        else p.replay()
    }

    private fun show(i: Int, dir: Int) {
        val np = Page(posts[i]); val old = page
        idx = i; page = np
        addView(np.view, FrameLayout.LayoutParams(MATCH, MATCH))
        if (dir == 0 || height == 0) { old?.let { removeView(it.view); it.release() }; np.start(); if (idx >= posts.size - 2) load(); return }
        busyAnim = true
        val h = height.toFloat()
        np.view.translationY = dir * h
        np.view.animate().translationY(0f).setDuration(240).start()
        if (old != null) old.view.animate().translationY(-dir * h).setDuration(240).withEndAction { removeView(old.view); old.release(); busyAnim = false }.start() else busyAnim = false
        np.start()
        chrome()
        if (i >= posts.size - 2) load()
    }

    private fun go(d: Int) {
        if (busyAnim) return
        val n = idx + d
        if (n < 0) return
        if (n >= posts.size) { if (!done) { pendingNext = d > 0; load() } else a.toast("ریل دیگه‌ای نیست"); return }
        show(n, d)
    }

    /** hold right half = 2×, hold left half = pause · drag left/right = scrub · double tap on the edges = ±10 s, in the middle = like · single tap = pause/play · swipe up/down = next/previous */
    private fun gDown(x: Float, y: Float) {
        gOn = true; gx = x; gy = y; lastY = y; gMode = ""; gFx = x / Math.max(1, width); val pg = page
        gWasPlaying = pg?.playing() ?: false; gT0 = pg?.pos() ?: 0L
        gHold?.let { removeCallbacks(it) }
        val h = Runnable {
            if (gOn && gMode.isEmpty()) {
                gMode = "hold"
                if (gFx > 0.5f) { page?.speed(2f); if (!gWasPlaying) page?.setPlaying(true); page?.showNote("⏩ ۲×", false) } else { page?.setPlaying(false); page?.showNote("⏸", false) }
            }
        }
        gHold = h; postDelayed(h, 260)
    }
    private fun gMove(x: Float, y: Float) {
        if (!gOn) return
        lastY = y
        val dx = x - gx; val dy = y - gy
        if (gMode.isEmpty()) {
            if (Math.abs(dy) > slop * 2 && Math.abs(dy) > Math.abs(dx)) { gMode = "swipe"; gHold?.let { removeCallbacks(it) } }
            else if (Math.abs(dx) > a.dp(14) && Math.abs(dx) > Math.abs(dy)) { gMode = "scrub"; gHold?.let { removeCallbacks(it) }; page?.setPlaying(false) }
        }
        if (gMode == "scrub") {
            val pg = page ?: return; val d = pg.dur()
            if (d > 0) { val t = (gT0 + dx / Math.max(1, width) * d * 1.2f).toLong().coerceIn(0L, Math.max(0L, d - 50)); pg.seekTo(t); pg.showNote(fmt(t) + " / " + fmt(d), false); pg.big(true) }
        }
    }
    private fun gUp(cancel: Boolean) {
        if (!gOn) return
        gOn = false; gHold?.let { removeCallbacks(it) }
        val pg = page; pg?.speed(1f)
        when (gMode) {
            "hold" -> { if (gFx <= 0.5f && gWasPlaying) pg?.setPlaying(true); if (gFx > 0.5f && !gWasPlaying) pg?.setPlaying(false); pg?.hideNote() }
            "scrub" -> { pg?.big(false); pg?.hideNote(); if (gWasPlaying) pg?.setPlaying(true) }
            "swipe" -> if (!cancel) { val dy = lastY - gy; if (dy < -a.dp(70)) go(1) else if (dy > a.dp(70)) go(-1) }
            else -> if (!cancel) {
                val now = System.currentTimeMillis()
                if (now - lastTap < 300 && Math.abs(gx - lastX) < a.dp(70)) {
                    tapRun?.let { removeCallbacks(it) }; lastTap = 0
                    if (gFx < 0.3f || gFx > 0.7f) { val d = if (gFx < 0.3f) -10_000L else 10_000L; pg?.seekTo((pg.pos() + d)); pg?.showNote(if (d < 0) "⏪ ۱۰ ثانیه" else "⏩ ۱۰ ثانیه", true) }
                    else pg?.likeIt()
                } else {
                    lastTap = now; lastX = gx
                    val r = Runnable { lastTap = 0; page?.toggle() }
                    tapRun = r; postDelayed(r, 300)
                }
            }
        }
    }

    override fun onInterceptTouchEvent(e: android.view.MotionEvent): Boolean {
        when (e.action) {
            android.view.MotionEvent.ACTION_DOWN -> { ix = e.x; iy = e.y }
            android.view.MotionEvent.ACTION_MOVE -> if (!gOn && (Math.abs(e.y - iy) > slop * 2 || Math.abs(e.x - ix) > a.dp(14))) { gDown(ix, iy); gMove(e.x, e.y); return true }     // a drag that started on a button
        }
        return false
    }
    override fun onTouchEvent(e: android.view.MotionEvent): Boolean {
        when (e.action) {
            android.view.MotionEvent.ACTION_DOWN -> gDown(e.x, e.y)
            android.view.MotionEvent.ACTION_MOVE -> gMove(e.x, e.y)
            android.view.MotionEvent.ACTION_UP -> { lastY = e.y; gUp(false) }
            android.view.MotionEvent.ACTION_CANCEL -> gUp(true)
        }
        return true
    }

    fun pause() { page?.pauseNow() }
    fun resume() { page?.resumeNow() }
    fun release() { page?.release(); page = null }
}

/** the "قاب" section, built like Instagram: ＋ and title on top, stories + feed, and a bottom bar (home, reels, search, profile) */
class GhabScreen(private val a: NativeActivity) : Screen() {
    private val th = a.th
    private val g = a.ghab
    private val ui = GhabUi(a, g)
    private val root = LinearLayout(a)
    override val view: View get() = root
    private val bar = LinearLayout(a)
    private val body = FrameLayout(a)
    private val nav = LinearLayout(a)
    private var tab = "home"
    private var reels: ReelsView? = null
    private val seen = LinkedHashSet<Long>()
    private lateinit var content: LinearLayout

    init {
        root.orientation = LinearLayout.VERTICAL; root.background = th.screenBg()
        bar.gravity = Gravity.CENTER_VERTICAL; bar.setPadding(a.dp(4), 0, a.dp(4), 0); bar.setBackgroundColor(th.bar)
        bar.addView(iconButton(a, th, "plus", th.text) { newPost() })
        bar.addView(label(a, "قاب", 26f, th.text, true).also { it.gravity = Gravity.CENTER }, lp(0, WRAP).weight(1f))
        bar.addView(iconButton(a, th, "back", th.text) { a.pop() })
        root.addView(bar, lp(MATCH, a.dp(56)))
        root.addView(body, lp(MATCH, 0).weight(1f))
        nav.gravity = Gravity.CENTER_VERTICAL; nav.setBackgroundColor(th.bar); nav.setPadding(a.dp(6), a.dp(4), a.dp(6), a.dp(4))
        root.addView(View(a).also { it.setBackgroundColor(th.line) }, lp(MATCH, 1))
        root.addView(nav, lp(MATCH, a.dp(56)))
        drawNav(); openTab("home")
        g.ready { drawNav() }                 // the avatar of the profile button needs the signed-in user
    }

    private fun drawNav() {
        nav.removeAllViews()
        for ((k, glyph) in listOf("home" to "🏠", "reels" to "▶", "explore" to "🔍", "me" to "")) {
            val on = tab == k
            val c = FrameLayout(a)
            if (on) c.background = rounded(if (th.dark) 0xFF262B33.toInt() else 0xFFE8EBEF.toInt(), a.dpf(22f))
            if (k == "me") c.addView(ui.avatar(g.me?.str("username") ?: "?", g.me?.str("avatar")?.ifEmpty { null }, 28), FrameLayout.LayoutParams(WRAP, WRAP, Gravity.CENTER))
            else c.addView(label(a, glyph, if (k == "reels") 20f else 22f, th.text, on).also { it.gravity = Gravity.CENTER }, FrameLayout.LayoutParams(WRAP, WRAP, Gravity.CENTER))
            c.isClickable = true; c.setOnClickListener { openTab(k) }
            nav.addView(c, lp(0, MATCH).weight(1f).also { it.setMargins(a.dp(4), a.dp(2), a.dp(4), a.dp(2)) })
        }
    }

    private fun scrolled(): ScrollView { val sc = ScrollView(a); sc.setOnScrollChangeListener { _, _, _, _, _ -> if (tab == "home") ui.updateInline() }; content = LinearLayout(a); content.orientation = LinearLayout.VERTICAL; sc.addView(content); body.addView(sc, FrameLayout.LayoutParams(MATCH, MATCH)); return sc }
    private fun waiting() { content.addView(label(a, "در حال بارگذاری…", 14f, th.muted).also { it.setPadding(a.dp(20), a.dp(30), a.dp(20), a.dp(30)); it.gravity = Gravity.CENTER }) }

    private fun openTab(k: String) {
        tab = k; drawNav(); reels?.release(); reels = null; ui.stopInline(); body.removeAllViews(); seen.clear()
        bar.visibility = if (k == "reels") View.GONE else View.VISIBLE
        when (k) {
            "home" -> { scrolled(); waiting(); loadFeed(true) }
            "explore" -> {
                scrolled()
                val et = EditText(a).styled(th, "جستجوی کاربر (نام کاربری)…"); et.imeOptions = android.view.inputmethod.EditorInfo.IME_ACTION_SEARCH; et.setSingleLine()
                et.setOnEditorActionListener { _, _, _ -> val q = et.text.toString().trim().trimStart('@'); if (q.isNotEmpty()) a.push(GhabProfileScreen(a, q)); true }
                content.addView(et, lp(MATCH, WRAP).also { it.setMargins(a.dp(12), a.dp(8), a.dp(12), a.dp(8)) })
                waiting()
                g.api("GET", "/api/explore") { r -> if (tab != "explore") return@api; content.removeViewAt(content.childCount - 1); if (r == null) fail() else content.addView(ui.grid(lm(r)) { p -> a.push(GhabPostScreen(a, p.lng("id"))) }) }
            }
            "reels" -> { val rv = ReelsView(a, g, ui, { id -> a.push(GhabPostScreen(a, id)) }, { u -> a.push(GhabProfileScreen(a, u)) }); reels = rv; body.addView(rv, FrameLayout.LayoutParams(MATCH, MATCH)) }
            "me" -> { scrolled(); waiting(); g.ready { ok -> if (tab != "me") return@ready; content.removeAllViews(); val u = g.me?.str("username"); if (!ok || u == null) fail() else GhabProfileScreen.fill(a, g, ui, content, u, true) { a.push(GhabPostScreen(a, it)) } } }
        }
    }

    private fun fail() { content.removeAllViews(); content.addView(label(a, "به قاب وصل نشد. دوباره امتحان کن.", 14f, th.muted).also { it.setPadding(a.dp(20), a.dp(30), a.dp(20), a.dp(30)); it.gravity = Gravity.CENTER; it.isClickable = true; it.setOnClickListener { openTab(tab) } }) }

    private fun loadFeed(first: Boolean) {
        val ex = if (seen.isEmpty()) "" else "&exclude=" + seen.joinToString(",")
        g.api("GET", "/api/feed?limit=10$ex") { r ->
            if (tab != "home") return@api
            if (first) content.removeAllViews() else content.removeViewAt(content.childCount - 1)
            if (r == null) { if (first) fail(); return@api }
            val posts = lm(r)
            if (first) { val row = HorizontalScrollView(a); row.isHorizontalScrollBarEnabled = false; val box = LinearLayout(a); box.setPadding(a.dp(8), a.dp(8), a.dp(8), a.dp(8)); row.addView(box); content.addView(row); loadStories(box) }
            posts.forEach { p -> seen.add(p.lng("id")); content.addView(ui.card(p, { x -> a.push(GhabPostScreen(a, x.lng("id"))) }) { u -> a.push(GhabProfileScreen(a, u)) }) }
            if (posts.isEmpty() && first) content.addView(label(a, "هنوز پستی نیست. اولین پست رو بذار!", 14f, th.muted).also { it.setPadding(a.dp(20), a.dp(30), a.dp(20), a.dp(30)); it.gravity = Gravity.CENTER })
            content.post { if (tab == "home") ui.updateInline() }
            if (posts.size >= 10) content.addView(textButton(a, th, "نمایش بیشتر") { content.removeViewAt(content.childCount - 1); content.addView(label(a, "…", 14f, th.muted).also { it.gravity = Gravity.CENTER }); loadFeed(false) })
        }
    }

    private fun loadStories(box: LinearLayout) {
        g.api("GET", "/api/stories") { r ->
            val groups = lm(r)
            val add = LinearLayout(a); add.orientation = LinearLayout.VERTICAL; add.gravity = Gravity.CENTER_HORIZONTAL; add.setPadding(a.dp(6), 0, a.dp(6), 0)
            add.addView(label(a, "＋", 26f, th.accent, true).also { it.gravity = Gravity.CENTER; it.background = GradientDrawable().also { d -> d.shape = GradientDrawable.OVAL; d.setStroke(a.dp(2), th.accent) } }, lp(a.dp(60), a.dp(60)))
            add.addView(label(a, "استوری من", 11f, th.muted).also { it.setPadding(0, a.dp(3), 0, 0) })
            add.isClickable = true; add.setOnClickListener { g.pickAndUpload("/api/stories", "") { ok -> if (ok) openTab("home") } }
            box.addView(add)
            groups.forEachIndexed { i, grp ->
                val c = LinearLayout(a); c.orientation = LinearLayout.VERTICAL; c.gravity = Gravity.CENTER_HORIZONTAL; c.setPadding(a.dp(6), 0, a.dp(6), 0)
                c.addView(ui.avatar(grp.str("username"), grp.str("avatar").ifEmpty { null }, 54, if (grp.bool("seen")) th.badgeMuted else 0xFFE1306C.toInt()))
                c.addView(label(a, if (grp.bool("mine")) "من" else grp.str("username"), 11f, th.text).oneLine().also { it.setPadding(0, a.dp(3), 0, 0); it.maxWidth = a.dp(66) })
                c.isClickable = true; c.setOnClickListener { ui.stories(groups, i) }
                box.addView(c)
            }
        }
    }

    private fun newPost() {
        val et = EditText(a); et.hint = "کپشن (اختیاری)"; et.setPadding(a.dp(20), a.dp(14), a.dp(20), a.dp(14))
        AlertDialog.Builder(a).setTitle("پست جدید").setView(et).setPositiveButton("انتخاب عکس / ویدیو") { _, _ ->
            g.pickAndUpload("/api/posts", et.text.toString().trim()) { ok -> if (ok) openTab("home") }
        }.setNegativeButton("لغو", null).show()
    }

    override fun onShow() { reels?.resume(); if (tab == "home") ui.updateInline() }
    override fun onHide() { reels?.pause(); ui.stopInline() }
    override fun onDestroy() { reels?.release(); reels = null; ui.stopInline() }
    override fun onBack(): Boolean = false
}

/** one post with its comments */
class GhabPostScreen(private val a: NativeActivity, private val id: Long) : Screen() {
    private val th = a.th
    private val g = a.ghab
    private val ui = GhabUi(a, g)
    private val root = LinearLayout(a)
    override val view: View get() = root
    private val col = LinearLayout(a)

    init {
        root.orientation = LinearLayout.VERTICAL; root.background = th.screenBg()
        val bar = LinearLayout(a); bar.gravity = Gravity.CENTER_VERTICAL; bar.setBackgroundColor(th.bar); bar.setPadding(a.dp(4), 0, a.dp(4), 0)
        bar.addView(iconButton(a, th, "back", th.barText) { a.pop() })
        bar.addView(label(a, "پست", 18f, th.barText, true).also { it.setPadding(a.dp(8), 0, 0, 0) }, lp(0, WRAP).weight(1f))
        root.addView(bar, lp(MATCH, a.dp(56)))
        val sc = ScrollView(a); col.orientation = LinearLayout.VERTICAL; sc.addView(col); root.addView(sc, lp(MATCH, 0).weight(1f))
        val inp = LinearLayout(a); inp.gravity = Gravity.CENTER_VERTICAL; inp.setBackgroundColor(th.panel); inp.setPadding(a.dp(8), a.dp(6), a.dp(8), a.dp(6))
        val et = EditText(a).styled(th, "نظر بنویس…")
        inp.addView(et, lp(0, WRAP).weight(1f))
        inp.addView(iconButton(a, th, "send", th.accent) {
            val t = et.text.toString().trim(); if (t.isEmpty()) return@iconButton
            et.setText("")
            g.api("POST", "/api/posts/$id/comments", org.json.JSONObject().put("text", t).toString()) { load() }
        })
        root.addView(inp, lp(MATCH, WRAP))
        load()
    }

    private fun load() {
        g.api("GET", "/api/post/$id") { r ->
            val p = mm(r) ?: run { a.toast("پست باز نشد"); return@api }
            col.removeAllViews()
            col.addView(ui.card(p, null) { u -> a.push(GhabProfileScreen(a, u)) })
            val cs = lm(p["comments"])
            if (cs.isEmpty()) col.addView(label(a, "هنوز نظری نیست", 13f, th.muted).also { it.setPadding(a.dp(16), a.dp(14), a.dp(16), a.dp(14)) })
            for (c in cs) {
                val row = LinearLayout(a); row.setPadding(a.dp(12), a.dp(6), a.dp(12), a.dp(6)); row.gravity = Gravity.TOP
                if (c["parent_id"] != null) row.setPadding(a.dp(44), a.dp(6), a.dp(12), a.dp(6))
                row.addView(ui.avatar(c.str("username"), c.str("avatar").ifEmpty { null }, 32))
                val t = LinearLayout(a); t.orientation = LinearLayout.VERTICAL; t.setPadding(a.dp(10), 0, 0, 0)
                t.addView(label(a, c.str("username") + "  " + since(num(c["created"])), 12f, th.muted))
                t.addView(label(a, c.str("text"), 14f, th.text))
                row.addView(t, lp(0, WRAP).weight(1f))
                val lk = label(a, (if (c.bool("liked")) "♥ " else "♡ ") + Fmt.digits(c.lng("likes").toString()), 14f, if (c.bool("liked")) 0xFFE53950.toInt() else th.muted)
                lk.setPadding(a.dp(8), a.dp(4), a.dp(4), a.dp(4)); lk.isClickable = true
                lk.setOnClickListener { g.api("POST", "/api/comments/${c.lng("id")}/like") { load() } }
                row.addView(lk)
                col.addView(row)
            }
        }
    }
}

/** a profile: avatar, counts, follow button, grid of posts */
class GhabProfileScreen(private val a: NativeActivity, private val username: String) : Screen() {
    private val th = a.th
    private val g = a.ghab
    private val ui = GhabUi(a, g)
    private val root = LinearLayout(a)
    override val view: View get() = root

    init {
        root.orientation = LinearLayout.VERTICAL; root.background = th.screenBg()
        val bar = LinearLayout(a); bar.gravity = Gravity.CENTER_VERTICAL; bar.setBackgroundColor(th.bar); bar.setPadding(a.dp(4), 0, a.dp(4), 0)
        bar.addView(iconButton(a, th, "back", th.barText) { a.pop() })
        bar.addView(label(a, username, 18f, th.barText, true).also { it.setPadding(a.dp(8), 0, 0, 0) }, lp(0, WRAP).weight(1f))
        root.addView(bar, lp(MATCH, a.dp(56)))
        val sc = ScrollView(a); val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL; sc.addView(col); root.addView(sc, lp(MATCH, 0).weight(1f))
        fill(a, g, ui, col, username, false) { a.push(GhabPostScreen(a, it)) }
    }

    companion object {
        internal fun fill(a: NativeActivity, g: GhabClient, ui: Any, col: LinearLayout, username: String, mine: Boolean, openPost: (Long) -> Unit) {
            val u = (ui as GhabUi); val th = a.th
            g.api("GET", "/api/user/" + URLEncoder.encode(username, "UTF-8")) { r ->
                val d = mm(r) ?: run { col.removeAllViews(); col.addView(label(a, "کاربر پیدا نشد", 14f, th.muted).also { it.setPadding(a.dp(20), a.dp(30), a.dp(20), a.dp(30)) }); return@api }
                col.removeAllViews()
                val head = LinearLayout(a); head.gravity = Gravity.CENTER_VERTICAL; head.setPadding(a.dp(16), a.dp(14), a.dp(16), a.dp(6))
                head.addView(u.avatar(d.str("username"), d.str("avatar").ifEmpty { null }, 76, if (mm(d["story"]) != null) 0xFFE1306C.toInt() else 0))
                val nums = LinearLayout(a); nums.weightSum = 3f; nums.setPadding(a.dp(12), 0, 0, 0)
                for ((n, t) in listOf(lm(d["posts"]).size.toLong() to "پست", d.lng("followers") to "دنبال‌کننده", d.lng("following") to "دنبال‌شونده")) {
                    val c = LinearLayout(a); c.orientation = LinearLayout.VERTICAL; c.gravity = Gravity.CENTER
                    c.addView(label(a, Fmt.digits(n.toString()), 17f, th.text, true)); c.addView(label(a, t, 11f, th.muted))
                    nums.addView(c, lp(0, WRAP).weight(1f))
                }
                head.addView(nums, lp(0, WRAP).weight(1f)); col.addView(head)
                col.addView(label(a, d.str("name").ifEmpty { d.str("username") }, 15f, th.text, true).also { it.setPadding(a.dp(16), a.dp(4), a.dp(16), 0) })
                if (d.str("bio").isNotEmpty()) col.addView(label(a, d.str("bio"), 13f, th.text).also { it.setPadding(a.dp(16), a.dp(2), a.dp(16), 0) })
                if (!d.bool("is_me")) {
                    val fb = primaryButton(a, th, if (d.bool("followed")) "دنبال می‌کنی" else if (d.bool("requested")) "درخواست داده شد" else "دنبال کردن") {}
                    fb.setOnClickListener { g.api("POST", "/api/user/" + URLEncoder.encode(username, "UTF-8") + "/follow") { fill(a, g, ui, col, username, mine, openPost) } }
                    col.addView(fb, lp(MATCH, WRAP).also { it.setMargins(a.dp(16), a.dp(10), a.dp(16), a.dp(4)) })
                }
                if (d.bool("locked")) col.addView(label(a, "این حساب خصوصیه. برای دیدن پست‌ها دنبالش کن.", 13f, th.muted).also { it.setPadding(a.dp(16), a.dp(20), a.dp(16), a.dp(20)) })
                else col.addView(u.grid(lm(d["posts"])) { openPost(it.lng("id")) }, lp(MATCH, WRAP).also { it.topMargin = a.dp(10) })
            }
        }
    }
}
