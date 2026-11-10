package ir.windroida.app.ui

import android.app.AlertDialog
import android.content.ClipData
import android.content.ClipboardManager
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import ir.windroida.app.NativeActivity
import ir.windroida.app.net.Model
import ir.windroida.app.net.bool
import ir.windroida.app.net.list
import ir.windroida.app.net.lng
import ir.windroida.app.net.map
import ir.windroida.app.net.str

/** Telegram-like info page of a chat: big photo, name, action buttons, details, and the shared media / files / links / music / voice (+ members for groups). */
class ProfileScreen(private val a: NativeActivity, private val chatId: Long) : Screen(), Model.Listener {
    private val th = a.th
    private val root = FrameLayout(a)
    override val view: View get() = root
    private val col = LinearLayout(a)
    private val chipsBox = LinearLayout(a)
    private val content = LinearLayout(a)
    private var tab = "media"
    private var seq = 0
    private var blocked = false
    private val isGroup: Boolean get() = chat()?.let { it.str("kind") == "group" && it.map("peer") == null } ?: false

    private fun chat() = a.model.chats[chatId]

    init {
        root.background = th.screenBg()
        val sv = ScrollView(a); sv.isFillViewport = true
        col.orientation = LinearLayout.VERTICAL
        sv.addView(col, FrameLayout.LayoutParams(MATCH, WRAP))
        root.addView(sv, FrameLayout.LayoutParams(MATCH, MATCH))
        // floating top buttons
        val top = LinearLayout(a); top.setPadding(a.dp(4), a.dp(8), a.dp(4), 0)
        top.addView(iconButton(a, th, "back", th.text) { a.pop() })
        top.addView(View(a), lp(0, 1).weight(1f))
        top.addView(iconButton(a, th, "more", th.text) { moreMenu() })
        root.addView(top, FrameLayout.LayoutParams(MATCH, WRAP, Gravity.TOP))
        build()
        if (chat()?.map("peer") != null) a.rpc("privacy_get") { ok, r -> if (ok) { val id = chat()?.map("peer")?.lng("id"); blocked = r.list("blocked").any { it.lng("id") == id }; build() } }
    }

    override fun onShow() { a.listen(this) }
    override fun onHide() { a.unlisten(this) }
    override fun onDestroy() { a.unlisten(this) }
    override fun onChatList() {}
    override fun onChatChanged(chatId: Long) { if (chatId == this.chatId) { if (chat() == null) a.pop() else build() } }
    override fun onMessages(chatId: Long, kind: Int, messageId: Long) {}
    override fun onTyping(chatId: Long) {}
    override fun onNeedRefresh() {}
    override fun onSessionEnded(reason: String) {}

    private fun build() {
        val c = chat() ?: return
        col.removeAllViews()
        val x = ChatText.avatarOf(c)
        val av = AvatarView(a, { a.img }, { a.mediaKey }); av.setRing(th.bg)
        if (c.bool("saved")) av.vector = { cv, cx, cy, r -> val p = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG); p.color = 0xFF3390EC.toInt(); cv.drawCircle(cx, cy, r, p); val d = IconDrawable("bookmark", 0xFFFFFFFF.toInt()); d.setBounds((cx - r * 0.5f).toInt(), (cy - r * 0.5f).toInt(), (cx + r * 0.5f).toInt(), (cy + r * 0.5f).toInt()); d.draw(cv) }
        av.bind(x.kind, x.id, x.name, x.at, false)
        if (x.at > 0 && !c.bool("saved")) {                       // tap the photo: full screen, swipe through every kept photo
            av.isClickable = true
            av.setOnClickListener {
                val peer = c.map("peer")
                val q: Map<String, Any?> = if (peer != null) mapOf("user_id" to peer.lng("id")) else mapOf("chat_id" to chatId)
                a.rpc("avatar_list", q) { ok, r ->
                    val pics = ((r["pics"] as? List<*>) ?: emptyList<Any?>()).mapNotNull { it as? String }
                    val mine = if (peer != null) peer.lng("id") == a.model.myId else (c.str("my_role") == "owner" || (c.bool("channel") && c.bool("can_post")))
                    val del: ((String, (Boolean) -> Unit) -> Unit)? = if (!mine) null else fun(pic: String, done: (Boolean) -> Unit) {
                        val dq: Map<String, Any?> = if (peer != null) mapOf("pic" to pic) else mapOf("chat_id" to chatId, "pic" to pic)
                        a.rpc("remove_avatar_pic", dq) { ok2, r2 ->
                            if (!ok2) a.toast(r2.str("error", "نشد")) else a.refreshChats()
                            done(ok2)
                        }
                    }
                    if (ok && pics.isNotEmpty()) a.openImage(0L, c.str("title"), pics.map { "/avatar/" + x.kind + x.id + "?pic=" + java.net.URLEncoder.encode(it, "UTF-8") }, del)
                    else if (ok) a.toast("عکسی نیست") else a.toast("باز نشد")
                }
            }
        }
        val avp = LinearLayout.LayoutParams(a.dp(112), a.dp(112)); avp.gravity = Gravity.CENTER_HORIZONTAL; avp.topMargin = a.dp(52)
        col.addView(av, avp)
        val name = label(a, c.str("title"), 24f, th.text, true); name.gravity = Gravity.CENTER; name.setPadding(a.dp(16), a.dp(14), a.dp(16), 0)
        col.addView(name, lp(MATCH, WRAP))
        val (sub, hi) = ChatText.subtitle(c, a.model)
        val sv = label(a, sub, 14f, if (hi) th.accent else th.muted); sv.gravity = Gravity.CENTER; sv.setPadding(0, a.dp(4), 0, a.dp(16))
        col.addView(sv, lp(MATCH, WRAP))
        // action buttons
        val acts = LinearLayout(a); acts.setPadding(a.dp(10), 0, a.dp(10), 0)
        fun act(ic: String, text: String, color: Int = th.accent, f: () -> Unit) {
            val b = LinearLayout(a); b.orientation = LinearLayout.VERTICAL; b.gravity = Gravity.CENTER
            b.background = ripple(rounded(th.panel, a.dpf(14f)), th.ripple); b.isClickable = true
            b.setPadding(0, a.dp(12), 0, a.dp(10))
            b.addView(icon(a, ic, color, 24)); b.addView(label(a, text, 12f, th.text, true).also { it.setPadding(0, a.dp(6), 0, 0); it.gravity = Gravity.CENTER })
            b.setOnClickListener { f() }
            val p = LinearLayout.LayoutParams(0, WRAP, 1f); p.setMargins(a.dp(4), 0, a.dp(4), 0)
            acts.addView(b, p)
        }
        act("send", "پیام") { a.pop() }
        act("bell", if (c.bool("muted")) "صدادار" else "بی‌صدا") { toggleMute() }
        act("search", "جستجو") { Dialogs.chatSearch(a, chatId) { id -> a.pop(); a.openChatAt(chatId, id) } }
        if (isGroup) {
            if (c.str("my_role") == "owner" || c.str("my_role") == "admin") act("plus", "افزودن") { addMember() }
            else act("logout", "خروج", th.danger) { leaveGroup() }
        } else if (c.map("peer") != null) act("lock", if (blocked) "رفع مسدودی" else "مسدود", th.danger) { toggleBlock() }
        col.addView(acts, lp(MATCH, WRAP))
        // details card
        val card = LinearLayout(a); card.orientation = LinearLayout.VERTICAL; card.background = rounded(th.panel, a.dpf(14f)); card.setPadding(a.dp(16), a.dp(6), a.dp(16), a.dp(6))
        fun row(value: String, caption: String, copy: Boolean = true) {
            if (value.isEmpty()) return
            val r = LinearLayout(a); r.orientation = LinearLayout.VERTICAL; r.setPadding(0, a.dp(8), 0, a.dp(8))
            r.addView(label(a, value, 16f, th.text)); r.addView(label(a, caption, 13f, th.muted).also { it.setPadding(0, a.dp(2), 0, 0) })
            if (copy) { r.isClickable = true; r.setOnClickListener { a.getSystemService(ClipboardManager::class.java)?.setPrimaryClip(ClipData.newPlainText("t", value)); a.toast("کپی شد") } }
            card.addView(r)
        }
        val peer = c.map("peer")
        if (peer != null) { row("@" + peer.str("username"), "نام‌کاربری"); row(peer.str("bio"), "درباره") }
        else { row(c.str("username").let { if (it.isNotEmpty()) "@$it" else "" }, "نام‌کاربری"); row(c.str("description"), "توضیحات") }
        if (card.childCount > 0) { val p = lp(MATCH, WRAP); p.setMargins(a.dp(14), a.dp(12), a.dp(14), 0); col.addView(card, p) }
        // tabs
        val hs = HorizontalScrollView(a); hs.isHorizontalScrollBarEnabled = false
        chipsBox.removeAllViews(); chipsBox.setPadding(a.dp(10), a.dp(4), a.dp(10), a.dp(4))
        (chipsBox.parent as? android.view.ViewGroup)?.removeView(chipsBox)       // build() can run again (profile reloaded): the old strip still holds it
        hs.addView(chipsBox)
        val cp = lp(MATCH, WRAP); cp.topMargin = a.dp(14)
        col.addView(hs, cp)
        content.orientation = LinearLayout.VERTICAL
        (content.parent as? android.view.ViewGroup)?.removeView(content)
        col.addView(content, lp(MATCH, WRAP))
        drawChips(); load()
    }

    private fun tabs(): List<Pair<String, String>> {
        val l = ArrayList<Pair<String, String>>()
        if (isGroup) l.add("members" to "اعضا")
        l.add("media" to "رسانه"); l.add("file" to "فایل‌ها"); l.add("link" to "لینک‌ها"); l.add("audio" to "موزیک"); l.add("voice" to "ویس")
        return l
    }

    private fun drawChips() {
        chipsBox.removeAllViews()
        if (tabs().none { it.first == tab }) tab = tabs().first().first
        for ((k, t) in tabs()) {
            val on = k == tab
            val ch = label(a, t, 14f, if (on) th.accent else th.muted, true)
            ch.background = if (on) rounded(if (th.dark) 0xFF1E3550.toInt() else 0xFFDCEBFA.toInt(), a.dpf(18f)) else null
            ch.setPadding(a.dp(16), a.dp(8), a.dp(16), a.dp(8)); ch.isClickable = true
            ch.setOnClickListener { tab = k; drawChips(); load() }
            chipsBox.addView(ch)
        }
    }

    private fun load() {
        val my = ++seq
        content.removeAllViews()
        if (tab == "members") { loadMembers(my); return }
        content.addView(label(a, "در حال بارگذاری…", 14f, th.muted).also { it.setPadding(a.dp(16), a.dp(20), a.dp(16), a.dp(20)) })
        a.rpc("shared", mapOf("chat_id" to chatId, "kind" to tab)) { ok, r ->
            if (my != seq) return@rpc
            content.removeAllViews()
            val l = if (ok) r.list("messages") else emptyList()
            if (l.isEmpty()) { content.addView(label(a, if (ok) "چیزی نیست" else r.str("error", "خطا"), 14f, th.muted).also { it.setPadding(a.dp(16), a.dp(24), a.dp(16), a.dp(24)); it.gravity = Gravity.CENTER }); return@rpc }
            if (tab == "media") grid(l) else for (m in l) content.addView(listRow(m))
        }
    }

    private fun open(m: Map<String, Any?>) { a.pop(); a.openChatAt(chatId, m.lng("id")) }

    private fun grid(l: List<Map<String, Any?>>) {
        val w = a.resources.displayMetrics.widthPixels / 3
        var row: LinearLayout? = null
        for ((i, m) in l.withIndex()) {
            if (i % 3 == 0) { row = LinearLayout(a); content.addView(row, lp(MATCH, w)) }
            val fl = FrameLayout(a); fl.setBackgroundColor(th.panel)
            val iv = ImageView(a); iv.scaleType = ImageView.ScaleType.CENTER_CROP
            fl.addView(iv, FrameLayout.LayoutParams(MATCH, MATCH))
            a.img?.load("/thumb/" + m.lng("id"), a.mediaKey, 320) { b -> if (b != null) iv.setImageBitmap(b) }
            if (m.map("file")?.str("kind") == "video") {
                val pc = FrameLayout(a); pc.background = rounded(0x99000000.toInt(), a.dpf(16f))
                pc.addView(icon(a, "play", 0xFFFFFFFF.toInt(), 16), FrameLayout.LayoutParams(a.dp(16), a.dp(16), Gravity.CENTER))
                fl.addView(pc, FrameLayout.LayoutParams(a.dp(32), a.dp(32), Gravity.CENTER))
            }
            fl.isClickable = true; fl.setOnClickListener { open(m) }
            val p = LinearLayout.LayoutParams(0, MATCH, 1f); p.setMargins(1, 1, 1, 1)
            row!!.addView(fl, p)
        }
        // pad the last row so cells keep their size
        val rest = l.size % 3
        if (rest != 0) for (k in rest until 3) row!!.addView(View(a), LinearLayout.LayoutParams(0, MATCH, 1f))
    }

    private fun listRow(m: Map<String, Any?>): View {
        val f = m.map("file")
        val r = LinearLayout(a); r.gravity = Gravity.CENTER_VERTICAL; r.setPadding(a.dp(16), a.dp(10), a.dp(16), a.dp(10))
        r.background = ripple(null, th.ripple); r.isClickable = true
        val ic = FrameLayout(a); ic.background = rounded(th.accentFill, a.dpf(22f))
        ic.addView(icon(a, if (tab == "link") "forward" else if (tab == "audio" || tab == "voice") "play" else "file", 0xFFFFFFFF.toInt(), 22), FrameLayout.LayoutParams(a.dp(22), a.dp(22), Gravity.CENTER))
        r.addView(ic, lp(a.dp(44), a.dp(44)))
        val c = LinearLayout(a); c.orientation = LinearLayout.VERTICAL; c.setPadding(a.dp(12), 0, 0, 0)
        val title = when { tab == "link" -> Regex("https?://\\S+").find(m.str("body"))?.value ?: m.str("body"); tab == "voice" -> "پیام صوتی " + Fmt.duration(f?.lng("dur") ?: 0L); else -> f?.str("name") ?: "" }
        c.addView(label(a, title, 15f, th.text, true).oneLine().also { if (tab == "link") it.textDirection = View.TEXT_DIRECTION_LTR })
        val sub = (if (f != null && tab != "voice") Fmt.size(f.lng("size")) + " · " else "") + m.str("sender_name") + " · " + Fmt.listTime(m.lng("created_at"))
        c.addView(label(a, sub, 12f, th.muted).oneLine())
        r.addView(c, lp(0, WRAP).weight(1f))
        r.setOnClickListener { if (tab == "link") { val u = Regex("https?://\\S+").find(m.str("body"))?.value; if (u != null) try { a.startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW, android.net.Uri.parse(u))) } catch (_: Exception) {} } else open(m) }
        r.setOnLongClickListener { open(m); true }
        return r
    }

    private fun loadMembers(my: Int) {
        content.addView(label(a, "در حال بارگذاری…", 14f, th.muted).also { it.setPadding(a.dp(16), a.dp(20), a.dp(16), a.dp(20)) })
        a.rpc("members", mapOf("chat_id" to chatId)) { ok, r ->
            if (my != seq) return@rpc
            content.removeAllViews()
            val sorted: List<Map<String, Any?>> = (if (ok) r.list("members") else emptyList()).sortedWith(compareBy<Map<String, Any?>>(
                { when (it.str("role")) { "owner" -> 0; "admin" -> 1; else -> 2 } },
                { if (it.bool("online")) 0 else 1 },
                { -it.lng("last_seen") }))
            for (u in sorted) {
                val row = LinearLayout(a); row.gravity = Gravity.CENTER_VERTICAL; row.setPadding(a.dp(16), a.dp(8), a.dp(16), a.dp(8))
                row.background = ripple(null, th.ripple); row.isClickable = true
                val av = AvatarView(a, { a.img }, { a.mediaKey }); av.setRing(th.bg); av.bind("u", u.lng("id"), u.str("display_name"), u.lng("avatar_at"), u.bool("online"))
                row.addView(av, lp(a.dp(44), a.dp(44)))
                val c = LinearLayout(a); c.orientation = LinearLayout.VERTICAL; c.setPadding(a.dp(12), 0, 0, 0)
                c.addView(label(a, u.str("display_name"), 16f, th.text, true).oneLine())
                val seenTxt = if (u.bool("online")) " · آنلاین" else if (u.bool("seen_hidden")) "" else " · " + Fmt.lastSeen(u.lng("last_seen"))
                c.addView(label(a, "@" + u.str("username") + seenTxt, 13f, if (u.bool("online")) th.accent else th.muted).oneLine())
                row.addView(c, lp(0, WRAP).weight(1f))
                val role = when (u.str("role")) { "owner" -> "سازنده"; "admin" -> "ادمین"; else -> "" }
                if (role.isNotEmpty()) row.addView(label(a, role, 12f, th.accent, true))
                val my = chat()?.str("my_role") ?: "member"
                val manage = (my == "owner" || (my == "admin" && u.str("role") == "member")) && u.str("role") != "owner" && u.lng("id") != a.model.myId && !(chat()?.bool("channel") ?: false)
                if (u.lng("muted_until") > 0) row.addView(label(a, "🔇", 14f, th.muted))
                if (manage) { row.setOnLongClickListener { a.groupAdmin.memberMenu(chatId, u, my == "owner") { load() }; true }
                    row.addView(iconButton(a, th, "more", th.muted) { a.groupAdmin.memberMenu(chatId, u, my == "owner") { load() } }) }
                row.setOnClickListener {
                    if (u.lng("id") != a.model.myId) a.rpc("open_private", mapOf("username" to u.str("username"))) { ok2, r2 ->
                        if (ok2) r2.map("chat")?.let { n -> a.model.chats[n.lng("id")] = LinkedHashMap(n); a.pop(); a.openChat(n.lng("id")) }
                    }
                }
                content.addView(row)
            }
        }
    }

    // ------------------------------------------------------------------ actions
    private fun toggleMute() {
        val c = chat() ?: return
        a.rpc("chat_settings", mapOf("chat_id" to chatId, "muted" to !c.bool("muted"))) { ok, r ->
            if (ok) r.map("chat")?.let { n -> c.putAll(n); a.model.listener?.onChatList(); build() } else a.toast(r.str("error", "خطا"))
        }
    }

    private fun toggleBlock() {
        val uid = chat()?.map("peer")?.lng("id") ?: return
        a.rpc(if (blocked) "unblock" else "block", mapOf("user_id" to uid)) { ok, r -> if (ok) { blocked = !blocked; build() } else a.toast(r.str("error", "خطا")) }
    }

    private fun addMember() {
        val e = EditText(a).styled(th, "نام‌کاربری"); e.setSingleLine(true)
        AlertDialog.Builder(a).setTitle("افزودن عضو").setView(e).setPositiveButton("اضافه کن") { _, _ ->
            a.rpc("add_member", mapOf("chat_id" to chatId, "username" to e.text.toString().trim().trimStart('@'), "origin" to (a.api?.cfg?.base ?: ""))) { ok, r -> a.toast(if (ok && r.bool("invited")) "این کاربر اجازه‌ی اضافه‌شدن مستقیم نمی‌ده؛ لینک دعوت تو پیوی خودش رفت" else if (ok) "اضافه شد" else r.str("error", "خطا")); if (ok) { a.refreshChats(); load() } }
        }.setNegativeButton("لغو", null).show()
    }

    private fun leaveGroup() {
        AlertDialog.Builder(a).setMessage("گروه رو ترک می‌کنی؟").setPositiveButton("ترک") { _, _ ->
            a.rpc("leave", mapOf("chat_id" to chatId)) { ok, r -> if (ok) { a.pop(); a.pop(); a.refreshChats() } else a.toast(r.str("error", "خطا")) }
        }.setNegativeButton("لغو", null).show()
    }

    private fun moreMenu() {
        val c = chat() ?: return
        val items = ArrayList<Pair<String, () -> Unit>>()
        if (isGroup) {
            if (c.str("my_role") == "owner" || c.str("my_role") == "admin") items.add(Pair("مدیریت گروه") { a.groupAdmin.settings(chatId) { build() } })
            if (c.str("my_role") == "owner" || c.str("my_role") == "admin") items.add(Pair("ترک گروه") { leaveGroup() })
            if (c.str("my_role") == "owner" && !c.bool("channel")) items.add(Pair("حذف") {
                AlertDialog.Builder(a).setMessage("گروه برای همه حذف بشه؟ فایل‌هاش ۴ ساعت بعد پاک می‌شن.").setPositiveButton("حذف") { _, _ ->
                    a.rpc("delete_group", mapOf("chat_id" to chatId)) { ok, r -> if (ok) { a.pop(); a.pop(); a.refreshChats() } else a.toast(r.str("error", "خطا")) }
                }.setNegativeButton("لغو", null).show()
            })
        } else if (!c.bool("saved") && c.map("peer") != null) {
            items.add(Pair("حذف") {
                AlertDialog.Builder(a).setMessage("این مخاطب از لیست تو حذف بشه؟ (پیام‌ها فقط برای خودت پنهان می‌شن)").setPositiveButton("حذف") { _, _ ->
                    a.rpc("delete_contact", mapOf("chat_id" to chatId)) { ok, r -> if (ok) { a.pop(); a.pop(); a.refreshChats() } else a.toast(r.str("error", "خطا")) }
                }.setNegativeButton("لغو", null).show()
            })
        }
        if (items.isEmpty()) return
        Dialogs.menu(a, null, null, items)
    }
}
