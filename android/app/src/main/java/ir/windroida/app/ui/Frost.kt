package ir.windroida.app.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorFilter
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PixelFormat
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.drawable.Drawable
import android.os.SystemClock
import android.view.View
import android.view.ViewTreeObserver
import android.widget.LinearLayout

/** Frosted-glass helpers (the "glassmorphism" look of the web app): blur of what is behind a panel + a light tint + a thin bright edge. */
object Frost {
    /** every touch / scroll calls this: live panels keep re-capturing what is behind them for a moment */
    @Volatile var activeUntil = 0L
    fun poke() { activeUntil = SystemClock.uptimeMillis() + 1600 }

    /** fast separable box blur (2 passes ≈ gaussian) on a small bitmap */
    fun blur(src: Bitmap, r: Int, passes: Int = 2): Bitmap {
        val w = src.width; val h = src.height
        val a = IntArray(w * h); src.getPixels(a, 0, w, 0, 0, w, h)
        val b = IntArray(w * h)
        repeat(passes) { boxH(a, b, w, h, r); boxV(b, a, w, h, r) }
        val out = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888); out.setPixels(a, 0, w, 0, 0, w, h); return out
    }

    private fun boxH(s: IntArray, d: IntArray, w: Int, h: Int, r: Int) {
        val div = 2 * r + 1
        for (y in 0 until h) {
            val row = y * w
            var a = 0; var rr = 0; var g = 0; var b = 0
            for (i in -r..r) { val p = s[row + i.coerceIn(0, w - 1)]; a += p ushr 24; rr += (p shr 16) and 255; g += (p shr 8) and 255; b += p and 255 }
            for (x in 0 until w) {
                d[row + x] = ((a / div) shl 24) or ((rr / div) shl 16) or ((g / div) shl 8) or (b / div)
                val ad = s[row + (x + r + 1).coerceAtMost(w - 1)]; val sb = s[row + (x - r).coerceAtLeast(0)]
                a += (ad ushr 24) - (sb ushr 24); rr += ((ad shr 16) and 255) - ((sb shr 16) and 255)
                g += ((ad shr 8) and 255) - ((sb shr 8) and 255); b += (ad and 255) - (sb and 255)
            }
        }
    }

    private fun boxV(s: IntArray, d: IntArray, w: Int, h: Int, r: Int) {
        val div = 2 * r + 1
        for (x in 0 until w) {
            var a = 0; var rr = 0; var g = 0; var b = 0
            for (i in -r..r) { val p = s[i.coerceIn(0, h - 1) * w + x]; a += p ushr 24; rr += (p shr 16) and 255; g += (p shr 8) and 255; b += p and 255 }
            for (y in 0 until h) {
                d[y * w + x] = ((a / div) shl 24) or ((rr / div) shl 16) or ((g / div) shl 8) or (b / div)
                val ad = s[(y + r + 1).coerceAtMost(h - 1) * w + x]; val sb = s[(y - r).coerceAtLeast(0) * w + x]
                a += (ad ushr 24) - (sb ushr 24); rr += ((ad shr 16) and 255) - ((sb shr 16) and 255)
                g += ((ad shr 8) and 255) - ((sb shr 8) and 255); b += (ad and 255) - (sb and 255)
            }
        }
    }

    private var wallBlur: Bitmap? = null
    private var wallKey = ""

    /** the app background (colour / aurora / photo) blurred, at 1/8 size; the same for every panel, so all glass shows one consistent backdrop */
    fun wall(th: Theme, w: Int, h: Int): Bitmap? {
        val c = Wall.appCtx ?: return null
        if (w <= 0 || h <= 0) return null
        val key = ir.windroida.app.Prefs.wall(c) + "|" + th.dark + "|" + w + "x" + h + "|" + Wall.photoReady()
        if (key == wallKey) return wallBlur
        val sw = Math.max(2, w / 8); val sh = Math.max(2, h / 8)
        val small = Bitmap.createBitmap(sw, sh, Bitmap.Config.ARGB_8888)
        val d = Wall.appBg(th); d.setBounds(0, 0, sw, sh); d.draw(Canvas(small))
        wallBlur = blur(small, 3); wallKey = key
        return wallBlur
    }
}

/** frosted panel: blurred wallpaper (aligned with the screen, so it really looks like glass over it) + tint (flat or 2-colour gradient) + bright edge */
class FrostDrawable(private val ctx: Context, private val th: Theme, private val radii: FloatArray, private val tint: IntArray, private val edge: Int) : Drawable() {
    private val path = Path(); private val rect = RectF()
    private val pBmp = Paint(Paint.FILTER_BITMAP_FLAG or Paint.ANTI_ALIAS_FLAG)
    private val pTint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val pEdge = Paint(Paint.ANTI_ALIAS_FLAG).also { it.style = Paint.Style.STROKE; it.strokeWidth = ctx.dpf(1f) }
    private val loc = IntArray(2)

    override fun onBoundsChange(b: android.graphics.Rect) {
        rect.set(b); path.reset(); path.addRoundRect(rect, radii, Path.Direction.CW)
        pTint.shader = if (tint.size > 1) LinearGradient(b.left.toFloat(), b.top.toFloat(), b.right.toFloat(), b.bottom.toFloat(), tint, null, Shader.TileMode.CLAMP) else null
        if (tint.size == 1) pTint.color = tint[0]
    }

    override fun draw(c: Canvas) {
        var cb: Any? = callback
        while (cb is Drawable) cb = cb.callback          // inside an InsetDrawable / wrapper: walk up to the View
        val v = cb as? View
        c.save(); c.clipPath(path)
        val root = v?.rootView
        if (v != null && root != null && root.width > 0) {
            val bm = Frost.wall(th, root.width, root.height)
            if (bm != null) {
                v.getLocationInWindow(loc)
                val dx = -loc[0].toFloat() + (if (v.translationX != 0f) -v.translationX else 0f)
                c.drawBitmap(bm, null, RectF(dx, -loc[1].toFloat(), dx + root.width, -loc[1].toFloat() + root.height), pBmp)
            }
        }
        c.drawPath(path, pTint)
        c.restore()
        pEdge.color = edge; c.drawPath(path, pEdge)
    }

    override fun setAlpha(alpha: Int) {}
    override fun setColorFilter(cf: ColorFilter?) {}
    @Suppress("OVERRIDE_DEPRECATION")
    override fun getOpacity(): Int = PixelFormat.TRANSLUCENT
}

/** a bar that blurs the LIVE content behind it (list rows, photos...) so nothing shows through unreadable: real backdrop blur */
class FrostLinear(ctx: Context, private val th: Theme, private val radiusDp: Int, private val scale: Int = 6) : LinearLayout(ctx) {
    private var snap: Bitmap? = null
    private var cv: Canvas? = null
    private var capturing = false
    private var last = 0L
    private val clip = Path(); private val rect = RectF()
    private val p = Paint(Paint.FILTER_BITMAP_FLAG or Paint.ANTI_ALIAS_FLAG)
    private val loc = IntArray(2)
    private val tick = object : Runnable { override fun run() { if (isAttachedToWindow) { invalidate(); postDelayed(this, 1000) } } }
    private val pre = ViewTreeObserver.OnPreDrawListener { if (SystemClock.uptimeMillis() < Frost.activeUntil) invalidate(); true }

    init { setWillNotDraw(false) }

    override fun onAttachedToWindow() { super.onAttachedToWindow(); viewTreeObserver.addOnPreDrawListener(pre); postDelayed(tick, 1000) }
    override fun onDetachedFromWindow() { viewTreeObserver.removeOnPreDrawListener(pre); removeCallbacks(tick); super.onDetachedFromWindow() }

    override fun draw(canvas: Canvas) {
        if (capturing) return                         // we are being photographed as part of the root: leave a hole, so the blur shows what is BEHIND us
        val w = width; val h = height
        if (w > 0 && h > 0) {
            val now = SystemClock.uptimeMillis()
            if (snap == null || now - last > 45) { capture(w, h); last = now }
            val s = snap
            if (s != null) {
                val r = context.dpf(radiusDp.toFloat())
                rect.set(0f, 0f, w.toFloat(), h.toFloat()); clip.reset(); clip.addRoundRect(rect, r, r, Path.Direction.CW)
                canvas.save(); canvas.clipPath(clip); canvas.drawBitmap(s, null, rect, p); canvas.restore()
            }
        }
        super.draw(canvas)
    }

    private fun capture(w: Int, h: Int) {
        val sw = Math.max(2, w / scale); val sh = Math.max(2, h / scale)
        val old = snap
        val b: Bitmap = if (old == null || old.width != sw || old.height != sh) Bitmap.createBitmap(sw, sh, Bitmap.Config.ARGB_8888).also { snap = it; cv = Canvas(it) } else old
        val c = cv ?: return
        val root = rootView
        getLocationInWindow(loc)
        c.drawColor(th.bg)
        c.save(); c.scale(sw.toFloat() / w, sh.toFloat() / h); c.translate(-loc[0].toFloat(), -loc[1].toFloat())
        capturing = true
        try { root.draw(c) } catch (_: Exception) {} finally { capturing = false }
        c.restore()
        snap = Frost.blur(b, 2).also { cv = Canvas(it); }
    }
}
