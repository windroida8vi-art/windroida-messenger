package ir.windroida.app.ui

import android.app.AlertDialog
import android.content.Intent
import android.text.InputFilter
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import ir.windroida.app.NativeActivity
import ir.windroida.app.net.*

/** Group moderation and group / profile photo, same server ops as the web app. */
class GroupAdmin(private val a: NativeActivity, private val th: Theme) {
    private val SLOWS = listOf(0 to "خاموش", 10 to "۱۰ ثانیه", 30 to "۳۰ ثانیه", 60 to "۱ دقیقه", 300 to "۵ دقیقه", 900 to "۱۵ دقیقه", 3600 to "۱ ساعت")
    private val MUTES = listOf(3600 to "۱ ساعت", 86400 to "۱ روز", 604800 to "۱ هفته", -1 to "برای همیشه")

    private fun done(ok: Boolean, r: Map<String, Any?>, then: () -> Unit) { if (ok) then() else a.toast(r.str("error", "انجام نشد")) }

    /** menu for one member (only called when I am owner / admin and the member is not the owner nor me) */
    fun memberMenu(chatId: Long, u: Map<String, Any?>, imOwner: Boolean, changed: () -> Unit) {
        val id = u.lng("id"); val name = u.str("display_name")
        val items = ArrayList<Pair<String, () -> Unit>>()
        if (u.str("role") == "member") {
            if (u.lng("muted_until") > 0) items.add(Pair("برداشتن ساکت‌بودن") { a.rpc("mute_member", mapOf("chat_id" to chatId, "user_id" to id, "secs" to 0)) { ok, r -> done(ok, r, changed) } })
            else items.add(Pair("ساکت کردن…") { Dialogs.menu(a, null, null, MUTES.map { (s, t) -> Pair(t) { a.rpc("mute_member", mapOf("chat_id" to chatId, "user_id" to id, "secs" to s)) { ok, r -> done(ok, r, changed) } } }) })
        }
        if (imOwner) items.add(Pair(if (u.str("role") == "admin") "برداشتن ادمینی" else "ادمین کردن") {
            a.rpc("set_role", mapOf("chat_id" to chatId, "user_id" to id, "admin" to (u.str("role") != "admin"))) { ok, r -> done(ok, r, changed) }
        })
        items.add(Pair("حذف از گروه") { confirm("$name از گروه حذف بشه؟") { a.rpc("remove_member", mapOf("chat_id" to chatId, "user_id" to id)) { ok, r -> done(ok, r, changed) } } })
        items.add(Pair("مسدود کردن (بن)") { confirm("$name مسدود بشه؟ دیگه نمی‌تونه برگرده.") { a.rpc("ban_member", mapOf("chat_id" to chatId, "user_id" to id)) { ok, r -> done(ok, r, changed) } } })
        Dialogs.menu(a, null, null, items)
    }

    private fun confirm(msg: String, f: () -> Unit) {
        AlertDialog.Builder(a).setMessage(msg).setPositiveButton("باشه") { _, _ -> f() }.setNegativeButton("نه", null).show()
    }

    /** group settings: name, description, slow mode, banned list, invite link, photo */
    fun settings(chatId: Long, changed: () -> Unit) {
        val c = a.model.chats[chatId] ?: return
        val owner = c.str("my_role") == "owner"
        val col = LinearLayout(a); col.orientation = LinearLayout.VERTICAL; col.setPadding(a.dp(18), a.dp(16), a.dp(18), a.dp(10))
        col.addView(label(a, "مدیریت گروه", 18f, th.text, true).also { it.setPadding(0, 0, 0, a.dp(8)) })
        fun field(text: String, hint: String, max: Int, lines: Int): EditText = EditText(a).also {
            it.styled(th, hint); it.setText(text); it.filters = arrayOf(InputFilter.LengthFilter(max)); it.maxLines = lines
            it.background = rounded(th.field, a.dpf(10f)); it.setPadding(a.dp(12), a.dp(10), a.dp(12), a.dp(10))
        }
        val title = field(c.str("title"), "نام گروه", 40, 1); val desc = field(c.str("description"), "توضیحات", 200, 4)
        col.addView(title, lp(MATCH, WRAP)); col.addView(desc, lp(MATCH, WRAP).also { it.topMargin = a.dp(8) })
        var d: AlertDialog? = null
        col.addView(primaryButton(a, th, "ذخیره‌ی نام و توضیحات") {
            a.rpc("edit_group", mapOf("chat_id" to chatId, "title" to title.text.toString(), "description" to desc.text.toString())) { ok, r ->
                if (ok) { r.map("chat")?.let { n -> a.model.chats[chatId]?.putAll(n) }; a.toast("ذخیره شد"); changed() } else a.toast(r.str("error", "ذخیره نشد"))
            }
        }, lp(MATCH, WRAP).also { it.topMargin = a.dp(8) })
        col.addView(textButton(a, th, "عکس گروه…") { d?.dismiss(); pickPhoto("chat", chatId, changed) })
        if (!c.bool("channel")) {
            val slowNow = c.int("slow")
            col.addView(textButton(a, th, "حالت آهسته: " + (SLOWS.firstOrNull { it.first == slowNow }?.second ?: "$slowNow ثانیه")) {
                d?.dismiss()
                Dialogs.menu(a, null, null, SLOWS.map { (s, t) -> Pair(t) { a.rpc("set_slow", mapOf("chat_id" to chatId, "secs" to s)) { ok, r -> done(ok, r) { a.toast("حالت آهسته: $t"); a.refreshChats(); changed() } } } })
            })
        }
        col.addView(textButton(a, th, "مسدودشده‌ها") { d?.dismiss(); bans(chatId) })
        if (owner) col.addView(textButton(a, th, "لینک دعوت") { d?.dismiss(); invite(chatId) })
        val sv = ScrollView(a); sv.addView(col)
        d = Dialogs.sheet(a, sv)
    }

    private fun bans(chatId: Long) {
        a.rpc("bans", mapOf("chat_id" to chatId)) { ok, r ->
            if (!ok) { a.toast(r.str("error", "در دسترس نیست")); return@rpc }
            val list = r.list("bans")
            if (list.isEmpty()) { a.toast("کسی مسدود نشده"); return@rpc }
            Dialogs.menu(a, null, null, list.map { u -> Pair("رفع مسدودی: " + u.str("display_name")) {
                a.rpc("unban_member", mapOf("chat_id" to chatId, "user_id" to u.lng("id"))) { ok2, r2 -> done(ok2, r2) { a.toast("رفع شد") } } } })
        }
    }

    private fun invite(chatId: Long) {
        a.rpc("invite_link", mapOf("chat_id" to chatId)) { ok, r ->
            if (!ok) { a.toast(r.str("error", "در دسترس نیست")); return@rpc }
            val cfg = a.api?.cfg
            val link = (cfg?.base ?: "") + "/#join=" + r.str("invite")
            val t = TextView(a); t.text = link; t.setTextColor(th.text); t.textSize = 14f; t.setTextIsSelectable(true); t.textDirection = View.TEXT_DIRECTION_LTR; t.setPadding(a.dp(20), a.dp(16), a.dp(20), a.dp(8))
            AlertDialog.Builder(a).setTitle("لینک دعوت").setView(t)
                .setPositiveButton("کپی") { _, _ -> (a.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager).setPrimaryClip(android.content.ClipData.newPlainText("link", link)); a.toast("کپی شد") }
                .setNeutralButton("لینک جدید") { _, _ -> a.rpc("invite_link", mapOf("chat_id" to chatId, "reset" to true)) { ok2, r2 -> done(ok2, r2) { invite(chatId) } } }
                .setNegativeButton("بستن", null).show()
        }
    }

    /** change my profile photo (target "me") or the group's (target "chat") */
    fun pickPhoto(target: String, chatId: Long, changed: () -> Unit) {
        val i = Intent(Intent.ACTION_GET_CONTENT); i.addCategory(Intent.CATEGORY_OPENABLE); i.type = "image/*"
        a.pickResult(Intent.createChooser(i, "انتخاب عکس")) { res, data ->
            val u = data?.data
            if (res != android.app.Activity.RESULT_OK || u == null) return@pickResult
            val h = a.http ?: return@pickResult a.toast("به سرور وصل نیستی")
            a.toast("در حال ارسال…")
            Thread {
                var err: String? = null
                try {
                    val bytes = a.contentResolver.openInputStream(u)?.use { it.readBytes() } ?: throw java.io.IOException("خوندن عکس ممکن نشد")
                    val bmp = Img.decode(bytes, 1024) ?: throw java.io.IOException("این فایل عکس نیست")
                    val out = java.io.ByteArrayOutputStream(); bmp.compress(android.graphics.Bitmap.CompressFormat.JPEG, 88, out)
                    val jpg = out.toByteArray()
                    val q = "/avatar?k=" + java.net.URLEncoder.encode(a.mediaKey, "UTF-8") + "&target=" + target + (if (target == "chat") "&chat_id=$chatId" else "")
                    h.upload(q, jpg.inputStream(), jpg.size.toLong())
                } catch (e: Exception) { err = e.message ?: "ارسال نشد" }
                a.main.post {
                    if (err != null) a.toast(err) else {
                        a.toast("عکس ذخیره شد"); a.img?.forget(if (target == "chat") "/avatar/c$chatId" else "/avatar/u" + a.model.myId)
                        if (target == "me") a.rpc("me") { ok, r -> if (ok) r.map("me")?.let { a.model.me = LinkedHashMap(it) } ; changed() }
                        a.refreshChats(); changed()
                    }
                }
            }.start()
        }
    }

    fun removePhoto(target: String, chatId: Long, changed: () -> Unit) {
        a.rpc("remove_avatar", if (target == "chat") mapOf("chat_id" to chatId) else emptyMap()) { ok, r -> done(ok, r) { a.refreshChats(); changed() } }
    }
}
