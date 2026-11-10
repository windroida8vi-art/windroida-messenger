package ir.windroida.app.ui

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.OpenableColumns
import ir.windroida.app.NativeActivity
import ir.windroida.app.net.Api
import ir.windroida.app.net.map
import ir.windroida.app.net.str

/** "Share to Windroida" from any other app (gallery, files, browser...): choose the chats, then text and files are sent to each of them. */
object Share {
    private class Item(val uri: Uri, val name: String, val size: Long)

    fun handle(a: NativeActivity, i: Intent?) {
        if (i == null) return
        if (i.action != Intent.ACTION_SEND && i.action != Intent.ACTION_SEND_MULTIPLE) return
        val uris = ArrayList<Uri>()
        try {
            if (i.action == Intent.ACTION_SEND) {
                (if (Build.VERSION.SDK_INT >= 33) i.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java) else @Suppress("DEPRECATION") i.getParcelableExtra<Uri>(Intent.EXTRA_STREAM))?.let { uris.add(it) }
            } else {
                (if (Build.VERSION.SDK_INT >= 33) i.getParcelableArrayListExtra(Intent.EXTRA_STREAM, Uri::class.java) else @Suppress("DEPRECATION") i.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM))?.let { uris.addAll(it) }
            }
        } catch (_: Exception) {}
        val text = (i.getStringExtra(Intent.EXTRA_TEXT) ?: "").trim()
        if (uris.isEmpty() && text.isEmpty()) return
        if (uris.size > 10) uris.subList(10, uris.size).clear()
        val items = uris.mapNotNull { u ->
            try {
                var name = "file"; var size = -1L
                a.contentResolver.query(u, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { c ->
                    if (c.moveToFirst()) { name = c.getString(0) ?: name; size = if (c.isNull(1)) -1L else c.getLong(1) }
                }
                name = name.replace(Regex("[\\\\/:*?\"<>|\\u0000-\\u001f]"), "_").take(120).ifEmpty { "file" }
                Item(u, name, size)
            } catch (_: Exception) { null }
        }
        // wait until the connection and the chat list are ready (cold start), then ask where to send
        var tries = 0
        fun ready() {
            if (a.api?.state == Api.ONLINE && a.model.chatList().isNotEmpty()) { ask(a, items, text); return }
            if (++tries > 60) { a.toast("به سرور وصل نشد؛ دوباره شیر کن"); return }
            a.main.postDelayed({ ready() }, 500)
        }
        ready()
    }

    private fun ask(a: NativeActivity, items: List<Item>, text: String) {
        val what = if (items.isEmpty()) "متن" else if (items.size == 1) items[0].name else "${items.size} فایل"
        Dialogs.pickChats(a, "ارسال «$what» به…") { ids ->
            if (text.isNotEmpty()) for (id in ids) a.rpc("send", mapOf("chat_id" to id, "text" to text)) { ok, r -> if (!ok) a.toast(r.str("error", "ارسال نشد")) }
            if (items.isNotEmpty()) sendFiles(a, items, ids) else a.toast("ارسال شد")
            if (ids.size == 1) a.openChat(ids[0])
        }
    }

    private fun sendFiles(a: NativeActivity, items: List<Item>, ids: List<Long>) {
        val h = a.http ?: run { a.toast("به سرور وصل نیستی"); return }
        val max = a.api?.maxUpload ?: (5L shl 20)
        val total = items.filter { it.size <= max }.sumOf { maxOf(it.size, 1L) } * ids.size
        var base = 0L; var n = 0; val count = items.size * ids.size
        val stopFlag = java.util.concurrent.atomic.AtomicBoolean(false)
        a.hud("در حال ارسال…", 0f) { stopFlag.set(true) }
        Thread {
            var sent = 0; var err: String? = null
            for (it in items) {
                if (stopFlag.get()) break
                if (it.size > max) { err = "«${it.name}» از سقف حجم سرور بزرگ‌تره"; continue }
                for (id in ids) {
                    n++
                    try {
                        val ins = a.contentResolver.openInputStream(it.uri) ?: throw java.io.IOException("cannot open")
                        val len = if (it.size >= 0) it.size else ins.available().toLong()
                        val q = h.q("k" to a.mediaKey, "chat_id" to id, "name" to it.name)
                        val idx = n
                        val res = ins.use { s -> h.upload("/upload?$q", s, len, { done, _ ->
                            val f = if (total > 0) (base + done).toFloat() / total else -1f
                            a.hud(ChatText.short(it.name, 22) + (if (count > 1) Fmt.digits("  ($idx از $count)") else "") + "\n" + Fmt.size(base + done) + " / " + Fmt.size(total), f)
                        }, { stopFlag.get() }) }
                        res.map("message")?.let { m -> a.main.post { a.model.ingest(m) } }
                        sent++
                    } catch (e: Exception) { err = if (stopFlag.get()) "ارسال لغو شد" else (e.message ?: "ارسال ناموفق بود") }
                    if (stopFlag.get()) break
                    base += maxOf(it.size, 1L)
                }
            }
            a.hudHide()
            a.main.post { a.toast(if (err != null && sent == 0) err!! else if (err != null) "بعضی‌ها ارسال نشدن: $err" else "ارسال شد") }
        }.start()
    }
}
