package ir.windroida.app.ui

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.LinearLayout
import com.airbnb.lottie.LottieAnimationView
import java.util.zip.GZIPInputStream

/** Telegram's animated emoji (the "telemoji" pack: assets/emoji/<code>.tgs + map.json).
 *  A message made only of 1-3 emoji is drawn as big animated emoji: it plays once, a tap plays it again.
 *  Anything that is not in the pack (or fails to load) falls back to the normal text emoji. */
object TEmoji {
    private var map: Map<String, String>? = null
    private val ui = Handler(Looper.getMainLooper())
    private val json = HashMap<String, String>()

    private fun key(s: String) = s.replace("\uFE0F", "")

    private fun table(ctx: Context): Map<String, String> {
        map?.let { return it }
        val m = HashMap<String, String>()
        try {
            val o = org.json.JSONObject(ctx.assets.open("emoji/map.json").bufferedReader(Charsets.UTF_8).use { it.readText() })
            val ks = o.keys()
            while (ks.hasNext()) { val k = ks.next(); m[k] = o.getString(k) }
        } catch (_: Exception) {}
        map = m
        return m
    }

    /** split "😂❤️👍" into its emoji (skin tones, joiners, variation selectors and keycaps stay with their emoji) */
    fun clusters(s: String): List<String> {
        val out = ArrayList<String>()
        val cur = StringBuilder()
        var i = 0
        var joined = false
        while (i < s.length) {
            val cp = s.codePointAt(i); i += Character.charCount(cp)
            val glue = cp == 0x200D || cp == 0xFE0F || cp == 0x20E3 || cp in 0x1F3FB..0x1F3FF
            if (cur.isNotEmpty() && !glue && !joined) { out.add(cur.toString()); cur.setLength(0) }
            cur.appendCodePoint(cp)
            joined = cp == 0x200D
        }
        if (cur.isNotEmpty()) out.add(cur.toString())
        return out
    }

    /** the file names of the animations for this text, or null if any emoji is not in the pack */
    fun names(ctx: Context, text: String): List<String>? {
        val cs = clusters(text.trim())
        if (cs.isEmpty() || cs.size > 3) return null
        val t = table(ctx)
        val out = cs.map { t[key(it)] ?: return null }
        return out
    }

    private fun load(ctx: Context, name: String): String? {
        json[name]?.let { return it }
        return try {
            val s = GZIPInputStream(ctx.assets.open("emoji/$name.tgs")).bufferedReader(Charsets.UTF_8).use { it.readText() }
            synchronized(json) { if (json.size > 60) json.clear(); json[name] = s }
            s
        } catch (_: Exception) { null }
    }

    /** tap effect: copies of the emoji fly up over the whole screen (like Telegram's emoji effect) */
    fun burst(ctx: Context, anchor: View, ch: String) {
        if (ch.isEmpty()) return
        val act = ctx as? android.app.Activity ?: return
        val deco = act.window.decorView as? android.view.ViewGroup ?: return
        val ov = android.widget.FrameLayout(ctx); ov.isClickable = false; ov.isFocusable = false
        deco.addView(ov, android.view.ViewGroup.LayoutParams(android.view.ViewGroup.LayoutParams.MATCH_PARENT, android.view.ViewGroup.LayoutParams.MATCH_PARENT))
        val loc = IntArray(2); anchor.getLocationInWindow(loc)
        val cx = loc[0] + anchor.width / 2f; val cy = loc[1] + anchor.height / 2f
        val w = deco.width.toFloat()
        val rnd = java.util.Random()
        for (i in 0 until 16) {
            val tv = android.widget.TextView(ctx); tv.text = ch; tv.includeFontPadding = false
            val sz = 22f + rnd.nextFloat() * 34f
            tv.setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, sz); tv.alpha = 0f
            val box = ctx.dp(sz.toInt() * 2)
            ov.addView(tv, android.widget.FrameLayout.LayoutParams(android.widget.FrameLayout.LayoutParams.WRAP_CONTENT, android.widget.FrameLayout.LayoutParams.WRAP_CONTENT))
            tv.x = cx - box / 4f; tv.y = cy - box / 4f; tv.scaleX = 0.3f; tv.scaleY = 0.3f
            val dx = (rnd.nextFloat() - 0.5f) * w * 0.9f
            val dy = -(ctx.dp(120) + rnd.nextFloat() * Math.min(ctx.dp(420).toFloat(), cy))
            val s = 0.8f + rnd.nextFloat() * 0.9f
            tv.animate().alpha(1f).setDuration(140).setStartDelay((rnd.nextFloat() * 180).toLong()).withEndAction {
                tv.animate().translationXBy(dx).translationYBy(dy).scaleX(s).scaleY(s).rotation((rnd.nextFloat() - 0.5f) * 70f).alpha(0f)
                    .setDuration(900 + rnd.nextInt(700).toLong()).setInterpolator(android.view.animation.DecelerateInterpolator()).start()
            }.start()
        }
        ui.postDelayed({ try { deco.removeView(ov) } catch (_: Exception) {} }, 2400)
    }

    /** a row of big animated emoji, or null when the text is not drawable (the caller then shows the plain text).
     *  onTap returns true when it used the tap itself (selection mode); onLong forwards a long press to the bubble. */
    fun row(ctx: Context, text: String, onTap: () -> Boolean, onLong: () -> Unit): View? {
        val ns = names(ctx, text) ?: return null
        val cs = clusters(text.trim())
        val size = ctx.dp(if (ns.size == 1) 128 else if (ns.size == 2) 96 else 76)
        val row = LinearLayout(ctx)
        row.orientation = LinearLayout.HORIZONTAL
        row.layoutDirection = View.LAYOUT_DIRECTION_LTR
        for (n in ns) {
            val lv = LottieAnimationView(ctx)
            lv.repeatCount = 0
            val ch = cs.getOrElse(ns.indexOf(n)) { "" }
            lv.setOnClickListener { if (!onTap()) { lv.progress = 0f; lv.playAnimation(); burst(ctx, lv, ch) } }
            lv.setOnLongClickListener { onLong(); true }
            row.addView(lv, LinearLayout.LayoutParams(size, size))
            Thread {
                val j = load(ctx, n)
                if (j != null) ui.post { try { lv.setAnimationFromJson(j, n); lv.playAnimation() } catch (_: Exception) {} }
            }.start()
        }
        return row
    }
}
