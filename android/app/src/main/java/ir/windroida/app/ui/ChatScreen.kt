package ir.windroida.app.ui

import android.app.AlertDialog
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.AbsListView
import android.widget.BaseAdapter
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.TextView
import ir.windroida.app.NativeActivity
import ir.windroida.app.Prefs
import ir.windroida.app.PlayerActivity
import ir.windroida.app.net.Api
import ir.windroida.app.net.Model
import ir.windroida.app.net.bool
import ir.windroida.app.net.list
import ir.windroida.app.net.int
import ir.windroida.app.net.lng
import ir.windroida.app.net.map
import ir.windroida.app.net.str
import java.io.File
import java.io.InputStream
import java.net.URLEncoder

/** One chat: header, pinned bar, messages, input bar (text, files, voice). [aroundId] > 0 = open at that message (search result). */
class ChatScreen(private val a: NativeActivity, val chatId: Long, private val aroundId: Long = 0L) : Screen(), Model.Listener, Bubbles.Host {
    private val th = a.th
    private val root = LinearLayout(a)
    override val view: View get() = root
    private val model = a.model
    private val bubbles = Bubbles(a, th)
    private val prefs = a.getSharedPreferences("native_chat", 0)

    private sealed class Item {
        class Day(val text: String) : Item()
        object Unread : Item()
        class Msg(val m: Map<String, Any?>) : Item()
    }

    // header
    private val av = AvatarView(a, { a.img }, { a.mediaKey })
    private lateinit var callBtns: LinearLayout
    private lateinit var gcallBtn: View
    private val bar = LinearLayout(a)
    private val titleV = label(a, "", 17f, th.barText, true).oneLine()
    private val subV = label(a, "", 13f, 0xCCFFFFFF.toInt()).oneLine()
    // multi-select (forward/delete several messages at once)
    private val selBar = LinearLayout(a)
    private val selCount = label(a, "", 17f, th.barText, true)
    private val selected = LinkedHashSet<Long>()
    private val pinBar = LinearLayout(a)
    private val pinText = label(a, "", 13f, th.text).oneLine()
    private val list = ListView(a)
    private val loadingV = label(a, "در حال بارگذاری…", 15f, th.muted)
    private val downBtn = FrameLayout(a)
    private val downBadge = label(a, "", 12f, 0xFFFFFFFF.toInt(), true)
    private val inputCol = LinearLayout(a)
    private val replyBar = LinearLayout(a)
    private val replyTitle = label(a, "", 13f, th.accent, true).oneLine()
    private val replyText = label(a, "", 13f, th.muted).oneLine()
    private val upBar = LinearLayout(a)
    /** the file being sent, shown like a message: ring + ✕ (cancel), "sent / total", clock */
    private val upBubble = LinearLayout(a)
    private val upRing = RingView(a, th.accentFill)
    private val upName = label(a, "", 15f, th.mineText, true).oneLine()
    private val upSize = label(a, "", 12f, th.mineMeta)
    private val upText = label(a, "", 13f, th.text)
    private val groupNote = label(a, "", 13f, th.text).also { it.gravity = Gravity.CENTER; it.setPadding(a.dp(14), a.dp(8), a.dp(14), a.dp(8)); it.setBackgroundColor(0x33F59E0B); it.visibility = View.GONE }
    private val field = EditText(a)
    private val micBtn = FrameLayout(a)
    private val micIcon = icon(a, "mic", 0xFFFFFFFF.toInt(), 22)
    private val sendIcon = icon(a, "send", 0xFFFFFFFF.toInt(), 22)
    private val recLabel = label(a, "", 15f, th.danger, true)
    private val fieldBox = FrameLayout(a)

    private var items: List<Item> = emptyList()
    private var newer = false                    // the window shown is not the newest part of the chat
    private var contigLast = 0L                  // newest id of the loaded window while [newer]
    private var firstUnreadId = 0L
    private var loadingOlder = false
    private var loadingNewer = false
    private var started = false
    private var net = Api.ONLINE
    private var replyId = 0L
    private var editId = 0L
    private var badge = 0
    private var flashId = 0L
    private var lastTyping = 0L
    private var pendingScroll: (() -> Unit)? = null

    // media state
    private val voiceViews = HashMap<Long, PlayView>()
    private val voiceProg = HashMap<Long, Float>()
    private var playingId = 0L
    private var playingNow = false
    private val dl = HashMap<Long, Float>()
    private val saved = HashMap<Long, Uri>()
    private var lastDlRefresh = 0L
    private var uploading = false
    private var cancelUp = false
    private val rec by lazy { VoiceRecorder(a) }
    private var recording = false
    private var fingerDown = false
    private var downX = 0f
    private var recTyping = 0L

    private val tick = object : Runnable { override fun run() { updateHeader(); a.main.postDelayed(this, 4500) } }
    private val recTick = object : Runnable {
        override fun run() {
            if (!recording) return
            rec.sample()
            recLabel.text = "● " + Fmt.duration(rec.seconds().toLong()) + "      برای لغو به کنار بکش"
            if (System.currentTimeMillis() - recTyping > 3000) { recTyping = System.currentTimeMillis(); a.rpc("typing", mapOf("chat_id" to chatId, "action" to "voice")) }
            if (rec.seconds() >= 300) { endRec(false); return }
            a.main.postDelayed(this, 100)
        }
    }

    private fun chat(): MutableMap<String, Any?>? = model.chats[chatId]

    // ---- Bubbles.Host
    override val myId: Long get() = model.myId
    override val isGroup: Boolean get() = chat()?.str("kind") == "group"
    override val peerRead: Long get() = chat()?.lng("peer_read") ?: 0L
    override fun reply(m: Map<String, Any?>) { val ch = chat(); if (ch != null && ch.bool("channel") && !ch.bool("can_post")) return; if (ch != null && ch.str("kind") == "group" && ch.lng("my_muted_until") > System.currentTimeMillis() / 1000) { a.toast("ساکت شدی"); return }; setReply(m) }
    override fun redraw(id: Long) { rows.evictAll(); adapter.notifyDataSetChanged() }
    override fun replyClicked(id: Long) = jumpTo(id)
    override fun fileClicked(m: Map<String, Any?>) = openFile(m)
    override fun menu(m: Map<String, Any?>) = showMenu(m)
    override fun react(m: Map<String, Any?>, e: String) = sendReaction(m, e)
    override fun downloadProgress(id: Long): Float = dl[id] ?: -1f
    override fun voiceView(id: Long, v: PlayView) { voiceViews[id] = v }
    override fun seek(id: Long, frac: Float) {
        if (a.voicePlayer.playingId == id) { a.voicePlayer.seek(frac); return }
        // another song: start it right at the chosen place
        val m = (model.msgs[chatId] ?: emptyList()).firstOrNull { it.lng("id") == id } ?: return
        val f = m.map("file") ?: return
        if (f.str("kind") != "audio" || f.bool("voice")) return
        a.voicePlayer.startFrac = frac
        playVoice(m, f)
    }
    private val playerListener: (Long, Float, Boolean) -> Unit = { id, p, playing -> onVoice(id, p, playing) }
    override fun voiceState(id: Long): Pair<Float, Boolean> = Pair(voiceProg[id] ?: 0f, id == playingId && playingNow)
    override var selecting: Boolean = false; private set
    override fun isSelected(id: Long) = selected.contains(id)
    override fun toggleSelect(id: Long) {
        if (!selected.remove(id)) selected.add(id)
        if (selected.isEmpty()) endSelect() else { updateSelCount(); redraw(0) }
    }

    // ------------------------------------------------------------------ multi-select (forward / delete several at once)
    private fun startSelect(id: Long) {
        selecting = true; selected.clear(); selected.add(id)
        bar.visibility = View.GONE; selBar.visibility = View.VISIBLE
        updateSelCount(); redraw(0)
    }
    private fun endSelect() {
        selecting = false; selected.clear()
        selBar.visibility = View.GONE; bar.visibility = View.VISIBLE
        redraw(0)
    }
    private fun updateSelCount() { selCount.text = Fmt.digits(selected.size.toString()) + " پیام" }
    private fun selDelete() {
        val ids = selected.toList(); if (ids.isEmpty()) return
        AlertDialog.Builder(a).setMessage(Fmt.digits(ids.size.toString()) + " پیام برای همه حذف بشه؟").setPositiveButton("حذف") { _, _ ->
            endSelect()
            for (id in ids) a.rpc("delete", mapOf("message_id" to id)) { ok, r -> if (ok) r.map("message")?.let { model.applyUpdate(it) } }
        }.setNegativeButton("لغو", null).show()
    }
    private fun selForward() {
        val ids = selected.toList(); if (ids.isEmpty()) return
        Dialogs.pickChats(a, "فوروارد " + Fmt.digits(ids.size.toString()) + " پیام به…") { chatIds ->
            endSelect()
            for (id in ids) a.rpc("forward", mapOf("message_id" to id, "chat_ids" to chatIds)) { ok, r -> if (!ok) a.toast(r.str("error", "ارسال نشد")) }
            a.toast("فوروارد شد")
        }
    }

    /** built message rows are kept (text / sticker / link messages only: no live progress inside) so scrolling back never rebuilds them */
    private val rows = android.util.LruCache<String, View>(70)
    private fun rowKey(m: Map<String, Any?>): String? {
        if (m.map("file") != null || m.map("poll") != null) return null
        val id = m.lng("id")
        val seen = if (m.lng("sender_id") == myId) (peerRead >= id) else false
        return id.toString() + "|" + m.str("body").hashCode() + "|" + m.lng("edited_at") + "|" + m.list("reactions").toString().hashCode() + "|" + seen + "|" + m.bool("deleted") + "|" + isGroup
    }
    private val adapter: BaseAdapter = object : BaseAdapter() {
        override fun getCount() = items.size
        override fun getItem(p: Int): Any = items[p]
        override fun getItemId(p: Int): Long = (items[p] as? Item.Msg)?.m?.lng("id") ?: -(p + 1L)
        override fun hasStableIds() = false
        override fun areAllItemsEnabled() = false
        override fun isEnabled(p: Int) = false
        override fun getView(p: Int, cv: View?, parent: ViewGroup): View {
            val it = items[p]
            val v = when (it) {
                is Item.Day -> bubbles.dayDivider(it.text)
                is Item.Unread -> bubbles.unreadDivider()
                is Item.Msg -> {
                    val key = if (selecting) null else rowKey(it.m)   // while selecting, rows must always rebuild to show the current checkbox state
                    val hit = if (key != null && flashId != it.m.lng("id")) rows.get(key) else null
                    if (hit != null) { (hit.parent as? ViewGroup)?.removeView(hit); return hit }
                    val r = bubbles.row(it.m, this@ChatScreen)
                    if (key != null && flashId != it.m.lng("id")) rows.put(key, r)
                    if (flashId == it.m.lng("id")) r.setBackgroundColor(if (th.dark) 0x335EB5F7 else 0x443390EC)
                    r
                }
            }
            v.animate().cancel(); v.alpha = 1f; v.translationY = 0f; v.scaleX = 1f; v.scaleY = 1f      // recycled rows never keep an old animation
            return v
        }
    }


    /** the chosen chat background (Settings > پس‌زمینه چت), drawn behind the list */
    private val wallV = android.widget.ImageView(a)
    private var wallCode = "\u0000"
    private fun applyWall() {
        val code = Prefs.wall(a)
        if (code == wallCode) return
        wallCode = code
        val on = Wall.apply(a, wallV, code)
        list.setBackgroundColor(0)
    }

    init {
        root.orientation = LinearLayout.VERTICAL
        root.background = th.screenBg()
        // ---- header
        bar.orientation = LinearLayout.HORIZONTAL; bar.gravity = Gravity.CENTER_VERTICAL
        bar.setBackgroundColor(th.bar); bar.setPadding(a.dp(4), 0, a.dp(4), 0); bar.elevation = a.dpf(3f)
        bar.addView(iconButton(a, th, "back", th.barText) { a.pop() })
        bar.addView(av, lp(a.dp(40), a.dp(40)))
        val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL; col.setPadding(a.dp(10), 0, a.dp(8), 0)
        col.addView(titleV); col.addView(subV, lp(MATCH, WRAP).also { it.topMargin = a.dp(2) })
        col.isClickable = true; col.setOnClickListener { a.push(ProfileScreen(a, chatId)) }
        bar.addView(col, lp(0, WRAP).weight(1f))
        callBtns = LinearLayout(a); callBtns.orientation = LinearLayout.HORIZONTAL; callBtns.visibility = View.GONE
        callBtns.addView(iconButton(a, th, "phone", th.barText) { startCall(false) })
        callBtns.addView(iconButton(a, th, "video", th.barText) { startCall(true) })
        gcallBtn = iconButton(a, th, "phone", th.barText) { a.openWebOnce("gcall=$chatId") }      // group call: only the call page opens (web), back returns here
        gcallBtn.visibility = View.GONE
        bar.addView(gcallBtn, lp(WRAP, WRAP))
        bar.addView(callBtns, lp(WRAP, WRAP))
        bar.addView(iconButton(a, th, "search", th.barText) { Dialogs.chatSearch(a, chatId) { id -> jumpTo(id) } })
        bar.addView(iconButton(a, th, "more", th.barText) { headerMenu() })
        root.addView(bar, lp(MATCH, a.dp(56)))
        // ---- selection bar (shown instead of the header while multi-selecting)
        selBar.orientation = LinearLayout.HORIZONTAL; selBar.gravity = Gravity.CENTER_VERTICAL
        selBar.setBackgroundColor(th.bar); selBar.setPadding(a.dp(4), 0, a.dp(12), 0); selBar.elevation = a.dpf(3f)
        selBar.visibility = View.GONE
        selBar.addView(iconButton(a, th, "close", th.barText) { endSelect() })
        selBar.addView(selCount, lp(0, WRAP).weight(1f).also { it.marginStart = a.dp(8) })
        selBar.addView(iconButton(a, th, "forward", th.barText) { selForward() })
        selBar.addView(iconButton(a, th, "trash", th.barText) { selDelete() })
        root.addView(selBar, lp(MATCH, a.dp(56)))
        // ---- pinned
        pinBar.orientation = LinearLayout.HORIZONTAL; pinBar.gravity = Gravity.CENTER_VERTICAL; pinBar.setBackgroundColor(th.panel)
        pinBar.setPadding(a.dp(12), a.dp(6), a.dp(12), a.dp(6)); pinBar.visibility = View.GONE
        val pb = View(a); pb.setBackgroundColor(th.quoteBar)
        pinBar.addView(pb, lp(a.dp(3), a.dp(32)))
        val pc = LinearLayout(a); pc.orientation = LinearLayout.VERTICAL; pc.setPadding(a.dp(10), 0, 0, 0)
        pc.addView(label(a, "پیام سنجاق‌شده", 12f, th.accent, true)); pc.addView(pinText)
        pinBar.addView(pc, lp(0, WRAP).weight(1f))
        pinBar.setOnClickListener { chat()?.map("pin_msg")?.let { jumpTo(it.lng("id")) } }
        root.addView(pinBar, lp(MATCH, WRAP))
        // ---- messages
        val body = FrameLayout(a)
        list.divider = null; list.setBackgroundColor(0); list.selector = android.graphics.drawable.ColorDrawable(0); list.cacheColorHint = 0
        list.adapter = adapter
        list.setOnScrollListener(object : AbsListView.OnScrollListener {
            override fun onScrollStateChanged(v: AbsListView?, st: Int) { if (st == AbsListView.OnScrollListener.SCROLL_STATE_IDLE) { markRead(); updateDown() } }
            override fun onScroll(v: AbsListView?, first: Int, visible: Int, total: Int) {
                if (!started || total == 0) return
                if (first <= 3 && !loadingOlder && model.hasMore[chatId] == true) loadOlder()
                if (first + visible >= total - 3 && newer && !loadingNewer) loadNewer()
                updateDown()
            }
        })
        body.addView(wallV, FrameLayout.LayoutParams(MATCH, MATCH))
        upBubble.orientation = LinearLayout.HORIZONTAL; upBubble.gravity = Gravity.CENTER_VERTICAL
        upBubble.background = rounded(th.mine, a.dpf(16f)); upBubble.setPadding(a.dp(10), a.dp(8), a.dp(14), a.dp(8)); upBubble.elevation = a.dp(2).toFloat(); upBubble.visibility = View.GONE
        upRing.isClickable = true; upRing.setOnClickListener { cancelUp = true }
        upBubble.addView(upRing, LinearLayout.LayoutParams(a.dp(44), a.dp(44)))
        val upCol = LinearLayout(a); upCol.orientation = LinearLayout.VERTICAL; upCol.setPadding(a.dp(10), 0, 0, 0)
        upCol.addView(upName); upCol.addView(upSize)
        upBubble.addView(upCol, LinearLayout.LayoutParams(WRAP, WRAP))
        upBubble.addView(icon(a, "clock", th.mineMeta, 16), LinearLayout.LayoutParams(a.dp(16), a.dp(16)).also { it.marginStart = a.dp(10); it.gravity = Gravity.BOTTOM })
        body.addView(list, FrameLayout.LayoutParams(MATCH, MATCH))
        body.addView(upBubble, FrameLayout.LayoutParams(a.dp(250), WRAP, Gravity.BOTTOM or Gravity.END).also { it.setMargins(a.dp(8), 0, a.dp(8), a.dp(8)) })
        applyWall()
        loadingV.gravity = Gravity.CENTER
        body.addView(loadingV, FrameLayout.LayoutParams(MATCH, MATCH))
        downBtn.background = rounded(th.panel, a.dpf(21f)); downBtn.elevation = a.dpf(4f); downBtn.visibility = View.GONE
        val di = icon(a, "forward", th.accent, 20); di.rotation = 90f
        downBtn.addView(di, FrameLayout.LayoutParams(a.dp(20), a.dp(20), Gravity.CENTER))
        downBadge.background = rounded(th.accentFill, a.dpf(9f)); downBadge.setPadding(a.dp(5), a.dp(1), a.dp(5), a.dp(1)); downBadge.visibility = View.GONE
        downBtn.addView(downBadge, FrameLayout.LayoutParams(WRAP, WRAP, Gravity.TOP or Gravity.CENTER_HORIZONTAL).also { it.topMargin = -a.dp(8) })
        downBtn.isClickable = true
        downBtn.setOnClickListener { goBottom() }
        val dl = FrameLayout.LayoutParams(a.dp(42), a.dp(42), Gravity.BOTTOM or Gravity.END); dl.setMargins(0, 0, a.dp(12), a.dp(12))
        body.addView(downBtn, dl)
        root.addView(body, lp(MATCH, 0).weight(1f))
        // ---- input
        inputCol.orientation = LinearLayout.VERTICAL; inputCol.setBackgroundColor(th.panel)
        replyBar.orientation = LinearLayout.HORIZONTAL; replyBar.gravity = Gravity.CENTER_VERTICAL; replyBar.visibility = View.GONE
        replyBar.setPadding(a.dp(12), a.dp(6), a.dp(4), a.dp(6))
        val rb = View(a); rb.setBackgroundColor(th.quoteBar)
        replyBar.addView(rb, lp(a.dp(3), a.dp(32)))
        val rc = LinearLayout(a); rc.orientation = LinearLayout.VERTICAL; rc.setPadding(a.dp(10), 0, 0, 0)
        rc.addView(replyTitle); rc.addView(replyText)
        replyBar.addView(rc, lp(0, WRAP).weight(1f))
        replyBar.addView(iconButton(a, th, "close", th.muted) { clearReplyEdit() })
        inputCol.addView(replyBar, lp(MATCH, WRAP))
        upBar.orientation = LinearLayout.HORIZONTAL; upBar.gravity = Gravity.CENTER_VERTICAL; upBar.visibility = View.GONE
        upBar.setPadding(a.dp(14), a.dp(4), a.dp(4), a.dp(4))
        upBar.addView(upText, lp(0, WRAP).weight(1f))
        upBar.addView(iconButton(a, th, "close", th.muted) { cancelUp = true })
        inputCol.addView(upBar, lp(MATCH, WRAP))
        val row = LinearLayout(a); row.orientation = LinearLayout.HORIZONTAL; row.gravity = Gravity.BOTTOM
        row.setPadding(a.dp(4), a.dp(4), a.dp(4), a.dp(4))
        field.styled(th, "پیام…")
        field.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        field.maxLines = 5
        field.setPadding(a.dp(14), a.dp(10), a.dp(4), a.dp(10))
        fieldBox.addView(field, FrameLayout.LayoutParams(MATCH, WRAP))
        recLabel.gravity = Gravity.CENTER_VERTICAL; recLabel.setPadding(a.dp(14), a.dp(10), a.dp(14), a.dp(10)); recLabel.visibility = View.GONE
        recLabel.background = rounded(th.field, a.dpf(22f))
        fieldBox.addView(recLabel, FrameLayout.LayoutParams(MATCH, MATCH))
        // Telegram's input: one rounded box holding the text and the paperclip; the round mic/send button sits outside on the right
        val inBox = LinearLayout(a); inBox.orientation = LinearLayout.HORIZONTAL; inBox.gravity = Gravity.BOTTOM
        inBox.background = rounded(th.field, a.dpf(22f))
        field.background = null; recLabel.background = null
        inBox.addView(fieldBox, lp(0, WRAP).weight(1f))
        inBox.addView(iconButton(a, th, "smile", th.muted) { toggleStickers() })
        inBox.addView(iconButton(a, th, "attach", th.muted) { attachMenu() })
        row.addView(inBox, lp(0, WRAP).weight(1f))
        micBtn.background = rounded(th.accentFill, a.dpf(22f))
        micBtn.addView(micIcon, FrameLayout.LayoutParams(a.dp(22), a.dp(22), Gravity.CENTER))
        micBtn.addView(sendIcon, FrameLayout.LayoutParams(a.dp(22), a.dp(22), Gravity.CENTER))
        sendIcon.visibility = View.GONE
        row.addView(micBtn, lp(a.dp(44), a.dp(44)).also { it.leftMargin = a.dp(4) })
        inputCol.addView(row, lp(MATCH, WRAP))
        root.addView(groupNote, lp(MATCH, WRAP))
        root.addView(inputCol, lp(MATCH, WRAP))
        field.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) {
                updateMic()
                if (!s.isNullOrEmpty() && System.currentTimeMillis() - lastTyping > 3000) { lastTyping = System.currentTimeMillis(); a.rpc("typing", mapOf("chat_id" to chatId)) }
            }
            override fun beforeTextChanged(s: CharSequence?, st: Int, c: Int, af: Int) {}
            override fun onTextChanged(s: CharSequence?, st: Int, b: Int, c: Int) {}
        })
        micBtn.setOnTouchListener { _, e -> micTouch(e) }
        field.setText(prefs.getString("d$chatId", "") ?: "")
        updateMic()
        applyCanPost()
        updateHeader()
    }

    // ------------------------------------------------------------------ life
    override fun onShow() {
        a.listen(this)
        applyWall()
        model.current = chatId
        a.addPlayerListener(playerListener)
        playingId = a.voicePlayer.playingId; playingNow = a.voicePlayer.isPlaying
        a.main.post(tick)
        if (!started) { started = true; start() } else { updateHeader(); markRead() }
    }

    override fun onHide() { leave() }
    override fun onDestroy() { leave(); if (recording) endRec(true); rec.release() }
    private fun leave() {
        a.unlisten(this)
        a.main.removeCallbacks(tick)
        if (model.current == chatId) model.current = 0L
        savePos()
        prefs.edit().putString("d$chatId", field.text.toString()).apply()
        a.removePlayerListener(playerListener)       // songs keep playing (the mini player at the top controls them)
        if (recording) endRec(true)
        val v = field; a.hideKeyboard(v)
    }

    override fun onBack(): Boolean {
        if (stickerPanel != null) { closeStickers(); return true }
        if (replyId != 0L || editId != 0L) { clearReplyEdit(); return true }
        return false
    }

    fun onNetState(s: Int) { net = s; updateHeader(); if (s == Api.ONLINE && started && !newer) loadLatest(true) }
    fun reloadLatest() { if (started && !newer) loadLatest(true) }

    // ------------------------------------------------------------------ loading
    private fun start() {
        val c = chat() ?: run { a.pop(); return }
        val unread = c.lng("unread").toInt()
        val saved = prefs.getLong("p$chatId", 0L)
        val target = if (aroundId > 0) aroundId else saved
        if (model.msgs[chatId].isNullOrEmpty()) a.restoreMsgs(chatId)        // saved history on the phone (like Telegram)
        val cached = model.msgs[chatId]
        if (target > 0 && (cached == null || cached.isEmpty() || cached.last().lng("id") > target || aroundId > 0)) { loadAround(target, aroundId > 0); return }
        if (cached != null && cached.isNotEmpty()) {
            firstUnreadId = findFirstUnread(cached, unread)
            rebuild(); loadingV.visibility = View.GONE
            scrollInitial()
            syncNewer(unread, 0)           // only what is new since the saved copy, not the whole history again
            return
        }
        loadLatest(false, unread)
    }

    /** brings the saved history up to date with a small request (messages after the last one we have); nothing at all when this chat is already current in this app run */
    private fun syncNewer(unread: Int, round: Int) {
        val l = model.msgs[chatId]
        if (l.isNullOrEmpty()) { loadLatest(false, unread); return }
        if (round == 0 && model.synced.contains(chatId)) { markRead(); return }
        if (round > 6) { loadLatest(false, unread); return }       // far behind: the newest 40 are enough, older ones load when scrolling up
        val lastId = l.last().lng("id")
        a.rpc("history", mapOf("chat_id" to chatId, "after_id" to lastId, "limit" to 100)) { ok, r ->
            if (!ok) return@rpc
            val atBottom = isAtBottom()
            val fresh = r.list("messages")
            if (fresh.isNotEmpty()) model.appendHistory(chatId, fresh)
            if (r.bool("has_newer")) { syncNewer(unread, round + 1); return@rpc }
            model.synced.add(chatId)
            if (fresh.isNotEmpty()) { if (unread >= 0) firstUnreadId = findFirstUnread(model.msgs[chatId] ?: emptyList(), unread); if (atBottom) list.post { list.setSelection(items.size - 1) } }
            markRead()
        }
    }

    private fun findFirstUnread(l: List<Map<String, Any?>>, unread: Int): Long {
        if (unread <= 0) return 0L
        var n = 0
        for (i in l.indices.reversed()) {
            val m = l[i]
            if (m.lng("sender_id") == myId || m.str("kind") == "system" || m.bool("deleted")) continue
            n++
            if (n == unread) return m.lng("id")
        }
        return 0L
    }

    private fun scrollInitial() {
        list.post {
            val ui = items.indexOfFirst { it is Item.Unread }
            if (ui >= 0) list.setSelectionFromTop(ui, a.dp(6)) else list.setSelection(items.size - 1)
            updateDown(); markRead()
        }
    }

    private fun loadLatest(silent: Boolean, unread: Int = -1) {
        if (!silent && items.isEmpty()) loadingV.visibility = View.VISIBLE
        a.rpc("history", mapOf("chat_id" to chatId, "limit" to 40)) { ok, r ->
            if (!ok) { loadingV.text = if (items.isEmpty()) r.str("error", "بارگذاری نشد؛ دوباره تلاش می‌کنم") else loadingV.text; return@rpc }
            val atBottom = isAtBottom()
            newer = false
            val first = items.isEmpty()
            if (unread >= 0) firstUnreadId = findFirstUnread(r.list("messages"), unread)
            model.setHistory(chatId, r.list("messages"), r.bool("has_more"))
            model.synced.add(chatId)
            loadingV.visibility = View.GONE
            if (first || unread >= 0) scrollInitial() else if (atBottom) list.post { list.setSelection(items.size - 1) }
        }
    }

    private fun loadAround(id: Long, flash: Boolean) {
        loadingV.visibility = View.VISIBLE
        a.rpc("history", mapOf("chat_id" to chatId, "around" to id, "limit" to 40)) { ok, r ->
            if (!ok) { a.toast(r.str("error", "پیام پیدا نشد")); loadingV.visibility = View.GONE; if (items.isEmpty()) loadLatest(false); return@rpc }
            val l = r.list("messages")
            newer = r.bool("has_newer")
            contigLast = l.lastOrNull()?.lng("id") ?: 0L
            firstUnreadId = 0L
            if (flash) flashId = id
            model.setHistory(chatId, l, r.bool("has_more"))
            loadingV.visibility = View.GONE
            list.post { scrollToMsg(id, true) }
        }
    }

    private fun loadOlder() {
        val l = model.msgs[chatId] ?: return
        val firstId = l.firstOrNull()?.lng("id") ?: return
        loadingOlder = true
        a.rpc("history", mapOf("chat_id" to chatId, "before_id" to firstId, "limit" to 40)) { ok, r ->
            loadingOlder = false
            if (ok) model.prependHistory(chatId, r.list("messages"), r.bool("has_more"))
        }
    }

    private fun loadNewer() {
        loadingNewer = true
        a.rpc("history", mapOf("chat_id" to chatId, "after_id" to contigLast, "limit" to 40)) { ok, r ->
            loadingNewer = false
            if (!ok) return@rpc
            val l = r.list("messages")
            newer = r.bool("has_newer")
            if (l.isNotEmpty()) contigLast = l.last().lng("id")
            model.appendHistory(chatId, l)
            if (!newer) { badge = 0; updateDown() }
        }
    }

    private fun goBottom() {
        if (newer) { newer = false; loadLatest(true); list.post { list.setSelection(items.size - 1) }; badge = 0; updateDown(); return }
        badge = 0
        list.smoothScrollToPosition(items.size - 1)
        list.postDelayed({ list.setSelection(items.size - 1); updateDown(); markRead() }, 350)
    }

    // ------------------------------------------------------------------ list
    private fun rebuild() {
        val src = model.msgs[chatId] ?: emptyList()
        val out = ArrayList<Item>()
        var lastDay = -1
        var shownUnread = false
        for (m in src) {
            val id = m.lng("id")
            if (newer && id > contigLast) break
            if (m.bool("deleted")) continue          // deleted messages vanish completely, like the web app / Telegram
            val d = Fmt.daysAgo(m.lng("created_at"))
            if (d != lastDay) { lastDay = d; out.add(Item.Day(Fmt.dayLabel(m.lng("created_at")))) }
            if (!shownUnread && firstUnreadId != 0L && id >= firstUnreadId) { shownUnread = true; out.add(Item.Unread) }
            out.add(Item.Msg(m))
        }
        items = out
        voiceViews.clear()
        adapter.notifyDataSetChanged()
    }

    private fun isAtBottom(): Boolean = items.isNotEmpty() && !newer && list.lastVisiblePosition >= items.size - 1

    private fun updateDown() {
        val show = items.isNotEmpty() && (newer || list.lastVisiblePosition < items.size - 2)
        downBtn.visibility = if (show) View.VISIBLE else View.GONE
        if (!show) badge = 0
        downBadge.visibility = if (badge > 0 && show) View.VISIBLE else View.GONE
        downBadge.text = Fmt.digits(badge.toString())
    }

    private fun scrollToMsg(id: Long, flash: Boolean) {
        val idx = items.indexOfFirst { it is Item.Msg && it.m.lng("id") == id }
        if (idx < 0) return
        list.setSelectionFromTop(idx, a.dp(120))
        if (flash) { flashId = id; adapter.notifyDataSetChanged(); a.main.postDelayed({ flashId = 0L; adapter.notifyDataSetChanged() }, 1600) }
        updateDown()
    }

    private fun jumpTo(id: Long) {
        val idx = items.indexOfFirst { it is Item.Msg && it.m.lng("id") == id }
        if (idx >= 0) { list.smoothScrollToPositionFromTop(idx, a.dp(120)); list.postDelayed({ scrollToMsg(id, true) }, 380) }
        else loadAround(id, true)
    }

    /** newest id fully on screen (for "read" and for the remembered reading position) */
    private fun lastVisibleMsgId(): Long {
        if (items.isEmpty()) return 0L
        var p = Math.min(list.lastVisiblePosition, items.size - 1)
        while (p >= 0) { val it = items[p]; if (it is Item.Msg) return it.m.lng("id"); p-- }
        return 0L
    }

    private fun savePos() {
        if (!started) return
        val id = lastVisibleMsgId()
        val ed = prefs.edit()
        if (id == 0L || (!newer && list.lastVisiblePosition >= items.size - 1)) ed.remove("p$chatId") else ed.putLong("p$chatId", id)
        ed.apply()
    }

    private fun markRead() {
        val c = chat() ?: return
        if (!model.viewing || model.current != chatId || net != Api.ONLINE || a.top() !== this) return
        val id = lastVisibleMsgId()
        if (id == 0L || id <= c.lng("my_read")) return
        c["my_read"] = id
        a.rpc("read", mapOf("chat_id" to chatId, "up_to" to id))
        if (!newer && id >= model.lastMessageId(chatId)) model.markReadLocal(chatId)
    }

    // ------------------------------------------------------------------ model events
    override fun onChatList() {}
    override fun onNeedRefresh() {}
    override fun onSessionEnded(reason: String) {}

    override fun onChatChanged(chatId: Long) {
        if (chatId != this.chatId) return
        if (chat() == null) { a.pop(); return }
        updateHeader(); applyCanPost()
    }

    /** a new message slides up and fades in */
    private fun popIn(v: View?, mine: Boolean) {
        if (v == null) return
        v.alpha = 0f; v.translationY = a.dpf(22f); v.scaleX = 0.96f; v.scaleY = 0.96f
        v.pivotX = if (mine) v.width * 0.85f else v.width * 0.15f; v.pivotY = v.height.toFloat()
        v.animate().alpha(1f).translationY(0f).scaleX(1f).scaleY(1f).setDuration(190).setInterpolator(android.view.animation.DecelerateInterpolator()).start()
    }

    override fun onTyping(chatId: Long) { if (chatId == this.chatId) updateHeader() }

    override fun onMessages(chatId: Long, kind: Int, messageId: Long) {
        if (chatId != this.chatId || !started) return
        when (kind) {
            Model.ADDED -> {
                val m = model.msgs[chatId]?.lastOrNull { it.lng("id") == messageId }
                val mine = m?.lng("sender_id") == myId
                val at = isAtBottom()
                rebuild()
                if (newer) { badge++; updateDown() }
                else if (at || mine) { list.post { list.setSelection(items.size - 1); updateDown(); markRead(); list.post { popIn(list.getChildAt(list.childCount - 1), mine) } } }
                else { badge++; updateDown() }
            }
            Model.UPDATED -> { rebuild() }
            else -> {
                if (pendingScroll != null) { rebuild(); pendingScroll?.invoke(); pendingScroll = null; return }
                val pos = list.firstVisiblePosition
                var anchorId = 0L; var top = 0
                var p = pos
                while (p < items.size) { val it = items[p]; if (it is Item.Msg) { anchorId = it.m.lng("id"); break }; p++ }
                if (anchorId != 0L) { val ch = list.getChildAt(p - pos); top = ch?.top ?: 0 }
                rebuild()
                if (anchorId != 0L) { val idx = items.indexOfFirst { it is Item.Msg && it.m.lng("id") == anchorId }; if (idx >= 0) list.setSelectionFromTop(idx, top) }
                updateDown(); updatePin()
            }
        }
        if (kind != Model.ADDED) updatePin()
    }

    // ------------------------------------------------------------------ header
    private fun startCall(video: Boolean) {
        val p = chat()?.map("peer") ?: return
        a.calls.invite(chatId, p.lng("id"), p.str("display_name").ifEmpty { chat()?.str("title") ?: "" }, video)
    }

    private fun updateHeader() {
        val c = chat() ?: return
        gcallBtn.visibility = if (c.str("kind") == "group" && !c.bool("channel")) View.VISIBLE else View.GONE
        callBtns.visibility = if (c.map("peer") != null && !c.bool("saved") && c.str("kind") == "private") View.VISIBLE else View.GONE
        val x = ChatText.avatarOf(c)
        av.setRing(th.bar)
        if (c.bool("saved")) { av.vector = { cv, cx, cy, r -> val p = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG); p.color = 0xFF3390EC.toInt(); cv.drawCircle(cx, cy, r, p); val d = IconDrawable("bookmark", 0xFFFFFFFF.toInt()); d.setBounds((cx - r * 0.55f).toInt(), (cy - r * 0.55f).toInt(), (cx + r * 0.55f).toInt(), (cy + r * 0.55f).toInt()); d.draw(cv) } }
        av.bind(x.kind, x.id, x.name, x.at, false)
        titleV.text = c.str("title")
        if (net != Api.ONLINE) { subV.text = "در حال اتصال…"; subV.setTextColor(0xCCFFFFFF.toInt()) }
        else { val (t, hi) = ChatText.subtitle(c, model); subV.text = t; subV.setTextColor(if (hi) 0xFFFFFFFF.toInt() else 0xCCFFFFFF.toInt()) }
        updatePin()
    }

    private fun updatePin() {
        val pm = chat()?.map("pin_msg")
        if (pm == null) pinBar.visibility = View.GONE
        else { pinBar.visibility = View.VISIBLE; pinText.text = ChatText.short(Stickers.label(pm.str("text")) ?: pm.str("text"), 70) }
    }

    private fun applyCanPost() {
        val c = chat() ?: return
        val can = c.bool("can_post", true)
        inputCol.visibility = if (can) View.VISIBLE else View.GONE
        // moderation notice (same wording idea as the web app): silenced / slow mode
        val now = System.currentTimeMillis() / 1000
        val mu = c.lng("my_muted_until"); val slow = c.int("slow")
        val txt = when {
            mu > now && mu > 4000000000L -> "ادمین گروه تو رو برای همیشه ساکت کرده؛ فقط می‌تونی بخونی."
            mu > now -> "ادمین گروه تو رو ساکت کرده؛ تا " + Fmt.digits(((mu - now + 59) / 60).toString()) + " دقیقه‌ی دیگه نمی‌تونی پیام بدی."
            slow > 0 && !c.bool("channel") -> "حالت آهسته: هر " + Fmt.digits(slow.toString()) + " ثانیه فقط یه پیام می‌تونی بفرستی."
            else -> ""
        }
        if (txt.isEmpty()) groupNote.visibility = View.GONE else { groupNote.text = txt; groupNote.visibility = View.VISIBLE }
    }

    private fun headerMenu() {
        val c = chat() ?: return
        Dialogs.menu(a, null, null, listOf(
            Pair("جستجو در گفتگو") { Dialogs.chatSearch(a, chatId) { id -> jumpTo(id) } },
            Pair(if (c.bool("muted")) "صدادار کردن" else "بی‌صدا کردن") { a.rpc("chat_settings", mapOf("chat_id" to chatId, "muted" to !c.bool("muted"))) { ok, r -> if (ok) r.map("chat")?.let { n -> c.putAll(n); model.listener?.onChatList(); updateHeader() } else a.toast(r.str("error", "خطا")) } },
            Pair("اطلاعات") { a.push(ProfileScreen(a, chatId)) },
        ))
    }

    // ------------------------------------------------------------------ sending
    private fun updateMic() {
        val has = field.text.isNotEmpty() || editId != 0L
        micIcon.visibility = if (has) View.GONE else View.VISIBLE
        sendIcon.visibility = if (has) View.VISIBLE else View.GONE
    }

    private fun clearReplyEdit() {
        if (editId != 0L) field.setText("")
        replyId = 0L; editId = 0L
        replyBar.visibility = View.GONE
        updateMic()
    }

    private fun setReply(m: Map<String, Any?>) {
        editId = 0L; replyId = m.lng("id")
        replyTitle.text = "پاسخ به " + m.str("sender_name"); replyText.text = ChatText.short(ChatText.messageLine(m), 70)
        replyBar.visibility = View.VISIBLE
        focusField()
    }

    private fun setEdit(m: Map<String, Any?>) {
        replyId = 0L; editId = m.lng("id")
        replyTitle.text = "ویرایش پیام"; replyText.text = ChatText.short(m.str("body"), 70)
        replyBar.visibility = View.VISIBLE
        field.setText(m.str("body")); field.setSelection(field.text.length)
        updateMic(); focusField()
    }

    private fun focusField() {
        field.requestFocus()
        val im = a.getSystemService(android.view.inputmethod.InputMethodManager::class.java)
        im?.showSoftInput(field, 0)
    }

    // ------------------------------------------------------------------ sticker panel (the same 26 stickers as the web app)
    private var stickerPanel: View? = null
    private fun toggleStickers() {
        val old = stickerPanel
        if (old != null) { closeStickers(); return }
        a.hideKeyboard(field)
        val grid = android.widget.GridLayout(a); grid.columnCount = 5; grid.setPadding(a.dp(8), a.dp(8), a.dp(8), a.dp(8))
        for ((id, emo) in Stickers.EMOJI) {
            val cell = label(a, emo, 34f, th.text); cell.gravity = Gravity.CENTER
            cell.isClickable = true; cell.background = ripple(null, th.ripple); cell.pressScale(0.8f)
            cell.setOnClickListener { sendSticker(id); closeStickers() }
            val gp = android.widget.GridLayout.LayoutParams(android.widget.GridLayout.spec(android.widget.GridLayout.UNDEFINED, 1f), android.widget.GridLayout.spec(android.widget.GridLayout.UNDEFINED, 1f))
            gp.width = 0; gp.height = a.dp(56)
            grid.addView(cell, gp)
        }
        val sv = android.widget.ScrollView(a); sv.addView(grid); sv.setBackgroundColor(th.panel)
        stickerPanel = sv
        inputCol.addView(sv, lp(MATCH, a.dp(230)))
        sv.translationY = a.dpf(230f); sv.animate().translationY(0f).setDuration(200).start()
    }
    private fun closeStickers() {
        val p = stickerPanel ?: return
        stickerPanel = null
        p.animate().translationY(a.dpf(230f)).setDuration(150).withEndAction { inputCol.removeView(p) }.start()
    }
    private fun sendSticker(id: String) {
        val p = LinkedHashMap<String, Any?>(); p["chat_id"] = chatId; p["text"] = ":st_$id:"; if (replyId != 0L) p["reply_to"] = replyId
        replyId = 0L; replyBar.visibility = View.GONE
        a.rpc("send", p) { ok, r -> if (ok) r.map("message")?.let { model.ingest(it) } else a.toast(r.str("error", "ارسال نشد")) }
    }

    private fun doSend() {
        val text = field.text.toString().trim()
        if (editId != 0L) {
            if (text.isEmpty()) return
            val id = editId
            clearReplyEditKeepText()
            field.setText("")
            a.rpc("edit", mapOf("message_id" to id, "text" to text)) { ok, r -> if (ok) r.map("message")?.let { model.applyUpdate(it) } else { a.toast(r.str("error", "ویرایش نشد")) } }
            return
        }
        if (text.isEmpty()) return
        val rep = replyId
        val p = LinkedHashMap<String, Any?>(); p["chat_id"] = chatId; p["text"] = text; if (rep != 0L) p["reply_to"] = rep
        field.setText("")                                  // the keyboard stays open: the field keeps the focus
        replyId = 0L; replyBar.visibility = View.GONE
        a.rpc("send", p) { ok, r ->
            if (ok) r.map("message")?.let { model.ingest(it) }
            else { a.toast(r.str("error", "ارسال نشد")); if (field.text.isEmpty()) field.setText(text) }
        }
    }

    private fun clearReplyEditKeepText() { replyId = 0L; editId = 0L; replyBar.visibility = View.GONE }

    private fun micTouch(e: MotionEvent): Boolean {
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                fingerDown = true; downX = e.rawX
                if (field.text.isEmpty() && editId == 0L) beginRec()
            }
            MotionEvent.ACTION_MOVE -> if (recording) recLabel.setTextColor(if (Math.abs(e.rawX - downX) > a.dp(90)) th.muted else th.danger)
            MotionEvent.ACTION_UP -> {
                fingerDown = false
                if (recording) endRec(Math.abs(e.rawX - downX) > a.dp(90)) else if (field.text.isNotEmpty() || editId != 0L) doSend()
            }
            MotionEvent.ACTION_CANCEL -> { fingerDown = false; if (recording) endRec(true) }
        }
        return true
    }

    private fun beginRec() {
        if (uploading) { a.toast("یه ارسال در جریانه"); return }
        if (a.checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            a.askPermission(android.Manifest.permission.RECORD_AUDIO) { ok -> a.toast(if (ok) "حالا دکمه میکروفون رو نگه دار" else "برای ضبط، اجازه‌ی میکروفون لازمه") }
            return
        }
        a.voicePlayer.stop()
        if (!rec.start()) { a.toast("ضبط شروع نشد"); return }
        recording = true
        recLabel.setTextColor(th.danger); recLabel.visibility = View.VISIBLE; field.visibility = View.INVISIBLE
        recTyping = 0L
        a.main.post(recTick)
    }

    private fun endRec(cancel: Boolean) {
        if (!recording) return
        recording = false
        a.main.removeCallbacks(recTick)
        recLabel.visibility = View.GONE; field.visibility = View.VISIBLE
        val r = rec.finish(cancel)
        if (r == null) { if (!cancel) a.toast("پیام صوتی خیلی کوتاه بود"); return }
        upload("voice.m4a", r.file.length(), { r.file.inputStream() }, Pair(r.dur, r.wave), "") { msg ->
            try { val nm = msg.map("file")?.str("name") ?: "voice.m4a"; r.file.copyTo(a.downloads.cached(msg.lng("id"), nm), true) } catch (_: Exception) {}
            r.file.delete()
        }
    }

    private fun attachMenu() {
        val items = arrayListOf<Pair<String, () -> Unit>>(
            Pair("عکس یا ویدیو") { pick("image/*,video/*") },
            Pair("فایل") { pick("*/*") },
        )
        if (isGroup) items.add(Pair("نظرسنجی") { a.polls.create(chatId) })     // polls: groups only
        Dialogs.menu(a, null, null, items)
    }

    private fun pick(types: String) {
        val i = Intent(Intent.ACTION_GET_CONTENT)
        i.addCategory(Intent.CATEGORY_OPENABLE)
        if (types.contains(",")) { i.type = "*/*"; i.putExtra(Intent.EXTRA_MIME_TYPES, types.split(",").toTypedArray()) } else i.type = types
        a.pickResult(Intent.createChooser(i, "انتخاب")) { res, data ->
            val u = data?.data
            if (res == android.app.Activity.RESULT_OK && u != null) sendUri(u)
        }
    }

    /** also used for "share to Windroida" later */
    fun sendUri(u: Uri) {
        var name = "file"; var size = -1L
        try {
            a.contentResolver.query(u, null, null, null, null)?.use { c ->
                if (c.moveToFirst()) {
                    val ni = c.getColumnIndex(OpenableColumns.DISPLAY_NAME); val si = c.getColumnIndex(OpenableColumns.SIZE)
                    if (ni >= 0) name = c.getString(ni) ?: name
                    if (si >= 0 && !c.isNull(si)) size = c.getLong(si)
                }
            }
        } catch (_: Exception) {}
        if (size <= 0) { a.toast("فایل خالیه یا خونده نشد"); return }
        val cap = field.text.toString().trim()
        upload(name, size, { a.contentResolver.openInputStream(u) ?: throw java.io.IOException("cannot open") }, null, cap) { if (cap.isNotEmpty()) field.setText("") }
    }

    private fun upload(name: String, length: Long, open: () -> InputStream, voice: Pair<Double, List<Int>>?, caption: String, onDone: (Map<String, Any?>) -> Unit) {
        if (uploading) { a.toast("یه ارسال در جریانه"); return }
        val h = a.http ?: run { a.toast("به سرور وصل نیستی"); return }
        val max = a.api?.maxUpload ?: (5L shl 20)
        if (length > max) { a.toast("حجم فایل بیشتر از " + Fmt.size(max) + " است"); return }
        val rep = replyId
        uploading = true; cancelUp = false
        upName.text = ChatText.short(name, 26); upSize.text = Fmt.size(0) + " / " + Fmt.size(length); upRing.progress = 0f; upBubble.visibility = View.VISIBLE
        val q = h.q("k" to a.mediaKey, "chat_id" to chatId, "name" to name, "text" to caption.ifEmpty { null },
            "reply_to" to (if (rep != 0L) rep else null), "voice" to (if (voice != null) 1 else null), "dur" to voice?.first, "wave" to voice?.second?.joinToString(","))
        Thread {
            var err: String? = null
            var res: Map<String, Any?>? = null
            try {
                res = h.uploadResumable("/upload?$q", open, length, { d, t -> a.main.post { upRing.progress = d.toFloat() / Math.max(1L, t); upSize.text = Fmt.size(d) + " / " + Fmt.size(t) } }, { cancelUp }, 300_000) { waiting -> a.main.post { upName.text = if (waiting) "منتظر اینترنت… (تا ۵ دقیقه)" else ChatText.short(name, 26) } }
            } catch (e: Exception) { err = if (cancelUp) "ارسال لغو شد" else (e.message ?: "ارسال ناموفق بود") }
            a.main.post {
                uploading = false; upBar.visibility = View.GONE; upBubble.visibility = View.GONE
                if (err != null) a.toast(err)
                else {
                    replyId = 0L; replyBar.visibility = View.GONE
                    res?.map("message")?.let { m -> model.ingest(m); onDone(m) }
                }
            }
        }.start()
    }

    // ------------------------------------------------------------------ message menu
    private fun canPin(): Boolean {
        val c = chat() ?: return false
        return if (c.bool("channel")) c.bool("can_post") else if (c.str("kind") == "group") c.str("my_role") == "owner" || c.str("my_role") == "admin" else true
    }

    private fun showMenu(m: Map<String, Any?>) {
        if (m.bool("deleted") || m.str("kind") == "system") return
        val c = chat() ?: return
        val id = m.lng("id")
        val mine = m.lng("sender_id") == myId
        val f = m.map("file")
        val body = m.str("body")
        val acts = ArrayList<Pair<String, () -> Unit>>()
        acts.add(Pair("پاسخ") { setReply(m) })
        if (body.isNotEmpty() && Stickers.parse(body) == null) acts.add(Pair("کپی متن") {
            val cm = a.getSystemService(ClipboardManager::class.java)
            cm?.setPrimaryClip(ClipData.newPlainText("msg", body)); a.toast("کپی شد")
        })
        if (f != null && !f.bool("voice")) acts.add(Pair("ذخیره در پوشه‌ی دانلود") { saveFile(m) })
        acts.add(Pair("ارسال به…") { Dialogs.pickChats(a, "ارسال به…") { ids -> a.rpc("forward", mapOf("message_id" to id, "chat_ids" to ids)) { ok, r -> a.toast(if (ok) "ارسال شد" else r.str("error", "ارسال نشد")) } } })
        acts.add(Pair("انتخاب چندتایی") { startSelect(id) })
        if (canPin()) {
            val pinned = c.map("pin_msg")?.lng("id") == id
            acts.add(Pair(if (pinned) "برداشتن سنجاق" else "سنجاق") { a.rpc("pin", mapOf("chat_id" to chatId, "message_id" to (if (pinned) null else id))) { ok, r -> if (!ok) a.toast(r.str("error", "خطا")) } })
        }
        acts.add(Pair("نشان کردن") { Dialogs.markDialog(a, id) })
        if (mine && f == null && m.map("game") == null) acts.add(Pair("ویرایش") { setEdit(m) })
        val owner = c.str("kind") == "group" && (c.str("my_role") == "owner" || c.str("my_role") == "admin")
        if (mine || owner) acts.add(Pair("حذف") {
            AlertDialog.Builder(a).setMessage("این پیام برای همه حذف بشه؟").setPositiveButton("حذف") { _, _ ->
                a.rpc("delete", mapOf("message_id" to id)) { ok, r -> if (ok) r.map("message")?.let { model.applyUpdate(it) } else a.toast(r.str("error", "حذف نشد")) }
            }.setNegativeButton("لغو", null).show()
        })
        Dialogs.menu(a, listOf("👍", "❤️", "🔥", "🎉", "😂", "😮", "😢", "🙏", "👎", "💯", "🤔", "👏"), { e -> sendReaction(m, e) }, acts)
    }

    private fun sendReaction(m: Map<String, Any?>, e: String) {
        a.rpc("react", mapOf("message_id" to m.lng("id"), "emoji" to e)) { ok, r -> if (ok) r.map("message")?.let { model.applyUpdate(it) } else a.toast(r.str("error", "خطا")) }
    }

    // ------------------------------------------------------------------ files, voice, video
    private fun openFile(m: Map<String, Any?>) {
        val f = m.map("file") ?: return
        val id = m.lng("id")
        val kind = f.str("kind")
        if (m.bool("deleted")) return
        if (f.bool("voice") || kind == "audio") { playVoice(m, f); return }
        if (kind == "image") { a.openImage(id, f.str("name")); return }
        if (kind == "video") {
            val h = a.http ?: return
            val i = Intent(a, PlayerActivity::class.java)
            i.putExtra("url", h.url("/media/$id?k=" + URLEncoder.encode(a.mediaKey, "UTF-8")))
            i.putExtra("title", f.str("name"))
            a.startActivity(i); return
        }
        if (a.downloads.isBusy(id)) { a.downloads.cancel(id); return }
        saved[id]?.let { u -> if (!a.downloads.open(u, f.str("name"))) a.toast("برنامه‌ای برای باز کردن این فایل نیست"); return }
        fetchThen(id, f.str("name")) { file ->
            val u = a.downloads.saveToDownloads(file, f.str("name"))
            if (u == null) a.toast("ذخیره نشد")
            else { saved[id] = u; if (!a.downloads.open(u, f.str("name"))) a.toast("ذخیره شد (Download/Windroida)؛ برنامه‌ای برای بازکردنش نیست") }
        }
    }

    private fun saveFile(m: Map<String, Any?>) {
        val f = m.map("file") ?: return
        val id = m.lng("id")
        if (saved[id] != null) { a.toast("قبلاً ذخیره شده: Download/Windroida"); return }
        fetchThen(id, f.str("name")) { file ->
            val u = a.downloads.saveToDownloads(file, f.str("name"))
            if (u != null) { saved[id] = u; a.toast("ذخیره شد: Download/Windroida") } else a.toast("ذخیره نشد")
        }
    }

    private fun fetchThen(id: Long, name: String, done: (File) -> Unit) {
        dl[id] = 0f; adapter.notifyDataSetChanged()
        a.downloads.fetch(id, name, { d, t ->
            val now = System.currentTimeMillis()
            if (t > 0 && now - lastDlRefresh > 300) { lastDlRefresh = now; dl[id] = d.toFloat() / t; adapter.notifyDataSetChanged() }
        }) { file, err ->
            dl.remove(id); adapter.notifyDataSetChanged()
            if (file != null) done(file) else a.toast(err ?: "دانلود نشد")
        }
    }

    private fun trackOf(m: Map<String, Any?>, f: Map<String, Any?>): Track {
        val base = f.str("name").substringBeforeLast('.')
        val dash = base.indexOf(" - ")
        return if (dash > 0) Track(m.lng("id"), f.str("name"), base.substring(dash + 3).trim(), base.substring(0, dash).trim())
        else Track(m.lng("id"), f.str("name"), base, m.str("sender_name"))
    }

    /** every song (not voice message) of this chat that is loaded, oldest first: the play queue */
    private fun songsOf(): List<Track> = (model.msgs[chatId] ?: emptyList()).mapNotNull { m ->
        val f = m.map("file")
        if (f != null && !m.bool("deleted") && f.str("kind") == "audio" && !f.bool("voice")) trackOf(m, f) else null
    }

    private fun playVoice(m: Map<String, Any?>, f: Map<String, Any?>) {
        val id = m.lng("id")
        if (!f.bool("voice")) {                                     // a song: streamed (starts playing before it is fully downloaded)
            if (a.voicePlayer.playingId == id) { if (!a.voicePlayer.loading) a.voicePlayer.toggleCurrent(); return }      // (a tap while it is still loading must not restart the download)
            val tracks = songsOf()
            val idx = tracks.indexOfFirst { it.id == id }
            val cfg = a.streamCfg()
            if (idx < 0 || cfg == null) { a.toast("به سرور وصل نیستی"); return }
            a.voicePlayer.playQueue(tracks, idx, cfg)
            // the queue is only what is loaded on screen: ask the server for ALL the songs of this chat so next / previous never skip or jump
            val cid = chatId
            a.rpc("shared", mapOf("chat_id" to cid, "kind" to "audio", "limit" to 600)) { ok, r ->
                if (!ok || chatId != cid) return@rpc
                val all = (r["messages"] as? List<*>)?.mapNotNull { it as? Map<String, Any?> }?.reversed()?.mapNotNull { mm ->
                    val ff = mm.map("file"); if (ff != null && !mm.bool("deleted")) trackOf(mm, ff) else null
                } ?: return@rpc
                val gone = (model.msgs[cid] ?: emptyList()).filter { it.bool("deleted") }.map { it.lng("id") }.toSet()
                val merged = LinkedHashMap<Long, Track>()
                for (t in all) merged[t.id] = t
                for (t in tracks) merged[t.id] = t
                a.voicePlayer.replaceQueue(merged.values.filter { it.id !in gone }.sortedBy { it.id })
            }
            return
        }
        if (a.downloads.isBusy(id)) { a.downloads.cancel(id); return }
        val cached = a.downloads.cached(id, f.str("name"))
        val go = { file: File ->
            if (a.voicePlayer.playingId != id) { a.voicePlayer.title = if (f.bool("voice")) "پیام صوتی" else f.str("name").substringBeforeLast('.'); a.voicePlayer.subtitle = m.str("sender_name") }
            a.voicePlayer.toggle(id, file)
            if (f.bool("voice") && m.lng("sender_id") != myId) a.rpc("voice_played", mapOf("message_id" to id))
        }
        if (cached.isFile && cached.length() > 0) go(cached) else fetchThen(id, f.str("name")) { go(it) }
    }

    private fun onVoice(id: Long, p: Float, playing: Boolean) {
        voiceProg[id] = if (!playing && p == 0f) 0f else p
        playingId = if (playing || p > 0f) id else 0L
        playingNow = playing
        voiceViews[id]?.set(voiceProg[id] ?: 0f, playing)
    }
}
