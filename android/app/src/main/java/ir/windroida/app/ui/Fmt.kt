package ir.windroida.app.ui

import android.icu.text.SimpleDateFormat
import android.icu.util.ULocale
import java.util.Date

/** Persian dates/times/sizes (Jalali calendar via ICU; falls back to plain numbers if ICU is missing). */
object Fmt {
    fun digits(s: String): String {
        val sb = StringBuilder(s.length)
        for (c in s) sb.append(if (c in '0'..'9') ('۰' + (c - '0')) else c)
        return sb.toString()
    }

    /** Persian/Arabic digits -> 0-9 (for parsing what the user typed) */
    fun latin(s: String): String {
        val sb = StringBuilder(s.length)
        for (c in s) sb.append(when (c) { in '۰'..'۹' -> '0' + (c - '۰'); in '٠'..'٩' -> '0' + (c - '٠'); else -> c })
        return sb.toString()
    }

    private fun fmt(pattern: String, ts: Long): String = try {
        val f = SimpleDateFormat(pattern, ULocale("fa_IR@calendar=persian"))
        f.format(Date(ts * 1000))
    } catch (e: Throwable) {
        digits(java.text.SimpleDateFormat("yyyy/MM/dd HH:mm", java.util.Locale.US).format(Date(ts * 1000)))
    }

    fun time(ts: Long): String = digits(java.text.SimpleDateFormat("HH:mm", java.util.Locale.US).format(Date(ts * 1000)))

    private fun dayStart(ts: Long): Long {
        val c = java.util.Calendar.getInstance(); c.timeInMillis = ts * 1000
        c.set(java.util.Calendar.HOUR_OF_DAY, 0); c.set(java.util.Calendar.MINUTE, 0); c.set(java.util.Calendar.SECOND, 0); c.set(java.util.Calendar.MILLISECOND, 0)
        return c.timeInMillis / 1000
    }

    fun daysAgo(ts: Long, now: Long = System.currentTimeMillis() / 1000): Int = ((dayStart(now) - dayStart(ts)) / 86400).toInt()

    fun dayLabel(ts: Long, now: Long = System.currentTimeMillis() / 1000): String {
        val d = daysAgo(ts, now)
        return when {
            d == 0 -> "امروز"
            d == 1 -> "دیروز"
            d in 2..6 -> fmt("EEEE", ts)
            else -> fmt("d MMMM", ts)
        }
    }

    /** Time column of the chat list: today -> 14:05, this week -> weekday, older -> 5 آبان. */
    fun listTime(ts: Long, now: Long = System.currentTimeMillis() / 1000): String {
        val d = daysAgo(ts, now)
        return when {
            d <= 0 -> time(ts)
            d in 1..6 -> fmt("EEEE", ts)
            else -> fmt("d MMM", ts)
        }
    }

    fun lastSeen(ts: Long, now: Long = System.currentTimeMillis() / 1000): String {
        if (ts <= 0) return "آخرین بازدید: مدت‌ها پیش"
        val d = daysAgo(ts, now)
        return when {
            now - ts < 60 -> "آخرین بازدید: همین الان"
            d == 0 -> "آخرین بازدید: امروز " + time(ts)
            d == 1 -> "آخرین بازدید: دیروز " + time(ts)
            else -> "آخرین بازدید: " + fmt("d MMMM", ts)
        }
    }

    fun size(b: Long): String = when {
        b < 1024 -> digits("$b B")
        b < 1048576 -> digits("%.0f KB".format(b / 1024.0))
        b < 1073741824L -> digits("%.1f MB".format(b / 1048576.0))
        else -> digits("%.2f GB".format(b / 1073741824.0))
    }

    fun duration(sec: Long): String = digits("%d:%02d".format(sec / 60, sec % 60))
}
