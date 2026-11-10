package ir.windroida.app.ui

import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.BaseAdapter
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.ScrollView
import android.widget.TextView
import ir.windroida.app.NativeActivity
import ir.windroida.app.SiteActivity
import ir.windroida.app.net.Api
import ir.windroida.app.net.Model
import ir.windroida.app.net.bool
import ir.windroida.app.net.list
import ir.windroida.app.net.lng
import ir.windroida.app.net.map
import ir.windroida.app.net.str

/** The chat list (home screen): bar, filters, search, rows, new-chat button and the side menu. */
/** the "found a bug? use the web version" note is shown once per app start */
private var bugNoteDone = false

class ListScreen(private val a: NativeActivity) : Screen(), Model.Listener {
    private val th = a.th
    private val root = FrameLayout(a)
    override val view: View get() = root
    private val title = label(a, "Windroida", 20f, th.barText, true)
    private val searchBox = EditText(a)
    private val bar = LinearLayout(a)
    private val chips = LinearLayout(a)
    private val list = ListView(a)
    private val empty = label(a, "", 15f, th.muted)
    private var filter = "all"
    private var query = ""
    private var searching = false
    private var seq = 0
    private var userHits: List<Map<String, Any?>> = emptyList()
    private var groupHits: List<Map<String, Any?>> = emptyList()
    private var msgHits: List<Map<String, Any?>> = emptyList()
    private val rows = ArrayList<Row>()
    private var drawer: View? = null
    private val tick = Runnable { refreshLater() }
    private var net = Api.CONNECTING

    private sealed class Row {
        class Chat(val c: Map<String, Any?>) : Row()
        class Head(val text: String) : Row()
        class User(val u: Map<String, Any?>) : Row()
        class Group(val g: Map<String, Any?>) : Row()
        class Msg(val m: Map<String, Any?>) : Row()
    }

    // ------------------------------------------------------------------ adapter
    private val adapter = object : BaseAdapter() {
        override fun getCount() = rows.size
        override fun getItem(p: Int): Any = rows[p]
        override fun getItemId(p: Int) = p.toLong()
        override fun getViewTypeCount() = 3
        override fun getItemViewType(p: Int) = when (rows[p]) { is Row.Head -> 0; is Row.Chat -> 1; else -> 2 }
        override fun getView(p: Int, cv: View?, parent: ViewGroup?): View = when (val r = rows[p]) {
            is Row.Head -> headView(cv, r.text)
            is Row.Chat -> chatView(cv, r.c)
            is Row.User -> simpleView(cv, r.u.str("display_name"), "@" + r.u.str("username"), "u", r.u.lng("id"), r.u.lng("avatar_at"))
            is Row.Group -> simpleView(cv, r.g.str("title"), "@" + r.g.str("username") + " · " + Fmt.digits(r.g.lng("member_count").toString()) + " عضو", "c", r.g.lng("id"), r.g.lng("avatar_at"))
            is Row.Msg -> msgView(cv, r.m)
        }
    }


    private val filters = listOf("all" to "همه", "unread" to "خوانده‌نشده", "private" to "شخصی", "group" to "گروه‌ها", "fav" to "سنجاق‌شده")
    init {
        root.background = th.screenBg()
        val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL
        // --- top bar
        bar.orientation = LinearLayout.HORIZONTAL; bar.gravity = Gravity.CENTER_VERTICAL; bar.background = th.frostBar(a, if (th.dark) 0x80101530.toInt() else 0xB3FFFFFF.toInt())
        bar.setPadding(a.dp(4), 0, a.dp(4), 0)
        buildBar()
        col.addView(bar, lp(MATCH, a.dp(56)))
        // --- filter chips
        val hs = HorizontalScrollView(a); hs.isHorizontalScrollBarEnabled = false; hs.background = th.frostBar(a, if (th.dark) 0x4D101530 else 0x80FFFFFF.toInt())
        chips.orientation = LinearLayout.HORIZONTAL; chips.setPadding(a.dp(8), a.dp(6), a.dp(8), a.dp(6)); hs.addView(chips)
        col.addView(hs, lp(MATCH, WRAP))
        // --- one-line note on every app start: the native app is the default; if something is broken the web version still has everything
        if (!bugNoteDone) {
            bugNoteDone = true
            val note = LinearLayout(a); note.orientation = LinearLayout.HORIZONTAL; note.gravity = Gravity.CENTER_VERTICAL
            note.setBackgroundColor(th.accent and 0x00FFFFFF or 0x22000000); note.setPadding(a.dp(14), a.dp(6), a.dp(6), a.dp(6))
            note.addView(label(a, "باگی دیدی؟ از نسخه وب استفاده کن 🙂", 13f, th.text), lp(0, WRAP).weight(1f))
            note.addView(label(a, "نسخه وب", 13f, th.accent, true).also { it.setPadding(a.dp(10), a.dp(6), a.dp(10), a.dp(6)); it.isClickable = true; it.setOnClickListener { bugNoteDone = true; a.openWeb() } })
            note.addView(label(a, "✕", 15f, th.muted).also { it.setPadding(a.dp(10), a.dp(6), a.dp(10), a.dp(6)); it.isClickable = true; it.setOnClickListener { bugNoteDone = true; col.removeView(note) } })
            col.addView(note, lp(MATCH, WRAP))
        }
        // --- list
        list.divider = null; list.setBackgroundColor(0); list.selector = ripple(null, th.ripple)
        list.adapter = adapter
        list.setOnItemClickListener { _, _, pos, _ -> onRowClick(rows[pos]) }
        list.setOnItemLongClickListener { _, _, pos, _ -> val r = rows[pos]; if (r is Row.Chat) { chatMenu(r.c); true } else false }
        val body = SwipeBody()
        body.addView(list, FrameLayout.LayoutParams(MATCH, MATCH))
        empty.gravity = Gravity.CENTER; empty.setPadding(a.dp(30), 0, a.dp(30), 0)
        body.addView(empty, FrameLayout.LayoutParams(MATCH, MATCH))
        col.addView(body, lp(MATCH, 0).weight(1f))
        root.addView(col, FrameLayout.LayoutParams(MATCH, MATCH))
        // --- new chat button
        val fab = FrameLayout(a)
        fab.background = rounded(th.accentFill, a.dpf(28f)); fab.elevation = a.dpf(6f)
        fab.addView(icon(a, "pencil", 0xFFFFFFFF.toInt(), 24), FrameLayout.LayoutParams(a.dp(24), a.dp(24), Gravity.CENTER))
        fab.isClickable = true
        fab.setOnClickListener { newMenu() }
        val fl = FrameLayout.LayoutParams(a.dp(56), a.dp(56), Gravity.BOTTOM or Gravity.END); fl.setMargins(a.dp(16), 0, a.dp(16), a.dp(96))
        root.addView(fab, fl)
        list.clipToPadding = false; list.setPadding(0, 0, 0, a.dp(92))
        root.addView(buildTabs(), FrameLayout.LayoutParams(MATCH, WRAP, Gravity.BOTTOM).also { it.setMargins(a.dp(14), 0, a.dp(14), a.dp(14)) })
        searchBox.styled(th, "جستجو…")
        searchBox.setTextColor(th.barText); searchBox.setHintTextColor(0x99FFFFFF.toInt())
        searchBox.setSingleLine(true)
        searchBox.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) { query = s?.toString()?.trim() ?: ""; rebuild(); scheduleSearch() }
            override fun beforeTextChanged(s: CharSequence?, st: Int, c: Int, af: Int) {}
            override fun onTextChanged(s: CharSequence?, st: Int, b: Int, c: Int) {}
        })
        buildChips()
        rebuild()
    }

    // ------------------------------------------------------------------ life
    override fun onShow() { a.listen(this); a.main.postDelayed(tick, 5000); rebuild(); updateTitle() }
    override fun onHide() { a.unlisten(this); a.main.removeCallbacks(tick) }
    override fun onDestroy() { a.unlisten(this); a.main.removeCallbacks(tick) }
    override fun onBack(): Boolean {
        if (drawer != null) { closeDrawer(); return true }
        if (searching) { setSearching(false); return true }
        return false
    }

    /** the "typing…" lines expire by themselves: redraw now and then */
    private fun refreshLater() { adapter.notifyDataSetChanged(); a.main.postDelayed(tick, 5000) }

    fun onNetState(s: Int) { net = s; updateTitle() }

    private fun updateTitle() {
        title.text = when (net) { Api.ONLINE -> "Windroida"; Api.CONNECTED -> "Windroida"; else -> if (net == Api.OFFLINE && a.netError.isNotEmpty()) "در حال اتصال… ⓘ" else "در حال اتصال…" }
    }

    override fun onChatList() { rebuild(); buildChips() }
    override fun onChatChanged(chatId: Long) {}
    override fun onMessages(chatId: Long, kind: Int, messageId: Long) {}
    override fun onTyping(chatId: Long) { adapter.notifyDataSetChanged() }
    override fun onNeedRefresh() {}
    override fun onSessionEnded(reason: String) {}

    // ------------------------------------------------------------------ top bar
    private fun buildBar() {
        bar.removeAllViews()
        if (searching) {
            bar.addView(iconButton(a, th, "back", th.barText) { setSearching(false) })
            bar.addView(searchBox, lp(0, WRAP).weight(1f))
            bar.addView(iconButton(a, th, "close", th.barText) { searchBox.setText("") })
            searchBox.requestFocus()
        } else {
            bar.addView(iconButton(a, th, "menu", th.barText) { openDrawer() })
            title.setPadding(a.dp(8), 0, 0, 0)
            bar.addView(title, lp(0, WRAP).weight(1f))
            title.isClickable = true
            title.setOnClickListener {
                if (net != Api.ONLINE) AlertDialog.Builder(a).setTitle("وضعیت اتصال")
                    .setMessage(if (a.netError.isNotEmpty()) a.netError else "در حال اتصال…")
                    .setPositiveButton("تلاش دوباره") { _, _ -> a.api?.reconnectNow() }.setNeutralButton("تأیید دوباره‌ی گواهی") { _, _ -> a.repin() }.setNegativeButton("بستن", null).show()
            }
            bar.addView(iconButton(a, th, "search", th.barText) { setSearching(true) })
        }
    }

    private fun setSearching(on: Boolean) {
        searching = on
        if (!on) { searchBox.setText(""); a.hideKeyboard(searchBox) }
        buildBar(); rebuild()
        if (on) { searchBox.requestFocus(); val im = a.getSystemService(android.view.inputmethod.InputMethodManager::class.java); im?.showSoftInput(searchBox, 0) }
    }

    // ------------------------------------------------------------------ filters

    /** drag the list left / right = the next / previous filter (like Telegram folders); the list follows the finger */
    private inner class SwipeBody : FrameLayout(a) {
        private var x0 = 0f; private var y0 = 0f; private var on = false; private var t0 = 0L
        private fun idx() = filters.indexOfFirst { it.first == filter }
        private fun detect(e: android.view.MotionEvent) {
            if (on || searching) return
            val dx = e.x - x0; val dy = e.y - y0
            if (Math.abs(dx) > a.dp(18) && Math.abs(dx) > Math.abs(dy) * 1.6f) { on = true; x0 = e.x; t0 = System.currentTimeMillis() }
        }
        override fun onInterceptTouchEvent(e: android.view.MotionEvent): Boolean {
            if (e.actionMasked == android.view.MotionEvent.ACTION_DOWN) { x0 = e.x; y0 = e.y; on = false }
            else if (e.actionMasked == android.view.MotionEvent.ACTION_MOVE) detect(e)
            return on
        }
        override fun onTouchEvent(e: android.view.MotionEvent): Boolean {
            when (e.actionMasked) {
                android.view.MotionEvent.ACTION_DOWN -> { x0 = e.x; y0 = e.y; on = false }
                android.view.MotionEvent.ACTION_MOVE -> {
                    detect(e)
                    if (on) { val dx = e.x - x0; val n = idx() + (if (dx < 0) 1 else -1); val ok = n >= 0 && n < filters.size; list.translationX = if (ok) dx else dx * 0.2f }
                }
                android.view.MotionEvent.ACTION_UP, android.view.MotionEvent.ACTION_CANCEL -> if (on) {
                    on = false
                    val dx = list.translationX; val w = Math.max(1, width).toFloat()
                    val dir = if (dx < 0) 1 else -1; val n = idx() + dir
                    val go = e.actionMasked == android.view.MotionEvent.ACTION_UP && n >= 0 && n < filters.size &&
                        (Math.abs(dx) > w * 0.25f || (Math.abs(dx) > a.dp(50) && System.currentTimeMillis() - t0 < 280))
                    if (!go) list.animate().translationX(0f).setDuration(150).start()
                    else list.animate().translationX(-dir * w).setDuration(120).withEndAction {
                        filter = filters[n].first; buildChips(); rebuild(); drawTabs()
                        list.setSelection(0)
                        list.translationX = dir * w
                        list.animate().translationX(0f).setDuration(170).start()
                    }.start()
                }
            }
            return true
        }
    }

    // ------------------------------------------------------------------ floating tab bar (Chats / Contacts / Games / Settings)
    private var tabBar: LinearLayout? = null
    private fun buildTabs(): View {
        val bar = FrostLinear(a, th, 30); bar.orientation = LinearLayout.HORIZONTAL; bar.gravity = Gravity.CENTER_VERTICAL
        bar.setPadding(a.dp(8), a.dp(6), a.dp(8), a.dp(6)); bar.elevation = a.dpf(10f)
        bar.background = th.glass(a, 30, if (th.dark) 0x5E1C2040 else 0x73FFFFFF)       // light tint on top of the live blur: real frosted glass
        tabBar = bar
        drawTabs()
        return bar
    }

    private fun drawTabs() {
        val bar = tabBar ?: return
        bar.removeAllViews()
        val tabs = listOf(Triple("all", "chat", "چت‌ها"), Triple("private", "person", "مخاطبین"), Triple("games", "gamepad", "بازی‌ها"), Triple("ghab", "image", "قاب"), Triple("settings", "settings", "تنظیمات"))
        for ((k, ic, text) in tabs) {
            val on = (k == "all" && filter != "private") || (k == "private" && filter == "private")
            val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL; col.gravity = Gravity.CENTER
            col.setPadding(a.dp(6), a.dp(6), a.dp(6), a.dp(5))
            val c = if (on) th.accent else th.muted
            col.addView(icon(a, ic, c, 24))
            val l = label(a, text, 11f, c, on); l.gravity = Gravity.CENTER; l.setPadding(0, a.dp(2), 0, 0)
            col.addView(l)
            if (on) col.background = rounded(if (th.dark) 0x33A597FF else 0x227A6BFF, a.dpf(24f))
            col.isClickable = true
            col.pressScale(0.92f)
            col.setOnClickListener {
                when (k) {
                    "all" -> { filter = "all"; buildChips(); rebuild(); drawTabs() }
                    "private" -> { filter = "private"; buildChips(); rebuild(); drawTabs() }
                    "games" -> gamesMenu()
                    "ghab" -> a.openGhabWeb()
                    else -> a.push(SettingsScreen(a))
                }
            }
            bar.addView(col, lp(0, WRAP).weight(1f).also { it.setMargins(a.dp(2), 0, a.dp(2), 0) })
        }
    }

    /** rooms and games live in the web app (one visit: the chosen version of the app does not change) */
    private fun gamesMenu() {
        val d = android.app.Dialog(a)
        d.requestWindowFeature(android.view.Window.FEATURE_NO_TITLE)
        val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL; col.setPadding(a.dp(16), a.dp(18), a.dp(16), a.dp(12))
        col.background = rounded(th.panel, a.dpf(24f))
        col.addView(label(a, "🎮 بازی‌ها و اتاق‌ها", 18f, th.text, true))
        col.addView(label(a, "با دوستات همزمان بازی کن یا آهنگ و فیلم ببین", 13f, th.muted).also { it.setPadding(0, a.dp(2), 0, a.dp(10)) })
        fun card(emoji: String, name: String, sub: String, c1: Int, c2: Int, kind: String) {
            val row = LinearLayout(a); row.orientation = LinearLayout.HORIZONTAL; row.gravity = Gravity.CENTER_VERTICAL
            row.setPadding(a.dp(14), a.dp(12), a.dp(14), a.dp(12))
            val g = android.graphics.drawable.GradientDrawable(android.graphics.drawable.GradientDrawable.Orientation.RIGHT_LEFT, intArrayOf(c1, c2))
            g.cornerRadius = a.dpf(18f); row.background = g
            val em = label(a, emoji, 28f, 0xFFFFFFFF.toInt()); row.addView(em)
            val t = LinearLayout(a); t.orientation = LinearLayout.VERTICAL; t.setPadding(a.dp(12), 0, 0, 0)
            t.addView(label(a, name, 16f, 0xFFFFFFFF.toInt(), true)); t.addView(label(a, sub, 12f, 0xDDFFFFFF.toInt()))
            row.addView(t, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            row.isClickable = true; row.pressScale(0.96f)
            row.setOnClickListener { d.dismiss(); a.openWebOnce("game=$kind") }
            col.addView(row, lp(MATCH, WRAP).also { it.bottomMargin = a.dp(8) })
        }
        card("🎬", "اتاق تماشا / گوش‌دادن", "فیلم و آهنگ همزمان با دوستان", 0xFF7C3AED.toInt(), 0xFF4F46E5.toInt(), "room")
        card("♟", "شطرنج", "دو نفره؛ تو اتاق", 0xFF0EA5E9.toInt(), 0xFF2563EB.toInt(), "chess")
        card("🎭", "مافیا", "۵ تا ۱۵ نفر؛ تو اتاق", 0xFFE11D48.toInt(), 0xFF9F1239.toInt(), "mafia")
        card("🎲", "منچ", "۲ تا ۴ نفر؛ تو اتاق", 0xFFF59E0B.toInt(), 0xFFEA580C.toInt(), "mensch")
        col.addView(label(a, "بازی‌ها تو یه اتاق جدید باز می‌شن (با دکمه‌ی برگشت برمی‌گردی همین‌جا).", 11f, th.muted).also { it.setPadding(a.dp(4), a.dp(4), a.dp(4), 0) })
        d.setContentView(col)
        d.window?.setBackgroundDrawable(android.graphics.drawable.ColorDrawable(0))
        d.window?.setLayout((a.resources.displayMetrics.widthPixels * 0.92f).toInt(), ViewGroup.LayoutParams.WRAP_CONTENT)
        d.window?.setGravity(Gravity.BOTTOM)
        d.window?.attributes?.let { it.y = a.dp(24); d.window?.attributes = it }
        d.window?.setWindowAnimations(android.R.style.Animation_InputMethod)
        d.show()
    }

    private fun buildChips() {
        chips.removeAllViews()
        for ((k, t) in filters) {
            var txt = t
            if (k == "unread") { val n = a.model.chats.values.count { it.lng("unread") > 0 && !it.bool("muted") }; if (n > 0) txt += "  " + Fmt.digits(n.toString()) }
            val on = filter == k
            val c = label(a, txt, 13f, if (on) 0xFFFFFFFF.toInt() else th.text, on)
            c.setPadding(a.dp(14), a.dp(7), a.dp(14), a.dp(7))
            c.background = rounded(if (on) th.accentFill else th.field, a.dpf(16f))
            c.isClickable = true
            c.setOnClickListener { filter = k; buildChips(); rebuild(); drawTabs() }
            val p = lp(WRAP, WRAP); p.setMargins(a.dp(4), 0, a.dp(4), 0)
            chips.addView(c, p)
        }
        chips.visibility = if (searching) View.GONE else View.VISIBLE
    }

    // ------------------------------------------------------------------ rows
    private fun rebuild() {
        rows.clear()
        val q = query.lowercase()
        chips.visibility = if (searching) View.GONE else View.VISIBLE
        var chats = a.model.chatList()
        if (!searching || q.isEmpty()) {
            chats = chats.filter {
                when (filter) {
                    "unread" -> it.lng("unread") > 0
                    "private" -> it.str("kind") == "private" && !it.bool("saved")
                    "group" -> it.str("kind") == "group"
                    "fav" -> it.bool("fav")
                    else -> true
                }
            }
            for (c in chats) rows.add(Row.Chat(c))
        } else {
            val mine = chats.filter { it.str("title").lowercase().contains(q) || (it.map("peer")?.str("username")?.lowercase()?.contains(q) ?: false) }
            if (mine.isNotEmpty()) { rows.add(Row.Head("چت‌ها")); for (c in mine) rows.add(Row.Chat(c)) }
            if (userHits.isNotEmpty()) { rows.add(Row.Head("کاربران")); for (u in userHits) rows.add(Row.User(u)) }
            if (groupHits.isNotEmpty()) { rows.add(Row.Head("گروه‌ها")); for (g in groupHits) rows.add(Row.Group(g)) }
            if (msgHits.isNotEmpty()) { rows.add(Row.Head("پیام‌ها")); for (m in msgHits) rows.add(Row.Msg(m)) }
        }
        adapter.notifyDataSetChanged()
        empty.text = when {
            rows.isNotEmpty() -> ""
            searching && q.isNotEmpty() -> "برای پیدا کردن کاربر جدید، نام کاربری کامل‌ش رو بنویس (مثلاً ali_123)"
            filter != "all" -> "چیزی تو این بخش نیست"
            else -> "هنوز چتی نداری؛ دکمه مداد رو بزن"
        }
    }

    private fun scheduleSearch() {
        val my = ++seq
        userHits = emptyList(); groupHits = emptyList(); msgHits = emptyList()
        val q = query.removePrefix("@")
        if (q.length < 2) return
        a.main.postDelayed({
            if (my != seq) return@postDelayed
            if (Regex("^(?=.*[A-Za-z0-9])[A-Za-z0-9_]{3,32}$").matches(q))
                a.rpc("search_users", mapOf("q" to q)) { ok, r -> if (ok && my == seq) { userHits = r.list("users"); groupHits = r.list("groups"); rebuild() } }
            a.rpc("search_all", mapOf("q" to q)) { ok, r -> if (ok && my == seq) { msgHits = r.list("results"); rebuild() } }
        }, 300)
    }

    private fun onRowClick(r: Row) {
        when (r) {
            is Row.Chat -> a.openChat(r.c.lng("id"))
            is Row.User -> openPrivate(r.u.str("username"))
            is Row.Group -> {
                val id = r.g.lng("id")
                if (a.model.chats.containsKey(id)) a.openChat(id)
                else AlertDialog.Builder(a).setTitle(r.g.str("title")).setMessage("به این گروه بپیوندی؟")
                    .setPositiveButton("عضو شو") { _, _ ->
                        a.rpc("join", mapOf("username" to r.g.str("username"))) { ok, res ->
                            if (ok) res.map("chat")?.let { c -> a.model.chats[c.lng("id")] = LinkedHashMap(c); a.openChat(c.lng("id")) } else a.toast(res.str("error", "خطا"))
                        }
                    }.setNegativeButton("لغو", null).show()
            }
            is Row.Msg -> {
                val id = r.m.lng("chat_id")
                if (a.model.chats.containsKey(id)) a.push(ChatScreen(a, id, r.m.lng("id")))
            }
            else -> {}
        }
    }

    fun openPrivate(username: String) {
        a.rpc("open_private", mapOf("username" to username)) { ok, r ->
            val c = r.map("chat")
            if (ok && c != null) {
                val id = c.lng("id")
                if (!a.model.chats.containsKey(id)) a.model.chats[id] = LinkedHashMap(c)
                if (searching) setSearching(false)
                a.openChat(id)
            } else a.toast(r.str("error", "پیدا نشد"))
        }
    }

    // ------------------------------------------------------------------ menus
    private fun chatMenu(c: Map<String, Any?>) {
        val id = c.lng("id")
        val items = ArrayList<Pair<String, () -> Unit>>()
        items.add((if (c.bool("fav")) "برداشتن سنجاق" else "سنجاق به بالای لیست") to { setChat(id, mapOf("fav" to !c.bool("fav"))) })
        items.add((if (c.bool("muted")) "فعال کردن اعلان" else "بی‌صدا کردن") to { setChat(id, mapOf("muted" to !c.bool("muted"))) })
        if (c.lng("unread") > 0) items.add("علامت‌گذاری خوانده‌شده" to {
            a.rpc("read", mapOf("chat_id" to id, "up_to" to (c.map("last")?.lng("id") ?: 0L))); a.model.markReadLocal(id)
        })
        if (c.str("kind") == "group" && !c.bool("channel")) items.add("ترک گروه" to { confirm("از گروه «${c.str("title")}» خارج بشی؟") { a.rpc("leave", mapOf("chat_id" to id)) { ok, r -> if (ok) removeChat(id) else a.toast(r.str("error", "خطا")) } } })
        if (c.str("kind") == "private" && !c.bool("saved")) items.add("حذف از مخاطب‌ها" to { confirm("«${c.str("title")}» از مخاطب‌هات حذف بشه؟ (پیام‌ها فقط برای تو پاک می‌شن)") { a.rpc("delete_contact", mapOf("chat_id" to id)) { ok, r -> if (ok) removeChat(id) else a.toast(r.str("error", "خطا")) } } })
        AlertDialog.Builder(a).setItems(items.map { it.first }.toTypedArray()) { _, i -> items[i].second() }.show()
    }

    private fun removeChat(id: Long) { a.model.applyEvent(mapOf("event" to "chat_removed", "chat_id" to id)) }

    private fun setChat(id: Long, patch: Map<String, Any?>) {
        val p = LinkedHashMap<String, Any?>(); p["chat_id"] = id; p.putAll(patch)
        a.rpc("chat_settings", p) { ok, r ->
            if (ok) r.map("chat")?.let { a.model.applyEvent(mapOf("event" to "chat_updated", "chat" to it)) } else a.toast(r.str("error", "خطا"))
        }
    }

    private fun confirm(msg: String, yes: () -> Unit) {
        AlertDialog.Builder(a).setMessage(msg).setPositiveButton("بله") { _, _ -> yes() }.setNegativeButton("نه", null).show()
    }

    private fun newMenu() {
        val items = arrayOf("چت جدید", "گروه جدید")
        AlertDialog.Builder(a).setItems(items) { _, i -> if (i == 0) newChatDialog() else newGroupDialog() }.show()
    }

    private fun newChatDialog() {
        val et = EditText(a); et.hint = "نام کاربری (مثلاً ali_123)"; et.setSingleLine(true); et.textDirection = View.TEXT_DIRECTION_LTR
        val box = FrameLayout(a); box.setPadding(a.dp(20), a.dp(8), a.dp(20), 0); box.addView(et)
        AlertDialog.Builder(a).setTitle("چت جدید").setView(box).setPositiveButton("باز کن") { _, _ ->
            val u = et.text.toString().trim().removePrefix("@")
            if (u.isNotEmpty()) openPrivate(u)
        }.setNegativeButton("لغو", null).show()
    }

    private fun newGroupDialog() {
        val box = LinearLayout(a); box.orientation = LinearLayout.VERTICAL; box.setPadding(a.dp(20), a.dp(8), a.dp(20), 0)
        val name = EditText(a); name.hint = "اسم گروه"; name.setSingleLine(true); box.addView(name)
        val mem = EditText(a); mem.hint = "نام کاربری اعضا، با فاصله یا ویرگول (اختیاری)"; mem.textDirection = View.TEXT_DIRECTION_LTR; box.addView(mem)
        AlertDialog.Builder(a).setTitle("گروه جدید").setView(box).setPositiveButton("بساز") { _, _ ->
            val names = mem.text.toString().split(Regex("[\\s,،]+")).map { it.trim().removePrefix("@") }.filter { it.isNotEmpty() }
            a.rpc("create_group", mapOf("title" to name.text.toString().trim(), "usernames" to names, "origin" to (a.api?.cfg?.base ?: ""))) { ok, r ->
                val c = r.map("chat")
                if (ok && c != null) { a.model.chats[c.lng("id")] = LinkedHashMap(c); a.openChat(c.lng("id")) } else a.toast(r.str("error", "خطا"))
            }
        }.setNegativeButton("لغو", null).show()
    }

    // ------------------------------------------------------------------ side menu
    private fun openDrawer() {
        if (drawer != null) return
        val scrim = FrameLayout(a); scrim.setBackgroundColor(0x88000000.toInt()); scrim.isClickable = true
        scrim.setOnClickListener { closeDrawer() }
        val panel = LinearLayout(a); panel.orientation = LinearLayout.VERTICAL; panel.setBackgroundColor(th.panel)
        val me = a.model.me
        val head = LinearLayout(a); head.orientation = LinearLayout.VERTICAL; head.setBackgroundColor(if (th.dark) 0xFF1F2C3A.toInt() else th.bar)
        head.setPadding(a.dp(18), a.dp(36), a.dp(18), a.dp(16))
        val av = AvatarView(a, { a.img }, { a.mediaKey }); av.setRing(if (th.dark) 0xFF1F2C3A.toInt() else th.bar)
        av.bind("u", me.lng("id"), me.str("display_name"), me.lng("avatar_at"), false)
        head.addView(av, lp(a.dp(64), a.dp(64)))
        val nm = label(a, me.str("display_name"), 17f, 0xFFFFFFFF.toInt(), true); nm.setPadding(0, a.dp(10), 0, a.dp(2)); head.addView(nm)
        val un = label(a, "@" + me.str("username"), 13f, 0xCCFFFFFF.toInt()); un.textDirection = View.TEXT_DIRECTION_LTR; head.addView(un)
        panel.addView(head, lp(MATCH, WRAP))
        val sv = ScrollView(a); val items = LinearLayout(a); items.orientation = LinearLayout.VERTICAL; sv.addView(items)
        fun item(ic: String, text: String, fn: () -> Unit) {
            val row = LinearLayout(a); row.orientation = LinearLayout.HORIZONTAL; row.gravity = Gravity.CENTER_VERTICAL
            row.setPadding(a.dp(20), a.dp(14), a.dp(20), a.dp(14)); row.background = ripple(null, th.ripple); row.isClickable = true
            row.addView(icon(a, ic, th.muted, 22)); row.addView(hSpace(a, 22))
            row.addView(label(a, text, 15f, th.text))
            row.setOnClickListener { closeDrawer(); fn() }
            items.addView(row, lp(MATCH, WRAP))
        }
        item("person", "پروفایل من") { a.push(SettingsScreen(a)) }
        item("group", "گروه جدید") { newGroupDialog() }
        item("pencil", "چت جدید") { newChatDialog() }
        item("bookmark", "پیام‌های ذخیره‌شده") { openPrivate(me.str("username")) }
        item("pin", "نشان‌های من") { Dialogs.marks(a) }
        item("search", "جستجوی پیشرفته") { Dialogs.advancedSearch(a) }
        item("film", "اتاق تماشا و بازی‌ها") { gamesMenu() }
        item("back", "برگشت به نسخه قدیمی (وب)") { AlertDialog.Builder(a).setMessage("به نسخه قدیمی اپ برگردی؟ هر وقت خواستی از منوی نسخه وب می‌تونی دوباره بیای اینجا.").setPositiveButton("برگرد") { _, _ -> a.openWeb() }.setNegativeButton("نه", null).show() }
        item("cloud", "فضای ابری") { openSso("drive_token") }
        item("image", "قاب") { a.openGhabWeb() }
        item("image", "قاب (نسخه وب)") { openSso("ghab_token") }
        item("settings", "تنظیمات و حریم خصوصی") { a.push(SettingsScreen(a)) }
        item("logout", "خروج") { confirm("از حساب خارج بشی؟") { a.logout() } }
        panel.addView(sv, lp(MATCH, 0).weight(1f))
        val ver = label(a, "Windroida · نسخه بومی (آزمایشی)", 11f, th.muted); ver.setPadding(a.dp(20), a.dp(8), a.dp(20), a.dp(12)); panel.addView(ver)
        val w = Math.min(a.resources.displayMetrics.widthPixels * 0.82f, a.dpf(320f)).toInt()
        scrim.addView(panel, FrameLayout.LayoutParams(w, MATCH, Gravity.START))
        root.addView(scrim, FrameLayout.LayoutParams(MATCH, MATCH))
        panel.translationX = w.toFloat(); scrim.alpha = 0f
        panel.animate().translationX(0f).setDuration(180).start(); scrim.animate().alpha(1f).setDuration(180).start()
        drawer = scrim
    }

    private fun closeDrawer() {
        val d = drawer ?: return
        drawer = null
        d.animate().alpha(0f).setDuration(140).withEndAction { root.removeView(d) }.start()
    }

    private fun openSso(op: String) {
        a.rpc(op) { ok, r ->
            if (!ok) { a.toast(r.str("error", "در دسترس نیست")); return@rpc }
            val cfg = a.api?.cfg ?: return@rpc
            // Cloud Drive / Ghab always go over https: they carry personal photos/files and a login cookie, and the
            // server spawns both with the SAME certificate as the main connection whenever one exists. Only if the
            // main connection itself has no certificate at all (cfg.tls false, a plain-http setup) do we fall back
            // to http here too, matching what the server can actually serve.
            val scheme = if (cfg.tls || cfg.pin.isNotEmpty()) "https://" else "http://"
            val url = scheme + cfg.host + ":" + r.lng("port") + "/sso?t=" + java.net.URLEncoder.encode(r.str("token"), "UTF-8")
            a.startActivity(Intent(a, SiteActivity::class.java).putExtra("url", url))
        }
    }

    private fun headView(cv: View?, text: String): View {
        val t = (cv as? TextView) ?: label(a, "", 13f, th.accent, true).also { it.setPadding(a.dp(16), a.dp(12), a.dp(16), a.dp(6)) }
        t.text = text
        return t
    }

    private class Holder(val av: AvatarView, val name: TextView, val sub: TextView, val time: TextView, val badge: TextView, val tick: android.widget.ImageView)

    private fun newRow(): Pair<View, Holder> {
        val row = LinearLayout(a); row.orientation = LinearLayout.HORIZONTAL; row.gravity = Gravity.CENTER_VERTICAL
        row.setPadding(a.dp(22), a.dp(11), a.dp(22), a.dp(11))
        row.background = th.frostRow(a)                      // glass card (wallpaper blurred behind it)
        val av = AvatarView(a, { a.img }, { a.mediaKey }); av.setRing(if (th.dark) 0xFF2A2F4A.toInt() else 0xFFE8EAF4.toInt())
        row.addView(av, lp(a.dp(54), a.dp(54)))
        val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL; col.setPadding(a.dp(12), 0, a.dp(2), 0)
        val top = LinearLayout(a); top.orientation = LinearLayout.HORIZONTAL; top.gravity = Gravity.CENTER_VERTICAL
        val name = label(a, "", 16f, th.text, true).oneLine()
        val tick = icon(a, "check2", th.accent, 16); tick.visibility = View.GONE
        val time = label(a, "", 12f, th.muted)
        top.addView(name, lp(0, WRAP).weight(1f)); top.addView(tick, lp(a.dp(16), a.dp(16))); top.addView(hSpace(a, 3)); top.addView(time)
        val bot = LinearLayout(a); bot.orientation = LinearLayout.HORIZONTAL; bot.gravity = Gravity.CENTER_VERTICAL
        val sub = label(a, "", 14f, th.muted).oneLine()
        val badge = label(a, "", 12f, 0xFFFFFFFF.toInt(), true); badge.gravity = Gravity.CENTER; badge.setPadding(a.dp(6), a.dp(2), a.dp(6), a.dp(2)); badge.minWidth = a.dp(20)
        bot.addView(sub, lp(0, WRAP).weight(1f)); bot.addView(badge)
        col.addView(top, lp(MATCH, WRAP)); col.addView(hSpace(a, 0).also { it.layoutParams = LinearLayout.LayoutParams(1, a.dp(5)) }); col.addView(bot, lp(MATCH, WRAP))
        row.addView(col, lp(0, WRAP).weight(1f))
        val h = Holder(av, name, sub, time, badge, tick)
        row.tag = h
        return Pair(row, h)
    }

    private fun chatView(cv: View?, c: Map<String, Any?>): View {
        val pair = if (cv?.tag is Holder) Pair(cv, cv.tag as Holder) else newRow()
        val h = pair.second
        val id = c.lng("id")
        val av = ChatText.avatarOf(c)
        if (c.bool("saved")) { h.av.vector = { cv2, x, y, r -> val ic = IconDrawable("bookmark", 0xFFFFFFFF.toInt()); ic.setBounds((x - r * 0.5f).toInt(), (y - r * 0.5f).toInt(), (x + r * 0.5f).toInt(), (y + r * 0.5f).toInt()); ic.draw(cv2) } } else h.av.vector = null
        h.av.bind(av.kind, av.id, av.name, av.at, av.online)
        h.name.text = c.str("title") + if (c.bool("muted")) " 🔇" else ""
        val last = c.map("last")
        h.time.text = if (last != null) Fmt.listTime(last.lng("created_at")) else ""
        val ty = a.model.typingIn(id)
        if (ty != null) { h.sub.text = if (ty == "voice") "در حال ضبط ویس…" else "در حال نوشتن…"; h.sub.setTextColor(th.accent) }
        else { h.sub.text = ChatText.preview(c, a.model.myId); h.sub.setTextColor(th.muted) }
        val mine = last != null && last.lng("sender_id") == a.model.myId && last.str("kind") != "system"
        if (mine) {
            h.tick.visibility = View.VISIBLE
            val read = last!!.lng("id") <= c.lng("peer_read")
            h.tick.setImageDrawable(IconDrawable(if (read) "check2" else "check", if (read) th.accent else th.muted))
        } else h.tick.visibility = View.GONE
        val unread = c.lng("unread")
        if (unread > 0) { h.badge.visibility = View.VISIBLE; h.badge.text = Fmt.digits(if (unread > 99) "99+" else unread.toString()); h.badge.background = rounded(if (c.bool("muted")) th.badgeMuted else th.badge, a.dpf(11f)) }
        else if (c.bool("fav")) { h.badge.visibility = View.VISIBLE; h.badge.text = "📌"; h.badge.background = null; h.badge.setTextColor(th.muted) }
        else h.badge.visibility = View.GONE
        return pair.first!!
    }

    private fun simpleView(cv: View?, name: String, sub: String, kind: String, id: Long, at: Long): View {
        val pair = if (cv?.tag is Holder) Pair(cv, cv.tag as Holder) else newRow()
        val h = pair.second
        h.av.vector = null; h.av.bind(kind, id, name, at, false)
        h.name.text = name; h.sub.text = sub; h.sub.setTextColor(th.muted); h.time.text = ""; h.tick.visibility = View.GONE; h.badge.visibility = View.GONE
        return pair.first!!
    }

    private fun msgView(cv: View?, m: Map<String, Any?>): View {
        val c = a.model.chats[m.lng("chat_id")]
        val pair = if (cv?.tag is Holder) Pair(cv, cv.tag as Holder) else newRow()
        val h = pair.second
        val av = if (c != null) ChatText.avatarOf(c) else null
        h.av.vector = null
        if (av != null) h.av.bind(av.kind, av.id, av.name, av.at, false) else h.av.bind("c", 0, "?", 0, false)
        h.name.text = (c?.str("title") ?: "—") + (if (m.str("sender").isNotEmpty()) " · " + m.str("sender") else "")
        h.sub.text = m.str("text"); h.sub.setTextColor(th.muted); h.time.text = Fmt.listTime(m.lng("at")); h.tick.visibility = View.GONE; h.badge.visibility = View.GONE
        return pair.first!!
    }
}
