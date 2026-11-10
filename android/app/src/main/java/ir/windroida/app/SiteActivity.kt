package ir.windroida.app

import android.annotation.SuppressLint
import android.app.Activity
import android.content.ContentValues
import android.content.Intent
import android.net.Uri
import android.net.http.SslError
import android.os.Build
import android.os.Bundle
import android.provider.MediaStore
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.MimeTypeMap
import android.webkit.PermissionRequest
import android.webkit.SslErrorHandler
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import java.net.HttpURLConnection
import java.net.URL
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.HttpsURLConnection

/**
 * Cloud Drive (فضای ابری) and Ghab (قاب) inside the app, in their own screen, so they get what the system browser can't give:
 *  - the server certificate is trusted by the SAME confirmed fingerprint as the main screen (no browser warning page),
 *  - uploads use the same full file picker as the main screen,
 *  - downloads are done natively with that pinned certificate and the page's login cookie (Chrome's download manager stalls on a
 *    self-signed server; a blob download can't leave a WebView).
 * Only the server's own host is allowed; any other link opens in the browser. Back = back inside the site, then closes this screen.
 */
class SiteActivity : Activity() {
    private lateinit var web: WebView
    private var fileCb: ValueCallback<Array<Uri>>? = null
    private var origin = ""
    private var cache: WebCache? = null

    private fun originOf(u: String): String? = try {
        val j = URL(u)
        val p = if (j.port == -1) j.defaultPort else j.port
        "${j.protocol}://${j.host}:$p"
    } catch (_: Exception) { null }

    /** same host (and scheme) as the Windroida server the app is set up for; the port may differ (Cloud Drive / Ghab have their own) */
    private fun sameHost(u: String): Boolean {
        val s = Prefs.server(this)
        return try {
            val a = URL(s)
            val b = URL(u)
            s.isNotEmpty() && a.host == b.host && a.protocol == b.protocol
        } catch (_: Exception) { false }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val url = intent.getStringExtra("url") ?: ""
        if (url.isEmpty() || !sameHost(url)) { Toast.makeText(this, "این آدرس مجاز نیست", Toast.LENGTH_SHORT).show(); finish(); return }
        origin = originOf(url) ?: ""
        if (url.startsWith("https://") && Prefs.pin(this).isEmpty()) {
            Toast.makeText(this, "اول تو صفحهٔ اصلی برنامه گواهی سرور رو تأیید کن", Toast.LENGTH_LONG).show(); finish(); return
        }
        web = WebView(this)
        setContentView(web)
        val s = web.settings
        s.javaScriptEnabled = true
        s.domStorageEnabled = true
        s.allowFileAccess = false
        s.cacheMode = WebSettings.LOAD_DEFAULT
        s.mediaPlaybackRequiresUserGesture = false   // feed/reels videos autoplay while scrolling
        s.userAgentString = s.userAgentString + " WindroidaApp/1"
        CookieManager.getInstance().setAcceptCookie(true)
        web.addJavascriptInterface(Bridge(), "WD")

        val wc = WebCache(this, origin); cache = wc
        web.webViewClient = object : WebViewClient() {
            // Ghab's photos and videos are kept on the phone (400 MB, like Instagram) and the pages work offline
            override fun shouldInterceptRequest(v: WebView, r: WebResourceRequest): android.webkit.WebResourceResponse? =
                try { wc.handle(r.url.toString(), r.method, r.requestHeaders ?: emptyMap()) } catch (_: Exception) { null }
            override fun onReceivedSslError(v: WebView, h: SslErrorHandler, e: SslError) {
                val cert = if (Build.VERSION.SDK_INT >= 29) e.certificate.x509Certificate else null
                if (cert != null && Prefs.pin(this@SiteActivity).isNotEmpty() && Trust.sha256(cert) == Prefs.pin(this@SiteActivity)) h.proceed()
                else {
                    h.cancel()
                    Toast.makeText(this@SiteActivity, "گواهی با اثر انگشت تأییدشده نمی‌خونه؛ وصل نشد", Toast.LENGTH_LONG).show()
                }
            }
            override fun shouldOverrideUrlLoading(v: WebView, r: WebResourceRequest): Boolean {
                val u = r.url.toString()
                if (originOf(u) == origin) return false
                // a link back to the messenger itself (e.g. Ghab's "message" button, same host/cert, just the other port):
                // open it inside the app instead of handing a self-signed https link to the system browser.
                if (sameHost(u)) {
                    val hash = u.substringAfter('#', "").ifEmpty { null }
                    startActivity(Intent(this@SiteActivity, MainActivity::class.java).putExtra("once", true).also { if (hash != null) it.putExtra("hash", hash) })
                    finish(); return true
                }
                try { startActivity(Intent(Intent.ACTION_VIEW, r.url)) } catch (_: Exception) {}
                return true
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(r: PermissionRequest) { runOnUiThread { r.deny() } }
            override fun onShowFileChooser(v: WebView, cb: ValueCallback<Array<Uri>>, p: WebChromeClient.FileChooserParams): Boolean {
                fileCb?.onReceiveValue(null)
                fileCb = cb
                val types = p.acceptTypes.map { it.trim() }.filter { it.contains("/") }
                val open = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = if (types.size == 1) types[0] else "*/*"
                    if (types.size > 1) putExtra(Intent.EXTRA_MIME_TYPES, types.toTypedArray())
                    putExtra(Intent.EXTRA_ALLOW_MULTIPLE, p.mode == WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE)
                }
                return try { startActivityForResult(open, 77); true } catch (_: Exception) {
                    try { startActivityForResult(p.createIntent(), 77); true } catch (_: Exception) { fileCb = null; false }
                }
            }
        }
        web.setDownloadListener { u, _, cd, mime, _ ->
            if (u.startsWith("blob:") || u.startsWith("data:")) Toast.makeText(this, "این نوع دانلود پشتیبانی نمی‌شه", Toast.LENGTH_SHORT).show()
            else saveFile(u, URLUtil.guessFileName(u, cd, mime), null)
        }
        web.loadUrl(url)
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(req: Int, res: Int, data: Intent?) {
        super.onActivityResult(req, res, data)
        if (req == 77) {
            fileCb?.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(res, data))
            fileCb = null
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (::web.isInitialized && web.canGoBack()) web.goBack() else finish()
    }

    override fun onDestroy() {
        if (::web.isInitialized) { web.stopLoading(); web.destroy() }
        super.onDestroy()
    }

    /** save one file of THIS site to Downloads/Windroida: pinned certificate + the page's login cookie; visible only when complete */
    private fun saveFile(url: String, rawName: String, id: String?) {
        if (id != null && !Regex("[A-Za-z0-9_]{1,40}").matches(id)) return
        if (originOf(url) != origin) { Toast.makeText(this, "این دانلود مجاز نیست", Toast.LENGTH_SHORT).show(); return }
        var name = rawName.replace(Regex("[\\\\/:*?\"<>|\\u0000-\\u001f]"), "_").trim().trim('.').take(120)
        if (name.isEmpty()) name = "file"
        val ext = name.substringAfterLast('.', "").lowercase()
        val mime = (if (ext.isNotEmpty()) MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext) else null)
            ?: (if (ext == "apk") "application/vnd.android.package-archive" else "application/octet-stream")
        val cookie = CookieManager.getInstance().getCookie(url) ?: ""
        if (id == null) Toast.makeText(this, "دانلود شروع شد: $name", Toast.LENGTH_SHORT).show()
        // progress box in the page: wdDl(id, bytesSoFar, total, state)  state 0 = running, 1 = done, 2 = failed
        var lastTick = 0L
        fun tell(got: Long, total: Long, state: Int) {
            if (id == null) return
            val now = System.currentTimeMillis()
            if (state == 0 && now - lastTick < 250) return
            lastTick = now
            runOnUiThread { try { web.evaluateJavascript("try{window.wdDl&&wdDl('$id',$got,$total,$state)}catch(e){}", null) } catch (_: Exception) {} }
        }
        Thread {
            var uri: Uri? = null
            try {
                val values = ContentValues()
                values.put(MediaStore.Downloads.DISPLAY_NAME, name)
                values.put(MediaStore.Downloads.MIME_TYPE, mime)
                values.put(MediaStore.Downloads.RELATIVE_PATH, "Download/Windroida")
                values.put(MediaStore.Downloads.IS_PENDING, 1)
                uri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)!!
                val c = URL(url).openConnection() as HttpURLConnection
                if (c is HttpsURLConnection) {
                    c.sslSocketFactory = Trust.pinnedContext(Prefs.pin(this)).socketFactory
                    c.hostnameVerifier = HostnameVerifier { _, _ -> true }   // the pinned fingerprint is what we trust
                }
                c.instanceFollowRedirects = false
                c.connectTimeout = 10000
                c.readTimeout = 30000
                if (cookie.isNotEmpty()) c.setRequestProperty("Cookie", cookie)
                if (c.responseCode != 200) throw RuntimeException("http " + c.responseCode)
                val total = c.contentLengthLong
                tell(0, total, 0)
                contentResolver.openOutputStream(uri)!!.use { out ->
                    c.inputStream.use { ins ->
                        val buf = ByteArray(64 * 1024)
                        var got = 0L
                        while (true) {
                            val r = ins.read(buf)
                            if (r < 0) break
                            out.write(buf, 0, r)
                            got += r
                            tell(got, total, 0)
                        }
                    }
                }
                tell(0, 0, 1)
                val done = ContentValues()
                done.put(MediaStore.Downloads.IS_PENDING, 0)
                contentResolver.update(uri, done, null, null)
                runOnUiThread { Toast.makeText(this, "ذخیره شد: Download/Windroida/$name", Toast.LENGTH_LONG).show() }
            } catch (e: Exception) {
                try { if (uri != null) contentResolver.delete(uri, null, null) } catch (_: Exception) {}
                tell(0, 0, 2)
                runOnUiThread { Toast.makeText(this, "دانلود نشد", Toast.LENGTH_LONG).show() }
            }
        }.start()
    }

    /** the only thing the site's page may ask the app to do */
    inner class Bridge {
        /** full-screen native player for a video of THIS site (same origin only; login cookie is passed along) */
        @JavascriptInterface
        fun playVideo(url: String, title: String) {
            runOnUiThread {
                val full = if (url.startsWith("/")) origin + url else url
                if (originOf(full) != origin) return@runOnUiThread
                startActivity(Intent(this@SiteActivity, PlayerActivity::class.java).putExtra("url", full).putExtra("title", title)
                    .putExtra("cookie", CookieManager.getInstance().getCookie(full) ?: ""))
            }
        }

        @JavascriptInterface
        fun saveFile(url: String, name: String) { runOnUiThread { this@SiteActivity.saveFile(url, name, null) } }

        /** same, but the page gets live progress through window.wdDl(id, got, total, state) and draws its own download box */
        @JavascriptInterface
        fun saveFileId(id: String, url: String, name: String) { runOnUiThread { this@SiteActivity.saveFile(url, name, id) } }
    }
}
