package ir.windroida.app.ui

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.text.SpannableString
import android.view.Gravity
import android.view.View
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import ir.windroida.app.NativeActivity
import ir.windroida.app.net.bool
import ir.windroida.app.net.int
import ir.windroida.app.net.list
import ir.windroida.app.net.lng
import ir.windroida.app.net.map
import ir.windroida.app.net.str

/** A linear layout that never gets wider than [maxPx] (bubbles are at most ~78% of the screen). */
class MaxWidthLayout(ctx: Context, var maxPx: Int) : LinearLayout(ctx) {
    override fun onMeasure(w: Int, h: Int) {
        val mode = View.MeasureSpec.getMode(w)
        val size = View.MeasureSpec.getSize(w)
        val cap = if (mode == View.MeasureSpec.UNSPECIFIED) maxPx else Math.min(size, maxPx)
        super.onMeasure(View.MeasureSpec.makeMeasureSpec(cap, if (mode == View.MeasureSpec.EXACTLY) View.MeasureSpec.AT_MOST else View.MeasureSpec.AT_MOST), h)
    }
}

/** Play button + 40 bars (the recorded waveform) + duration; the played part is drawn in the accent color. */
interface PlayView { fun set(progress: Float, playing: Boolean); fun showLoading(v: Float) }

class VoiceView(ctx: Context, private val th: Theme, private val mine: Boolean, private val wave: IntArray, private val dur: Long, private var unplayed: Boolean) : View(ctx), PlayView {
    private val p = Paint(Paint.ANTI_ALIAS_FLAG)
    private val tp = Paint(Paint.ANTI_ALIAS_FLAG).also { it.textSize = ctx.dpf(11f) }
    var progress = 0f
    var playing = false
    var loading = -1f           // -1 = file is here, 0..1 = downloading
    private val ic = IconDrawable("play", 0xFFFFFFFF.toInt())
    private val icPause = IconDrawable("pause", 0xFFFFFFFF.toInt())
    private val icDown = IconDrawable("download", 0xFFFFFFFF.toInt())

    override fun set(progress: Float, playing: Boolean) { this.progress = progress; this.playing = playing; if (playing) unplayed = false; invalidate() }
    override fun showLoading(v: Float) { loading = v; invalidate() }

    override fun onMeasure(w: Int, h: Int) { setMeasuredDimension(context.dp(210), context.dp(40)) }

    override fun onDraw(c: Canvas) {
        val d = context.dp(1).toFloat()
        val r = height / 2f
        p.style = Paint.Style.FILL
        p.color = th.accentFill
        c.drawCircle(r, r, r - d, p)
        val box = (r * 0.9f).toInt()
        val dr = if (loading >= 0f) icDown else if (playing) icPause else ic
        dr.setBounds((r - box / 2f).toInt(), (r - box / 2f).toInt(), (r + box / 2f).toInt(), (r + box / 2f).toInt())
        dr.draw(c)
        if (loading >= 0f) {
            p.style = Paint.Style.STROKE; p.strokeWidth = 2 * d; p.color = 0xFFFFFFFF.toInt()
            c.drawArc(RectF(d * 2, d * 2, height - d * 2, height - d * 2), -90f, 360f * loading, false, p)
        }
        val x0 = height + 8 * d
        val x1 = width - 4 * d
        val n = wave.size
        val bw = (x1 - x0) / n
        p.style = Paint.Style.FILL
        for (i in 0 until n) {
            val lv = Math.max(2, wave[i])
            val bh = (lv / 31f) * (height * 0.55f)
            val done = (i + 0.5f) / n <= progress
            p.color = if (done) th.accentFill else if (mine) th.mineMeta else th.muted
            val cx = x0 + i * bw
            c.drawRoundRect(RectF(cx + bw * 0.15f, height * 0.4f - bh / 2f, cx + bw * 0.8f, height * 0.4f + bh / 2f), d, d, p)
        }
        tp.color = if (mine) th.mineMeta else th.muted
        c.drawText(Fmt.duration(dur), x0, height - 2 * d, tp)
        if (unplayed && !mine) { p.color = th.accentFill; c.drawCircle(x0 + context.dp(38).toFloat(), height - 6 * d, 2.5f * d, p) }
    }
}

/** A song / audio file: round play button, name, progress line, size. Plays inside the app (no video player). */
class AudioView(ctx: Context, private val th: Theme, private val mine: Boolean, private val name: String, private val size: Long, private val dur: Long, private val onSeek: (Float) -> Unit) : View(ctx), PlayView {
    private val p = Paint(Paint.ANTI_ALIAS_FLAG)
    private val tp = Paint(Paint.ANTI_ALIAS_FLAG)
    var progress = 0f
    var playing = false
    var loading = -1f
    private val ic = IconDrawable("play", 0xFFFFFFFF.toInt())
    private val icPause = IconDrawable("pause", 0xFFFFFFFF.toInt())
    private val icDown = IconDrawable("download", 0xFFFFFFFF.toInt())
    override fun set(progress: Float, playing: Boolean) { if (!seeking) this.progress = progress; this.playing = playing; invalidate() }
    override fun showLoading(v: Float) { loading = v; invalidate() }
    override fun onMeasure(w: Int, h: Int) { setMeasuredDimension(context.dp(230), context.dp(52)) }
    private var seeking = false
    private var x0d = 0f; private var y0d = 0f; private var longFired = false
    private val slop = android.view.ViewConfiguration.get(ctx).scaledTouchSlop
    private val longPress = Runnable { longFired = true; (parent as? View)?.performLongClick() }
    private fun frac(e: android.view.MotionEvent): Float { val x0 = height + context.dp(10).toFloat(); val x1 = width - context.dp(4).toFloat(); return ((e.x - x0) / (x1 - x0)).coerceIn(0f, 1f) }
    /** the whole area right of the round button is a scrub area (like Telegram): drag sideways to seek, tap = play / pause, hold = menu */
    override fun onTouchEvent(e: android.view.MotionEvent): Boolean {
        when (e.actionMasked) {
            android.view.MotionEvent.ACTION_DOWN -> {
                if (e.x <= height) return false                  // the round button: the bubble handles it
                x0d = e.x; y0d = e.y; longFired = false; seeking = false
                postDelayed(longPress, android.view.ViewConfiguration.getLongPressTimeout().toLong())
                return true
            }
            android.view.MotionEvent.ACTION_MOVE -> {
                if (!seeking && !longFired && Math.abs(e.x - x0d) > slop && Math.abs(e.x - x0d) > Math.abs(e.y - y0d)) {
                    seeking = true; removeCallbacks(longPress); parent?.requestDisallowInterceptTouchEvent(true)
                    performHapticFeedback(android.view.HapticFeedbackConstants.CLOCK_TICK)
                }
                if (seeking) { progress = frac(e); invalidate() }
                return true
            }
            android.view.MotionEvent.ACTION_UP -> {
                removeCallbacks(longPress)
                if (seeking) { seeking = false; val f = frac(e); invalidate(); onSeek(f) }
                else if (!longFired) (parent as? View)?.performClick()
                return true
            }
            android.view.MotionEvent.ACTION_CANCEL -> { removeCallbacks(longPress); if (seeking) { seeking = false; invalidate() } ; return true }
        }
        return super.onTouchEvent(e)
    }
    override fun onDraw(c: Canvas) {
        val d = context.dp(1).toFloat()
        val r = height / 2f
        p.style = Paint.Style.FILL; p.color = th.accentFill
        c.drawCircle(r, r, r - d, p)
        val box = (r * 0.9f).toInt()
        val dr = if (loading >= 0f) icDown else if (playing) icPause else ic
        dr.setBounds((r - box / 2f).toInt(), (r - box / 2f).toInt(), (r + box / 2f).toInt(), (r + box / 2f).toInt()); dr.draw(c)
        if (loading >= 0f) { p.style = Paint.Style.STROKE; p.strokeWidth = 2 * d; p.color = 0xFFFFFFFF.toInt(); c.drawArc(RectF(d * 2, d * 2, height - d * 2, height - d * 2), -90f, 360f * loading, false, p); p.style = Paint.Style.FILL }
        val x0 = height + 10 * d; val x1 = width - 4 * d
        tp.color = if (mine) th.mineText else th.text; tp.textSize = context.dpf(15f); tp.isFakeBoldText = true
        val shown = android.text.TextUtils.ellipsize(name, android.text.TextPaint(tp), x1 - x0, android.text.TextUtils.TruncateAt.END).toString()
        c.drawText(shown, x0, height * 0.40f, tp)
        // progress line
        val y = height * 0.58f
        val lh = if (seeking) 5 * d else 3 * d
        p.color = if (mine) th.mineMeta else th.muted; p.alpha = 90
        c.drawRoundRect(RectF(x0, y, x1, y + lh), d, d, p)
        p.alpha = 255; p.color = th.accentFill
        c.drawRoundRect(RectF(x0, y, x0 + (x1 - x0) * progress, y + lh), d, d, p)
        if (playing || seeking || progress > 0f) c.drawCircle(x0 + (x1 - x0) * progress, y + lh / 2f, if (seeking) 7 * d else 4.5f * d, p)
        if (seeking && dur > 0) {                                   // the time under the finger
            val t = Fmt.duration((dur * progress).toLong()); val tw = tp.measureText(t)
            val cx = (x0 + (x1 - x0) * progress).coerceIn(x0 + tw / 2f + 6 * d, x1 - tw / 2f - 6 * d)
            p.color = th.accentFill; c.drawRoundRect(RectF(cx - tw / 2f - 6 * d, y - 26 * d, cx + tw / 2f + 6 * d, y - 6 * d), 8 * d, 8 * d, p)
            val old = tp.color; tp.color = 0xFFFFFFFF.toInt(); c.drawText(t, cx - tw / 2f, y - 12 * d, tp); tp.color = old
        }
        tp.isFakeBoldText = false; tp.textSize = context.dpf(11f); tp.color = if (mine) th.mineMeta else th.muted
        val now = if (dur > 0 && (playing || progress > 0f)) Fmt.duration((dur * progress).toLong()) + " / " else ""
        c.drawText(if (dur > 0) now + Fmt.duration(dur) + "  ·  " + Fmt.size(size) else Fmt.size(size), x0, height * 0.88f, tp)
    }
}

/** Builds one chat row (day divider, system line or bubble). The screen answers the taps through [Host]. */
class Bubbles(private val a: NativeActivity, private val th: Theme) {
    interface Host {
        fun redraw(id: Long)
        fun reply(m: Map<String, Any?>)
        val myId: Long
        val isGroup: Boolean
        val peerRead: Long
        fun replyClicked(id: Long)
        fun fileClicked(m: Map<String, Any?>)
        fun menu(m: Map<String, Any?>)
        fun react(m: Map<String, Any?>, e: String)
        fun downloadProgress(id: Long): Float
        fun voiceView(id: Long, v: PlayView)
        fun seek(id: Long, frac: Float)
        fun voiceState(id: Long): Pair<Float, Boolean>
        /** multi-select (forward/delete several messages at once): while true, a tap on any bubble toggles it
         * instead of opening it / reacting, and [row] draws the little checkbox circle. */
        val selecting: Boolean
        fun isSelected(id: Long): Boolean
        fun toggleSelect(id: Long)
    }

    private val screenW = a.resources.displayMetrics.widthPixels
    private val maxW = (screenW * 0.78f).toInt()
    private val nameColors = intArrayOf(0xFFE17076.toInt(), 0xFFEB9D52.toInt(), 0xFFA695E7.toInt(), 0xFF6AB35E.toInt(), 0xFF4FB4C6.toInt(), 0xFF65AADD.toInt(), 0xFFEE7AAE.toInt())

    fun dayDivider(text: String): View = pill(text, th.muted, if (th.dark) 0x3317212B else 0x55FFFFFF)

    fun unreadDivider(): View {
        val t = label(a, "پیام‌های خوانده‌نشده", 13f, th.accent, true)
        t.gravity = Gravity.CENTER
        t.setBackgroundColor(if (th.dark) 0x331F2C3A else 0x44FFFFFF)
        t.setPadding(0, a.dp(6), 0, a.dp(6))
        return t
    }

    private fun pill(text: String, color: Int, bg: Int): View {
        val box = FrameLayout(a)
        val t = label(a, text, 13f, color, true)
        t.background = rounded(bg, a.dpf(12f)); t.setPadding(a.dp(10), a.dp(3), a.dp(10), a.dp(3))
        box.addView(t, FrameLayout.LayoutParams(WRAP, WRAP, Gravity.CENTER))
        box.setPadding(0, a.dp(6), 0, a.dp(4))
        return box
    }

    fun row(m: Map<String, Any?>, h: Host): View {
        if (m.str("kind") == "system") return pill(m.str("body"), th.muted, if (th.dark) 0x3317212B else 0x55FFFFFF)
        val mine = m.lng("sender_id") == h.myId
        val outer = LinearLayout(a)
        outer.layoutDirection = View.LAYOUT_DIRECTION_LTR
        outer.gravity = if (mine) Gravity.END else Gravity.START
        outer.setPadding(a.dp(8) + (if (h.selecting && !m.bool("deleted")) a.dp(28) else 0), a.dp(2), a.dp(8), a.dp(2))
        outer.addView(bubble(m, h, mine))
        if (m.bool("deleted")) return outer
        // behind the row waits the reply arrow that the swipe gesture reveals
        val root = FrameLayout(a)
        val ar = icon(a, "reply", th.accent, 24); ar.alpha = 0f; ar.tag = "swipe-arrow"
        root.addView(ar, FrameLayout.LayoutParams(a.dp(24), a.dp(24), Gravity.END or Gravity.CENTER_VERTICAL).also { it.rightMargin = a.dp(14) })
        root.addView(outer, FrameLayout.LayoutParams(MATCH, WRAP))
        if (h.selecting) {
            val id = m.lng("id")
            val on = h.isSelected(id)
            val dot = View(a)
            dot.background = android.graphics.drawable.GradientDrawable().also {
                it.shape = android.graphics.drawable.GradientDrawable.OVAL
                if (on) it.setColor(th.accent) else { it.setColor(android.graphics.Color.TRANSPARENT); it.setStroke(a.dp(2), th.accent) }
            }
            root.addView(dot, FrameLayout.LayoutParams(a.dp(20), a.dp(20), Gravity.START or Gravity.CENTER_VERTICAL).also { it.leftMargin = a.dp(10) })
        }
        return root
    }

    private fun bubble(m: Map<String, Any?>, h: Host, mine: Boolean): View {
        val b = MaxWidthLayout(a, maxW)
        b.orientation = LinearLayout.VERTICAL
        val big = Stickers.parse(m.str("body"))
        val bigEmoji = big == null && m.map("file") == null && isEmojiOnly(m.str("body"))
        val bg = if (big != null || bigEmoji) 0 else if (mine) th.mine else th.theirs
        if (bg != 0) b.background = th.bubbleBg(a, mine)
        val pad = if (bg == 0) 0 else a.dp(8)
        b.setPadding(pad + a.dp(2), pad - a.dp(2) + a.dp(2), pad + a.dp(2), a.dp(4))
        val textColor = if (mine) th.mineText else th.text
        val meta = if (mine) th.mineMeta else th.muted

        if (m.bool("deleted")) {
            b.addView(label(a, "پیام حذف شده", 14f, meta).also { it.typeface = Typeface.create(Typeface.DEFAULT, Typeface.ITALIC) })
            b.addView(metaRow(m, h, mine, meta))
            return b
        }
        val fwd = m.str("fwd")
        if (fwd.isNotEmpty()) b.addView(label(a, "ارسال‌شده از $fwd", 12f, th.accent, true).also { it.setPadding(0, 0, 0, a.dp(2)) })
        if (h.isGroup && !mine && bg != 0) {
            val nm = m.str("sender_name")
            if (nm.isNotEmpty()) b.addView(label(a, nm, 13f, nameColors[(Math.abs(m.lng("sender_id")) % nameColors.size).toInt()], true).oneLine().also { it.setPadding(0, 0, 0, a.dp(2)) })
        }
        m.map("reply")?.let { r -> b.addView(quote(r, h, mine)) }

        val f = m.map("file")
        if (f != null) addFile(b, m, f, h, mine, textColor, meta)
        if (m.map("game") != null) {
            val g = label(a, "♟ بازی — برای بازکردن بزن (توی وب باز می‌شه)", 15f, th.accent, true); g.setPadding(0, a.dp(4), 0, a.dp(4))
            b.addView(g)
        }
        if (m.map("poll") != null) {
            b.addView(a.polls.card(m, textColor, meta) { h.redraw(m.lng("id")) })
        } else if (big != null) {
            val st = label(a, Stickers.EMOJI[big] ?: "", 72f, textColor).also { it.setPadding(a.dp(4), 0, a.dp(4), 0) }
            wobble(st, big)
            b.addView(st)
        } else if (bigEmoji) {
            val anim = TEmoji.row(a, m.str("body"), { if (h.selecting) { h.toggleSelect(m.lng("id")); true } else false }, { b.performLongClick() })
            b.addView(anim ?: label(a, m.str("body"), 44f, textColor))
        } else {
            val body = m.str("body")
            if (body.isNotEmpty() && !(f != null && f.bool("voice") && body.isEmpty())) {
                val t = label(a, "", 16f, textColor)
                t.text = SpannableString(Md.render(body, if (th.dark) 0x44FFFFFF else 0x22000000, th.accent))
                t.includeFontPadding = true
                t.setLineSpacing(0f, 1.05f)
                b.addView(t)
            }
        }
        linkCard(m.str("body"), mine)?.let { b.addView(it) }
        b.addView(metaRow(m, h, mine, meta))
        val rx = m.list("reactions")
        if (rx.isNotEmpty()) b.addView(reactions(m, rx, h, mine))
        b.isClickable = true
        b.setOnClickListener { if (h.selecting) h.toggleSelect(m.lng("id")) else onTap(m, h) }
        b.setOnLongClickListener { if (h.selecting) h.toggleSelect(m.lng("id")) else { pop(b); h.menu(m) }; true }
        if (!h.selecting) gestures(b, m, h)
        return b
    }

    /** stickers come alive: a small wobble / hop every time the row appears on screen, and again when tapped */
    private fun wobble(v: View, kind: String) {
        val hop = kind in setOf("laugh", "rofl", "party", "clap", "grin", "fire", "thumbs")
        val go = {
            v.animate().cancel(); v.rotation = 0f; v.translationY = 0f; v.scaleX = 0.6f; v.scaleY = 0.6f
            v.pivotX = v.width / 2f; v.pivotY = v.height.toFloat()
            v.animate().scaleX(1f).scaleY(1f).setDuration(260).setInterpolator(android.view.animation.OvershootInterpolator(3f)).withEndAction {
                val set = android.animation.AnimatorSet()
                val a1 = if (hop) android.animation.ObjectAnimator.ofFloat(v, "translationY", 0f, -a.dpf(14f), 0f, -a.dpf(7f), 0f)
                         else android.animation.ObjectAnimator.ofFloat(v, "rotation", 0f, -10f, 10f, -6f, 6f, 0f)
                a1.duration = 700; set.play(a1); set.start()
            }.start()
        }
        v.addOnAttachStateChangeListener(object : View.OnAttachStateChangeListener {
            override fun onViewAttachedToWindow(x: View) { x.post(go) }
            override fun onViewDetachedFromWindow(x: View) { x.animate().cancel(); x.scaleX = 1f; x.scaleY = 1f; x.rotation = 0f; x.translationY = 0f }
        })
        v.isClickable = true
        v.setOnClickListener { go() }
    }

    /** a card for the first link of a message: coloured bar, site name, the address. (Nothing is fetched from the site, so it works with the national network and leaks nothing.) */
    private fun linkCard(body: String, mine: Boolean): View? {
        val url = Regex("https?://[^\\s]+").find(body)?.value ?: return null
        val uri = try { android.net.Uri.parse(url) } catch (_: Exception) { return null }
        val host = (uri.host ?: return null).removePrefix("www.")
        // links to this server's own services get their own name + icon
        val own = a.api?.cfg?.host == uri.host && uri.port > 0
        var badge = host.take(1).uppercase(); var title = host
        var subLine = ChatText.short(url.removePrefix("https://").removePrefix("http://"), 44)
        if (own && uri.port == 8082) { badge = "☁️"; title = "فضای ابری"; subLine = "باز کردن در فضای ابری" }
        else if (own && uri.port == 8084) { badge = "🖼"; title = "قاب (Ghab)"; subLine = Regex("^/p/(\\d+)").find(uri.path ?: "")?.let { "پست " + Fmt.digits(it.groupValues[1]) + "؛ برای دیدن بزن" } ?: "باز کردن در قاب" }
        val box = LinearLayout(a); box.orientation = LinearLayout.HORIZONTAL
        box.background = rounded(if (mine) (if (th.dark) 0x33FFFFFF else 0x1A000000) else (if (th.dark) 0x22FFFFFF else 0x0F000000), a.dpf(8f))
        val bar = View(a); bar.setBackgroundColor(th.accent)
        box.addView(bar, LinearLayout.LayoutParams(a.dp(3), MATCH))
        val ic = FrameLayout(a); ic.background = rounded(th.accentFill, a.dpf(18f))
        ic.addView(label(a, badge, 16f, 0xFFFFFFFF.toInt(), true).also { it.gravity = Gravity.CENTER }, FrameLayout.LayoutParams(MATCH, MATCH))
        box.addView(ic, LinearLayout.LayoutParams(a.dp(36), a.dp(36)).also { it.setMargins(a.dp(8), a.dp(8), 0, a.dp(8)) })
        val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL; col.setPadding(a.dp(10), a.dp(6), a.dp(8), a.dp(6))
        col.addView(label(a, title, 14f, th.accent, true).oneLine())
        col.addView(label(a, subLine, 12f, th.muted).oneLine())
        box.addView(col, LinearLayout.LayoutParams(0, WRAP, 1f))
        box.setOnClickListener {
            // a Ghab post / profile sent in a chat opens inside the native Ghab screens
            val gp = if (own && uri.port == 8084) Regex("^/p/(\\d+)").find(uri.path ?: "")?.groupValues?.get(1)?.toLongOrNull() else null
            val gu = if (own && uri.port == 8084) Regex("^/u/([^/]+)").find(uri.path ?: "")?.groupValues?.get(1) else null
            if (gp != null) a.openGhabWeb("/p/$gp")
            else if (gu != null) a.openGhabWeb("/u/" + java.net.URLEncoder.encode(java.net.URLDecoder.decode(gu, "UTF-8"), "UTF-8"))
            else try { a.startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW, uri)) } catch (_: Exception) {}
        }
        box.pressScale(0.97f)
        return box.also { it.layoutParams = LinearLayout.LayoutParams(MATCH, WRAP).also { p -> p.topMargin = a.dp(4) } }
    }

    private fun isEmojiOnly(t: String): Boolean {
        val s = t.trim()
        if (s.isEmpty() || s.length > 8) return false
        var i = 0; var n = 0
        while (i < s.length) {
            val cp = s.codePointAt(i); i += Character.charCount(cp)
            if (cp == 0x200D || cp == 0xFE0F || cp in 0x1F3FB..0x1F3FF) continue
            val ok = cp in 0x1F300..0x1FAFF || cp in 0x2600..0x27BF || cp in 0x1F000..0x1F2FF || cp == 0x2B50 || cp == 0x2764
            if (!ok) return false
            n++
        }
        return n in 1..3
    }

    /** finger gestures like Telegram / the web app: swipe the message to the left = reply (the row follows the finger, an arrow appears,
     *  a short buzz tells when it will trigger); double tap on a plain message = 👍 */
    @android.annotation.SuppressLint("ClickableViewAccessibility")
    private fun gestures(b: View, m: Map<String, Any?>, h: Host) {
        if (m.bool("deleted") || m.str("kind") == "system") return
        val slop = android.view.ViewConfiguration.get(a).scaledTouchSlop
        val trigger = a.dpf(64f); val maxDx = a.dpf(96f)
        val plain = m.map("file") == null && m.map("poll") == null && m.map("game") == null && !Regex("https?://").containsMatchIn(m.str("body"))
        var x0 = 0f; var y0 = 0f; var dx = 0f; var mode = 0      // 0 idle, 1 undecided, 2 swiping, 3 not ours
        var buzzed = false
        var arrow: View? = null
        val gd = if (plain) android.view.GestureDetector(a, object : android.view.GestureDetector.SimpleOnGestureListener() {
            override fun onDown(e: android.view.MotionEvent) = true
            override fun onDoubleTap(e: android.view.MotionEvent): Boolean { h.react(m, "👍"); pop(b); return true }
        }) else null
        b.setOnTouchListener { v, e ->
            gd?.onTouchEvent(e)
            val row = v.parent as? View ?: return@setOnTouchListener false
            when (e.actionMasked) {
                android.view.MotionEvent.ACTION_DOWN -> { x0 = e.rawX; y0 = e.rawY; dx = 0f; mode = 1; buzzed = false; row.animate().cancel() }
                android.view.MotionEvent.ACTION_MOVE -> if (mode == 1 || mode == 2) {
                    val mx = e.rawX - x0; val my = e.rawY - y0
                    if (mode == 1) {
                        if (Math.abs(my) > slop && Math.abs(my) > Math.abs(mx)) mode = 3
                        else if (mx < -slop && Math.abs(mx) > Math.abs(my) * 1.4f) { mode = 2; v.parent?.requestDisallowInterceptTouchEvent(true); v.cancelLongPress() }
                    }
                    if (mode == 2) {
                        dx = Math.max(-maxDx, Math.min(0f, mx))
                        row.translationX = dx
                        if (arrow == null) arrow = (row.parent as? FrameLayout)?.findViewWithTag<View>("swipe-arrow")
                        val k = Math.min(1f, -dx / trigger)
                        arrow?.alpha = k; arrow?.scaleX = 0.5f + 0.5f * k; arrow?.scaleY = 0.5f + 0.5f * k
                        if (-dx >= trigger && !buzzed) { buzzed = true; v.performHapticFeedback(android.view.HapticFeedbackConstants.KEYBOARD_TAP) }
                        if (-dx < trigger) buzzed = false
                    }
                }
                android.view.MotionEvent.ACTION_UP, android.view.MotionEvent.ACTION_CANCEL -> {
                    if (mode == 2) {
                        val go = -dx >= trigger && e.actionMasked == android.view.MotionEvent.ACTION_UP
                        row.animate().translationX(0f).setDuration(180).setInterpolator(android.view.animation.OvershootInterpolator(1.4f)).withEndAction { arrow?.alpha = 0f; arrow = null }.start()
                        if (go) h.reply(m)
                        mode = 0
                        return@setOnTouchListener true           // swallow: no click after a swipe
                    }
                    mode = 0
                }
            }
            false
        }
    }

    /** small bounce used when a reaction is given with a double tap */
    private fun pop(v: View) {
        v.animate().cancel(); v.scaleX = 1f; v.scaleY = 1f
        v.animate().scaleX(1.06f).scaleY(1.06f).setDuration(90).withEndAction { v.animate().scaleX(1f).scaleY(1f).setDuration(160).setInterpolator(android.view.animation.OvershootInterpolator(3f)).start() }.start()
    }

    /** links of this very server: invites are handled here, rooms / games open the web app once (they live there) */
    private fun openOwnLink(url: String, chatId: Long): Boolean {
        val cfg = a.api?.cfg ?: return false
        val u = try { android.net.Uri.parse(url) } catch (_: Exception) { return false }
        if (u.host != cfg.host) return false
        val frag = u.fragment ?: return false
        if (frag.startsWith("join=")) { a.joinByInvite(frag.removePrefix("join=")); return true }
        if (frag.startsWith("room=")) { a.openWebOnce(frag); return true }
        return false
    }

    private fun onTap(m: Map<String, Any?>, h: Host) {
        if (m.map("game") != null) { a.openWebOnce(null, m.lng("chat_id")); return }
        val f = m.map("file")
        if (f != null) { h.fileClicked(m); return }
        val url = Regex("https?://[^\\s]+").find(m.str("body"))?.value ?: return
        if (openOwnLink(url, m.lng("chat_id"))) return
        try { a.startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW, android.net.Uri.parse(url))) } catch (_: Exception) {}
    }

    private fun quote(r: Map<String, Any?>, h: Host, mine: Boolean): View {
        val box = LinearLayout(a)
        box.orientation = LinearLayout.HORIZONTAL
        box.setPadding(0, 0, 0, a.dp(4))
        val bar = View(a); bar.setBackgroundColor(th.quoteBar)
        box.addView(bar, LinearLayout.LayoutParams(a.dp(3), MATCH))
        val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL; col.setPadding(a.dp(8), 0, a.dp(4), 0)
        col.addView(label(a, r.str("sender_name").ifEmpty { "پیام" }, 13f, th.accent, true).oneLine())
        col.addView(label(a, ChatText.short(Stickers.label(r.str("text")) ?: r.str("text"), 60), 13f, if (mine) th.mineMeta else th.muted).oneLine())
        box.addView(col, lp(WRAP, WRAP))
        box.isClickable = true
        box.setOnClickListener { h.replyClicked(r.lng("id")) }
        return box
    }

    private fun addFile(b: LinearLayout, m: Map<String, Any?>, f: Map<String, Any?>, h: Host, mine: Boolean, textColor: Int, meta: Int) {
        val id = m.lng("id")
        if (f.bool("voice")) {
            val wl = (f["wave"] as? List<*>)?.map { ((it as? Number)?.toInt() ?: 0) } ?: emptyList()
            val wave = IntArray(40) { if (it < wl.size) wl[it] else 3 }
            val played = (f["played"] as? List<*>)?.isNotEmpty() == true
            val v = VoiceView(a, th, mine, wave, f.lng("dur"), !played)
            val (pg, pl) = h.voiceState(id)
            v.set(pg, pl)
            val dl = h.downloadProgress(id)
            if (dl >= 0f) v.showLoading(dl)
            h.voiceView(id, v)
            b.addView(v)
            return
        }
        val kind = f.str("kind")
        if (kind == "audio") {
            val v = AudioView(a, th, mine, f.str("name"), f.lng("size"), f.lng("dur")) { fr -> h.seek(id, fr) }
            val (pg, pl) = h.voiceState(id); v.set(pg, pl)
            val dl0 = h.downloadProgress(id); if (dl0 >= 0f) v.showLoading(dl0)
            h.voiceView(id, v); b.addView(v); return
        }
        val tw = f.int("tw"); val th2 = f.int("th")
        if ((kind == "image" || kind == "video") && f.str("thumb").isNotEmpty() || (kind == "image" && tw > 0)) {
            val w = if (tw > 0 && th2 > 0) { val s = Math.min(1f, Math.min(a.dp(240).toFloat() / tw, a.dp(300).toFloat() / th2)); Pair((tw * s).toInt().coerceAtLeast(a.dp(80)), (th2 * s).toInt().coerceAtLeast(a.dp(80))) } else Pair(a.dp(220), a.dp(160))
            val fl = FrameLayout(a)
            val iv = ImageView(a); iv.scaleType = ImageView.ScaleType.CENTER_CROP
            iv.setBackgroundColor(if (th.dark) 0xFF0E1621.toInt() else 0xFFCFD8DC.toInt())
            fl.addView(iv, FrameLayout.LayoutParams(MATCH, MATCH))
            var sync = true
            a.img?.load("/thumb/$id", a.mediaKey, 512) { bmp -> if (bmp != null) { iv.setImageBitmap(bmp); if (!sync) { iv.alpha = 0f; iv.animate().alpha(1f).setDuration(180).start() } } }
            sync = false
            if (kind == "video") {
                val pc = FrameLayout(a); pc.background = rounded(0x99000000.toInt(), a.dpf(24f))
                pc.addView(icon(a, "play", 0xFFFFFFFF.toInt(), 22), FrameLayout.LayoutParams(a.dp(22), a.dp(22), Gravity.CENTER))
                fl.addView(pc, FrameLayout.LayoutParams(a.dp(48), a.dp(48), Gravity.CENTER))
            }
            val dl = h.downloadProgress(id)
            if (dl >= 0f) fl.addView(RingView(a, 0x99000000.toInt()).also { it.progress = dl }, FrameLayout.LayoutParams(a.dp(52), a.dp(52), Gravity.CENTER))
            b.addView(fl, LinearLayout.LayoutParams(w.first, w.second).also { it.bottomMargin = a.dp(4) })
            return
        }
        val row = LinearLayout(a); row.orientation = LinearLayout.HORIZONTAL; row.gravity = Gravity.CENTER_VERTICAL
        val dl = h.downloadProgress(id)
        val c = FrameLayout(a)
        if (dl >= 0f) c.addView(RingView(a, th.accentFill).also { it.progress = dl }, FrameLayout.LayoutParams(MATCH, MATCH))        // downloading: ring + ✕ like Telegram
        else { c.background = rounded(th.accentFill, a.dpf(22f)); c.addView(icon(a, if (kind == "audio") "play" else "file", 0xFFFFFFFF.toInt(), 22), FrameLayout.LayoutParams(a.dp(22), a.dp(22), Gravity.CENTER)) }
        row.addView(c, lp(a.dp(44), a.dp(44)))
        val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL; col.setPadding(a.dp(10), 0, 0, 0)
        col.addView(label(a, f.str("name"), 15f, textColor, true).oneLine())
        col.addView(label(a, if (dl >= 0f) Fmt.size((f.lng("size") * dl).toLong()) + " / " + Fmt.size(f.lng("size")) else Fmt.size(f.lng("size")), 12f, meta))
        row.addView(col, lp(WRAP, WRAP))
        row.setPadding(0, 0, 0, a.dp(2))
        b.addView(row)
    }

    private fun metaRow(m: Map<String, Any?>, h: Host, mine: Boolean, meta: Int): View {
        val r = LinearLayout(a); r.orientation = LinearLayout.HORIZONTAL; r.gravity = Gravity.CENTER_VERTICAL or Gravity.END
        r.layoutDirection = View.LAYOUT_DIRECTION_LTR
        if (m.lng("edited_at") > 0 && !m.bool("deleted")) r.addView(label(a, "ویرایش‌شده  ", 11f, meta))
        r.addView(label(a, Fmt.time(m.lng("created_at")), 11f, meta))
        if (mine && !m.bool("deleted")) {
            val read = h.peerRead >= m.lng("id")
            val ic = icon(a, if (read) "check2" else "check", if (read) th.accent else meta, 16)
            (ic.layoutParams as LinearLayout.LayoutParams).leftMargin = a.dp(3)
            r.addView(ic)
        }
        r.setPadding(0, a.dp(2), 0, 0)
        return r
    }

    private fun reactions(m: Map<String, Any?>, rx: List<Map<String, Any?>>, h: Host, mine: Boolean): View {
        val wrap = android.widget.HorizontalScrollView(a); wrap.isHorizontalScrollBarEnabled = false
        val row = LinearLayout(a); row.orientation = LinearLayout.HORIZONTAL; row.setPadding(0, a.dp(4), 0, a.dp(2))
        for (r in rx) {
            val users = (r["users"] as? List<*>) ?: emptyList<Any?>()
            val me = users.any { (it as? Number)?.toLong() == h.myId }
            val chip = label(a, r.str("e") + " " + Fmt.digits(users.size.toString()), 13f, if (me) 0xFFFFFFFF.toInt() else th.text, me)
            chip.background = rounded(if (me) th.accentFill else (if (th.dark) 0x33FFFFFF else 0x14000000), a.dpf(12f))
            chip.setPadding(a.dp(8), a.dp(3), a.dp(8), a.dp(3))
            chip.isClickable = true
            chip.setOnClickListener { h.react(m, r.str("e")) }
            val lp = LinearLayout.LayoutParams(WRAP, WRAP); lp.rightMargin = a.dp(4)
            row.addView(chip, lp)
        }
        wrap.addView(row)
        return wrap
    }
}
