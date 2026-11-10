import ir.windroida.app.net.*
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.CopyOnWriteArrayList

var okN = 0
val bad = ArrayList<String>()
fun check(name: String, c: Boolean) { if (c) okN++ else { bad.add(name); println("FAIL  $name") } }

fun waitFor(ms: Long = 8000, f: () -> Boolean): Boolean { val t = System.currentTimeMillis(); while (System.currentTimeMillis() - t < ms) { if (f()) return true; Thread.sleep(25) }; return f() }

class Probe : Api.Listener {
    val events = CopyOnWriteArrayList<Map<String, Any?>>()
    val states = CopyOnWriteArrayList<Int>()
    override fun onEvent(e: Map<String, Any?>) { events.add(e) }
    override fun onState(state: Int, detail: String) { states.add(state) }
}

fun newApi(port: Int, p: Probe): Api { val a = Api(ServerCfg("127.0.0.1", port, false, "")); a.listener = p; a.start(); return a }

fun tlsMain(port: Int) {
    val fp = fetchFingerprint("127.0.0.1", port)
    check("fingerprint looks like SHA-256", Regex("([0-9A-F]{2}:){31}[0-9A-F]{2}").matches(fp))
    val p1 = Probe(); val ok = Api(ServerCfg("127.0.0.1", port, true, fp)); ok.listener = p1; ok.start()
    check("TLS with the right pin connects", waitFor { ok.state == Api.CONNECTED })
    val p2 = Probe(); val wrong = Api(ServerCfg("127.0.0.1", port, true, fp.replace(fp.substring(0, 2), if (fp.startsWith("00")) "11" else "00"))); wrong.listener = p2; wrong.start()
    Thread.sleep(2500)
    check("TLS with a wrong pin never connects", wrong.state != Api.CONNECTED && wrong.state != Api.ONLINE && !p2.states.contains(Api.CONNECTED))
    val p3 = Probe(); val nopin = Api(ServerCfg("127.0.0.1", port, true, "")); nopin.listener = p3; nopin.start()
    Thread.sleep(1500)
    check("TLS with no pin refuses to talk", !p3.states.contains(Api.CONNECTED))
    val l = java.util.concurrent.CountDownLatch(1); var good = false
    ok.register("tlsuser", "Str0ng-pass1", "tls", "سوال تستی؟", "x1", "t") { o, _ -> good = o; l.countDown() }; l.await(10, TimeUnit.SECONDS)
    check("register + hello over TLS", good && waitFor { ok.state == Api.ONLINE })
    ok.stop(); wrong.stop(); nopin.stop()
    println("kotlin net (tls): $okN ok, ${bad.size} failed")
    System.exit(if (bad.isEmpty()) 0 else 1)
}

fun main(args: Array<String>) {
    val port = args[0].toInt()
    if (args.size > 1 && args[1] == "TLS") return tlsMain(port)
    // ---- Json
    val j = Json.parse("""{"a":1,"b":[1,2.5,"xé😀"],"c":{"d":null,"e":true},"f":-3}""") as Map<String, Any?>
    check("json basic", j.lng("a") == 1L && j.lng("f") == -3L && j.map("c")!!.bool("e") && (j["b"] as List<*>)[2] == "xé😀")
    check("json round trip", Json.parse(Json.stringify(j)) == j)
    check("json escapes", Json.obj(Json.stringify(mapOf("t" to "a\"b\\c\n é")))!!.str("t") == "a\"b\\c\n é")
    check("json garbage refused", Json.obj("{bad") == null && Json.obj("[1,2]") == null && Json.obj("") == null)
    check("server url parse", ServerCfg.parse("https://203.0.113.5:8081/", "")!!.let { it.host == "203.0.113.5" && it.port == 8081 && it.tls } && ServerCfg.parse("ftp://x", "") == null && ServerCfg.parse("http://h", "")!!.port == 80)

    val pa = Probe(); val pb = Probe()
    val A = newApi(port, pa); val B = newApi(port, pb)
    check("connects", waitFor { A.state == Api.CONNECTED && B.state == Api.CONNECTED })
    fun reg(a: Api, u: String): Boolean {
        val l = CountDownLatch(1); var ok = false; var err = ""
        a.register(u, "Str0ng-pass1", u, "سوال تستی؟", "x1", "test") { o, e -> ok = o; err = e; l.countDown() }
        l.await(10, TimeUnit.SECONDS); if (!ok) println("register error: $err"); return ok
    }
    check("register alice", reg(A, "alice")); check("register bobby", reg(B, "bobby"))
    check("online after register + hello", waitFor { A.state == Api.ONLINE && B.state == Api.ONLINE } && A.mediaKey.isNotEmpty() && A.token.isNotEmpty())
    check("me is filled", A.me?.str("username") == "alice")

    val bad1 = CountDownLatch(1); var badOk = true
    A.login("alice", "wrong-pass-1", "t") { o, _ -> badOk = o; bad1.countDown() }; bad1.await(10, TimeUnit.SECONDS)
    check("wrong password refused", !badOk)

    val chat = A.callBlocking("open_private", mapOf("username" to "bobby")).map("chat")!!
    val cid = chat.lng("id")
    check("private chat opened", cid > 0 && chat.str("kind") == "private")
    pb.events.clear()
    val sent = A.callBlocking("send", mapOf("chat_id" to cid, "text" to "سلام 😀 دنیا")).map("message")!!
    check("message sent", sent.str("body") == "سلام 😀 دنیا" && sent.lng("id") > 0)
    check("bobby got the message event", waitFor { pb.events.any { it.str("event") == "message" && it.map("message")?.str("body") == "سلام 😀 دنیا" } })
    val hist = B.callBlocking("history", mapOf("chat_id" to cid, "limit" to 40)).list("messages")
    check("history has it", hist.size == 1 && hist[0].lng("id") == sent.lng("id"))
    val chats = B.callBlocking("chats").list("chats")
    val cb = chats.firstOrNull { it.lng("id") == cid }
    check("chat list for bobby (plus his Saved Messages)", chats.size == 2 && cb != null && cb.map("last")?.str("body") == "سلام 😀 دنیا")
    A.callBlocking("edit", mapOf("message_id" to sent.lng("id"), "text" to "ویرایش شد"))
    check("edit event", waitFor { pb.events.any { it.str("event") == "message_updated" && it.map("message")?.str("body") == "ویرایش شد" } })
    B.callBlocking("react", mapOf("message_id" to sent.lng("id"), "emoji" to "👍"))
    check("reaction event", waitFor { pa.events.any { it.str("event") == "message_updated" && (it.map("message")?.list("reactions")?.size ?: 0) == 1 } })
    B.call("typing", mapOf("chat_id" to cid))
    check("typing event", waitFor { pa.events.any { it.str("event") == "typing" } })
    A.callBlocking("delete", mapOf("message_id" to sent.lng("id")))
    check("delete event", waitFor { pb.events.any { it.str("event") == "message_updated" && it.map("message")?.bool("deleted") == true } })

    val big = "ب".repeat(70000) // > 64 KB frame (64-bit length path), Persian multi-byte
    val m2 = A.callBlocking("send", mapOf("chat_id" to cid, "text" to big.take(3500)))
    check("normal long text ok", m2.map("message")!!.str("body").length == 3500)
    val tooBig = try { A.callBlocking("send", mapOf("chat_id" to cid, "text" to big)); false } catch (e: ApiError) { e.fromServer }
    check("oversize text is refused by the server (not by us)", tooBig)
    check("still online after a big frame", A.state == Api.ONLINE && (try { A.callBlocking("ping"); true } catch (e: Exception) { false }))

    // ---- HTTP: upload + download with the media key
    val http = Http(A.cfg)
    val payload = ByteArray(300_000) { (it * 7 % 251).toByte() }
    var lastProg = 0L
    val up = http.upload("/upload?" + http.q("k" to A.mediaKey, "chat_id" to cid, "name" to "نمونه.txt", "text" to "فایل تست"), payload.inputStream(), payload.size.toLong(), { d, _ -> lastProg = d })
    val fm = up.map("message")!!
    check("upload makes a file message", fm.str("kind") == "file" && fm.map("file")?.str("name") == "نمونه.txt" && fm.str("body") == "فایل تست" && lastProg == payload.size.toLong())
    check("bobby is told about the file", waitFor { pb.events.any { it.str("event") == "message" && it.map("message")?.lng("id") == fm.lng("id") } })
    val back = http.get("/media/" + fm.lng("id") + "?" + http.q("k" to B.mediaKey))
    check("download gives the same bytes", back.contentEquals(payload))
    val tmpf = java.io.File.createTempFile("wdtest", ".bin"); tmpf.delete()
    http.download("/media/" + fm.lng("id") + "?" + http.q("k" to B.mediaKey), tmpf)
    check("download to a file", tmpf.readBytes().contentEquals(payload) && !java.io.File(tmpf.path + ".part").exists())
    val badGet = try { http.get("/media/" + fm.lng("id") + "?k=wrong"); false } catch (e: java.io.IOException) { true }
    check("wrong media key is refused", badGet)
    val refused = try { http.upload("/upload?" + http.q("k" to A.mediaKey, "chat_id" to 999999, "name" to "x.txt"), ByteArray(10).inputStream(), 10); false } catch (e: ApiError) { e.fromServer }
    check("server refusal (not a member) is read as an error", refused)
    val vo = http.upload("/upload?" + http.q("k" to A.mediaKey, "chat_id" to cid, "name" to "voice.m4a", "voice" to 1, "dur" to 3, "wave" to "1,5,9,4"), ByteArray(2000) { 1 }.inputStream(), 2000)
    check("voice upload keeps the voice flag", vo.map("message")?.map("file")?.bool("voice") == true)
    // resume with the saved token on a fresh session
    val pc = Probe(); val C = newApi(port, pc); C.token = A.token
    check("resume with token -> ONLINE", waitFor { C.state == Api.ONLINE } && C.me?.str("username") == "alice")
    // bad token
    val pd = Probe(); val D = newApi(port, pd); D.token = "not-a-token"
    check("bad token -> LOGGED_OUT, token dropped", waitFor { pd.states.contains(Api.LOGGED_OUT) } && D.token.isEmpty())
    val dl = CountDownLatch(1); var dok = false
    D.login("alice", "Str0ng-pass1", "t2") { o, _ -> dok = o; dl.countDown() }; dl.await(10, TimeUnit.SECONDS)
    check("login works on the same connection afterwards", dok && waitFor { D.state == Api.ONLINE })
    // reconnect after the socket dies
    pa.states.clear()
    A.reconnectNow()
    check("auto reconnect keeps the session", waitFor(10000) { pa.states.contains(Api.OFFLINE) || pa.states.contains(Api.CONNECTING) } && waitFor(15000) { A.state == Api.ONLINE })
    check("works after reconnect", (try { A.callBlocking("chats").list("chats").size == 2 } catch (e: Exception) { false }))
    // calls while offline fail fast
    val E = Api(ServerCfg("127.0.0.1", 1, false, "")); var failed = false
    E.call("ping") { ok, _ -> failed = !ok }
    check("call without connection fails at once", failed)
    val F = newApi(1, Probe())
    check("unreachable server: state OFFLINE, no crash", waitFor { F.state == Api.OFFLINE || F.state == Api.CONNECTING })
    F.stop(); A.stop(); B.stop(); C.stop(); D.stop()
    println("kotlin net: $okN ok, ${bad.size} failed")
    System.exit(if (bad.isEmpty()) 0 else 1)
}
