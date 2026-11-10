package ir.windroida.app.ui

import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.BaseAdapter
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.SeekBar
import android.widget.TextView
import ir.windroida.app.NativeActivity

/** Bottom sheet of the music player (like Telegram): the queue, a seek bar and the controls. Slides up over the current screen. */
class PlayerSheet(private val a: NativeActivity, private val vp: VoicePlayer) {
    private val th = a.th
    val view = FrameLayout(a)
    /** the panel follows a finger that drags down (outside the seek bar / a scrolled list) and closes when pulled far enough */
    private inner class DragPanel : LinearLayout(a) {
        private var y0 = 0f; private var drag = false; private var t0 = 0L
        private fun inView(v: View, e: android.view.MotionEvent): Boolean { val r = android.graphics.Rect(); v.getGlobalVisibleRect(r); return r.contains(e.rawX.toInt(), e.rawY.toInt()) }
        override fun onInterceptTouchEvent(e: android.view.MotionEvent): Boolean {
            when (e.actionMasked) {
                android.view.MotionEvent.ACTION_DOWN -> { y0 = e.rawY; drag = false; t0 = System.currentTimeMillis() }
                android.view.MotionEvent.ACTION_MOVE -> if (!drag) {
                    val dy = e.rawY - y0
                    if (dy > a.dp(14) && !inView(seek, e) && !(inView(list, e) && list.canScrollVertically(-1))) { drag = true; y0 = e.rawY; t0 = System.currentTimeMillis() }
                }
            }
            return drag
        }
        override fun onTouchEvent(e: android.view.MotionEvent): Boolean {
            when (e.actionMasked) {
                android.view.MotionEvent.ACTION_MOVE -> { translationY = Math.max(0f, e.rawY - y0); view.alpha = 1f - 0.6f * Math.min(1f, translationY / height) }
                android.view.MotionEvent.ACTION_UP, android.view.MotionEvent.ACTION_CANCEL -> {
                    val dy = translationY
                    if (e.actionMasked == android.view.MotionEvent.ACTION_UP && (dy > height * 0.3f || (dy > a.dp(50) && System.currentTimeMillis() - t0 < 250))) close()
                    else { animate().translationY(0f).setDuration(160).start(); view.animate().alpha(1f).setDuration(160).start() }
                    drag = false
                }
            }
            return true
        }
    }
    private val panel: LinearLayout = DragPanel()
    private val list = ListView(a)
    private val titleV = label(a, "", 18f, th.text, true)
    private val artistV = label(a, "", 14f, th.muted)
    private val seek = SeekBar(a)
    private val posV = label(a, "0:00", 12f, th.muted)
    private val durV = label(a, "0:00", 12f, th.muted)
    private val ppBtn = FrameLayout(a)
    private val ppIcon = android.widget.ImageView(a)
    private val repBtn = FrameLayout(a)
    private val repIcon = android.widget.ImageView(a)
    private val shBtn = FrameLayout(a)
    private val shIcon = android.widget.ImageView(a)
    private var dragging = false
    private var closing = false
    private val tick = object : Runnable { override fun run() { refreshTime(); a.main.postDelayed(this, 300) } }
    private val onState: () -> Unit = { refresh() }

    private val adapter = object : BaseAdapter() {
        override fun getCount() = vp.queue.size
        override fun getItem(p: Int): Any = vp.queue[p]
        override fun getItemId(p: Int) = vp.queue[p].id
        override fun getView(p: Int, cv: View?, parent: ViewGroup?): View {
            val t = vp.queue[p]
            val cur = p == vp.qIndex
            val row = LinearLayout(a); row.orientation = LinearLayout.HORIZONTAL; row.gravity = Gravity.CENTER_VERTICAL
            row.setPadding(a.dp(16), a.dp(8), a.dp(16), a.dp(8))
            if (cur) row.setBackgroundColor(if (th.dark) 0x2A5EB5F7 else 0x1A3390EC)
            val ic = FrameLayout(a)
            ic.background = rounded(if (cur) th.accentFill else th.badgeMuted, a.dpf(22f))
            ic.addView(icon(a, if (cur && vp.isPlaying) "pause" else "play", 0xFFFFFFFF.toInt(), 20), FrameLayout.LayoutParams(a.dp(20), a.dp(20), Gravity.CENTER))
            row.addView(ic, LinearLayout.LayoutParams(a.dp(44), a.dp(44)))
            val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL; col.setPadding(a.dp(14), 0, 0, 0)
            col.addView(label(a, t.title, 15f, th.text, cur).oneLine())
            col.addView(label(a, t.artist, 13f, th.muted).oneLine())
            row.addView(col, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            row.isClickable = true
            row.setOnClickListener { if (cur) vp.toggleCurrent() else vp.playAt(p) }
            return row
        }
    }

    init {
        view.setBackgroundColor(0x88000000.toInt())
        view.setOnClickListener { close() }
        panel.orientation = LinearLayout.VERTICAL
        panel.background = roundedCorners(th.panel, a.dpf(22f), a.dpf(22f), 0f, 0f)
        panel.isClickable = true                                   // taps on the panel must not reach the scrim
        val handle = View(a); handle.background = rounded(th.badgeMuted, a.dpf(3f))
        panel.addView(handle, LinearLayout.LayoutParams(a.dp(40), a.dp(5)).also { it.gravity = Gravity.CENTER_HORIZONTAL; it.topMargin = a.dp(8); it.bottomMargin = a.dp(6) })
        list.adapter = adapter; list.divider = null; list.selector = android.graphics.drawable.ColorDrawable(0)
        panel.addView(list, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, a.dp(60)))
        val info = LinearLayout(a); info.orientation = LinearLayout.VERTICAL; info.setPadding(a.dp(20), a.dp(14), a.dp(20), 0)
        titleV.oneLine(); artistV.oneLine()
        info.addView(titleV); info.addView(artistV)
        seek.max = 1000
        seek.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(s: SeekBar?, p: Int, fromUser: Boolean) { if (fromUser) posV.text = fmt((vp.durationMs.toLong() * p / 1000)) }
            override fun onStartTrackingTouch(s: SeekBar?) { dragging = true }
            override fun onStopTrackingTouch(s: SeekBar?) { dragging = false; vp.seek((s?.progress ?: 0) / 1000f) }
        })
        info.addView(seek, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).also { it.topMargin = a.dp(6) })
        val times = LinearLayout(a); times.orientation = LinearLayout.HORIZONTAL
        times.addView(posV, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)); times.addView(durV)
        info.addView(times)
        panel.addView(info)
        val ctl = LinearLayout(a); ctl.orientation = LinearLayout.HORIZONTAL; ctl.gravity = Gravity.CENTER; ctl.setPadding(a.dp(8), a.dp(8), a.dp(8), a.dp(16))
        fun btn(box: FrameLayout, img: android.widget.ImageView, size: Int, fn: () -> Unit): FrameLayout {
            box.addView(img, FrameLayout.LayoutParams(a.dp(size), a.dp(size), Gravity.CENTER))
            box.isClickable = true; box.setOnClickListener { fn() }; box.pressScale(0.88f)
            return box
        }
        fun plain(kind: String, fn: () -> Unit): FrameLayout { val i = android.widget.ImageView(a); i.setImageDrawable(IconDrawable(kind, th.text)); return btn(FrameLayout(a), i, 26, fn) }
        ctl.addView(btn(shBtn, shIcon, 24) { vp.toggleShuffle() }, LinearLayout.LayoutParams(a.dp(56), a.dp(56)))
        ctl.addView(plain("prev") { vp.prev() }, LinearLayout.LayoutParams(a.dp(60), a.dp(56)))
        ppBtn.background = rounded(th.accentFill, a.dpf(32f))
        ctl.addView(btn(ppBtn, ppIcon, 30) { vp.toggleCurrent() }, LinearLayout.LayoutParams(a.dp(64), a.dp(64)).also { it.setMargins(a.dp(6), 0, a.dp(6), 0) })
        ctl.addView(plain("next") { vp.next() }, LinearLayout.LayoutParams(a.dp(60), a.dp(56)))
        ctl.addView(btn(repBtn, repIcon, 24) { vp.cycleRepeat() }, LinearLayout.LayoutParams(a.dp(56), a.dp(56)))
        panel.addView(ctl)
        view.addView(panel, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM))
        vp.addStateListener(onState)
        refresh()
        a.main.post(tick)
        panel.post { panel.translationY = panel.height.toFloat(); panel.animate().translationY(0f).setDuration(220).start() }
        view.alpha = 0f; view.animate().alpha(1f).setDuration(200).start()
    }

    private fun fmt(ms: Long): String { val s = ms / 1000; return (s / 60).toString() + ":" + (s % 60).toString().padStart(2, '0') }

    private fun refresh() {
        if (vp.playingId == 0L) { close(); return }
        titleV.text = vp.title; artistV.text = vp.subtitle
        ppIcon.setImageDrawable(IconDrawable(if (vp.isPlaying) "pause" else "play", 0xFFFFFFFF.toInt()))
        repIcon.setImageDrawable(IconDrawable(if (vp.repeat == VoicePlayer.REPEAT_ONE) "repeat1" else "repeat", if (vp.repeat == VoicePlayer.REPEAT_OFF) th.muted else th.accent))
        shIcon.setImageDrawable(IconDrawable("shuffle", if (vp.shuffle) th.accent else th.muted))
        val lp = list.layoutParams; lp.height = minOf(vp.queue.size * a.dp(60), (a.resources.displayMetrics.heightPixels * 0.38f).toInt()); list.layoutParams = lp
        list.visibility = if (vp.queue.isEmpty()) View.GONE else View.VISIBLE
        adapter.notifyDataSetChanged()
        refreshTime()
    }

    private fun refreshTime() {
        if (dragging) return
        val d = vp.durationMs
        durV.text = if (vp.loading) "…" else fmt(d.toLong())
        posV.text = fmt(vp.positionMs.toLong())
        seek.progress = if (d > 0) (vp.positionMs.toLong() * 1000 / d).toInt() else 0
    }

    fun close() {
        if (closing) return
        closing = true
        a.main.removeCallbacks(tick)
        vp.removeStateListener(onState)
        panel.animate().translationY(panel.height.toFloat()).setDuration(180).start()
        view.animate().alpha(0f).setDuration(180).withEndAction { a.removeOverlay(view, this) }.start()
    }
}
