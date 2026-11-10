package ir.windroida.app.ui

import android.text.InputFilter
import android.view.Gravity
import android.view.View
import android.widget.CheckBox
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import ir.windroida.app.NativeActivity
import ir.windroida.app.net.*

/** Polls (نظرسنجی): the card inside a message bubble, voting, closing, "who voted", and the creation dialog. Same server ops as the web app (poll_*). */
class Polls(private val a: NativeActivity, private val th: Theme) {
    private val mine = HashMap<Long, List<Long>>()          // poll id -> my chosen options
    private val asked = HashSet<Long>()

    private fun pct(n: Long, t: Long) = if (t <= 0) 0 else Math.round(n * 100f / t)

    private fun canClose(m: Map<String, Any?>): Boolean {
        val c = a.model.chats[m.lng("chat_id")] ?: return false
        return m.lng("sender_id") == a.model.myId || (c.str("kind") == "group" && !c.bool("channel") && (c.str("my_role") == "owner" || c.str("my_role") == "admin"))
    }

    /** the card for [m] (a message with "poll"); [again] re-draws the message when my own vote arrives */
    fun card(m: Map<String, Any?>, textColor: Int, metaColor: Int, again: () -> Unit): View {
        val p = m.map("poll") ?: return View(a)
        val pid = p.lng("id")
        val opts = (p["opts"] as? List<*>)?.map { it.toString() } ?: emptyList()
        val counts = (p["counts"] as? List<*>)?.map { (it as? Number)?.toLong() ?: 0L } ?: emptyList()
        val multi = p.bool("multi"); val anon = p.bool("anon"); val closed = p.bool("closed")
        val voters = p.lng("voters")
        val total = if (multi) voters else counts.sum()
        val my = mine[pid]
        val box = LinearLayout(a); box.orientation = LinearLayout.VERTICAL
        box.addView(label(a, p.str("q"), 16f, textColor, true))
        box.addView(label(a, listOf(if (anon) "ناشناس" else "عمومی", if (multi) "چندانتخابی" else "تک‌انتخابی", if (closed) "بسته شده" else "").filter { it.isNotEmpty() }.joinToString(" · "), 12f, metaColor).also { it.setPadding(0, a.dp(2), 0, a.dp(6)) })
        for ((i, o) in opts.withIndex()) {
            val on = my?.contains(i.toLong()) == true
            val n = counts.getOrElse(i) { 0L }
            val row = FrameLayout(a)
            row.background = android.graphics.drawable.GradientDrawable().also {
                it.cornerRadius = a.dpf(10f); it.setStroke(a.dp(1), if (on) th.accentFill else metaColor and 0x66FFFFFF)
            }
            val bar = View(a); bar.setBackgroundColor(if (th.dark) 0x445EB5F7 else 0x333390EC)
            val barBox = FrameLayout(a); barBox.addView(bar, FrameLayout.LayoutParams(0, MATCH))
            row.addView(barBox, FrameLayout.LayoutParams(MATCH, MATCH))
            val line = LinearLayout(a); line.orientation = LinearLayout.HORIZONTAL; line.gravity = Gravity.CENTER_VERTICAL; line.setPadding(a.dp(10), a.dp(9), a.dp(10), a.dp(9))
            line.addView(label(a, (if (on) "✓ " else "") + o, 15f, textColor, on), lp(0, WRAP).weight(1f))
            line.addView(label(a, Fmt.digits(pct(n, total).toString()) + "٪ · " + Fmt.digits(n.toString()), 12f, metaColor))
            row.addView(line, FrameLayout.LayoutParams(MATCH, WRAP))
            val frac = pct(n, total) / 100f
            row.post { val lp0 = bar.layoutParams; val target = (row.width * frac).toInt(); lp0.width = 0; bar.layoutParams = lp0
                android.animation.ValueAnimator.ofInt(0, target).setDuration(350).also { v -> v.addUpdateListener { x -> val l = bar.layoutParams; l.width = x.animatedValue as Int; bar.layoutParams = l } }.start() }
            row.isClickable = !closed
            if (!closed) { row.setOnClickListener { vote(m, i.toLong(), multi, again) }; row.pressScale(0.98f) }
            box.addView(row, lp(MATCH, WRAP).also { it.topMargin = a.dp(4) })
        }
        val foot = LinearLayout(a); foot.orientation = LinearLayout.HORIZONTAL; foot.gravity = Gravity.CENTER_VERTICAL; foot.setPadding(0, a.dp(8), 0, 0)
        foot.addView(label(a, Fmt.digits(voters.toString()) + " نفر رأی دادن", 12f, metaColor), lp(0, WRAP).weight(1f))
        if (!anon && voters > 0) foot.addView(textButton(a, th, "کی رأی داده؟") { whoVoted(m) }.also { it.setPadding(a.dp(8), a.dp(4), a.dp(8), a.dp(4)); it.textSize = 12f })
        if (!closed && canClose(m)) foot.addView(textButton(a, th, "بستن", th.danger) { closePoll(m) }.also { it.setPadding(a.dp(8), a.dp(4), a.dp(8), a.dp(4)); it.textSize = 12f })
        box.addView(foot)
        if (my == null && asked.add(pid)) a.rpc("poll_get", mapOf("poll_id" to pid)) { ok, r ->
            if (ok) { mine[pid] = (r["mine"] as? List<*>)?.mapNotNull { (it as? Number)?.toLong() } ?: emptyList(); again() } else asked.remove(pid)
        }
        return box
    }

    private fun vote(m: Map<String, Any?>, i: Long, multi: Boolean, again: () -> Unit) {
        val pid = m.map("poll")!!.lng("id")
        val cur = mine[pid] ?: emptyList()
        val next = if (multi) (if (cur.contains(i)) cur - i else cur + i) else (if (cur.contains(i)) emptyList() else listOf(i))
        a.rpc("poll_vote", mapOf("poll_id" to pid, "options" to next)) { ok, r ->
            if (!ok) { a.toast(r.str("error", "رأی ثبت نشد")); return@rpc }
            mine[pid] = (r["mine"] as? List<*>)?.mapNotNull { (it as? Number)?.toLong() } ?: next
            r.map("message")?.let { a.model.applyUpdate(it) }
            again()
        }
    }

    private fun closePoll(m: Map<String, Any?>) {
        android.app.AlertDialog.Builder(a).setMessage("نظرسنجی بسته بشه؟ بعدش کسی نمی‌تونه رأی بده.")
            .setPositiveButton("ببند") { _, _ ->
                a.rpc("poll_close", mapOf("poll_id" to m.map("poll")!!.lng("id"))) { ok, r ->
                    if (ok) r.map("message")?.let { a.model.applyUpdate(it) } else a.toast(r.str("error", "بسته نشد"))
                }
            }.setNegativeButton("نه", null).show()
    }

    private fun whoVoted(m: Map<String, Any?>) {
        val p = m.map("poll") ?: return
        a.rpc("poll_get", mapOf("poll_id" to p.lng("id"), "voters" to true)) { ok, r ->
            if (!ok) { a.toast(r.str("error", "در دسترس نیست")); return@rpc }
            val v = r.map("voters") ?: emptyMap()
            val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL; col.setPadding(a.dp(18), a.dp(14), a.dp(18), a.dp(10))
            col.addView(label(a, "رأی‌دهنده‌ها", 17f, th.text, true).also { it.setPadding(0, 0, 0, a.dp(8)) })
            val opts = (p["opts"] as? List<*>)?.map { it.toString() } ?: emptyList()
            for ((i, o) in opts.withIndex()) {
                col.addView(label(a, o, 15f, th.accent, true).also { it.setPadding(0, a.dp(8), 0, 0) })
                val names = (v[i.toString()] as? List<*>)?.joinToString("، ") { it.toString() } ?: ""
                col.addView(label(a, names.ifEmpty { "—" }, 14f, th.text))
            }
            val sv = ScrollView(a); sv.addView(col)
            Dialogs.sheet(a, sv)
        }
    }

    /** "new poll" dialog for [chatId] */
    fun create(chatId: Long) {
        val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL; col.setPadding(a.dp(18), a.dp(16), a.dp(18), a.dp(8))
        col.addView(label(a, "نظرسنجی جدید", 18f, th.text, true).also { it.setPadding(0, 0, 0, a.dp(8)) })
        fun field(hint: String, max: Int): EditText = EditText(a).also {
            it.styled(th, hint); it.setSingleLine(true); it.filters = arrayOf(InputFilter.LengthFilter(max))
            it.background = rounded(th.field, a.dpf(10f)); it.setPadding(a.dp(12), a.dp(10), a.dp(12), a.dp(10))
        }
        val q = field("سؤال", 200); col.addView(q, lp(MATCH, WRAP))
        val box = LinearLayout(a); box.orientation = LinearLayout.VERTICAL
        val inputs = ArrayList<EditText>()
        lateinit var addBtn: TextView
        fun add() { if (inputs.size >= 10) return; val e = field("گزینه " + Fmt.digits((inputs.size + 1).toString()), 100); inputs.add(e); box.addView(e, lp(MATCH, WRAP).also { it.topMargin = a.dp(6) }); if (inputs.size >= 10) addBtn.visibility = View.GONE }
        col.addView(box)
        addBtn = textButton(a, th, "+ گزینه") { add() }
        col.addView(addBtn)
        add(); add()
        val multi = CheckBox(a); multi.text = "چندانتخابی"; multi.setTextColor(th.text)
        val anon = CheckBox(a); anon.text = "ناشناس (کسی نمی‌بینه چه کسی رأی داده)"; anon.setTextColor(th.text)
        col.addView(multi); col.addView(anon)
        val err = label(a, "", 13f, th.danger); col.addView(err)
        var d: android.app.AlertDialog? = null
        col.addView(primaryButton(a, th, "ارسال") {
            val opts = inputs.map { it.text.toString().trim() }.filter { it.isNotEmpty() }
            if (q.text.toString().isBlank()) { err.text = "سؤال رو بنویس"; return@primaryButton }
            if (opts.size < 2) { err.text = "حداقل دو گزینه لازمه"; return@primaryButton }
            a.rpc("poll_create", mapOf("chat_id" to chatId, "question" to q.text.toString(), "options" to opts, "multi" to (if (multi.isChecked) 1 else 0), "anon" to (if (anon.isChecked) 1 else 0))) { ok, r ->
                if (ok) { r.map("message")?.let { a.model.ingest(it) }; d?.dismiss() } else err.text = r.str("error", "ساخته نشد")
            }
        }, lp(MATCH, WRAP).also { it.topMargin = a.dp(8) })
        val sv = ScrollView(a); sv.addView(col)
        d = Dialogs.sheet(a, sv)
    }
}
