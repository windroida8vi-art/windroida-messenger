package ir.windroida.app

import android.content.Context
import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/** Saved settings: server address, pinned certificate fingerprint, session token. */
object Prefs {
    private fun sp(c: Context) = c.getSharedPreferences("wd", Context.MODE_PRIVATE)
    fun server(c: Context): String = sp(c).getString("server", "") ?: ""
    fun pin(c: Context): String = sp(c).getString("pin", "") ?: ""
    fun token(c: Context): String = sp(c).getString("token", "") ?: ""
    /** "native" (the native screens, default) or "web" (the WebView app, always available as the fallback): the native side switches itself to "web" after a crash */
    fun mode(c: Context): String = sp(c).getString("mode", "native") ?: "native"
    fun setMode(c: Context, v: String) = sp(c).edit().putString("mode", v).apply()
    fun setServer(c: Context, v: String) = sp(c).edit().putString("server", v.trim().trimEnd('/')).apply()
    fun setPin(c: Context, v: String) = sp(c).edit().putString("pin", v).apply()
    fun setToken(c: Context, v: String) = sp(c).edit().putString("token", v).apply()
    /** cap, in MB, on the downloaded-files folder (chat media/voice/files kept like Telegram); 0 = unlimited */
    fun downloadLimitMb(c: Context): Int = sp(c).getInt("dl_limit_mb", 4096)
    fun setDownloadLimitMb(c: Context, v: Int) = sp(c).edit().putInt("dl_limit_mb", v).apply()
    /** chat background: "" = default, "g<n>" = built-in gradient/colour, "srv:<name>|<v>" = server picture, "mine:<v>" = own picture */
    fun wall(c: Context): String = sp(c).getString("wall", "") ?: ""
    fun setWall(c: Context, v: String) = sp(c).edit().putString("wall", v).apply()
}

/** Trust ONLY the server certificate whose SHA-256 fingerprint you confirmed (no system certificate store needed). */
object Trust {
    fun sha256(cert: X509Certificate): String =
        MessageDigest.getInstance("SHA-256").digest(cert.encoded).joinToString(":") { "%02X".format(it) }

    fun pinnedTm(pin: String): X509TrustManager = object : X509TrustManager {
        override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
        override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
            if (chain.isEmpty() || sha256(chain[0]) != pin) throw CertificateException("certificate does not match the pinned fingerprint")
        }
        override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
    }

    fun pinnedContext(pin: String): SSLContext {
        val tm = pinnedTm(pin)
        val ctx = SSLContext.getInstance("TLS")
        ctx.init(null, arrayOf<TrustManager>(tm), null)
        return ctx
    }
}
