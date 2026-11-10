package ir.windroida.app.ui

import android.app.AlertDialog
import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import ir.windroida.app.NativeActivity
import ir.windroida.app.net.bool
import ir.windroida.app.net.list
import ir.windroida.app.net.lng
import ir.windroida.app.net.map
import ir.windroida.app.net.str

/** Dialogs and sheets shared by the native screens (message menu, chat info, profile, bookmarks, search, forward picker). */
object Dialogs {
    /** A rounded dialog around [content]. */
    fun sheet(a: NativeActivity, content: View): AlertDialog {
        val th = a.th
        val box = LinearLayout(a); box.orientation = LinearLayout.VERTICAL
        box.background = rounded(th.panel, a.dpf(16f))
        box.addView(content, lp(MATCH, WRAP))
        val d = AlertDialog.Builder(a).setView(box).create()
        d.window?.setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
        d.show()
        return d
    }

    private fun rowText(a: NativeActivity, text: String, color: Int, onClick: () -> Unit): TextView {
        val t = label(a, text, 16f, color)
        t.setPadding(a.dp(20), a.dp(14), a.dp(20), a.dp(14))
        t.background = ripple(null, a.th.ripple); t.isClickable = true
        t.setOnClickListener { onClick() }
        return t
    }

    /** Menu with an optional row of reaction emoji on top. */
    fun menu(a: NativeActivity, reactions: List<String>?, onReact: ((String) -> Unit)?, items: List<Pair<String, () -> Unit>>) {
        val th = a.th
        val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL
        var dlg: AlertDialog? = null
        if (reactions != null && onReact != null) {
            val hs = HorizontalScrollView(a); hs.isHorizontalScrollBarEnabled = false
            val row = LinearLayout(a); row.setPadding(a.dp(8), a.dp(8), a.dp(8), a.dp(4))
            for (e in reactions) {
                val t = label(a, e, 26f, th.text); t.setPadding(a.dp(8), a.dp(4), a.dp(8), a.dp(4)); t.isClickable = true
                t.setOnClickListener { dlg?.dismiss(); onReact(e) }
                row.addView(t)
            }
            hs.addView(row); col.addView(hs)
        }
        for ((text, act) in items) col.addView(rowText(a, text, if (text == "حذف") th.danger else th.text) { dlg?.dismiss(); act() })
        val sc = ScrollView(a); sc.addView(col)
        dlg = sheet(a, sc)
    }

    private fun input(a: NativeActivity, hint: String, text: String = ""): EditText {
        val e = EditText(a).styled(a.th, hint)
        e.setText(text); e.background = rounded(a.th.field, a.dpf(10f)); e.setPadding(a.dp(12), a.dp(10), a.dp(12), a.dp(10))
        return e
    }

    private fun form(a: NativeActivity, title: String): LinearLayout {
        val c = LinearLayout(a); c.orientation = LinearLayout.VERTICAL; c.setPadding(a.dp(18), a.dp(16), a.dp(18), a.dp(10))
        c.addView(label(a, title, 18f, a.th.text, true).also { it.setPadding(0, 0, 0, a.dp(10)) })
        return c
    }

    private fun gap(a: NativeActivity) = View(a).also { it.layoutParams = lp(1, a.dp(8)) }

    // ------------------------------------------------------------------ bookmarks
    fun markDialog(a: NativeActivity, messageId: Long) {
        val c = form(a, "نشان کردن پیام")
        val tag = input(a, "دسته (اختیاری)"); val note = input(a, "یادداشت (اختیاری)")
        c.addView(tag); c.addView(gap(a)); c.addView(note)
        val row = LinearLayout(a); row.gravity = Gravity.END
        var d: AlertDialog? = null
        row.addView(textButton(a, a.th, "لغو", a.th.muted) { d?.dismiss() })
        row.addView(textButton(a, a.th, "نشان کن") {
            a.rpc("mark_set", mapOf("message_id" to messageId, "tag" to tag.text.toString().trim(), "note" to note.text.toString().trim())) { ok, r -> a.toast(if (ok) "نشان شد" else r.str("error", "خطا")) }
            d?.dismiss()
        })
        c.addView(row)
        d = sheet(a, c)
    }

    private fun openMsg(a: NativeActivity, chatId: Long, id: Long) {
        if (a.model.chats.containsKey(chatId)) a.push(ChatScreen(a, chatId, id)) else a.toast("این چت دیگه در دسترس نیست")
    }

    fun marks(a: NativeActivity) {
        val c = form(a, "نشان‌های من")
        val box = LinearLayout(a); box.orientation = LinearLayout.VERTICAL
        val sc = ScrollView(a); sc.addView(box)
        c.addView(sc, lp(MATCH, a.dp(420)))
        val d = sheet(a, c)
        box.addView(label(a, "در حال بارگذاری…", 14f, a.th.muted))
        a.rpc("marks") { ok, r ->
            box.removeAllViews()
            if (!ok) { box.addView(label(a, r.str("error", "خطا"), 14f, a.th.danger)); return@rpc }
            val l = r.list("marks")
            if (l.isEmpty()) box.addView(label(a, "هنوز پیامی رو نشان نکردی. روی پیام نگه دار و «نشان کردن» رو بزن.", 14f, a.th.muted))
            for (m in l) {
                val row = LinearLayout(a); row.orientation = LinearLayout.VERTICAL; row.setPadding(0, a.dp(8), 0, a.dp(8))
                val tg = m.str("tag")
                row.addView(label(a, m.str("sender") + (if (tg.isNotEmpty()) "  ·  #$tg" else ""), 13f, a.th.accent, true).oneLine())
                row.addView(label(a, ChatText.short(m.str("text"), 120), 15f, a.th.text).also { it.maxLines = 3 })
                if (m.str("note").isNotEmpty()) row.addView(label(a, "📝 " + m.str("note"), 13f, a.th.muted))
                row.background = ripple(null, a.th.ripple); row.isClickable = true
                row.setOnClickListener { d.dismiss(); openMsg(a, m.lng("chat_id"), m.lng("id")) }
                row.setOnLongClickListener {
                    AlertDialog.Builder(a).setMessage("نشان برداشته بشه؟").setPositiveButton("بله") { _, _ ->
                        a.rpc("mark_remove", mapOf("message_id" to m.lng("id"))) { ok2, _ -> if (ok2) { box.removeView(row) } }
                    }.setNegativeButton("نه", null).show(); true
                }
                box.addView(row)
            }
        }
    }

    // ------------------------------------------------------------------ search
    private fun resultRow(a: NativeActivity, who: String, text: String, ts: Long, onClick: () -> Unit): View {
        val row = LinearLayout(a); row.orientation = LinearLayout.VERTICAL; row.setPadding(0, a.dp(8), 0, a.dp(8))
        row.addView(label(a, who + "  ·  " + Fmt.listTime(ts), 12f, a.th.accent, true).oneLine())
        row.addView(label(a, ChatText.short(text, 120), 15f, a.th.text).also { it.maxLines = 2 })
        row.background = ripple(null, a.th.ripple); row.isClickable = true
        row.setOnClickListener { onClick() }
        return row
    }

    fun chatSearch(a: NativeActivity, chatId: Long, onPick: (Long) -> Unit) {
        val c = form(a, "جستجو در گفتگو")
        val q = input(a, "متن…"); q.setSingleLine(true); q.imeOptions = android.view.inputmethod.EditorInfo.IME_ACTION_SEARCH
        c.addView(q)
        val box = LinearLayout(a); box.orientation = LinearLayout.VERTICAL
        val sc = ScrollView(a); sc.addView(box)
        c.addView(sc, lp(MATCH, a.dp(340)))
        val d = sheet(a, c)
        q.setOnEditorActionListener { _, _, _ ->
            val t = q.text.toString().trim()
            if (t.isEmpty()) return@setOnEditorActionListener true
            box.removeAllViews(); box.addView(label(a, "در حال جستجو…", 14f, a.th.muted))
            a.rpc("search_messages", mapOf("chat_id" to chatId, "q" to t)) { ok, r ->
                box.removeAllViews()
                val l = if (ok) r.list("messages") else emptyList()
                if (l.isEmpty()) box.addView(label(a, if (ok) "چیزی پیدا نشد" else r.str("error", "خطا"), 14f, a.th.muted))
                for (m in l) box.addView(resultRow(a, m.str("sender_name"), ChatText.messageLine(m), m.lng("created_at")) { d.dismiss(); onPick(m.lng("id")) })
            }
            true
        }
        q.requestFocus()
    }

    fun advancedSearch(a: NativeActivity) {
        val c = form(a, "جستجوی پیشرفته")
        val q = input(a, "متن"); val who = input(a, "نام یا نام‌کاربری فرستنده"); val days = input(a, "فقط چند روز اخیر (مثلاً ۷)")
        days.inputType = InputType.TYPE_CLASS_NUMBER
        c.addView(q); c.addView(gap(a)); c.addView(who); c.addView(gap(a)); c.addView(days); c.addView(gap(a))
        val box = LinearLayout(a); box.orientation = LinearLayout.VERTICAL
        var d: AlertDialog? = null
        c.addView(primaryButton(a, a.th, "جستجو") {
            val p = LinkedHashMap<String, Any?>()
            p["q"] = q.text.toString().trim(); p["sender"] = who.text.toString().trim()
            val n = Fmt.latin(days.text.toString()).toLongOrNull()
            if (n != null && n > 0) p["from_ts"] = System.currentTimeMillis() / 1000 - n * 86400
            box.removeAllViews(); box.addView(label(a, "در حال جستجو…", 14f, a.th.muted))
            a.rpc("search_all", p) { ok, r ->
                box.removeAllViews()
                val l = if (ok) r.list("results") else emptyList()
                if (l.isEmpty()) box.addView(label(a, if (ok) "چیزی پیدا نشد" else r.str("error", "حداقل یه فیلد رو پر کن"), 14f, a.th.muted))
                for (m in l) box.addView(resultRow(a, m.str("sender_name"), m.str("body").ifEmpty { m.str("file_name") }, m.lng("created_at")) { d?.dismiss(); openMsg(a, m.lng("chat_id"), m.lng("id")) })
            }
        })
        val sc = ScrollView(a); sc.addView(box)
        c.addView(sc, lp(MATCH, a.dp(260)))
        d = sheet(a, c)
    }

    // ------------------------------------------------------------------ forward picker
    fun pickChats(a: NativeActivity, title: String, onDone: (List<Long>) -> Unit) {
        val c = form(a, title)
        val chosen = LinkedHashSet<Long>()
        val box = LinearLayout(a); box.orientation = LinearLayout.VERTICAL
        for (ch in a.model.chatList()) {
            if (!ch.bool("can_post", true)) continue
            val id = ch.lng("id")
            val x = ChatText.avatarOf(ch)
            val row = LinearLayout(a); row.gravity = Gravity.CENTER_VERTICAL; row.setPadding(0, a.dp(6), 0, a.dp(6))
            val av = AvatarView(a, { a.img }, { a.mediaKey }); av.setRing(a.th.panel); av.bind(x.kind, x.id, x.name, x.at, false)
            row.addView(av, lp(a.dp(40), a.dp(40)))
            val nm = label(a, ch.str("title"), 16f, a.th.text).oneLine(); nm.setPadding(a.dp(12), 0, a.dp(8), 0)
            row.addView(nm, lp(0, WRAP).weight(1f))
            val ck = label(a, "", 18f, a.th.accent, true)
            row.addView(ck)
            row.isClickable = true
            row.setOnClickListener {
                if (chosen.contains(id)) { chosen.remove(id); ck.text = "" }
                else if (chosen.size >= 5) a.toast("حداکثر ۵ چت") else { chosen.add(id); ck.text = "✓" }
            }
            box.addView(row)
        }
        val sc = ScrollView(a); sc.addView(box)
        c.addView(sc, lp(MATCH, a.dp(340)))
        var d: AlertDialog? = null
        c.addView(primaryButton(a, a.th, "ارسال") { if (chosen.isEmpty()) a.toast("یه چت انتخاب کن") else { d?.dismiss(); onDone(chosen.toList()) } })
        d = sheet(a, c)
    }

    // ------------------------------------------------------------------ profile
    fun profile(a: NativeActivity) {
        val me = a.model.me
        val c = form(a, "پروفایل من")
        c.addView(label(a, "@" + me.str("username"), 14f, a.th.muted).also { it.setPadding(0, 0, 0, a.dp(8)) })
        val name = input(a, "نام نمایشی", me.str("display_name")); val bio = input(a, "بیو", me.str("bio"))
        c.addView(name); c.addView(gap(a)); c.addView(bio); c.addView(gap(a))
        var d: AlertDialog? = null
        c.addView(primaryButton(a, a.th, "ذخیره") {
            a.rpc("update_profile", mapOf("display_name" to name.text.toString().trim(), "bio" to bio.text.toString().trim())) { ok, r ->
                if (ok) { val u = r.map("me") ?: r.map("user"); if (u != null) a.model.me.putAll(u) else { a.model.me["display_name"] = name.text.toString().trim(); a.model.me["bio"] = bio.text.toString().trim() }; a.toast("ذخیره شد"); d?.dismiss() }
                else a.toast(r.str("error", "خطا"))
            }
        })
        c.addView(textButton(a, a.th, "تغییر عکس پروفایل") { d?.dismiss(); a.groupAdmin.pickPhoto("me", 0) { } })
        d = sheet(a, c)
    }

    // ------------------------------------------------------------------ chat info
    fun chatInfo(a: NativeActivity, chatId: Long) {
        val ch = a.model.chats[chatId] ?: return
        val th = a.th
        val c = form(a, ch.str("title"))
        val x = ChatText.avatarOf(ch)
        var d: AlertDialog? = null
        val peer = ch.map("peer")
        if (peer != null) {
            c.addView(label(a, "@" + peer.str("username"), 14f, th.muted))
            if (peer.str("bio").isNotEmpty()) c.addView(label(a, peer.str("bio"), 15f, th.text).also { it.setPadding(0, a.dp(6), 0, 0) })
            c.addView(gap(a))
            val uid = peer.lng("id")
            val blockBtn = textButton(a, th, "…", th.danger) {}
            var blocked = false
            fun paint() { blockBtn.text = if (blocked) "رفع مسدودی" else "مسدود کردن" }
            paint()
            blockBtn.setOnClickListener {
                a.rpc(if (blocked) "unblock" else "block", mapOf("user_id" to uid)) { ok, r -> if (ok) { blocked = !blocked; paint() } else a.toast(r.str("error", "خطا")) }
            }
            a.rpc("privacy_get") { ok, r -> if (ok) { blocked = r.list("blocked").any { it.lng("id") == uid }; paint() } }
            c.addView(blockBtn)
            if (!ch.bool("saved")) c.addView(textButton(a, th, "حذف مخاطب", th.danger) {
                AlertDialog.Builder(a).setMessage("این مخاطب از لیست تو حذف بشه؟ (پیام‌ها فقط برای خودت پنهان می‌شن)").setPositiveButton("حذف") { _, _ ->
                    d?.dismiss(); a.rpc("delete_contact", mapOf("chat_id" to chatId)) { ok, r -> if (ok) { a.pop(); a.refreshChats() } else a.toast(r.str("error", "خطا")) }
                }.setNegativeButton("لغو", null).show()
            })
        } else if (!ch.bool("saved")) {
            if (ch.str("description").isNotEmpty()) c.addView(label(a, ch.str("description"), 15f, th.text).also { it.setPadding(0, 0, 0, a.dp(6)) })
            c.addView(label(a, Fmt.digits(ch.lng("member_count").toString()) + " عضو", 13f, th.muted))
            val box = LinearLayout(a); box.orientation = LinearLayout.VERTICAL
            val sc = ScrollView(a); sc.addView(box)
            c.addView(sc, lp(MATCH, a.dp(240)))
            a.rpc("members", mapOf("chat_id" to chatId)) { ok, r ->
                if (!ok) return@rpc
                for (u in r.list("members")) {
                    val role = when (u.str("role")) { "owner" -> " · سازنده"; "admin" -> " · ادمین"; else -> "" }
                    val row = label(a, u.str("display_name") + role, 15f, th.text).oneLine()
                    row.setPadding(0, a.dp(9), 0, a.dp(9)); row.isClickable = true
                    row.setOnClickListener {
                        if (u.lng("id") != a.model.myId) a.rpc("open_private", mapOf("username" to u.str("username"))) { ok2, r2 ->
                            if (ok2) r2.map("chat")?.let { n -> a.model.chats[n.lng("id")] = LinkedHashMap(n); d?.dismiss(); a.openChat(n.lng("id")) }
                        }
                    }
                    box.addView(row)
                }
            }
            if (ch.str("my_role") == "owner" || ch.str("my_role") == "admin") c.addView(textButton(a, th, "افزودن عضو") {
                val e = input(a, "نام‌کاربری")
                AlertDialog.Builder(a).setTitle("افزودن عضو").setView(e).setPositiveButton("اضافه کن") { _, _ ->
                    a.rpc("add_member", mapOf("chat_id" to chatId, "username" to e.text.toString().trim().trimStart('@'), "origin" to (a.api?.cfg?.base ?: ""))) { ok, r -> a.toast(if (ok && r.bool("invited")) "این کاربر اجازه‌ی اضافه‌شدن مستقیم نمی‌ده؛ لینک دعوت تو پیوی خودش رفت" else if (ok) "اضافه شد" else r.str("error", "خطا")) }
                }.setNegativeButton("لغو", null).show()
            })
            if (!ch.bool("channel")) c.addView(textButton(a, th, "ترک گروه", th.danger) {
                AlertDialog.Builder(a).setMessage("گروه رو ترک می‌کنی؟").setPositiveButton("ترک") { _, _ ->
                    d?.dismiss(); a.rpc("leave", mapOf("chat_id" to chatId)) { ok, r -> if (ok) { a.pop(); a.refreshChats() } else a.toast(r.str("error", "خطا")) }
                }.setNegativeButton("لغو", null).show()
            })
            if (ch.str("my_role") == "owner" && !ch.bool("channel")) c.addView(textButton(a, th, "حذف گروه", th.danger) {
                AlertDialog.Builder(a).setMessage("گروه برای همه حذف بشه؟ فایل‌هاش ۴ ساعت بعد پاک می‌شن.").setPositiveButton("حذف") { _, _ ->
                    d?.dismiss(); a.rpc("delete_group", mapOf("chat_id" to chatId)) { ok, r -> if (ok) { a.pop(); a.refreshChats() } else a.toast(r.str("error", "خطا")) }
                }.setNegativeButton("لغو", null).show()
            })
        }
        d = sheet(a, c)
        @Suppress("UNUSED_VARIABLE") val unused = x
    }
}
