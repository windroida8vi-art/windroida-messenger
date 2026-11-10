package ir.windroida.app.ui

import android.app.AlertDialog
import android.graphics.Typeface
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import ir.windroida.app.NativeActivity
import ir.windroida.app.Prefs
import ir.windroida.app.net.ServerCfg
import ir.windroida.app.net.str

/** Spinner while the first connection is made; when it fails it shows WHY and offers retry / change server / old web app. */
class WaitScreen(private val a: NativeActivity, text: String) : Screen() {
    override val view: View
    private val t: TextView
    private val btns = LinearLayout(a)
    init {
        val th = a.th
        val box = LinearLayout(a); box.orientation = LinearLayout.VERTICAL; box.gravity = Gravity.CENTER; box.setBackgroundColor(th.bg)
        box.setPadding(a.dp(24), 0, a.dp(24), 0)
        val logo = label(a, "W", 38f, 0xFFFFFFFF.toInt(), true); logo.gravity = Gravity.CENTER
        logo.background = rounded(th.accentFill, a.dpf(40f)); box.addView(logo, lp(a.dp(80), a.dp(80)))
        t = label(a, text, 15f, th.muted); t.gravity = Gravity.CENTER; t.setPadding(0, a.dp(18), 0, a.dp(12))
        box.addView(t)
        box.addView(ProgressBar(a), lp(a.dp(32), a.dp(32)))
        btns.orientation = LinearLayout.VERTICAL; btns.visibility = View.GONE; btns.setPadding(0, a.dp(18), 0, 0)
        btns.addView(primaryButton(a, th, "تلاش دوباره") { a.api?.reconnectNow() }, lp(MATCH, WRAP))
        btns.addView(textButton(a, th, "تأیید دوباره‌ی گواهی سرور (اگه گواهی عوض شده)") { a.repin() }, lp(MATCH, WRAP))
        btns.addView(textButton(a, th, "تغییر آدرس سرور") { a.replaceAll(SetupScreen(a)) }, lp(MATCH, WRAP))
        btns.addView(textButton(a, th, "باز کردن نسخه وب قدیمی") { a.openWeb() }, lp(MATCH, WRAP))
        box.addView(btns, lp(MATCH, WRAP))
        view = box
    }
    /** the connection attempt failed: [why] is the technical reason (shown so it can be reported) */
    fun setError(why: String) {
        t.text = "وصل نشد به سرور\n\n" + why
        t.textDirection = View.TEXT_DIRECTION_LTR
        btns.visibility = View.VISIBLE
    }
}

/** Ask for the server address (first launch, or "change server"). */
class SetupScreen(private val a: NativeActivity, private val error: String = "") : Screen() {
    override val view: View
    init {
        val th = a.th
        val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL; col.gravity = Gravity.CENTER_HORIZONTAL
        col.setPadding(a.dp(28), a.dp(70), a.dp(28), a.dp(28))
        val logo = label(a, "W", 38f, 0xFFFFFFFF.toInt(), true); logo.gravity = Gravity.CENTER
        logo.background = rounded(th.accentFill, a.dpf(40f)); col.addView(logo, lp(a.dp(80), a.dp(80)))
        val h = label(a, "Windroida", 24f, th.text, true); h.gravity = Gravity.CENTER; h.setPadding(0, a.dp(16), 0, a.dp(4)); col.addView(h)
        val s = label(a, "آدرس سرور رو بنویس", 14f, th.muted); s.gravity = Gravity.CENTER; s.setPadding(0, 0, 0, a.dp(22)); col.addView(s)
        val et = EditText(a).styled(th, "https://your-server:8081")
        et.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        et.setText(Prefs.server(a).ifEmpty { "https://" })
        et.background = rounded(th.field, a.dpf(10f)); et.setPadding(a.dp(14), a.dp(12), a.dp(14), a.dp(12))
        et.layoutDirection = View.LAYOUT_DIRECTION_LTR; et.textDirection = View.TEXT_DIRECTION_LTR;
        col.addView(et, lp(MATCH, WRAP))
        val err = label(a, error, 13f, th.danger); err.setPadding(0, a.dp(8), 0, 0); err.visibility = if (error.isEmpty()) View.GONE else View.VISIBLE
        col.addView(err)
        val go = primaryButton(a, th, "اتصال") {
            val v = et.text.toString().trim().trimEnd('/')
            val cfg = ServerCfg.parse(v, "")
            if (cfg == null) { err.text = "آدرس باید با https:// یا http:// شروع بشه"; err.visibility = View.VISIBLE }
            else {
                if (v != Prefs.server(a)) { Prefs.setPin(a, ""); Prefs.setToken(a, "") }
                Prefs.setServer(a, v)
                val pin = Prefs.pin(a)
                if (cfg.tls && pin.isEmpty()) a.confirmCertificate(cfg) else a.startNet(ServerCfg(cfg.host, cfg.port, cfg.tls, pin))
            }
        }
        val lpGo = lp(MATCH, WRAP); lpGo.topMargin = a.dp(16); col.addView(go, lpGo)
        val web = textButton(a, th, "باز کردن نسخه وب") { a.openWeb() }
        col.addView(web, lp(WRAP, WRAP))
        val sv = ScrollView(a); sv.background = th.screenBg(); sv.isFillViewport = true; sv.addView(col)
        view = sv
    }
}

/** Login / register (+ password reset through the security question). */
class AuthScreen(private val a: NativeActivity, private val note: String = "") : Screen() {
    override val view: View
    private var registerMode = false
    private val col = LinearLayout(a)
    private val th = a.th
    private val questions = listOf("یه کلمه یا جمله مخفی که فقط خودم می‌دونم", "اسم اولین کتابی که یادمه و خوندمش؟", "اسم کوچه یا جایی که برای من خاطره خاصی داره؟", "یه عبارت شخصی که هیچ‌وقت جایی نگفتم؟")
    private var qIndex = 0
    private var err: TextView? = null
    private var busy = false

    init {
        col.orientation = LinearLayout.VERTICAL; col.gravity = Gravity.CENTER_HORIZONTAL
        col.setPadding(a.dp(28), a.dp(56), a.dp(28), a.dp(28))
        draw()
        val sv = ScrollView(a); sv.background = th.screenBg(); sv.isFillViewport = true; sv.addView(col)
        view = sv
    }

    private fun field(hint: String, password: Boolean = false, ltr: Boolean = false): EditText {
        val et = EditText(a).styled(th, hint)
        et.background = rounded(th.field, a.dpf(10f)); et.setPadding(a.dp(14), a.dp(12), a.dp(14), a.dp(12))
        if (ltr) { et.layoutDirection = View.LAYOUT_DIRECTION_LTR; et.textDirection = View.TEXT_DIRECTION_LTR; }
        et.setSingleLine(true)
        // inputType AFTER setSingleLine: setSingleLine resets the transformation method and would show the password in clear text
        et.inputType = if (password) InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD else InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        if (password) et.transformationMethod = android.text.method.PasswordTransformationMethod.getInstance()
        val p = lp(MATCH, WRAP); p.topMargin = a.dp(10); col.addView(et, p)
        return et
    }

    private fun draw() {
        col.removeAllViews()
        val logo = label(a, "W", 38f, 0xFFFFFFFF.toInt(), true); logo.gravity = Gravity.CENTER
        logo.background = rounded(th.accentFill, a.dpf(40f)); col.addView(logo, lp(a.dp(80), a.dp(80)))
        val h = label(a, if (registerMode) "ساخت حساب" else "ورود به Windroida", 22f, th.text, true); h.gravity = Gravity.CENTER; h.setPadding(0, a.dp(14), 0, a.dp(6)); col.addView(h)
        if (note.isNotEmpty()) { val n = label(a, note, 13f, th.danger); n.gravity = Gravity.CENTER; col.addView(n) }
        val user = field("نام کاربری (انگلیسی)", ltr = true)
        val display = if (registerMode) field("نام نمایشی") else null
        val pass = field("رمز عبور", password = true, ltr = true)
        var answer: EditText? = null
        if (registerMode) {
            val q = label(a, questions[qIndex], 13f, th.accent); q.setPadding(a.dp(4), a.dp(14), a.dp(4), a.dp(2))
            q.isClickable = true
            q.setOnClickListener { qIndex = (qIndex + 1) % questions.size; q.text = questions[qIndex] }
            col.addView(q)
            val hint = label(a, "(برای عوض کردن سوال بزن؛ برای بازیابی رمز لازمه)", 11f, th.muted); hint.setPadding(a.dp(4), 0, 0, 0); col.addView(hint)
            answer = field("جواب سوال امنیتی")
        }
        val e = label(a, "", 13f, th.danger); e.setPadding(a.dp(4), a.dp(8), a.dp(4), 0); col.addView(e); err = e
        val go = primaryButton(a, th, if (registerMode) "ثبت‌نام" else "ورود") {
            if (busy) return@primaryButton
            val u = user.text.toString().trim(); val p = pass.text.toString()
            if (u.isEmpty() || p.isEmpty()) { e.text = "نام کاربری و رمز رو بنویس"; return@primaryButton }
            val api = a.api ?: run { e.text = "هنوز به سرور وصل نیستی"; return@primaryButton }
            busy = true; e.text = ""
            val done: (Boolean, String) -> Unit = { ok, msg -> a.main.post { busy = false; if (!ok) e.text = msg } }
            val device = "Android " + android.os.Build.MODEL
            if (registerMode) api.register(u, p, display!!.text.toString().trim().ifEmpty { u }, questions[qIndex], answer!!.text.toString(), device, done)
            else api.login(u, p, device, done)
        }
        val gp = lp(MATCH, WRAP); gp.topMargin = a.dp(14); col.addView(go, gp)
        col.addView(textButton(a, th, if (registerMode) "حساب دارم؛ ورود" else "حساب ندارم؛ ثبت‌نام") { registerMode = !registerMode; draw() }, lp(WRAP, WRAP))
        if (!registerMode) col.addView(textButton(a, th, "رمزم رو فراموش کردم", th.muted) { resetDialog(user.text.toString().trim()) }, lp(WRAP, WRAP))
        col.addView(textButton(a, th, "تغییر آدرس سرور", th.muted) { a.replaceAll(SetupScreen(a)) }, lp(WRAP, WRAP))
    }

    private fun resetDialog(prefill: String) {
        val box = LinearLayout(a); box.orientation = LinearLayout.VERTICAL; box.setPadding(a.dp(20), a.dp(8), a.dp(20), 0)
        val u = EditText(a); u.hint = "نام کاربری"; u.setText(prefill); u.setSingleLine(true); u.textDirection = View.TEXT_DIRECTION_LTR
        box.addView(u)
        val qv = TextView(a); qv.setPadding(0, a.dp(12), 0, 0); box.addView(qv)
        val ans = EditText(a); ans.hint = "جواب سوال امنیتی"; ans.setSingleLine(true); ans.visibility = View.GONE; box.addView(ans)
        val np = EditText(a); np.hint = "رمز جدید"; np.setSingleLine(true); np.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD; np.transformationMethod = android.text.method.PasswordTransformationMethod.getInstance(); np.visibility = View.GONE; box.addView(np)
        var asked = false
        val dlg = AlertDialog.Builder(a).setTitle("بازیابی رمز").setView(box).setPositiveButton("ادامه", null).setNegativeButton("بستن", null).create()
        dlg.show()
        dlg.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
            if (!asked) {
                a.rpc("reset_question", mapOf("username" to u.text.toString().trim())) { ok, r ->
                    if (ok) { asked = true; qv.text = r.str("question"); ans.visibility = View.VISIBLE; np.visibility = View.VISIBLE; dlg.getButton(AlertDialog.BUTTON_POSITIVE).text = "تغییر رمز" }
                    else a.toast(r.str("error", "خطا"))
                }
            } else {
                a.rpc("reset_password", mapOf("username" to u.text.toString().trim(), "answer" to ans.text.toString(), "new_password" to np.text.toString())) { ok, r ->
                    if (ok) { a.toast("رمز عوض شد؛ حالا وارد شو"); dlg.dismiss() } else a.toast(r.str("error", "خطا"))
                }
            }
        }
    }
}
