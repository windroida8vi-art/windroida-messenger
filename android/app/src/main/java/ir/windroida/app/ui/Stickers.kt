package ir.windroida.app.ui

/** Sticker messages travel as the text ":st_<id>:" (the web app draws them as animated SVG). The native app shows the matching emoji, large. */
object Stickers {
    val EMOJI = mapOf(
        "laugh" to "😂",
        "rofl" to "🤣",
        "smile" to "😊",
        "grin" to "😁",
        "love" to "😍",
        "hearts" to "🥰",
        "kiss" to "😘",
        "cry" to "😭",
        "sad" to "😢",
        "plead" to "🥺",
        "cool" to "😎",
        "think" to "🤔",
        "sweat" to "😅",
        "angry" to "😡",
        "roll" to "🙄",
        "sleep" to "😴",
        "scream" to "😱",
        "wink" to "😉",
        "party" to "🥳",
        "heart" to "❤️",
        "broken" to "💔",
        "fire" to "🔥",
        "thumbs" to "👍",
        "pray" to "🙏",
        "clap" to "👏",
        "ghost" to "👻",
    )
    val NAME = mapOf(
        "laugh" to "خنده",
        "rofl" to "غش‌وریسه",
        "smile" to "لبخند",
        "grin" to "دندون‌نما",
        "love" to "عاشق",
        "hearts" to "دوستت دارم",
        "kiss" to "بوس",
        "cry" to "گریه",
        "sad" to "ناراحت",
        "plead" to "ناز و گدایی",
        "cool" to "باحال",
        "think" to "فکر",
        "sweat" to "عرق‌ریزون",
        "angry" to "عصبانی",
        "roll" to "چشم‌غره",
        "sleep" to "خواب",
        "scream" to "جیغ",
        "wink" to "چشمک",
        "party" to "جشن",
        "heart" to "قلب",
        "broken" to "دل‌شکسته",
        "fire" to "آتش",
        "thumbs" to "عالی",
        "pray" to "دعا",
        "clap" to "آفرین",
        "ghost" to "روح",
    )
    private val RE = Regex("^:st_([a-z]{3,10}):$")
    /** the sticker id if [text] is exactly one sticker message and we know it */
    fun parse(text: String): String? { val m = RE.matchEntire(text.trim()) ?: return null; return if (EMOJI.containsKey(m.groupValues[1])) m.groupValues[1] else null }
    fun label(text: String): String? { val id = parse(text) ?: return null; return (EMOJI[id] ?: "") + " استیکر " + (NAME[id] ?: "") }
}
