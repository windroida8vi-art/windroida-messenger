import ir.windroida.app.net.*
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

var mOk = 0
val mBad = ArrayList<String>()
fun mcheck(name: String, c: Boolean) { if (c) mOk++ else { mBad.add(name); println("FAIL  $name") } }
fun mwait(ms: Long = 8000, f: () -> Boolean): Boolean { val t = System.currentTimeMillis(); while (System.currentTimeMillis() - t < ms) { if (f()) return true; Thread.sleep(25) }; return f() }

/** Everything the model hears, plus all model calls go through ONE thread, like the UI thread in the app. */
class Rec : Model.Listener {
    val log = CopyOnWriteArrayList<String>()
    override fun onChatList() { log.add("list") }
    override fun onChatChanged(chatId: Long) { log.add("chat:$chatId") }
    override fun onMessages(chatId: Long, kind: Int, messageId: Long) { log.add("msg:$chatId:$kind:$messageId") }
    override fun onTyping(chatId: Long) { log.add("typing:$chatId") }
    override fun onNeedRefresh() { log.add("refresh") }
    override fun onSessionEnded(reason: String) { log.add("ended:$reason") }
}

fun main(args: Array<String>) {
    val port = args[0].toInt()
    val ui = Executors.newSingleThreadExecutor()
    fun <T> onUi(f: () -> T): T = ui.submit<T> { f() }.get(10, TimeUnit.SECONDS)
    fun mk(user: String): Triple<Api, Model, Rec> {
        val a = Api(ServerCfg("127.0.0.1", port, false, "")); val m = Model(); val r = Rec(); m.listener = r
        a.listener = object : Api.Listener {
            override fun onEvent(e: Map<String, Any?>) { ui.execute { m.applyEvent(e) } }
            override fun onState(state: Int, detail: String) {}
        }
        a.start()
        mwait { a.state == Api.CONNECTED }
        val l = CountDownLatch(1)
        a.register(user, "Str0ng-pass1", user.replaceFirstChar { it.uppercase() }, "سوال تستی؟", "x1", "t") { _, _ -> l.countDown() }
        l.await(10, TimeUnit.SECONDS); mwait { a.state == Api.ONLINE }
        onUi { m.replaceMe(a.me) }
        return Triple(a, m, r)
    }
    val (A, MA, RA) = mk("alice"); val (B, MB, RB) = mk("bobby")
    mcheck("both online", A.state == Api.ONLINE && B.state == Api.ONLINE && MB.myId > 0)

    val cid = A.callBlocking("open_private", mapOf("username" to "bobby")).map("chat")!!.lng("id")
    onUi { MA.setChats(A.callBlocking("chats").list("chats")); MB.setChats(B.callBlocking("chats").list("chats")) }
    mcheck("an empty private chat is not listed yet (server rule)", onUi { !MA.chats.containsKey(cid) })
    mcheck("bobby does not see an empty chat yet", onUi { !MB.chats.containsKey(cid) })

    // first message to a chat bobby does not know -> he must be told to reload
    A.callBlocking("send", mapOf("chat_id" to cid, "text" to "اولین"))
    mcheck("unknown chat -> refresh requested", mwait { RB.log.contains("refresh") })
    onUi { MB.setChats(B.callBlocking("chats").list("chats")) }
    mcheck("after reload the chat is there with 1 unread", onUi { MB.chats[cid]?.lng("unread") == 1L && MB.chatList().first { it.lng("id") == cid }.map("peer")?.str("username") == "alice" })
    onUi { MB.setHistory(cid, B.callBlocking("history", mapOf("chat_id" to cid, "limit" to 40)).list("messages"), false) }
    mcheck("history loaded", onUi { MB.msgs[cid]?.size == 1 })

    // not viewing -> unread grows; viewing -> it does not
    A.callBlocking("send", mapOf("chat_id" to cid, "text" to "دومی"))
    mcheck("unread 2 while not looking", mwait { onUi { MB.chats[cid]?.lng("unread") == 2L && MB.msgs[cid]?.size == 2 } })
    onUi { MB.current = cid; MB.viewing = true; MB.markReadLocal(cid) }
    A.callBlocking("send", mapOf("chat_id" to cid, "text" to "سومی"))
    mcheck("no unread while looking", mwait { onUi { MB.msgs[cid]?.size == 3 } } && onUi { MB.chats[cid]?.lng("unread") == 0L })
    mcheck("last message follows", onUi { MB.chats[cid]?.map("last")?.str("body") == "سومی" })
    val dup = onUi { MB.msgs[cid]!!.last() }
    onUi { MB.ingest(dup) }
    mcheck("duplicate event ignored", onUi { MB.msgs[cid]!!.size == 3 })

    // edit / react / delete
    val mid = onUi { MB.msgs[cid]!![1].lng("id") }
    A.callBlocking("edit", mapOf("message_id" to mid, "text" to "ویرایش‌شده"))
    mcheck("edit applied", mwait { onUi { MB.msgs[cid]!![1].str("body") == "ویرایش‌شده" } })
    val rr = B.callBlocking("react", mapOf("message_id" to mid, "emoji" to "❤️"))
    onUi { MB.applyUpdate(rr.map("message")!!) }      // the reply carries the new message (the server does not echo to the sender)
    mcheck("reaction applied", mwait { onUi { MB.msgs[cid]!![1].list("reactions").size == 1 } })
    RB.log.clear()
    val lastId = onUi { MB.msgs[cid]!!.last().lng("id") }
    A.callBlocking("delete", mapOf("message_id" to lastId))
    mcheck("deleting the last message asks for a refresh", mwait { RB.log.contains("refresh") } && onUi { MB.msgs[cid]!!.last().bool("deleted") })

    // typing + presence + read
    A.call("typing", mapOf("chat_id" to cid))
    mcheck("typing shows then expires", mwait { onUi { MB.typingIn(cid) != null } } && onUi { MB.typingIn(cid, System.currentTimeMillis() + 10_000) == null })
    RB.log.clear()
    val C = Api(ServerCfg("127.0.0.1", port, false, "")); C.start(); mwait { C.state == Api.CONNECTED }
    C.token = A.token; C.reconnectNow()   // a second device of alice: she is already online, so no presence flip; then drop B's partner
    B.call("read", mapOf("chat_id" to cid, "up_to" to lastId))
    mcheck("read receipt reaches alice", mwait { onUi { MA.chats[cid]?.lng("peer_read") == lastId } })
    C.stop()

    // cache round trip
    val json = onUi { MB.toCache() }
    val M2 = Model()
    mcheck("cache loads for the same user", M2.loadCache(json, MB.myId) && M2.chats.containsKey(cid) && M2.msgs[cid]?.size == 3)
    mcheck("cache refuses another user", !Model().loadCache(json, MB.myId + 99))
    mcheck("cache of garbage is refused", !Model().loadCache("{nope", 0))
    // session end
    RB.log.clear()
    onUi { MB.applyEvent(mapOf("event" to "banned")) }
    mcheck("banned event reaches the UI", RB.log.contains("ended:banned"))
    // chat removed
    onUi { MB.applyEvent(mapOf("event" to "chat_removed", "chat_id" to cid)) }
    mcheck("chat_removed clears everything", onUi { !MB.chats.containsKey(cid) && MB.msgs[cid] == null })
    A.stop(); B.stop(); ui.shutdown()
    println("kotlin model: $mOk ok, ${mBad.size} failed")
    System.exit(if (mBad.isEmpty()) 0 else 1)
}
