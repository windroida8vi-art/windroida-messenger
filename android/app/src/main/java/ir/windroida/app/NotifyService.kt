package ir.windroida.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import javax.net.ssl.HttpsURLConnection

/** Long-polls the Windroida server (POST /notify) and shows a notification for every new message while the app is in the background. No Google services needed. */
class NotifyService : Service() {
    @Volatile private var running = false
    @Volatile private var wakeNow = false
    private var worker: Thread? = null
    private var wake: android.os.PowerManager.WakeLock? = null

    companion object {
        const val CH_SVC = "svc"
        const val CH_MSG = "msg"
        fun start(c: Context) {
            if (Prefs.token(c).isEmpty() || Prefs.server(c).isEmpty()) return
            ContextCompat.startForegroundService(c, Intent(c, NotifyService::class.java))
        }
        fun stop(c: Context) { c.stopService(Intent(c, NotifyService::class.java)) }
    }

    override fun onBind(i: Intent?): IBinder? = null

    @Volatile private var status = "متصل برای دریافت پیام‌ها"
    private var netCb: android.net.ConnectivityManager.NetworkCallback? = null

    /** The permanent notification. It is "ongoing"; if the user swipes it away anyway (Android 14 allows that) the delete-intent
     *  starts this service again, which puts the notification straight back. */
    private fun svcNotification(text: String): Notification {
        val again = PendingIntent.getForegroundService(this, 8, Intent(this, NotifyService::class.java).putExtra("repost", true), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val open = PendingIntent.getActivity(this, 9, Intent(this, if (Prefs.mode(this) == "web") MainActivity::class.java else NativeActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, CH_SVC)
            .setSmallIcon(android.R.drawable.stat_notify_chat)
            .setContentTitle("Windroida")
            .setContentText(text)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setShowWhen(false)
            .setContentIntent(open)
            .setDeleteIntent(again)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .build()
    }

    private fun setStatus(t: String) {
        if (t == status) return
        status = t
        try { getSystemService(NotificationManager::class.java).notify(1, svcNotification(t)) } catch (_: Exception) {}
    }

    override fun onCreate() {
        super.onCreate()
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CH_SVC, "اتصال Windroida", NotificationManager.IMPORTANCE_MIN))
        nm.createNotificationChannel(NotificationChannel(CH_MSG, "پیام‌ها", NotificationManager.IMPORTANCE_HIGH))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val n: Notification = svcNotification(status)
        if (Build.VERSION.SDK_INT >= 34) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE) else startForeground(1, n)
        if (wake == null) {
            try { wake = getSystemService(android.os.PowerManager::class.java).newWakeLock(android.os.PowerManager.PARTIAL_WAKE_LOCK, "windroida:notify").also { it.setReferenceCounted(false); it.acquire() } } catch (_: Exception) {}
        }
        if (!running) {
            running = true
            worker = Thread { loop() }.also { it.isDaemon = true; it.start() }
            try {                                    // internet came back -> don't wait out the retry pause
                val cm = getSystemService(android.net.ConnectivityManager::class.java)
                netCb = object : android.net.ConnectivityManager.NetworkCallback() {
                    override fun onAvailable(network: android.net.Network) { wakeNow = true; worker?.interrupt() }
                }
                cm.registerDefaultNetworkCallback(netCb!!)
            } catch (_: Exception) {}
        }
        return START_STICKY
    }

    /** swiped out of the recent apps: come back right away so notifications keep arriving */
    override fun onTaskRemoved(rootIntent: Intent?) {
        try {
            val pi = PendingIntent.getForegroundService(this, 7, Intent(this, NotifyService::class.java), PendingIntent.FLAG_ONE_SHOT or PendingIntent.FLAG_IMMUTABLE)
            (getSystemService(Context.ALARM_SERVICE) as android.app.AlarmManager).set(android.app.AlarmManager.ELAPSED_REALTIME, android.os.SystemClock.elapsedRealtime() + 1500, pi)
        } catch (_: Exception) {}
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        try { if (wake?.isHeld == true) wake?.release() } catch (_: Exception) {}
        wake = null
        running = false
        try { netCb?.let { getSystemService(android.net.ConnectivityManager::class.java).unregisterNetworkCallback(it) } } catch (_: Exception) {}
        netCb = null
        worker?.interrupt()
        super.onDestroy()
    }

    private fun loop() {
        var since = -1L
        var backoff = 2000L
        while (running) {
            val server = Prefs.server(this)
            val token = Prefs.token(this)
            val pin = Prefs.pin(this)
            if (server.isEmpty() || token.isEmpty() || (server.startsWith("https") && pin.isEmpty())) {
                sleep(5000); continue
            }
            try {
                val res = post("$server/notify", JSONObject().put("token", token).put("since", since).toString(), pin)
                val seq = res.optLong("seq", since)
                if (since >= 0) {
                    val items = res.optJSONArray("items")
                    if (items != null) for (i in 0 until items.length()) show(items.getJSONObject(i))
                }
                since = seq
                backoff = 2000L
                setStatus("متصل برای دریافت پیام‌ها")
            } catch (e: AuthException) {
                sleep(60000)                       // session ended (logged out / expired): check again in a minute
            } catch (e: Exception) {
                if (!running) return
                setStatus("اینترنت قطعه؛ به‌محض وصل‌شدن دوباره وصل می‌شم")
                if (wakeNow) { wakeNow = false; backoff = 2000L }
                sleep(backoff)
                backoff = minOf(backoff * 2, 60000L)
            }
        }
    }

    private class AuthException : Exception()

    private fun post(url: String, body: String, pin: String): JSONObject {
        val c = URL(url).openConnection() as HttpURLConnection
        try {
            if (c is HttpsURLConnection) {
                c.sslSocketFactory = Trust.pinnedContext(pin).socketFactory
                c.hostnameVerifier = javax.net.ssl.HostnameVerifier { _, _ -> true }   // the pinned fingerprint is what we trust
            }
            c.requestMethod = "POST"
            c.connectTimeout = 10000
            c.readTimeout = 45000
            c.doOutput = true
            c.setRequestProperty("Content-Type", "application/json")
            c.outputStream.use { it.write(body.toByteArray()) }
            val code = c.responseCode
            if (code == 403) throw AuthException()
            if (code != 200) throw Exception("http $code")
            return JSONObject(c.inputStream.bufferedReader().readText())
        } finally {
            c.disconnect()
        }
    }

    private fun sleep(ms: Long) { try { Thread.sleep(ms) } catch (_: InterruptedException) {} }

    private fun show(o: JSONObject) {
        if (App.foreground) return                  // you are looking at the app: it plays its own sound
        val chat = o.optInt("chat_id")
        val isCall = o.optBoolean("call")
        val open = Intent(this, if (Prefs.mode(this) == "web") MainActivity::class.java else NativeActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            .putExtra("chat", chat)
        val pi = PendingIntent.getActivity(this, chat, open, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val n = NotificationCompat.Builder(this, CH_MSG)
            .setSmallIcon(android.R.drawable.stat_notify_chat)
            .setContentTitle(o.optString("title"))
            .setContentText(o.optString("text"))
            .setStyle(NotificationCompat.BigTextStyle().bigText(o.optString("text")))
            .setAutoCancel(true)
            .setContentIntent(pi)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(if (isCall) NotificationCompat.CATEGORY_CALL else NotificationCompat.CATEGORY_MESSAGE)
            .build()
        try { getSystemService(NotificationManager::class.java).notify(if (isCall) 3000 + chat else 2000 + chat, n) } catch (_: SecurityException) {}
    }
}
