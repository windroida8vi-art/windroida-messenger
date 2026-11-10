package ir.windroida.app.ui

import android.app.AlertDialog
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import ir.windroida.app.NativeActivity
import ir.windroida.app.Prefs
import ir.windroida.app.net.lng
import ir.windroida.app.net.str

/** Chat background (same choices as the web app): default, built-in colours, pictures the server owner added, the user's own pictures.
 *  The choice is kept on this phone (Prefs.wall) and drawn behind the message list of every chat. */
object Wall {
    private fun c(v: Long) = (0xFF000000L or v).toInt()
    /** name, colours (one colour = flat) */
    val presets: List<Pair<String, IntArray>> = listOf(
        "شب" to intArrayOf(c(0x0f2027), c(0x203a43), c(0x2c5364)),
        "غروب" to intArrayOf(c(0xff9966), c(0xff5e62), c(0x7b4397)),
        "جنگل" to intArrayOf(c(0x134e5e), c(0x71b280)),
        "اقیانوس" to intArrayOf(c(0x2193b0), c(0x6dd5ed)),
        "بنفش" to intArrayOf(c(0x41295a), c(0x2f0743), c(0x6a3093)),
        "ساده روشن" to intArrayOf(c(0xe9eef3)),
        "ساده تیره" to intArrayOf(c(0x10151b)),
        "شفق شیشه‌ای" to intArrayOf(c(0xa5b4fc), c(0xf9a8d4), c(0x67e8f9)),
        "شفق تیره" to intArrayOf(c(0x2a2380), c(0x6b1d6b), c(0x0b5f73)),
        "نعنا" to intArrayOf(c(0x6ee7b7), c(0x7dd3fc)),
        "غروب بنفش" to intArrayOf(c(0xfb7185), c(0x8b5cf6), c(0x1e1b4b)),
    )

    /** the choice is used behind EVERY screen (not only chats); a photo is decoded once and kept here */
    var appCtx: android.content.Context? = null
    private var bmp: android.graphics.Bitmap? = null
    private var bmpCode = ""

    /** true when the chosen photo is decoded (blur caches must be rebuilt once it is) */
    fun photoReady(): Boolean = bmp != null

    fun appBg(th: Theme): android.graphics.drawable.Drawable {
        val c = appCtx ?: return th.aurora()
        val code = Prefs.wall(c)
        if (code.isEmpty()) return th.aurora()
        if (code.startsWith("g")) return preset(code.substring(1).toIntOrNull() ?: -1) ?: th.aurora()
        val b = bmp
        return if (b != null && bmpCode == code) CoverDrawable(b, if (th.dark) 0x66000000 else 0x22FFFFFF) else th.aurora()
    }

    /** loads the chosen photo (when it is one), then [done] runs on the main thread; waits for the connection at app start */
    fun preload(a: NativeActivity, tries: Int = 0, done: () -> Unit) {
        val code = Prefs.wall(a)
        val p = path(code)
        if (p == null) { done(); return }
        val img = a.img
        if (img == null) { if (tries < 30) a.main.postDelayed({ preload(a, tries + 1, done) }, 500); return }
        if (bmp != null && bmpCode == code) { done(); return }
        img.load(p, a.mediaKey, 1280) { b -> if (b != null) { bmp = b; bmpCode = code }; done() }
    }

    fun preset(i: Int): GradientDrawable? {
        val cs = presets.getOrNull(i)?.second ?: return null
        return if (cs.size == 1) GradientDrawable().also { it.setColor(cs[0]) }
        else GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, cs)
    }

    /** server path (without the media key) of a picture background, or null for colours / default */
    fun path(code: String, small: Boolean = false): String? {
        val s = if (small) "&s=1" else ""
        return when {
            code.startsWith("srv:") -> { val p = code.substring(4).split("|"); "/wall/" + java.net.URLEncoder.encode(p[0], "UTF-8").replace("+", "%20") + "?v=" + (p.getOrNull(1) ?: "0") + s }
            code.startsWith("mine:") -> "/userwall?v=" + code.substring(5) + s
            else -> null
        }
    }

    /** draws [code] into [v]; returns true when something other than the default is shown (the list must then be see-through) */
    fun apply(a: NativeActivity, v: ImageView, code: String, small: Boolean = false, maxPx: Int = 1280): Boolean {
        v.tag = code
        v.setImageDrawable(null); v.background = null
        v.scaleType = ImageView.ScaleType.CENTER_CROP
        if (code.isEmpty()) return false
        if (code.startsWith("g")) { val d = preset(code.substring(1).toIntOrNull() ?: -1) ?: return false; v.background = d; return true }
        val p = path(code, small) ?: return false
        val img = a.img ?: return false
        v.setBackgroundColor(if (a.th.dark) 0xFF0E1621.toInt() else 0xFFDDE6EC.toInt())
        img.load(p, a.mediaKey, maxPx) { bmp -> if (v.tag == code && bmp != null) v.setImageBitmap(bmp) }
        return true
    }

    /** the picker dialog; [onChange] runs after a new background was chosen */
    fun pick(a: NativeActivity, onChange: () -> Unit) {
        val th = a.th
        val cur = Prefs.wall(a)
        val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL; col.setPadding(a.dp(12), a.dp(8), a.dp(12), a.dp(8))
        var dlg: AlertDialog? = null
        fun choose(code: String) { Prefs.setWall(a, code); dlg?.dismiss(); preload(a) { a.refreshBackgrounds(); onChange() } }
        fun group(title: String): LinearLayout {
            col.addView(label(a, title, 13f, th.accent, true).also { it.setPadding(a.dp(6), a.dp(12), a.dp(6), a.dp(4)) })
            val box = LinearLayout(a); box.orientation = LinearLayout.VERTICAL
            col.addView(box, lp(MATCH, WRAP)); return box
        }
        fun cell(code: String, selected: Boolean, text: String? = null): ImageView {
            val iv = ImageView(a); iv.clipToOutline = true
            val ring = rounded(0x00000000, a.dpf(12f)); ring.setStroke(a.dp(if (selected) 3 else 1), if (selected) th.accent else th.line)
            iv.foreground = ring
            iv.outlineProvider = object : android.view.ViewOutlineProvider() { override fun getOutline(v: View, o: android.graphics.Outline) { o.setRoundRect(0, 0, v.width, v.height, a.dpf(12f)) } }
            if (code.isEmpty()) { iv.setBackgroundColor(th.chatBg); iv.setImageDrawable(null) } else apply(a, iv, code, small = true, maxPx = 240)
            iv.isClickable = true; iv.pressScale(0.92f)
            iv.setOnClickListener { choose(code) }
            if (code.startsWith("mine:")) iv.setOnLongClickListener {
                AlertDialog.Builder(a).setMessage("این عکس پس‌زمینه حذف بشه؟").setPositiveButton("حذف") { _, _ ->
                    val v = code.substring(5).toLongOrNull() ?: return@setPositiveButton
                    a.rpc("userwall_remove", mapOf("v" to v)) { ok, r ->
                        if (!ok) { a.toast(r.str("error", "حذف نشد")); return@rpc }
                        a.api?.walls = (r["walls"] as? List<*>)?.mapNotNull { (it as? Number)?.toLong() } ?: emptyList()
                        if (Prefs.wall(a) == code) Prefs.setWall(a, "")
                        dlg?.dismiss(); a.refreshBackgrounds(); onChange(); pick(a, onChange)
                    }
                }.setNegativeButton("نه", null).show(); true
            }
            return iv
        }
        fun fill(box: LinearLayout, codes: List<String>) {
            var row: LinearLayout? = null
            codes.forEachIndexed { i, code ->
                if (i % 4 == 0) { row = LinearLayout(a); box.addView(row, lp(MATCH, a.dp(76)).also { it.topMargin = a.dp(6) }) }
                row!!.addView(cell(code, code == cur), lp(0, MATCH).also { it.weight = 1f; it.marginStart = a.dp(3); it.marginEnd = a.dp(3) })
            }
            val rest = (4 - codes.size % 4) % 4
            for (k in 0 until rest) row?.addView(View(a), lp(0, MATCH).also { it.weight = 1f })
        }
        val add = label(a, "➕  عکس از گوشی (نگه داشتن روی عکس خودت = حذف)", 14f, th.accent, true)
        add.setPadding(a.dp(8), a.dp(10), a.dp(8), a.dp(10)); add.isClickable = true
        add.setOnClickListener {
            a.pickResult(android.content.Intent(android.content.Intent.ACTION_GET_CONTENT).setType("image/*").addCategory(android.content.Intent.CATEGORY_OPENABLE)) { res, data ->
                val u = data?.data
                if (res != android.app.Activity.RESULT_OK || u == null) return@pickResult
                a.toast("در حال ذخیره…")
                Thread {
                    var err: String? = null; var v = 0L
                    try {
                        val opt = android.graphics.BitmapFactory.Options(); opt.inJustDecodeBounds = true
                        a.contentResolver.openInputStream(u)!!.use { android.graphics.BitmapFactory.decodeStream(it, null, opt) }
                        var ss = 1; while (Math.max(opt.outWidth, opt.outHeight) / ss > 2560) ss *= 2
                        val o2 = android.graphics.BitmapFactory.Options(); o2.inSampleSize = ss
                        var bmp = a.contentResolver.openInputStream(u)!!.use { android.graphics.BitmapFactory.decodeStream(it, null, o2) } ?: throw java.io.IOException("عکس خونده نشد")
                        val k = Math.min(1f, 1280f / Math.max(bmp.width, bmp.height))
                        if (k < 1f) bmp = android.graphics.Bitmap.createScaledBitmap(bmp, Math.round(bmp.width * k), Math.round(bmp.height * k), true)
                        val bo = java.io.ByteArrayOutputStream(); bmp.compress(android.graphics.Bitmap.CompressFormat.JPEG, 82, bo)
                        val bytes = bo.toByteArray()
                        val h = a.http ?: throw java.io.IOException("به سرور وصل نیستی")
                        val r = h.upload("/userwall?" + h.q("k" to a.mediaKey), java.io.ByteArrayInputStream(bytes), bytes.size.toLong())
                        v = r.lng("v"); if (v == 0L) throw java.io.IOException(r.str("error", "ذخیره نشد"))
                    } catch (e: Exception) { err = e.message ?: "ذخیره نشد" }
                    a.main.post {
                        if (err != null) { a.toast(err!!); return@post }
                        a.api?.walls = listOf(v) + (a.api?.walls ?: emptyList()).filter { it != v }
                        Prefs.setWall(a, "mine:$v"); dlg?.dismiss(); preload(a) { a.refreshBackgrounds(); onChange() }
                    }
                }.start()
            }
        }
        col.addView(add)
        fill(group("رنگ‌ها"), listOf("") + presets.indices.map { "g$it" })
        val own = a.api?.walls ?: emptyList()
        if (own.isNotEmpty()) fill(group("عکس‌های خودت"), own.map { "mine:$it" })
        val srvBox = group("عکس‌های سرور")
        val sv = ScrollView(a); sv.addView(col)
        dlg = AlertDialog.Builder(a).setTitle("پس‌زمینه برنامه").setView(sv).setNegativeButton("بستن", null).show()
        a.rpc("wallpaper_list") { ok, r ->
            if (!ok) return@rpc
            @Suppress("UNCHECKED_CAST")
            val l = (r["walls"] as? List<*>)?.mapNotNull { it as? Map<String, Any?> } ?: return@rpc
            val codes = l.map { "srv:" + it["name"] + "|" + ((it["v"] as? Number)?.toLong() ?: 0L) }
            if (codes.isEmpty()) srvBox.addView(label(a, "هنوز عکسی اضافه نشده", 13f, th.muted)) else fill(srvBox, codes)
        }
    }
}

/** a photo painted "cover" (centre-cropped to fill) with a light/dark veil so text stays readable */
class CoverDrawable(private val b: android.graphics.Bitmap, private val veil: Int) : android.graphics.drawable.Drawable() {
    private val p = android.graphics.Paint(android.graphics.Paint.FILTER_BITMAP_FLAG or android.graphics.Paint.ANTI_ALIAS_FLAG)
    override fun draw(c: android.graphics.Canvas) {
        val r = bounds
        val k = Math.max(r.width().toFloat() / b.width, r.height().toFloat() / b.height)
        val w = b.width * k; val h = b.height * k
        val l = r.left + (r.width() - w) / 2f; val t = r.top + (r.height() - h) / 2f
        c.save(); c.clipRect(r); c.drawBitmap(b, null, android.graphics.RectF(l, t, l + w, t + h), p); c.drawColor(veil); c.restore()
    }
    override fun setAlpha(alpha: Int) {}
    override fun setColorFilter(cf: android.graphics.ColorFilter?) {}
    @Suppress("OVERRIDE_DEPRECATION")
    override fun getOpacity(): Int = android.graphics.PixelFormat.OPAQUE
}
