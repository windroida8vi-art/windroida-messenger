package ir.windroida.app.ui

import android.app.AlertDialog
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import ir.windroida.app.NativeActivity
import ir.windroida.app.Prefs
import ir.windroida.app.net.bool
import ir.windroida.app.net.list
import ir.windroida.app.net.lng
import ir.windroida.app.net.map
import ir.windroida.app.net.str

/** Settings: profile + photo, privacy, security (password, sessions, blocked), app (notifications, storage, server, web version), logout. */
class SettingsScreen(private val a: NativeActivity) : Screen() {
    private val th = a.th
    private val root = LinearLayout(a)
    override val view: View get() = root
    private val body = LinearLayout(a)
    private var seen = "all"
    private var addMode = "nobody"
    private var receipts = true

    init {
        root.orientation = LinearLayout.VERTICAL; root.background = th.screenBg()
        val bar = LinearLayout(a); bar.gravity = Gravity.CENTER_VERTICAL; bar.setBackgroundColor(th.bar); bar.setPadding(a.dp(4), 0, a.dp(8), 0)
        bar.addView(iconButton(a, th, "back", th.barText) { a.pop() })
        bar.addView(label(a, "تنظیمات", 19f, th.barText, true).also { it.setPadding(a.dp(8), 0, 0, 0) })
        root.addView(bar, lp(MATCH, a.dp(56)))
        val sv = ScrollView(a); body.orientation = LinearLayout.VERTICAL; sv.addView(body)
        root.addView(sv, lp(MATCH, 0).weight(1f))
        build()
        a.rpc("privacy_get") { ok, r -> if (ok) { seen = r.str("priv_seen", "all"); addMode = r.str("priv_add", "nobody"); receipts = r.bool("read_receipts", true); build() } }
    }

    override fun onShow() { build() }

    private fun section(title: String) { body.addView(label(a, title, 13f, th.accent, true).also { it.setPadding(a.dp(18), a.dp(18), a.dp(18), a.dp(6)) }) }

    private fun row(title: String, sub: String = "", color: Int = th.text, onClick: () -> Unit): View {
        val r = LinearLayout(a); r.orientation = LinearLayout.VERTICAL; r.setPadding(a.dp(18), a.dp(12), a.dp(18), a.dp(12))
        r.background = ripple(null, th.ripple); r.isClickable = true
        r.addView(label(a, title, 16f, color))
        if (sub.isNotEmpty()) r.addView(label(a, sub, 13f, th.muted).also { it.setPadding(0, a.dp(2), 0, 0) })
        r.setOnClickListener { onClick() }
        body.addView(r, lp(MATCH, WRAP))
        return r
    }

    private fun build() {
        body.removeAllViews()
        val me = a.model.me
        // ---- header with photo
        val head = LinearLayout(a); head.orientation = LinearLayout.VERTICAL; head.gravity = Gravity.CENTER_HORIZONTAL; head.setPadding(0, a.dp(20), 0, a.dp(8))
        val av = AvatarView(a, { a.img }, { a.mediaKey }); av.setRing(th.bg); av.bind("u", me.lng("id"), me.str("display_name"), me.lng("avatar_at"), false)
        av.isClickable = true; av.setOnClickListener { pickPhoto() }
        head.addView(av, lp(a.dp(96), a.dp(96)))
        head.addView(textButton(a, th, "تغییر عکس") { pickPhoto() })
        head.addView(label(a, me.str("display_name"), 20f, th.text, true).also { it.gravity = Gravity.CENTER })
        head.addView(label(a, "@" + me.str("username"), 14f, th.muted).also { it.gravity = Gravity.CENTER; it.textDirection = View.TEXT_DIRECTION_LTR })
        body.addView(head, lp(MATCH, WRAP))
        section("حساب")
        row("نام نمایشی و بیو", me.str("display_name") + if (me.str("bio").isNotEmpty()) " · " + ChatText.short(me.str("bio"), 40) else "") { editProfile() }
        section("حریم خصوصی")
        row("آخرین بازدید و آنلاین بودن من", when (seen) { "contacts" -> "فقط مخاطب‌ها"; "nobody" -> "هیچ‌کس"; else -> "همه" }) {
            Dialogs.menu(a, null, null, listOf(
                Pair("همه") { setPrivacy("priv_seen", "all") }, Pair("فقط مخاطب‌ها") { setPrivacy("priv_seen", "contacts") }, Pair("هیچ‌کس") { setPrivacy("priv_seen", "nobody") }))
        }
        row("چه کسی می‌تونه منو به گروه اضافه کنه؟", when (addMode) { "all" -> "همه (مستقیم اضافه می‌شم)"; "contacts" -> "فقط مخاطب‌ها؛ بقیه لینک دعوت می‌فرستن"; else -> "هیچ‌کس؛ فقط لینک دعوت تو پیوی" }) {
            Dialogs.menu(a, null, null, listOf(
                Pair("همه") { setPrivacy("priv_add", "all") }, Pair("فقط مخاطب‌ها") { setPrivacy("priv_add", "contacts") }, Pair("هیچ‌کس (فقط لینک دعوت)") { setPrivacy("priv_add", "nobody") }))
        }
        val rr = LinearLayout(a); rr.gravity = Gravity.CENTER_VERTICAL; rr.setPadding(a.dp(18), a.dp(10), a.dp(18), a.dp(10))
        val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL
        col.addView(label(a, "تیک خوانده‌شدن (دو تیک آبی)", 16f, th.text)); col.addView(label(a, "اگه خاموش کنی، تو هم تیک بقیه رو نمی‌بینی", 13f, th.muted))
        rr.addView(col, lp(0, WRAP).weight(1f))
        val sw = Switch(a); sw.isChecked = receipts
        sw.setOnCheckedChangeListener { _, v -> if (v != receipts) setPrivacy("read_receipts", v) }
        rr.addView(sw)
        body.addView(rr, lp(MATCH, WRAP))
        row("کاربران مسدود", "") { blockedDialog() }
        section("امنیت")
        row("تغییر رمز عبور") { passwordDialog() }
        row("نشست‌های فعال (دستگاه‌ها)") { sessionsDialog() }
        section("برنامه")
        row("پس‌زمینه برنامه (شیشه‌ای)", wallName()) { Wall.pick(a) { build() } }
        row("اعلان‌ها", "تنظیمات اعلان اندروید") {
            try { a.startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, a.packageName)) } catch (_: Exception) { a.toast("باز نشد") }
        }
        row("حافظه و فایل‌ها", storageSub()) { storageDialog() }
        row("آدرس سرور", Prefs.server(a)) {
            AlertDialog.Builder(a).setMessage("آدرس سرور عوض بشه؟ از حساب خارج می‌شی.").setPositiveButton("بله") { _, _ -> a.logout(); a.replaceAll(SetupScreen(a)) }.setNegativeButton("نه", null).show()
        }
        row("برگشت به نسخه وب") { a.openWeb() }
        row("خروج از حساب", "", th.danger) { AlertDialog.Builder(a).setMessage("از حساب خارج بشی؟").setPositiveButton("خروج") { _, _ -> a.logout() }.setNegativeButton("نه", null).show() }
        body.addView(View(a), lp(1, a.dp(30)))
    }

    private fun wallName(): String {
        val w = Prefs.wall(a)
        return when {
            w.isEmpty() -> "پیش‌فرض"
            w.startsWith("g") -> Wall.presets.getOrNull(w.substring(1).toIntOrNull() ?: -1)?.first ?: "پیش‌فرض"
            w.startsWith("srv:") -> w.substring(4).substringBefore("|").substringBeforeLast(".")
            else -> "عکس خودت"
        }
    }

    private fun setPrivacy(key: String, v: Any) {
        a.rpc("privacy_set", mapOf(key to v)) { ok, r -> if (ok) { seen = r.str("priv_seen", seen); addMode = r.str("priv_add", addMode); receipts = r.bool("read_receipts", receipts); build() } else { a.toast(r.str("error", "خطا")); build() } }
    }

    private fun input(hint: String, text: String = "", pass: Boolean = false): EditText {
        val e = EditText(a).styled(th, hint); e.setText(text); e.setSingleLine(true)
        if (pass) { e.inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD; e.transformationMethod = android.text.method.PasswordTransformationMethod.getInstance() }
        e.background = rounded(th.field, a.dpf(10f)); e.setPadding(a.dp(12), a.dp(10), a.dp(12), a.dp(10))
        return e
    }

    private fun form(vararg v: View): LinearLayout {
        val c = LinearLayout(a); c.orientation = LinearLayout.VERTICAL; c.setPadding(a.dp(20), a.dp(8), a.dp(20), 0)
        for (x in v) { c.addView(x, lp(MATCH, WRAP).also { it.topMargin = a.dp(8) }) }
        return c
    }

    private fun editProfile() {
        val me = a.model.me
        val n = input("نام نمایشی", me.str("display_name")); val b = input("بیو", me.str("bio"))
        AlertDialog.Builder(a).setTitle("پروفایل").setView(form(n, b)).setPositiveButton("ذخیره") { _, _ ->
            a.rpc("update_profile", mapOf("display_name" to n.text.toString().trim(), "bio" to b.text.toString().trim())) { ok, r ->
                if (ok) { (r.map("me") ?: r.map("user"))?.let { u -> a.model.me.putAll(u) } ?: run { a.model.me["display_name"] = n.text.toString().trim(); a.model.me["bio"] = b.text.toString().trim() }; build(); a.toast("ذخیره شد") }
                else a.toast(r.str("error", "خطا"))
            }
        }.setNegativeButton("لغو", null).show()
    }

    private fun passwordDialog() {
        val o = input("رمز فعلی", "", true); val n = input("رمز جدید", "", true)
        AlertDialog.Builder(a).setTitle("تغییر رمز").setView(form(o, n)).setPositiveButton("تغییر") { _, _ ->
            a.rpc("change_password", mapOf("old_password" to o.text.toString(), "new_password" to n.text.toString())) { ok, r -> a.toast(if (ok) "رمز عوض شد" else r.str("error", "خطا")) }
        }.setNegativeButton("لغو", null).show()
    }

    private fun sessionsDialog() {
        val box = LinearLayout(a); box.orientation = LinearLayout.VERTICAL; box.setPadding(a.dp(20), a.dp(8), a.dp(20), 0)
        val sv = ScrollView(a); sv.addView(box)
        val d = AlertDialog.Builder(a).setTitle("نشست‌های فعال").setView(sv).setNegativeButton("بستن", null)
            .setNeutralButton("بستن بقیه") { _, _ -> a.rpc("terminate_others") { ok, r -> a.toast(if (ok) "بقیه‌ی نشست‌ها بسته شدن" else r.str("error", "خطا")) } }.show()
        box.addView(label(a, "در حال بارگذاری…", 14f, th.muted))
        a.rpc("sessions") { ok, r ->
            box.removeAllViews()
            for (s in if (ok) r.list("sessions") else emptyList()) {
                val row = LinearLayout(a); row.orientation = LinearLayout.VERTICAL; row.setPadding(0, a.dp(8), 0, a.dp(8))
                row.addView(label(a, s.str("device").ifEmpty { "دستگاه" } + if (s.bool("current")) "  (همین دستگاه)" else "", 15f, th.text, true))
                row.addView(label(a, "آخرین فعالیت: " + Fmt.listTime(s.lng("last_used")), 12f, th.muted))
                if (!s.bool("current")) { row.isClickable = true; row.setOnClickListener {
                    AlertDialog.Builder(a).setMessage("این نشست بسته بشه؟").setPositiveButton("بسته بشه") { _, _ -> a.rpc("terminate_session", mapOf("session_id" to s.lng("id"))) { ok2, r2 -> if (ok2) { box.removeView(row) } else a.toast(r2.str("error", "خطا")) } }.setNegativeButton("نه", null).show() } }
                box.addView(row)
            }
            if (box.childCount == 0) box.addView(label(a, "چیزی نیست", 14f, th.muted))
        }
        @Suppress("UNUSED_EXPRESSION") d
    }

    private fun blockedDialog() {
        val box = LinearLayout(a); box.orientation = LinearLayout.VERTICAL; box.setPadding(a.dp(20), a.dp(8), a.dp(20), 0)
        val sv = ScrollView(a); sv.addView(box)
        AlertDialog.Builder(a).setTitle("کاربران مسدود").setView(sv).setNegativeButton("بستن", null).show()
        a.rpc("privacy_get") { ok, r ->
            val l = if (ok) r.list("blocked") else emptyList()
            if (l.isEmpty()) box.addView(label(a, "کسی مسدود نیست", 14f, th.muted))
            for (u in l) {
                val row = LinearLayout(a); row.gravity = Gravity.CENTER_VERTICAL; row.setPadding(0, a.dp(6), 0, a.dp(6))
                row.addView(label(a, u.str("display_name") + "  @" + u.str("username"), 15f, th.text), lp(0, WRAP).weight(1f))
                row.addView(textButton(a, th, "رفع مسدودی") { a.rpc("unblock", mapOf("user_id" to u.lng("id"))) { ok2, _ -> if (ok2) box.removeView(row) } })
                box.addView(row)
            }
        }
    }

    // ------------------------------------------------------------------ storage (downloaded media persists like Telegram; this is where the user manages it)
    private fun storageSub(): String {
        val (mb, _) = a.downloads.stats(); val (ib, _) = a.img?.stats() ?: (0L to 0)
        return "ذخیره‌شده: " + Fmt.size(mb + ib + ir.windroida.app.WebCache.stats(a).first)
    }

    private fun storageDialog() {
        val box = LinearLayout(a); box.orientation = LinearLayout.VERTICAL; box.setPadding(a.dp(20), a.dp(8), a.dp(20), 0)
        lateinit var d: AlertDialog
        fun refresh() {
            box.removeAllViews()
            val (mb, mc) = a.downloads.stats(); val (ib, ic) = a.img?.stats() ?: (0L to 0)
            val limit = Prefs.downloadLimitMb(a)
            fun line(t: String, s: String) { box.addView(label(a, t, 15f, th.text)); box.addView(label(a, s, 13f, th.muted).also { it.setPadding(0, a.dp(2), 0, a.dp(10)) }) }
            line("عکس، ویدیو، صدا و فایل‌های دانلودشده در چت‌ها", Fmt.digits("$mc") + " فایل · " + Fmt.size(mb))
            box.addView(textButton(a, th, "پاک کردن این فایل‌ها") {
                AlertDialog.Builder(a).setMessage("فایل‌های دانلودشده پاک بشن؟ روی سرور چیزی پاک نمی‌شه، دوباره لازم شد از سرور دانلود می‌شن.")
                    .setPositiveButton("پاک کن") { _, _ -> a.downloads.clearCache(); refresh() }.setNegativeButton("نه", null).show()
            })
            line("کش عکس‌ها (پروفایل‌ها و پیش‌نمایش‌ها)", Fmt.digits("$ic") + " فایل · " + Fmt.size(ib))
            box.addView(textButton(a, th, "پاک کردن کش عکس‌ها") { a.img?.clear(); refresh() })
            val (wb, wc) = ir.windroida.app.WebCache.stats(a)
            line("کش قاب (ویدیو و عکس‌های دیده‌شده؛ آفلاین هم باز می‌شن)", Fmt.digits("$wc") + " فایل · " + Fmt.size(wb) + " از " + Fmt.digits("${ir.windroida.app.WebCache.limitMb(a)}") + " مگابایت")
            box.addView(textButton(a, th, "پاک کردن کش قاب") {
                AlertDialog.Builder(a).setMessage("کش قاب پاک بشه؟ ویدیوها دوباره از سرور لود می‌شن.")
                    .setPositiveButton("پاک کن") { _, _ -> ir.windroida.app.WebCache.clear(a); refresh() }.setNegativeButton("نه", null).show()
            })
            box.addView(textButton(a, th, "سقف کش قاب") {
                Dialogs.menu(a, null, null, listOf(200, 400, 800, 1600).map { v ->
                    Pair(Fmt.digits("$v") + " مگابایت") { ir.windroida.app.WebCache.setLimitMb(a, v); refresh() }
                })
            })
            box.addView(label(a, "سقف فایل‌های دانلودشده", 15f, th.text).also { it.setPadding(0, a.dp(10), 0, 0) })
            box.addView(textButton(a, th, if (limit <= 0) "بدون محدودیت" else Fmt.digits("$limit") + " مگابایت") {
                Dialogs.menu(a, null, null, listOf(500, 1024, 2048, 4096, 8192, 0).map { v ->
                    Pair(if (v <= 0) "بدون محدودیت" else Fmt.digits("$v") + " مگابایت") { Prefs.setDownloadLimitMb(a, v); refresh() }
                })
            })
        }
        refresh()
        val sv = ScrollView(a); sv.addView(box)
        d = AlertDialog.Builder(a).setTitle("حافظه و فایل‌ها").setView(sv).setPositiveButton("بستن", null).show()
    }

    // ------------------------------------------------------------------ profile photo
    private fun pickPhoto() {
        val i = Intent(Intent.ACTION_GET_CONTENT); i.type = "image/*"; i.addCategory(Intent.CATEGORY_OPENABLE)
        a.pickResult(Intent.createChooser(i, "عکس پروفایل")) { res, data ->
            val u: Uri? = data?.data
            if (res == android.app.Activity.RESULT_OK && u != null) uploadPhoto(u)
        }
    }

    private fun uploadPhoto(u: Uri) {
        val h = a.http ?: run { a.toast("به سرور وصل نیستی"); return }
        a.toast("در حال ارسال عکس…")
        val key = a.mediaKey
        Thread {
            var err: String? = null
            try {
                val bytes = scaled(u)
                h.upload("/avatar?" + h.q("k" to key, "target" to "me"), java.io.ByteArrayInputStream(bytes), bytes.size.toLong())
            } catch (e: Exception) { err = e.message ?: "ارسال نشد" }
            a.main.post { if (err != null) a.toast(err) else { a.toast("عکس عوض شد"); a.img?.forget("/avatar/u" + a.model.myId); a.refreshChats() } }
        }.start()
    }

    /** the picked photo as a JPEG at most 768 px wide/high (small upload on a slow link) */
    private fun scaled(u: Uri): ByteArray {
        val bo = BitmapFactory.Options(); bo.inJustDecodeBounds = true
        a.contentResolver.openInputStream(u)?.use { BitmapFactory.decodeStream(it, null, bo) }
        var s = 1
        while (bo.outWidth / (s * 2) >= 768 && bo.outHeight / (s * 2) >= 768) s *= 2
        val o = BitmapFactory.Options(); o.inSampleSize = s
        val bmp = a.contentResolver.openInputStream(u)?.use { BitmapFactory.decodeStream(it, null, o) } ?: throw java.io.IOException("عکس خونده نشد")
        val m = Math.max(bmp.width, bmp.height)
        val out = if (m > 768) Bitmap.createScaledBitmap(bmp, bmp.width * 768 / m, bmp.height * 768 / m, true) else bmp
        val bs = java.io.ByteArrayOutputStream()
        out.compress(Bitmap.CompressFormat.JPEG, 86, bs)
        return bs.toByteArray()
    }
}
