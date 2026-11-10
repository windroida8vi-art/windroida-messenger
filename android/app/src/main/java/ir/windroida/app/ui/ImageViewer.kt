package ir.windroida.app.ui

import android.graphics.Bitmap
import android.graphics.Matrix
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.ImageView
import ir.windroida.app.NativeActivity

/** Full-screen photo: opens with a fade + zoom, pinch to zoom, drag to move, double tap to zoom in / out, tap or back to close. */
class ImageViewer(private val a: NativeActivity, private val messageId: Long, private val title: String, galleryIn: List<String>? = null,
                  private val onDelete: ((String, (Boolean) -> Unit) -> Unit)? = null) {
    private val gallery: MutableList<String>? = galleryIn?.toMutableList()
    val view = FrameLayout(a)
    private val iv = ImageView(a)
    private val m = Matrix()
    private var bmp: Bitmap? = null
    private var base = 1f
    private var scale = 1f
    private var closing = false
    private var dragY = 0f
    private var gi = 0
    private var counter: android.widget.TextView? = null

    init {
        view.setBackgroundColor(0xFF000000.toInt())
        iv.scaleType = ImageView.ScaleType.MATRIX
        view.addView(iv, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        val close = iconButton(a, a.th, "close", 0xFFFFFFFF.toInt()) { close() }
        view.addView(close, FrameLayout.LayoutParams(a.dp(44), a.dp(44), android.view.Gravity.TOP or android.view.Gravity.END).also { it.setMargins(0, a.dp(24), a.dp(8), 0) })
        if (onDelete != null && gallery != null) {                 // "..." menu: delete exactly the photo on screen (like Telegram)
            val more = iconButton(a, a.th, "more", 0xFFFFFFFF.toInt()) { askDelete() }
            view.addView(more, FrameLayout.LayoutParams(a.dp(44), a.dp(44), android.view.Gravity.TOP or android.view.Gravity.END).also { it.setMargins(0, a.dp(24), a.dp(52), 0) })
        }
        val ttl = label(a, title, 14f, 0xFFFFFFFF.toInt(), true).oneLine()
        view.addView(ttl, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, android.view.Gravity.TOP).also { it.setMargins(a.dp(16), a.dp(36), a.dp(if (onDelete != null) 108 else 64), 0) })
        val sd = ScaleGestureDetector(a, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            override fun onScale(d: ScaleGestureDetector): Boolean {
                val ns = (scale * d.scaleFactor).coerceIn(1f, 6f)
                val f = ns / scale; scale = ns
                m.postScale(f, f, d.focusX, d.focusY); fix(); iv.imageMatrix = m
                return true
            }
        })
        val gd = GestureDetector(a, object : GestureDetector.SimpleOnGestureListener() {
            override fun onSingleTapConfirmed(e: MotionEvent): Boolean { close(); return true }
            override fun onFling(e1: MotionEvent?, e2: MotionEvent, vx: Float, vy: Float): Boolean {
                val g = gallery
                if (g != null && g.size > 1 && scale <= 1.01f && Math.abs(vx) > 600f && Math.abs(vx) > Math.abs(vy) * 1.5f) { go(if (vx < 0) 1 else -1); return true }
                return false
            }
            override fun onDoubleTap(e: MotionEvent): Boolean {
                val target = if (scale > 1.05f) 1f else 2.5f
                val f = target / scale; scale = target
                m.postScale(f, f, e.x, e.y); fix(); iv.imageMatrix = m
                return true
            }
            override fun onScroll(e1: MotionEvent?, e2: MotionEvent, dx: Float, dy: Float): Boolean {
                if (scale > 1.01f) { m.postTranslate(-dx, -dy); fix(); iv.imageMatrix = m }
                else if (e2.pointerCount == 1) {                         // not zoomed: dragging up / down slides the photo away like Telegram
                    dragY -= dy; iv.translationY = dragY
                    view.setBackgroundColor((((1f - Math.min(1f, Math.abs(dragY) / (view.height * 0.5f))) * 255).toInt() shl 24))
                }
                return true
            }
        })
        view.setOnTouchListener { _, e ->
            sd.onTouchEvent(e); if (!sd.isInProgress) gd.onTouchEvent(e)
            if ((e.actionMasked == MotionEvent.ACTION_UP || e.actionMasked == MotionEvent.ACTION_CANCEL) && dragY != 0f) {
                if (Math.abs(dragY) > a.dp(110) && e.actionMasked == MotionEvent.ACTION_UP) {
                    closing = true
                    iv.animate().translationY(if (dragY > 0) view.height.toFloat() else -view.height.toFloat()).setDuration(160).start()
                    view.animate().alpha(0f).setDuration(170).withEndAction { a.removeViewer(this) }.start()
                } else { dragY = 0f; iv.animate().translationY(0f).setDuration(160).start(); view.setBackgroundColor(0xFF000000.toInt()) }
            }
            true
        }
        view.alpha = 0f
        view.animate().alpha(1f).setDuration(200).start()
        iv.scaleX = 0.92f; iv.scaleY = 0.92f; iv.animate().scaleX(1f).scaleY(1f).setDuration(220).start()
        if (gallery != null && gallery.isNotEmpty()) {
            val t = label(a, "", 13f, 0xFFFFFFFF.toInt(), true); counter = t
            view.addView(t, FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, android.view.Gravity.BOTTOM or android.view.Gravity.CENTER_HORIZONTAL).also { it.bottomMargin = a.dp(36) })
            loadGallery()
        } else {
            // the small picture is already cached: show it at once, the big one replaces it when it arrives
            a.img?.load("/thumb/$messageId", a.mediaKey, 512) { b -> if (bmp == null && b != null) show(b) }
            a.img?.load("/media/$messageId", a.mediaKey, 2048) { b -> if (b != null) show(b) else if (bmp == null) a.toast("عکس باز نشد") }
        }
    }

    /** gallery mode (profile photos): a swipe sideways shows the next / previous kept photo, newest first */
    private fun loadGallery() {
        val g = gallery ?: return
        val mine = gi
        counter?.text = if (g.size > 1) ir.windroida.app.ui.Fmt.digits("${gi + 1} / ${g.size}") else ""
        a.img?.load(g[gi] + "&s=1", a.mediaKey, 512) { b -> if (mine == gi && bmp == null && b != null) show(b) }
        a.img?.load(g[gi], a.mediaKey, 2048) { b -> if (mine == gi) { if (b != null) show(b) else if (bmp == null) a.toast("عکس باز نشد") } }
    }

    private fun askDelete() {
        val g = gallery ?: return
        val del = onDelete ?: return
        val pic = g.getOrNull(gi) ?: return
        val file = android.net.Uri.parse(pic).getQueryParameter("pic") ?: return
        android.app.AlertDialog.Builder(a).setItems(arrayOf("حذف این عکس")) { _, _ ->
            android.app.AlertDialog.Builder(a).setMessage("این عکس حذف بشه؟")
                .setPositiveButton("حذف") { _, _ ->
                    del(file) lbl@{ ok ->
                        if (!ok) return@lbl
                        g.removeAt(gi)
                        a.toast("عکس حذف شد")
                        if (g.isEmpty()) { close(); return@lbl }
                        gi = Math.min(gi, g.size - 1)
                        bmp = null; iv.setImageBitmap(null)
                        loadGallery()
                    }
                }.setNegativeButton("لغو", null).show()
        }.show()
    }

    private fun go(dir: Int) {
        val g = gallery ?: return
        gi = (gi + dir + g.size) % g.size
        bmp = null; iv.setImageBitmap(null)
        iv.translationX = dir * view.width * 0.4f; iv.alpha = 0f
        iv.animate().translationX(0f).alpha(1f).setDuration(180).start()
        loadGallery()
    }

    private fun show(b: Bitmap) {
        bmp = b
        iv.setImageBitmap(b)
        val place = {
            val vw = view.width.toFloat(); val vh = view.height.toFloat()
            base = Math.min(vw / b.width, vh / b.height)
            m.reset(); m.postScale(base, base); m.postTranslate((vw - b.width * base) / 2f, (vh - b.height * base) / 2f)
            scale = 1f; iv.imageMatrix = m
        }
        if (view.width > 0) place() else view.post(place)
    }

    /** keep the picture on screen: centred while it is smaller than the screen, never dragged past an edge when it is bigger */
    private fun fix() {
        val b = bmp ?: return
        val v = FloatArray(9); m.getValues(v)
        val w = b.width * v[Matrix.MSCALE_X]; val h = b.height * v[Matrix.MSCALE_Y]
        var tx = v[Matrix.MTRANS_X]; var ty = v[Matrix.MTRANS_Y]
        val vw = view.width.toFloat(); val vh = view.height.toFloat()
        tx = if (w <= vw) (vw - w) / 2f else tx.coerceIn(vw - w, 0f)
        ty = if (h <= vh) (vh - h) / 2f else ty.coerceIn(vh - h, 0f)
        v[Matrix.MTRANS_X] = tx; v[Matrix.MTRANS_Y] = ty; m.setValues(v)
    }

    fun close() {
        if (closing) return
        closing = true
        view.animate().alpha(0f).setDuration(160).withEndAction { a.removeViewer(this) }.start()
    }
}
