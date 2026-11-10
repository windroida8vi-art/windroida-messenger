package ir.windroida.app.ui

import android.graphics.Typeface
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.BackgroundColorSpan
import android.text.style.ForegroundColorSpan
import android.text.style.StrikethroughSpan
import android.text.style.StyleSpan
import android.text.style.TypefaceSpan

/** The same light formatting as the web app: **bold**, __italic__, ~~strike~~, `code` (no nesting). Everything else stays plain text. */
object Md {
    private val RE = Regex("`([^`\\n]+)`|\\*\\*(.+?)\\*\\*|__(.+?)__|~~(.+?)~~")
    private val MENTION = Regex("(?<![A-Za-z0-9_])@[A-Za-z][A-Za-z0-9_]{2,31}")

    class Span(val kind: String, val start: Int, val end: Int)

    /** pure part (testable on the JVM): the text without markers and the spans on it */
    fun parse(text: String): Pair<String, List<Span>> {
        val sb = StringBuilder()
        val spans = ArrayList<Span>()
        var last = 0
        for (m in RE.findAll(text)) {
            sb.append(text, last, m.range.first)
            val kind = when { m.groups[1] != null -> "code"; m.groups[2] != null -> "b"; m.groups[3] != null -> "i"; else -> "s" }
            val inner = (m.groups[1] ?: m.groups[2] ?: m.groups[3] ?: m.groups[4])!!.value
            val s = sb.length
            sb.append(inner)
            spans.add(Span(kind, s, sb.length))
            last = m.range.last + 1
        }
        sb.append(text, last, text.length)
        return Pair(sb.toString(), spans)
    }

    fun render(text: String, codeBg: Int, mention: Int): CharSequence {
        val (plain, spans) = parse(text)
        val out = SpannableStringBuilder(plain)
        for (sp in spans) {
            if (sp.start >= sp.end) continue
            val f = Spanned.SPAN_EXCLUSIVE_EXCLUSIVE
            when (sp.kind) {
                "b" -> out.setSpan(StyleSpan(Typeface.BOLD), sp.start, sp.end, f)
                "i" -> out.setSpan(StyleSpan(Typeface.ITALIC), sp.start, sp.end, f)
                "s" -> out.setSpan(StrikethroughSpan(), sp.start, sp.end, f)
                else -> { out.setSpan(TypefaceSpan("monospace"), sp.start, sp.end, f); out.setSpan(BackgroundColorSpan(codeBg), sp.start, sp.end, f) }
            }
        }
        for (m in MENTION.findAll(plain)) out.setSpan(ForegroundColorSpan(mention), m.range.first, m.range.last + 1, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        return out
    }
}
