package ir.windroida.app.net

/**
 * The app's state in memory (chats, messages, who is typing) and the rules for applying server events to it.
 * No Android classes here, so the same code runs in the JVM tests. Every call happens on ONE thread (the UI thread).
 */
class Model {
    companion object {
        const val ADDED = 0
        const val UPDATED = 1
        const val RELOADED = 2
        const val TYPING_MS = 4300L
        const val KEEP_PER_CHAT = 300
    }

    interface Listener {
        fun onChatList()                                   // the list (order, previews, unread) changed
        fun onChatChanged(chatId: Long)                    // header info of one chat changed
        fun onMessages(chatId: Long, kind: Int, messageId: Long)
        fun onTyping(chatId: Long)
        fun onNeedRefresh()                                // something happened we can't apply locally: reload the chat list
        fun onSessionEnded(reason: String)
    }

    var listener: Listener? = null
    var me: MutableMap<String, Any?> = LinkedHashMap()
    val chats = LinkedHashMap<Long, MutableMap<String, Any?>>()
    val msgs = HashMap<Long, MutableList<Map<String, Any?>>>()
    val hasMore = HashMap<Long, Boolean>()
    private val early = HashMap<Long, MutableList<Map<String, Any?>>>()
    private val typing = HashMap<String, Pair<Long, String>>()
    var current = 0L
    private var lastGroupRefresh = 0L
    var viewing = false                                    // the app is in front

    val myId: Long get() = me.lng("id")

    // ------------------------------------------------------------------ loading
    fun replaceMe(m: Map<String, Any?>?) { me = if (m == null) LinkedHashMap() else LinkedHashMap(m) }

    fun setChats(list: List<Map<String, Any?>>) {
        chats.clear()
        for (c in list) chats[c.lng("id")] = LinkedHashMap(c)
        listener?.onChatList()
    }

    fun setHistory(chatId: Long, list: List<Map<String, Any?>>, more: Boolean) {
        val l = ArrayList<Map<String, Any?>>(list)
        for (m in early.remove(chatId) ?: emptyList<Map<String, Any?>>()) if (l.none { it.lng("id") == m.lng("id") }) l.add(m)
        l.sortBy { it.lng("id") }
        msgs[chatId] = l
        hasMore[chatId] = more
        listener?.onMessages(chatId, RELOADED, 0)
    }

    fun prependHistory(chatId: Long, older: List<Map<String, Any?>>, more: Boolean) {
        val l = msgs.getOrPut(chatId) { ArrayList() }
        val have = HashSet<Long>(l.map { it.lng("id") })
        val add = older.filter { have.add(it.lng("id")) }
        l.addAll(0, add)
        l.sortBy { it.lng("id") }
        hasMore[chatId] = more
        listener?.onMessages(chatId, RELOADED, 0)
    }

    fun appendHistory(chatId: Long, newer: List<Map<String, Any?>>) {
        val l = msgs.getOrPut(chatId) { ArrayList() }
        val have = HashSet<Long>(l.map { it.lng("id") })
        l.addAll(newer.filter { have.add(it.lng("id")) })
        l.sortBy { it.lng("id") }
        listener?.onMessages(chatId, RELOADED, 0)
    }

    fun chatList(): List<Map<String, Any?>> =
        chats.values.sortedWith(compareByDescending<Map<String, Any?>> { it.bool("fav") }
            .thenByDescending { it.map("last")?.lng("created_at") ?: it.lng("created_at") }
            .thenByDescending { it.map("last")?.lng("id") ?: 0L })

    fun lastMessageId(chatId: Long): Long = msgs[chatId]?.lastOrNull()?.lng("id") ?: chats[chatId]?.map("last")?.lng("id") ?: 0L

    // ------------------------------------------------------------------ typing / presence
    fun typingIn(chatId: Long, now: Long = System.currentTimeMillis()): String? {
        var best: String? = null
        val it = typing.entries.iterator()
        while (it.hasNext()) {
            val e = it.next()
            if (e.value.first < now) { it.remove(); continue }
            if (e.key.startsWith("$chatId:")) best = e.value.second
        }
        return best
    }

    // ------------------------------------------------------------------ events from the server
    fun applyEvent(e: Map<String, Any?>) {
        when (e.str("event")) {
            "message" -> e.map("message")?.let { ingest(it) }
            "message_updated" -> e.map("message")?.let { applyUpdate(it) }
            "read" -> {
                val c = chats[e.lng("chat_id")]
                if (c != null && e.lng("user_id") != myId) {
                    c["peer_read"] = Math.max(c.lng("peer_read"), e.lng("up_to"))
                    listener?.onMessages(c.lng("id"), UPDATED, 0)
                }
            }
            "typing" -> {
                val cid = e.lng("chat_id")
                typing["$cid:${e.lng("user_id")}"] = Pair(System.currentTimeMillis() + TYPING_MS, e.str("action"))
                listener?.onTyping(cid)
            }
            "presence" -> {
                var hit = false
                for (c in chats.values) {
                    val p = c.map("peer") ?: continue
                    if (p.lng("id") == e.lng("user_id")) {
                        val np = LinkedHashMap(p)
                        np["online"] = e.bool("online"); np["last_seen"] = e.lng("last_seen"); np["seen_hidden"] = e.bool("seen_hidden")
                        c["peer"] = np; hit = true
                        listener?.onChatChanged(c.lng("id"))
                    }
                }
                if (hit) listener?.onChatList()
                // an open group shows "N members, M online": reload it (at most every 5 s) when somebody comes or goes
                val cur = chats[current]
                if (cur != null && cur.str("kind") == "group" && !cur.bool("channel")) {
                    val t = System.currentTimeMillis()
                    if (t - lastGroupRefresh > 5000L) { lastGroupRefresh = t; listener?.onNeedRefresh() }
                }
            }
            "profile" -> e.map("user")?.let { u ->
                if (u.lng("id") == myId) me.putAll(u)
                for (c in chats.values) {
                    val p = c.map("peer") ?: continue
                    if (p.lng("id") == u.lng("id")) {
                        c["peer"] = u
                        if (c.str("kind") == "private") c["title"] = u.str("display_name")
                        listener?.onChatChanged(c.lng("id"))
                    }
                }
                listener?.onChatList()
            }
            "chat_added" -> e.map("chat")?.let { chats[it.lng("id")] = LinkedHashMap(it); listener?.onChatList() }
            "chat_updated" -> e.map("chat")?.let {
                val old = chats[it.lng("id")]
                if (old == null) chats[it.lng("id")] = LinkedHashMap(it) else old.putAll(it)
                listener?.onChatList(); listener?.onChatChanged(it.lng("id"))
            }
            "chat_removed" -> {
                val id = e.lng("chat_id")
                chats.remove(id); msgs.remove(id); hasMore.remove(id); early.remove(id)
                listener?.onChatList(); listener?.onChatChanged(id)
            }
            "members_changed" -> listener?.onNeedRefresh()
            "voice_played" -> {
                val l = msgs[e.lng("chat_id")]
                val i = l?.indexOfFirst { it.lng("id") == e.lng("message_id") } ?: -1
                if (l != null && i >= 0) {
                    val m = LinkedHashMap(l[i])
                    val f = m.map("file")
                    if (f != null) {
                        val nf = LinkedHashMap(f)
                        val played = ArrayList<Any?>((f["played"] as? List<*>) ?: emptyList<Any?>())
                        if (played.none { (it as? Long) == e.lng("user_id") }) played.add(e.lng("user_id"))
                        nf["played"] = played; m["file"] = nf; l[i] = m
                        listener?.onMessages(e.lng("chat_id"), UPDATED, m.lng("id"))
                    }
                }
            }
            "session_ended", "banned" -> listener?.onSessionEnded(e.str("event"))
        }
    }

    fun ingest(m: Map<String, Any?>) {
        val id = m.lng("chat_id")
        val c = chats[id]
        if (c == null) { listener?.onNeedRefresh(); return }
        val l = msgs[id]
        if (l == null) early.getOrPut(id) { ArrayList() }.add(m)
        else {
            if (l.any { it.lng("id") == m.lng("id") }) return
            l.add(m); l.sortBy { it.lng("id") }
            while (l.size > 400 && id != current) l.removeAt(0)
        }
        c["last"] = m
        val mine = m.lng("sender_id") == myId
        val looking = id == current && viewing
        if (!mine && m.str("kind") != "system" && !looking) c["unread"] = c.lng("unread") + 1
        listener?.onChatList()
        if (l != null) listener?.onMessages(id, ADDED, m.lng("id"))
    }

    fun applyUpdate(m: Map<String, Any?>) {
        val id = m.lng("chat_id")
        val l = msgs[id]
        val i = l?.indexOfFirst { it.lng("id") == m.lng("id") } ?: -1
        if (l != null && i >= 0) l[i] = m
        val c = chats[id]
        if (c != null && c.map("last")?.lng("id") == m.lng("id")) {
            if (m.bool("deleted")) listener?.onNeedRefresh() else { c["last"] = m; listener?.onChatList() }
        }
        if (i >= 0) listener?.onMessages(id, UPDATED, m.lng("id"))
    }

    fun markReadLocal(chatId: Long) {
        val c = chats[chatId] ?: return
        if (c.lng("unread") != 0L) { c["unread"] = 0L; listener?.onChatList() }
    }

    // ------------------------------------------------------------------ names
    fun userName(id: Long): String {
        if (id == myId) return me.str("display_name", "من")
        for (c in chats.values) { val p = c.map("peer"); if (p != null && p.lng("id") == id) return p.str("display_name") }
        return ""
    }

    // ------------------------------------------------------------------ saved copy (instant start, works offline)
    fun toCache(): String {
        val m = LinkedHashMap<String, Any?>()
        m["u"] = myId; m["me"] = me; m["chats"] = chats.values.toList()
        val mm = LinkedHashMap<String, Any?>()
        var n = 0
        for (c in chatList()) {                  // only the newest 40 messages of 30 chats go into this small file; the rest is in msgs/<chat>.json
            val id = c.lng("id")
            val l = msgs[id] ?: continue
            if (l.isEmpty() || n >= 30) continue
            mm[id.toString()] = l.takeLast(40); n++
        }
        m["msgs"] = mm
        return Json.stringify(m)
    }

    /** chats that were brought up to date in this app run: opening them again asks the server for nothing (live events keep them current) */
    val synced = HashSet<Long>()
    private val savedSig = HashMap<Long, String>()

    /** the chats whose messages changed since the last save: (chat id, JSON of its newest KEEP_PER_CHAT messages). Telegram-style local history. */
    fun dirtyMsgs(): List<Pair<Long, String>> {
        val out = ArrayList<Pair<Long, String>>()
        for ((id, l) in msgs.entries.toList()) {
            if (l.isEmpty()) continue
            val last = l.last()
            val sig = l.size.toString() + ":" + last.lng("id") + ":" + (last["text"]?.hashCode() ?: 0) + ":" + (last["edited_at"] ?: "") + ":" + last.bool("deleted")
            if (savedSig[id] == sig) continue
            savedSig[id] = sig
            out.add(id to Json.stringify(l.takeLast(KEEP_PER_CHAT)))
        }
        return out
    }

    /** the saved history of one chat (read from its file when the chat is opened) */
    fun loadMsgs(id: Long, text: String): Boolean {
        @Suppress("UNCHECKED_CAST")
        val l = (Json.parse(text) as? List<Any?>)?.mapNotNull { it as? Map<String, Any?> } ?: return false
        if (l.isEmpty()) return false
        msgs[id] = ArrayList(l); hasMore[id] = true
        return true
    }

    fun loadCache(text: String, forUser: Long): Boolean {
        val j = Json.obj(text) ?: return false
        if (forUser != 0L && j.lng("u") != forUser) return false
        replaceMe(j.map("me"))
        chats.clear(); msgs.clear()
        for (c in j.list("chats")) chats[c.lng("id")] = LinkedHashMap(c)
        val mm = j.map("msgs")
        if (mm != null) for ((k, v) in mm) {
            val id = k.toLongOrNull() ?: continue
            @Suppress("UNCHECKED_CAST")
            val l = (v as? List<Any?>)?.mapNotNull { it as? Map<String, Any?> } ?: continue
            msgs[id] = ArrayList(l); hasMore[id] = true
        }
        return chats.isNotEmpty() || me.isNotEmpty()
    }
}
