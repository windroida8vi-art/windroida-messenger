package ir.windroida.app

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Shader
import android.graphics.Typeface
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.animation.LinearInterpolator
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

/** Native splash drawn on a Canvas (no images, no libraries): a dark gradient, a pulsing ring and the app name.
 *  It covers the WebView until the page is ready, so there is no white flash while the page loads. */
class SplashView(ctx: Context) : View(ctx) {
    private val bg = Paint(Paint.ANTI_ALIAS_FLAG)
    private val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 6f; color = Color.parseColor("#A855F7") }
    private val disc = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#7C3AED") }
    private val letter = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; textAlign = Paint.Align.CENTER; typeface = Typeface.DEFAULT_BOLD }
    private val title = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#E8E6F5"); textAlign = Paint.Align.CENTER; typeface = Typeface.DEFAULT_BOLD }
    private var t = 0f
    private var anim: ValueAnimator? = null

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        anim = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 1400
            repeatCount = ValueAnimator.INFINITE
            interpolator = LinearInterpolator()
            addUpdateListener { t = it.animatedValue as Float; invalidate() }
            start()
        }
    }

    override fun onDetachedFromWindow() {
        anim?.cancel()
        anim = null
        super.onDetachedFromWindow()
    }

    override fun onSizeChanged(w: Int, h: Int, ow: Int, oh: Int) {
        bg.shader = LinearGradient(0f, 0f, 0f, h.toFloat(), Color.parseColor("#0B0A14"), Color.parseColor("#1B1033"), Shader.TileMode.CLAMP)
    }

    override fun onDraw(c: Canvas) {
        val w = width.toFloat()
        val h = height.toFloat()
        c.drawRect(0f, 0f, w, h, bg)
        val cx = w / 2f
        val cy = h * 0.42f
        val r = minOf(w, h) * 0.13f
        // two rings expanding and fading out, one half a cycle behind the other
        for (k in 0..1) {
            val p = (t + k * 0.5f) % 1f
            ring.alpha = ((1f - p) * 170f).toInt().coerceIn(0, 255)
            c.drawCircle(cx, cy, r * (1f + p * 0.9f), ring)
        }
        c.drawCircle(cx, cy, r, disc)
        letter.textSize = r * 1.25f
        c.drawText("W", cx, cy + r * 0.42f, letter)
        title.textSize = minOf(w, h) * 0.06f
        c.drawText("Windroida", cx, cy + r * 2.5f, title)
    }
}

/** Native "could not connect" screen (replaces the old plain dialog). */
object ErrorUi {
    fun build(ctx: Context, onRetry: () -> Unit, onServer: () -> Unit): LinearLayout {
        val d = ctx.resources.displayMetrics.density
        fun dp(v: Int) = (v * d).toInt()
        val box = LinearLayout(ctx)
        box.orientation = LinearLayout.VERTICAL
        box.gravity = Gravity.CENTER
        box.setBackgroundColor(Color.parseColor("#0B0A14"))
        box.setPadding(dp(28), dp(28), dp(28), dp(28))
        val icon = TextView(ctx)
        icon.text = "📡"
        icon.textSize = 54f
        icon.gravity = Gravity.CENTER
        val head = TextView(ctx)
        head.tag = "head"
        head.text = "به سرور وصل نشد"
        head.setTextColor(Color.WHITE)
        head.textSize = 20f
        head.typeface = Typeface.DEFAULT_BOLD
        head.gravity = Gravity.CENTER
        head.setPadding(0, dp(12), 0, dp(6))
        val sub = TextView(ctx)
        sub.tag = "sub"
        sub.setTextColor(Color.parseColor("#B8B4D0"))
        sub.textSize = 14f
        sub.gravity = Gravity.CENTER
        sub.setPadding(0, 0, 0, dp(22))
        val retry = Button(ctx)
        retry.text = "تلاش دوباره"
        retry.setOnClickListener { onRetry() }
        val server = Button(ctx)
        server.text = "تغییر آدرس سرور"
        server.setOnClickListener { onServer() }
        val lp = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        lp.bottomMargin = dp(10)
        box.addView(icon)
        box.addView(head)
        box.addView(sub)
        box.addView(retry, lp)
        box.addView(server, lp)
        return box
    }

    fun setAddress(box: LinearLayout, address: String) {
        val sub = box.findViewWithTag<TextView>("sub")
        sub?.text = "آدرس فعلی:\n$address\n\nخودش با برگشتن شبکه دوباره تلاش می‌کنه.\nاگه آی‌پی سرور عوض شده، آدرس جدید رو وارد کن."
    }
}
