package ir.windroida.app.ui

import ir.windroida.app.net.Model
import ir.windroida.app.net.bool
import ir.windroida.app.net.lng
import ir.windroida.app.net.map
import ir.windroida.app.net.str

/** Text helpers shared by the chat list and the chat screen (previews, names, subtitles). */
object ChatText {
    fun short(t: String, n: Int): String { val s = t.replace(Regex("\\s+"), " ").trim(); return if (s.length > n) s.substring(0, n - 1) + "…" else s }

    fun fileKindIcon(k: String): String = when (k) { "image" -> "🖼 "; "video" -> "🎬 "; "audio" -> "🎵 "; else -> "📎 " }

    /** One line for the chat list / reply quote / pin bar. */
    fun messageLine(m: Map<String, Any?>): String {
        if (m.str("kind") == "system") return short(m.str("body"), 60)
        if (m.bool("deleted")) return "پیام حذف شده"
        val body = m.str("body")
        Stickers.label(body)?.let { return it }
        val f = m.map("file")
        if (f != null) {
            if (f.bool("voice")) return "🎤 پیام صوتی " + Fmt.duration(f.lng("dur"))
            return fileKindIcon(f.str("kind")) + body.ifEmpty { f.str("name") }
        }
        if (m.map("game") != null) return "♟ بازی شطرنج"
        return body
    }

    fun preview(c: Map<String, Any?>, myId: Long): String {
        val m = c.map("last") ?: return "هنوز پیامی نیست"
        if (m.str("kind") == "system" || m.bool("deleted")) return if (m.bool("deleted")) "" else messageLine(m)
        val t = messageLine(m)
        val p = if (m.lng("sender_id") == myId) "تو: " else if (c.str("kind") == "group" && m.str("sender_name").isNotEmpty()) short(m.str("sender_name"), 12) + ": " else ""
        return short(p + t, 60)
    }

    fun subtitle(c: Map<String, Any?>, model: Model): Pair<String, Boolean> {
        val id = c.lng("id")
        val ty = model.typingIn(id)
        if (ty != null) return Pair(if (ty == "voice") "در حال ضبط پیام صوتی…" else "در حال نوشتن…", true)
        if (c.bool("saved")) return Pair("فقط خودت می‌بینی", false)
        if (c.bool("channel")) return Pair(Fmt.digits(c.lng("member_count").toString()) + " مشترک", false)
        if (c.str("kind") == "group") {
            val online = c.lng("online_count")
            return Pair(Fmt.digits(c.lng("member_count").toString()) + " عضو" + (if (online > 0L) "، " + Fmt.digits(online.toString()) + " آنلاین" else ""), false)
        }
        val p = c.map("peer") ?: return Pair("", false)
        if (p.bool("online")) return Pair("آنلاین", true)
        if (p.bool("seen_hidden")) return Pair("آخرین بازدید: به‌تازگی", false)
        return Pair(Fmt.lastSeen(p.lng("last_seen")), false)
    }

    /** avatar info of a chat: kind ("u"/"c"), id, name, photo stamp, online */
    class Av(val kind: String, val id: Long, val name: String, val at: Long, val online: Boolean)

    fun avatarOf(c: Map<String, Any?>): Av {
        val p = c.map("peer")
        return if (p != null) Av("u", p.lng("id"), p.str("display_name"), p.lng("avatar_at"), p.bool("online"))
        else Av("c", c.lng("id"), c.str("title"), c.lng("avatar_at"), false)
    }
}
