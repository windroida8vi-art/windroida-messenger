package ir.windroida.app.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapShader
import android.graphics.Canvas
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Shader
import android.graphics.Typeface
import android.view.View

/** Round profile picture: colored disc with the first letter until (or unless) the real photo arrives. */
class AvatarView(ctx: Context, private val img: () -> Img?, private val mediaKey: () -> String) : View(ctx) {
    private val disc = Paint(Paint.ANTI_ALIAS_FLAG)
    private val txt = Paint(Paint.ANTI_ALIAS_FLAG).also { it.color = 0xFFFFFFFF.toInt(); it.textAlign = Paint.Align.CENTER; it.typeface = Typeface.DEFAULT_BOLD }
    private val pic = Paint(Paint.ANTI_ALIAS_FLAG)
    private val dotBg = Paint(Paint.ANTI_ALIAS_FLAG)
    private val dot = Paint(Paint.ANTI_ALIAS_FLAG).also { it.color = 0xFF4FAE4E.toInt() }
    private var letter = "?"
    private var shader: BitmapShader? = null
    private var bmp: Bitmap? = null
    private var online = false
    private var token = ""
    private var ringColor = 0xFF17212B.toInt()
    var vector: ((Canvas, Float, Float, Float) -> Unit)? = null     // e.g. the bookmark symbol of "Saved messages"

    fun setRing(c: Int) { ringColor = c; dotBg.color = c }

    /** kind: "u" (user) or "c" (chat); [at] is the version stamp (0 = no photo). */
    fun bind(kind: String, id: Long, name: String, at: Long, isOnline: Boolean) {
        letter = initial(name)
        disc.color = Theme.AVATAR_COLORS[(Math.abs(id) % Theme.AVATAR_COLORS.size).toInt()]
        online = isOnline
        val t = "$kind$id:$at"
        if (t != token) {
            token = t; bmp = null; shader = null
            if (at > 0) {
                val loader = img()
                val key = mediaKey()
                if (loader != null && key.isNotEmpty()) {
                    val mine = t
                    loader.load("/avatar/$kind$id?v=$at&s=1", key, 160) { b -> if (token == mine && b != null) { bmp = b; shader = null; invalidate() } }
                }
            }
        }
        invalidate()
    }

    private fun initial(name: String): String {
        val t = name.trim()
        if (t.isEmpty()) return "?"
        val cp = t.codePointAt(0)
        return String(Character.toChars(cp)).uppercase()
    }

    override fun onDraw(c: Canvas) {
        val w = width.toFloat(); val h = height.toFloat(); val r = Math.min(w, h) / 2f
        c.drawCircle(w / 2f, h / 2f, r, disc)
        val b = bmp
        if (b != null) {
            var sh = shader
            if (sh == null) {
                sh = BitmapShader(b, Shader.TileMode.CLAMP, Shader.TileMode.CLAMP)
                val m = Matrix(); val sc = Math.max(w / b.width, h / b.height)
                m.postScale(sc, sc); m.postTranslate((w - b.width * sc) / 2f, (h - b.height * sc) / 2f)
                sh.setLocalMatrix(m); shader = sh
            }
            pic.shader = sh
            c.drawCircle(w / 2f, h / 2f, r, pic)
        } else if (vector != null) vector!!.invoke(c, w / 2f, h / 2f, r)
        else { txt.textSize = r * 0.95f; c.drawText(letter, w / 2f, h / 2f - (txt.descent() + txt.ascent()) / 2f, txt) }
        if (online) { val dr = r * 0.26f; c.drawCircle(w * 0.84f, h * 0.84f, dr * 1.35f, dotBg); c.drawCircle(w * 0.84f, h * 0.84f, dr, dot) }
    }
}
