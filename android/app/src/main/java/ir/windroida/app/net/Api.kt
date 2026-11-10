package ir.windroida.app.net

import java.io.IOException
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong

/** Where the server is: https://host:port (or http://). */
class ServerCfg(val host: String, val port: Int, val tls: Boolean, val pin: String) {
    val base: String get() = (if (tls) "https://" else "http://") + host + ":" + port
    companion object {
        fun parse(url: String, pin: String): ServerCfg? {
            val u = url.trim().trimEnd('/')
            val tls = when {
                u.startsWith("https://") -> true
                u.startsWith("http://") -> false
                else -> return null
            }
            val rest = u.substringAfter("://").substringBefore('/')
            if (rest.isEmpty()) return null
            val host = rest.substringBeforeLast(':', rest)
            val port = if (rest.contains(':')) rest.substringAfterLast(':').toIntOrNull() ?: return null else if (tls) 443 else 80
            if (host.isEmpty() || port !in 1..65535) return null
            return ServerCfg(host, port, tls, pin)
        }
    }
}

class ApiError(msg: String, val fromServer: Boolean = false) : Exception(msg)

/**
 * One WebSocket session with auto-reconnect, request/response matching and server events.
 * Callbacks arrive on background threads: the UI must hop to the main thread itself.
 */
class Api(val cfg: ServerCfg) {
    companion object {
        const val OFFLINE = 0       // no connection (will retry)
        const val CONNECTING = 1
        const val CONNECTED = 2     // socket is up, nobody is logged in yet
        const val ONLINE = 3        // logged in, ready
        const val LOGGED_OUT = 4    // the saved token was refused (or the server ended the session)
    }

    interface Listener {
        fun onEvent(e: Map<String, Any?>)
        fun onState(state: Int, detail: String)
    }

    private class Pending(val cb: ((Boolean, Map<String, Any?>) -> Unit)?, val at: Long)

    @Volatile var listener: Listener? = null
    @Volatile var token: String = ""
    @Volatile var me: Map<String, Any?>? = null
    @Volatile private var mk = ""
    @Volatile private var mkAt = 0L
    /** the signed key of /media URLs lives 24 h on the server: it is renewed in the background once it is 6 h old (the web app does the same) */
    var mediaKey: String
        get() {
            val now = System.currentTimeMillis()
            if (mk.isNotEmpty() && now - mkAt > 6 * 3600_000L && state == ONLINE) {
                mkAt = now
                call("media_key") { ok, r -> if (ok && r.str("media_key").isNotEmpty()) { mk = r.str("media_key"); mkAt = System.currentTimeMillis() } else mkAt = System.currentTimeMillis() - 5 * 3600_000L - 1800_000L }
            }
            return mk
        }
        set(v) { mk = v; mkAt = System.currentTimeMillis() }
    @Volatile var maxUpload: Long = 5L * 1048576
    /** versions of the user's own chat backgrounds (newest first), from "hello" */
    @Volatile var walls: List<Long> = emptyList()
    @Volatile var state = OFFLINE
        private set

    private val ids = AtomicLong(1)
    private val pending = ConcurrentHashMap<Long, Pending>()
    @Volatile private var ws: WsClient? = null
    @Volatile private var running = false
    @Volatile private var gen = 0                 // a restarted Api must never keep two loops alive
    @Volatile private var lastRx = 0L
    @Volatile private var kick: CountDownLatch? = null
    private var thread: Thread? = null
    /** ALL socket writes happen on this one thread: Android throws NetworkOnMainThreadException when the UI thread touches a socket */
    private val sender = java.util.concurrent.Executors.newSingleThreadExecutor { r -> Thread(r, "wd-send").also { it.isDaemon = true } }
    @Volatile var lastError = ""

    private fun setState(s: Int, detail: String = "") {
        state = s
        try { listener?.onState(s, detail) } catch (_: Exception) {}
    }

    // ------------------------------------------------------------------ requests
    fun call(op: String, params: Map<String, Any?> = emptyMap(), cb: ((Boolean, Map<String, Any?>) -> Unit)? = null) {
        val w = ws
        if (w == null || !w.open) { cb?.invoke(false, mapOf("error" to "به سرور وصل نیستی")); return }
        val id = ids.getAndIncrement()
        val req = LinkedHashMap<String, Any?>()
        req["id"] = id; req["op"] = op
        req.putAll(params)
        pending[id] = Pending(cb, System.currentTimeMillis())
        val text = Json.stringify(req)
        try {
            sender.execute {
                try { w.send(text) } catch (e: Exception) {
                    pending.remove(id)?.cb?.invoke(false, mapOf("error" to "ارتباط با سرور قطع شد (" + e.javaClass.simpleName + ")"))
                }
            }
        } catch (e: Exception) { pending.remove(id)?.cb?.invoke(false, mapOf("error" to "ارتباط با سرور قطع شد")) }
    }

    private val backlog = java.util.concurrent.atomic.AtomicInteger(0)
    /** Fire-and-forget (call audio/video frames): no id, no reply expected; frames are dropped when the link is slow. */
    fun fire(op: String, params: Map<String, Any?>) {
        val w = ws
        if (w == null || !w.open || backlog.get() > 30) return
        val req = LinkedHashMap<String, Any?>(); req["op"] = op; req.putAll(params)
        val text = Json.stringify(req)
        backlog.incrementAndGet()
        try { sender.execute { try { w.send(text) } catch (_: Exception) {} finally { backlog.decrementAndGet() } } } catch (_: Exception) { backlog.decrementAndGet() }
    }

    /** Blocking variant for background threads and tests. Throws ApiError. */
    fun callBlocking(op: String, params: Map<String, Any?> = emptyMap(), timeoutMs: Long = 20000): Map<String, Any?> {
        val latch = CountDownLatch(1)
        var okv = false
        var res: Map<String, Any?> = emptyMap()
        call(op, params) { ok, r -> okv = ok; res = r; latch.countDown() }
        if (!latch.await(timeoutMs, TimeUnit.MILLISECONDS)) throw ApiError("پاسخی از سرور نیومد")
        if (!okv) throw ApiError(res.str("error", "خطا"), res.bool("_server"))
        return res
    }

    private fun handle(text: String) {
        lastRx = System.currentTimeMillis()
        val m = Json.obj(text) ?: return
        if (m.containsKey("event")) {
            val ev = m.str("event")
            if (ev == "session_ended" || ev == "banned") { token = ""; setState(LOGGED_OUT, ev) }
            try { listener?.onEvent(m) } catch (_: Exception) {}
            return
        }
        val id = m.lng("id", -1)
        val p = pending.remove(id) ?: return
        if (m.bool("ok")) p.cb?.invoke(true, m)
        else p.cb?.invoke(false, LinkedHashMap(m).also { it["_server"] = true })
    }

    private fun failAll(why: String) {
        for (k in pending.keys.toList()) pending.remove(k)?.cb?.invoke(false, mapOf("error" to why))
    }

    // ------------------------------------------------------------------ login / session
    /** Signs in with a password (the account must exist). On success the token is kept for automatic resume. */
    fun login(user: String, pass: String, device: String, cb: (Boolean, String) -> Unit) =
        auth("login", mapOf("username" to user, "password" to pass, "device" to device), cb)

    fun register(user: String, pass: String, display: String, question: String, answer: String, device: String, cb: (Boolean, String) -> Unit) =
        auth("register", mapOf("username" to user, "password" to pass, "display_name" to display,
            "sec_question" to question, "sec_answer" to answer, "device" to device), cb)

    private fun auth(op: String, params: Map<String, Any?>, cb: (Boolean, String) -> Unit) {
        call(op, params) { ok, r ->
            if (!ok) { cb(false, r.str("error", "خطا")); return@call }
            token = r.str("session")
            me = r.map("me") ?: me
            Thread {
                try { afterLogin(); cb(true, "") } catch (e: Exception) { cb(false, e.message ?: "خطا") }
            }.also { it.isDaemon = true }.start()
        }
    }

    private fun afterLogin() {
        val h = callBlocking("hello", mapOf("caps" to listOf("call")))
        mediaKey = h.str("media_key")
        maxUpload = h.lng("max_upload", maxUpload)
        walls = (h["walls"] as? List<*>)?.mapNotNull { (it as? Number)?.toLong() } ?: emptyList()
        setState(ONLINE)
    }

    fun logout() {
        try { call("logout") } catch (_: Exception) {}
        token = ""; me = null
    }

    // ------------------------------------------------------------------ connection loop
    fun start() {
        if (running) return
        running = true
        val my = ++gen
        val t = Thread { loop(my) }
        t.isDaemon = true; t.name = "wd-api"
        thread = t
        t.start()
    }

    fun stop() {
        running = false
        kick?.countDown()
        val w = ws
        try { sender.execute { try { w?.close() } catch (_: Exception) {} } } catch (_: Exception) {}
    }

    /** Drop the current connection now (e.g. the network came back) so the loop reconnects without waiting. */
    fun reconnectNow() {
        if (state == CONNECTING || state == CONNECTED) return      // an attempt is already running: killing it would restart the whole handshake (and made "connecting…" endless on a slow line)
        val w = ws
        try { sender.execute { try { w?.close() } catch (_: Exception) {} } } catch (_: Exception) {}
        kick?.countDown()
    }

    @Volatile private var probeAt = 0L
    @Volatile private var failures = 0
    /** "is the link still alive?": reconnects at once when it is down, otherwise pings and drops a dead socket within ~5 s */
    fun probe() {
        when (state) {
            OFFLINE -> reconnectNow()
            ONLINE -> { probeAt = System.currentTimeMillis(); try { call("ping") } catch (_: Exception) {} }
        }
    }

    private fun loop(my: Int) {
        var delay = 700L
        while (running && my == gen) {
            val closed = CountDownLatch(1)
            kick = closed
            val w = WsClient(cfg.host, cfg.port, cfg.tls, cfg.pin)
            try {
                setState(CONNECTING)
                lastRx = System.currentTimeMillis()
                w.connect(object : WsClient.Listener {
                    override fun onText(s: String) { handle(s) }
                    override fun onClosed(reason: String) { closed.countDown() }
                }, Math.min(8000 + failures * 6000, 40000))
                ws = w
                setState(CONNECTED)
                if (token.isNotEmpty()) {
                    try {
                        val r = callBlocking("resume", mapOf("token" to token), Math.min(15000L + failures * 6000L, 45000L))
                        me = r.map("me") ?: me
                        afterLogin()
                    } catch (e: ApiError) {
                        if (e.fromServer) { token = ""; me = null; setState(LOGGED_OUT, e.message ?: "") } else throw e
                    }
                }
                delay = 700L; failures = 0
                // keep alive until the socket dies
                var lastPing = System.currentTimeMillis()
                while (running && my == gen && !closed.await(1, TimeUnit.SECONDS)) {
                    val now = System.currentTimeMillis()
                    if (now - lastPing >= 10000) { lastPing = now; call("ping") }
                    if (probeAt > 0 && now - probeAt > 5000) { if (lastRx < probeAt) { w.close(); break } else probeAt = 0 }      // no answer to the check: the link is dead
                    if (now - lastRx > 35000) { w.close(); break }
                    for ((id, p) in pending) if (now - p.at > 40000) pending.remove(id)?.cb?.invoke(false, mapOf("error" to "پاسخی از سرور نیومد"))
                }
            } catch (e: Exception) {
                // connection failed or broke: remember why (shown in the UI), then fall through to the retry wait
                lastError = e.javaClass.simpleName + ": " + (e.message ?: "") + (e.cause?.let { " / " + it.javaClass.simpleName + ": " + (it.message ?: "") } ?: "")
            }
            try { w.close() } catch (_: Exception) {}
            ws = null
            failAll("ارتباط با سرور قطع شد")
            if (!running || my != gen) break
            if (state != LOGGED_OUT) setState(OFFLINE, lastError)
            failures = Math.min(failures + 1, 6)
            val wait = CountDownLatch(1)
            kick = wait
            wait.await(delay, TimeUnit.MILLISECONDS)
            delay = Math.min((delay * 1.5).toLong(), 4000L)       // never wait long: the next try is at most 4 s away
        }
        if (my == gen) setState(OFFLINE)
    }
}
