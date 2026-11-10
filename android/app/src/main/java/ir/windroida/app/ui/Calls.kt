package ir.windroida.app.ui

import android.Manifest
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.graphics.Rect
import android.graphics.SurfaceTexture
import android.graphics.YuvImage
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.media.Ringtone
import android.media.RingtoneManager
import android.os.HandlerThread
import android.os.PowerManager
import android.util.Base64
import android.view.Gravity
import android.view.View
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import ir.windroida.app.NativeActivity
import ir.windroida.app.net.lng
import ir.windroida.app.net.map
import ir.windroida.app.net.str
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit

/**
 * 1:1 voice/video calls through the Windroida server (same relay as the web app): 16 kHz mono PCM16 audio frames and
 * small JPEG video frames over the WebSocket. No STUN/TURN/internet needed. The web client sends PCM until the
 * other side announces Opus ("hq"), and this client never announces it, so both sides always understand each other.
 * Rings only while the app is open.
 */
class CallManager(private val a: NativeActivity) {
    companion object { const val IDLE = 0; const val RINGING = 1; const val INCOMING = 2; const val ACTIVE = 3 }

    var state = IDLE; private set
    var id = ""; private set
    var chatId = 0L; private set
    var peerId = 0L; private set
    var peerName = ""; private set
    var wantVideo = false; private set
    var muted = false; private set
    var speaker = false; private set
    var camOn = false; private set
    var peerCam = false; private set
    var away = false; private set
    var t0 = 0L; private set
    var remote: Bitmap? = null; private set
    var endText = ""; private set
    var screen: CallScreen? = null

    private var ring: Ringtone? = null
    private var wake: PowerManager.WakeLock? = null
    private var rec: AudioRecord? = null
    private var recThread: Thread? = null
    private var track: AudioTrack? = null
    private var trackSr = 0
    private var playThread: Thread? = null
    private val playQ = LinkedBlockingQueue<ShortArray>()
    private var playSr = 16000
    @Volatile private var running = false
    private var cam: android.hardware.Camera? = null
    private var camThread: HandlerThread? = null
    private val decoder = Executors.newSingleThreadExecutor { r -> Thread(r, "wd-vdec").also { it.isDaemon = true } }
    @Volatile private var decoding = false
    private var savedMode = AudioManager.MODE_NORMAL
    private val am get() = a.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    private fun myCallId() = id

    // ---------------------------------------------------------------- user actions
    fun invite(chatId: Long, peerId: Long, peerName: String, video: Boolean) {
        if (state != IDLE) { a.toast("تو یه تماس دیگه‌ای"); return }
        a.askPermission(Manifest.permission.RECORD_AUDIO) { ok ->
            if (!ok) { a.toast("برای تماس اجازه‌ی میکروفون لازمه"); return@askPermission }
            a.rpc("call_invite", mapOf("chat_id" to chatId, "video" to video)) { ok2, r ->
                if (!ok2) { a.toast(r.str("error", "تماس برقرار نشد")); return@rpc }
                this.id = r.str("call_id"); this.chatId = chatId; this.peerId = peerId; this.peerName = peerName
                wantVideo = video; muted = false; speaker = video; camOn = false; peerCam = false; away = false; remote = null; endText = ""
                state = RINGING
                open()
            }
        }
    }

    fun accept() {
        if (state != INCOMING) return
        a.askPermission(Manifest.permission.RECORD_AUDIO) { ok ->
            if (!ok) { a.toast("برای تماس اجازه‌ی میکروفون لازمه"); hangup(); return@askPermission }
            a.rpc("call_accept", mapOf("call_id" to id)) { ok2, r ->
                if (!ok2) { finish(r.str("error", "تماس دیگه فعال نیست")); return@rpc }
                stopRing(); begin()
            }
        }
    }

    fun hangup() {
        val cid = id
        if (cid.isNotEmpty()) a.rpc("call_end", mapOf("call_id" to cid))
        finish(if (state == ACTIVE) "تماس تموم شد" else "")
    }

    fun toggleMute() { muted = !muted; screen?.refresh() }
    fun toggleSpeaker() { speaker = !speaker; try { am.isSpeakerphoneOn = speaker } catch (_: Exception) {}; screen?.refresh() }
    fun toggleCam() {
        if (state != ACTIVE) return
        if (camOn) { stopCam(); a.api?.fire("call_video", mapOf("call_id" to id, "d" to "")); screen?.refresh(); return }
        a.askPermission(Manifest.permission.CAMERA) { ok -> if (ok) { startCam(); screen?.refresh() } else a.toast("اجازه‌ی دوربین داده نشد") }
    }

    // ---------------------------------------------------------------- events from the server
    fun onEvent(e: Map<String, Any?>) {
        val cid = e.str("call_id")
        when (e.str("event")) {
            "gcall_incoming" -> {          // a group call started: the call itself lives in the web page (only that page opens)
                val who = e.str("from"); val gid = e.str("call_id")
                if (state == IDLE && gid.isNotEmpty()) android.app.AlertDialog.Builder(a).setTitle("تماس گروهی")
                    .setMessage(who.ifEmpty { "کسی" } + " تو «" + (a.model.chats[e.lng("chat_id")]?.str("title") ?: "گروه") + "» تماس گروهی شروع کرد. بپیوندی؟")
                    .setPositiveButton("بپیوند") { _, _ -> a.openWebOnce("gjoin=$gid") }.setNegativeButton("نه", null).show()
            }
            "call_incoming" -> {
                if (state != IDLE) { a.rpc("call_end", mapOf("call_id" to cid)); return }
                val f = e.map("from")
                id = cid; chatId = e.lng("chat_id"); peerId = f?.lng("id") ?: 0L; peerName = f?.str("display_name") ?: "؟"
                wantVideo = e["video"] == true; muted = false; speaker = wantVideo; camOn = false; peerCam = false; away = false; remote = null; endText = ""
                state = INCOMING
                startRing(); open()
            }
            "call_accepted" -> if (cid == id && state == RINGING) begin()
            "call_ended" -> if (cid == id) finish(when (e.str("reason")) {
                "hangup" -> "تماس تموم شد"; "rejected" -> "تماس رد شد"; "cancelled" -> "تماس لغو شد"
                "missed" -> "پاسخی داده نشد"; "disconnected" -> "ارتباط تماس قطع شد"; else -> "" })
            "call_peer" -> if (cid == id) { away = e.str("state") == "reconnecting"; screen?.refresh() }
            "call_video" -> if (cid == id) onVideo(e.str("d"))
        }
    }

    /** runs on the socket thread (many frames per second): decode and queue only */
    fun onAudio(e: Map<String, Any?>) {
        if (state != ACTIVE || e.str("call_id") != id || e.str("c") == "opus") return
        try {
            val b = Base64.decode(e.str("d"), Base64.DEFAULT)
            val n = b.size / 2
            val s = ShortArray(n)
            for (i in 0 until n) s[i] = ((b[2 * i].toInt() and 0xFF) or (b[2 * i + 1].toInt() shl 8)).toShort()
            val sr = e.lng("sr", 16000L).toInt().coerceIn(8000, 48000)
            if (sr != playSr) { playSr = sr }
            playQ.offer(s)
            while (playQ.size > 28) playQ.poll()        // more than ~1.8 s behind: skip ahead, stay live
        } catch (_: Exception) {}
    }

    private fun onVideo(d: String) {
        if (d.isEmpty()) { peerCam = false; remote = null; screen?.refresh(); return }
        if (decoding) return
        decoding = true
        decoder.execute {
            try {
                val b = Base64.decode(d, Base64.DEFAULT)
                val bm = BitmapFactory.decodeByteArray(b, 0, b.size)
                if (bm != null) a.main.post { remote = bm; peerCam = true; screen?.refresh() }
            } catch (_: Exception) {} finally { decoding = false }
        }
    }

    fun onOnline() {
        if (state == ACTIVE) a.rpc("call_rejoin", mapOf("call_id" to id)) { ok, r -> if (!ok) finish("تماس تموم شده بود") else { away = r["peer_online"] == false; screen?.refresh() } }
    }

    // ---------------------------------------------------------------- lifecycle
    private fun open() { val s = CallScreen(a, this); screen = s; a.push(s) }

    private fun begin() {
        state = ACTIVE; t0 = System.currentTimeMillis(); stopRing()
        try {
            savedMode = am.mode; am.mode = AudioManager.MODE_IN_COMMUNICATION; am.isSpeakerphoneOn = speaker
            wake = (a.getSystemService(Context.POWER_SERVICE) as PowerManager).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "windroida:call").also { it.acquire(4 * 3600 * 1000L) }
        } catch (_: Exception) {}
        running = true
        startPlayback(); startCapture()
        if (wantVideo) toggleCam()
        screen?.refresh()
    }

    private fun finish(text: String) {
        if (state == IDLE && id.isEmpty()) return
        running = false
        stopRing(); stopCam()
        try { recThread?.join(300) } catch (_: Exception) {}
        try { rec?.stop() } catch (_: Exception) {}; try { rec?.release() } catch (_: Exception) {}; rec = null
        playQ.clear(); playQ.offer(ShortArray(0))
        try { playThread?.join(300) } catch (_: Exception) {}
        try { track?.stop() } catch (_: Exception) {}; try { track?.release() } catch (_: Exception) {}; track = null; trackSr = 0
        try { am.isSpeakerphoneOn = false; am.mode = savedMode } catch (_: Exception) {}
        try { if (wake?.isHeld == true) wake?.release() } catch (_: Exception) {}; wake = null
        val was = state
        state = IDLE; id = ""; remote = null; peerCam = false; camOn = false; endText = text
        val s = screen; screen = null
        if (s != null) s.ended(text, was == ACTIVE) 
        if (text.isNotEmpty() && s == null) a.toast(text)
    }

    private fun startRing() {
        try { ring = RingtoneManager.getRingtone(a, RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)); ring?.play() } catch (_: Exception) {}
    }
    private fun stopRing() { try { ring?.stop() } catch (_: Exception) {}; ring = null }

    // ---------------------------------------------------------------- audio
    private fun startCapture() {
        val sr = 16000
        val minB = AudioRecord.getMinBufferSize(sr, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val r = try { AudioRecord(MediaRecorder.AudioSource.VOICE_COMMUNICATION, sr, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, Math.max(minB, 8192)) } catch (_: Exception) { null }
        if (r == null || r.state != AudioRecord.STATE_INITIALIZED) { a.toast("میکروفون باز نشد"); return }
        rec = r
        try { if (android.media.audiofx.AcousticEchoCanceler.isAvailable()) android.media.audiofx.AcousticEchoCanceler.create(r.audioSessionId)?.enabled = true } catch (_: Exception) {}
        try { if (android.media.audiofx.NoiseSuppressor.isAvailable()) android.media.audiofx.NoiseSuppressor.create(r.audioSessionId)?.enabled = true } catch (_: Exception) {}
        val cid = id
        recThread = Thread {
            try {
                r.startRecording()
                val buf = ShortArray(1024)
                val bytes = ByteArray(2048)
                while (running && id == cid) {
                    var got = 0
                    while (got < buf.size && running) { val n = r.read(buf, got, buf.size - got); if (n <= 0) break; got += n }
                    if (got < buf.size || muted) continue
                    for (i in buf.indices) { bytes[2 * i] = (buf[i].toInt() and 0xFF).toByte(); bytes[2 * i + 1] = (buf[i].toInt() shr 8).toByte() }
                    a.api?.fire("call_audio", mapOf("call_id" to cid, "sr" to sr, "c" to "pcm", "hq" to 0, "d" to Base64.encodeToString(bytes, Base64.NO_WRAP)))
                }
            } catch (_: Exception) {}
        }.also { it.isDaemon = true; it.start() }
    }

    private fun startPlayback() {
        playQ.clear()
        playThread = Thread {
            try {
                var primed = false
                while (running) {
                    if (!primed) { if (playQ.size < 3) { Thread.sleep(20); continue }; primed = true }
                    val s = playQ.poll(400, TimeUnit.MILLISECONDS)
                    if (s == null) { primed = false; continue }       // ran dry: re-buffer (~200 ms) before continuing
                    if (s.isEmpty()) break
                    val t = trackFor(playSr)
                    t.write(s, 0, s.size)
                }
            } catch (_: Exception) {}
        }.also { it.isDaemon = true; it.start() }
    }

    private fun trackFor(sr: Int): AudioTrack {
        val cur = track
        if (cur != null && trackSr == sr) return cur
        try { cur?.stop(); cur?.release() } catch (_: Exception) {}
        val minB = AudioTrack.getMinBufferSize(sr, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val t = AudioTrack.Builder()
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
            .setAudioFormat(AudioFormat.Builder().setSampleRate(sr).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
            .setBufferSizeInBytes(Math.max(minB * 2, 16384)).setTransferMode(AudioTrack.MODE_STREAM).build()
        t.play(); track = t; trackSr = sr
        return t
    }

    // ---------------------------------------------------------------- camera (frames as small JPEGs, ~8 fps)
    @Suppress("DEPRECATION")
    private fun startCam() {
        if (camOn) return
        camOn = true
        val th = HandlerThread("wd-cam"); th.start(); camThread = th
        val cid = id
        android.os.Handler(th.looper).post {
            try {
                val n = android.hardware.Camera.getNumberOfCameras()
                var idx = 0
                val info = android.hardware.Camera.CameraInfo()
                for (i in 0 until n) { android.hardware.Camera.getCameraInfo(i, info); if (info.facing == android.hardware.Camera.CameraInfo.CAMERA_FACING_FRONT) { idx = i; break } }
                android.hardware.Camera.getCameraInfo(idx, info)
                val c = android.hardware.Camera.open(idx)
                val p = c.parameters
                val sz = p.supportedPreviewSizes.filter { it.width >= 320 }.minByOrNull { it.width * it.height } ?: p.supportedPreviewSizes[0]
                p.setPreviewSize(sz.width, sz.height)
                try { p.setPreviewFpsRange(8000, 15000) } catch (_: Exception) {}
                c.parameters = p
                c.setPreviewTexture(SurfaceTexture(11))
                val front = info.facing == android.hardware.Camera.CameraInfo.CAMERA_FACING_FRONT
                val rot = info.orientation
                var last = 0L
                c.setPreviewCallback { data, camera ->
                    val now = System.currentTimeMillis()
                    if (now - last < 125 || id != cid || !camOn) return@setPreviewCallback
                    last = now
                    try {
                        val ps = camera.parameters.previewSize
                        val o = ByteArrayOutputStream()
                        YuvImage(data, android.graphics.ImageFormat.NV21, ps.width, ps.height, null).compressToJpeg(Rect(0, 0, ps.width, ps.height), 60, o)
                        val raw = o.toByteArray()
                        val bm = BitmapFactory.decodeByteArray(raw, 0, raw.size)
                        val m = Matrix(); m.postRotate(rot.toFloat()); if (front) m.postScale(-1f, 1f)
                        val rb = Bitmap.createBitmap(bm, 0, 0, bm.width, bm.height, m, true)
                        val o2 = ByteArrayOutputStream(); rb.compress(Bitmap.CompressFormat.JPEG, 50, o2)
                        a.api?.fire("call_video", mapOf("call_id" to cid, "d" to Base64.encodeToString(o2.toByteArray(), Base64.NO_WRAP)))
                        bm.recycle(); if (rb !== bm) rb.recycle()
                    } catch (_: Exception) {}
                }
                c.startPreview()
                cam = c
            } catch (e: Exception) { camOn = false; a.main.post { a.toast("دوربین باز نشد"); screen?.refresh() } }
        }
    }

    @Suppress("DEPRECATION")
    private fun stopCam() {
        camOn = false
        val c = cam; cam = null
        try { c?.setPreviewCallback(null); c?.stopPreview(); c?.release() } catch (_: Exception) {}
        try { camThread?.quitSafely() } catch (_: Exception) {}; camThread = null
    }
}

/** the full-screen call UI (dark, like every call app) */
class CallScreen(private val a: NativeActivity, private val cm: CallManager) : Screen() {
    private val th = a.th
    private val root = FrameLayout(a)
    override val view: View get() = root
    private val video = ImageView(a)
    private val av = AvatarView(a, { a.img }, { a.mediaKey })
    private val nameV = label(a, cm.peerName, 26f, 0xFFFFFFFF.toInt(), true)
    private val statV = label(a, "", 16f, 0xCCFFFFFF.toInt())
    private val ctrl = LinearLayout(a)
    private var closing = false
    private val tick = object : Runnable { override fun run() { if (!closing) { refresh(); a.main.postDelayed(this, 1000) } } }

    init {
        root.setBackgroundColor(0xFF0F1B27.toInt()); root.keepScreenOn = true; root.isClickable = true
        video.scaleType = ImageView.ScaleType.CENTER_CROP; video.visibility = View.GONE
        root.addView(video, FrameLayout.LayoutParams(-1, -1))
        val mid = LinearLayout(a); mid.orientation = LinearLayout.VERTICAL; mid.gravity = Gravity.CENTER_HORIZONTAL
        av.setRing(0xFF0F1B27.toInt())
        val x = cm.peerId
        av.bind("u", x, cm.peerName, 0L, false)
        mid.addView(av, lp(a.dp(120), a.dp(120)).also { it.topMargin = a.dp(90) })
        nameV.gravity = Gravity.CENTER; mid.addView(nameV, lp(-2, -2).also { it.topMargin = a.dp(18) })
        statV.gravity = Gravity.CENTER; mid.addView(statV, lp(-2, -2).also { it.topMargin = a.dp(6) })
        root.addView(mid, FrameLayout.LayoutParams(-1, -2, Gravity.TOP))
        ctrl.orientation = LinearLayout.HORIZONTAL; ctrl.gravity = Gravity.CENTER
        root.addView(ctrl, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM).also { it.bottomMargin = a.dp(48) })
        refresh()
        a.main.postDelayed(tick, 1000)
    }

    private fun circle(kind: String, bg: Int, on: Boolean = false, click: () -> Unit): View {
        val b = FrameLayout(a)
        b.background = rounded(if (on) 0xFFFFFFFF.toInt() else bg, a.dpf(32f))
        b.addView(icon(a, kind, if (on) 0xFF0F1B27.toInt() else 0xFFFFFFFF.toInt(), 28), FrameLayout.LayoutParams(a.dp(28), a.dp(28), Gravity.CENTER))
        b.isClickable = true; b.setOnClickListener { click() }
        ctrl.addView(b, lp(a.dp(64), a.dp(64)).also { it.leftMargin = a.dp(12); it.rightMargin = a.dp(12) })
        return b
    }

    fun refresh() {
        if (closing) return
        ctrl.removeAllViews()
        val gray = 0x33FFFFFF
        when (cm.state) {
            CallManager.INCOMING -> {
                statV.text = if (cm.wantVideo) "تماس تصویری ورودی…" else "تماس صوتی ورودی…"
                circle("hangup", th.danger) { cm.hangup() }
                circle("phone", th.ok) { cm.accept() }
            }
            CallManager.RINGING -> {
                statV.text = "در حال زنگ زدن…"
                circle("hangup", th.danger) { cm.hangup() }
            }
            CallManager.ACTIVE -> {
                val s = ((System.currentTimeMillis() - cm.t0) / 1000).toInt()
                statV.text = if (cm.away) "ارتباط طرف مقابل قطع شده، منتظر برگشتش…" else String.format("%d:%02d", s / 60, s % 60)
                circle(if (cm.muted) "micoff" else "mic", gray, cm.muted) { cm.toggleMute() }
                circle(if (cm.camOn) "video" else "videooff", gray, cm.camOn) { cm.toggleCam() }
                circle("speaker", gray, cm.speaker) { cm.toggleSpeaker() }
                circle("hangup", th.danger) { cm.hangup() }
            }
            else -> {}
        }
        val rb = cm.remote
        if (cm.state == CallManager.ACTIVE && cm.peerCam && rb != null) { video.setImageBitmap(rb); video.visibility = View.VISIBLE; av.visibility = View.GONE; nameV.alpha = 0.9f }
        else { video.visibility = View.GONE; av.visibility = View.VISIBLE; nameV.alpha = 1f }
    }

    fun ended(text: String, wasActive: Boolean) {
        closing = true
        statV.text = text.ifEmpty { "تماس تموم شد" }
        ctrl.removeAllViews()
        a.main.postDelayed({ if (a.top() === this) a.pop() }, if (text.isEmpty()) 0 else 900)
    }

    override fun onBack(): Boolean { return true }       // hang up with the red button, not by accident
}
