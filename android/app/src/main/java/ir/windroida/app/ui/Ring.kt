package ir.windroida.app.ui

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.view.View

/** Telegram-style round progress: a coloured disc, a white ring that fills up while a file is sent / downloaded, and a ✕ (cancel) in the middle.
 *  progress < 0 = size unknown: the ring just spins. */
class RingView(ctx: Context, var fill: Int, private val kind: String = "close") : View(ctx) {
    var progress = -1f
        set(v) { field = v; invalidate() }
    private var spin = 0f
    private val disc = Paint(Paint.ANTI_ALIAS_FLAG)
    private val ring = Paint(Paint.ANTI_ALIAS_FLAG).also { it.style = Paint.Style.STROKE; it.strokeCap = Paint.Cap.ROUND; it.color = 0xFFFFFFFF.toInt() }
    private val ic = IconDrawable(kind, 0xFFFFFFFF.toInt())
    private val box = RectF()

    override fun onDraw(c: Canvas) {
        val w = width.toFloat(); val r = w / 2f
        disc.color = fill
        c.drawCircle(r, r, r, disc)
        val sw = w * 0.07f; ring.strokeWidth = sw
        val inset = sw * 1.7f
        box.set(inset, inset, w - inset, w - inset)
        ring.alpha = 60; c.drawArc(box, 0f, 360f, false, ring); ring.alpha = 255
        spin = (spin + 5f) % 360f
        val sweep = if (progress < 0f) 100f else (360f * progress.coerceIn(0f, 1f)).coerceAtLeast(14f)
        c.drawArc(box, -90f + spin, sweep, false, ring)
        val s = (w * 0.40f).toInt(); val o = ((w - s) / 2f).toInt()
        ic.setBounds(o, o, o + s, o + s); ic.draw(c)
        if (isAttachedToWindow && visibility == VISIBLE) postInvalidateOnAnimation()      // keeps turning while it is on screen
    }
}
