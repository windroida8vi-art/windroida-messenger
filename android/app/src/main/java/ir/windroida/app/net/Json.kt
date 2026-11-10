package ir.windroida.app.net

/** Tiny JSON reader/writer with no Android dependency (so the network core can be tested on a plain JVM).
 *  Objects -> Map<String, Any?>, arrays -> List<Any?>, integers -> Long, other numbers -> Double. */
object Json {
    class ParseError(msg: String) : Exception(msg)

    fun parse(s: String): Any? {
        val p = Parser(s)
        p.ws()
        val v = p.value()
        p.ws()
        if (p.i != s.length) throw ParseError("trailing data")
        return v
    }

    @Suppress("UNCHECKED_CAST")
    fun obj(s: String): Map<String, Any?>? = try { parse(s) as? Map<String, Any?> } catch (e: Exception) { null }

    private class Parser(val s: String) {
        var i = 0
        fun ws() { while (i < s.length && (s[i] == ' ' || s[i] == '\n' || s[i] == '\r' || s[i] == '\t')) i++ }
        fun value(depth: Int = 0): Any? {
            if (depth > 64) throw ParseError("too deep")
            if (i >= s.length) throw ParseError("eof")
            return when (val c = s[i]) {
                '{' -> {
                    i++
                    val m = LinkedHashMap<String, Any?>()
                    ws()
                    if (i < s.length && s[i] == '}') { i++; return m }
                    while (true) {
                        ws()
                        if (i >= s.length || s[i] != '"') throw ParseError("key expected")
                        val k = str()
                        ws()
                        if (i >= s.length || s[i] != ':') throw ParseError(": expected")
                        i++
                        ws()
                        m[k] = value(depth + 1)
                        ws()
                        if (i >= s.length) throw ParseError("eof")
                        if (s[i] == ',') { i++; continue }
                        if (s[i] == '}') { i++; break }
                        throw ParseError("bad object")
                    }
                    m
                }
                '[' -> {
                    i++
                    val l = ArrayList<Any?>()
                    ws()
                    if (i < s.length && s[i] == ']') { i++; return l }
                    while (true) {
                        ws()
                        l.add(value(depth + 1))
                        ws()
                        if (i >= s.length) throw ParseError("eof")
                        if (s[i] == ',') { i++; continue }
                        if (s[i] == ']') { i++; break }
                        throw ParseError("bad array")
                    }
                    l
                }
                '"' -> str()
                't' -> lit("true", true)
                'f' -> lit("false", false)
                'n' -> lit("null", null)
                else -> if (c == '-' || c in '0'..'9') num() else throw ParseError("unexpected '$c'")
            }
        }
        fun lit(w: String, v: Any?): Any? {
            if (!s.startsWith(w, i)) throw ParseError("bad literal")
            i += w.length
            return v
        }
        fun num(): Any {
            val st = i
            if (s[i] == '-') i++
            while (i < s.length && s[i] in '0'..'9') i++
            var isD = false
            if (i < s.length && s[i] == '.') { isD = true; i++; while (i < s.length && s[i] in '0'..'9') i++ }
            if (i < s.length && (s[i] == 'e' || s[i] == 'E')) {
                isD = true; i++
                if (i < s.length && (s[i] == '+' || s[i] == '-')) i++
                while (i < s.length && s[i] in '0'..'9') i++
            }
            val t = s.substring(st, i)
            if (t.isEmpty() || t == "-") throw ParseError("bad number")
            return if (!isD) (t.toLongOrNull() ?: t.toDouble()) else t.toDouble()
        }
        fun str(): String {
            i++ // opening quote
            val sb = StringBuilder()
            while (true) {
                if (i >= s.length) throw ParseError("unterminated string")
                val c = s[i++]
                when (c) {
                    '"' -> return sb.toString()
                    '\\' -> {
                        if (i >= s.length) throw ParseError("bad escape")
                        when (val e = s[i++]) {
                            '"' -> sb.append('"'); '\\' -> sb.append('\\'); '/' -> sb.append('/')
                            'b' -> sb.append('\b'); 'f' -> sb.append('\u000c'); 'n' -> sb.append('\n')
                            'r' -> sb.append('\r'); 't' -> sb.append('\t')
                            'u' -> {
                                if (i + 4 > s.length) throw ParseError("bad \\u")
                                val h = s.substring(i, i + 4).toIntOrNull(16) ?: throw ParseError("bad \\u")
                                sb.append(h.toChar()); i += 4
                            }
                            else -> throw ParseError("bad escape \\$e")
                        }
                    }
                    else -> sb.append(c)
                }
            }
        }
    }

    fun stringify(v: Any?): String { val sb = StringBuilder(); write(sb, v); return sb.toString() }

    private fun write(sb: StringBuilder, v: Any?) {
        when (v) {
            null -> sb.append("null")
            is String -> quote(sb, v)
            is Boolean -> sb.append(if (v) "true" else "false")
            is Int, is Long, is Short, is Byte -> sb.append(v.toString())
            is Double -> sb.append(if (v.isNaN() || v.isInfinite()) "null" else (if (v == Math.floor(v) && Math.abs(v) < 1e15) v.toLong().toString() else v.toString()))
            is Float -> write(sb, v.toDouble())
            is Map<*, *> -> {
                sb.append('{')
                var first = true
                for ((k, x) in v) {
                    if (!first) sb.append(',')
                    first = false
                    quote(sb, k.toString()); sb.append(':'); write(sb, x)
                }
                sb.append('}')
            }
            is Iterable<*> -> {
                sb.append('[')
                var first = true
                for (x in v) { if (!first) sb.append(','); first = false; write(sb, x) }
                sb.append(']')
            }
            else -> quote(sb, v.toString())
        }
    }

    private fun quote(sb: StringBuilder, s: String) {
        sb.append('"')
        for (c in s) {
            when {
                c == '"' -> sb.append("\\\"")
                c == '\\' -> sb.append("\\\\")
                c == '\n' -> sb.append("\\n")
                c == '\r' -> sb.append("\\r")
                c == '\t' -> sb.append("\\t")
                c < ' ' || c == ' ' || c == ' ' -> sb.append("\\u%04x".format(c.code))
                else -> sb.append(c)
            }
        }
        sb.append('"')
    }
}

// ---- small typed readers, so the UI code never needs a cast ----
@Suppress("UNCHECKED_CAST")
fun Map<String, Any?>.map(k: String): Map<String, Any?>? = this[k] as? Map<String, Any?>
@Suppress("UNCHECKED_CAST")
fun Map<String, Any?>.list(k: String): List<Map<String, Any?>> = (this[k] as? List<Any?>)?.mapNotNull { it as? Map<String, Any?> } ?: emptyList()
fun Map<String, Any?>.str(k: String, d: String = ""): String = (this[k] as? String) ?: d
fun Map<String, Any?>.lng(k: String, d: Long = 0L): Long = when (val v = this[k]) { is Long -> v; is Int -> v.toLong(); is Double -> v.toLong(); else -> d }
fun Map<String, Any?>.int(k: String, d: Int = 0): Int = lng(k, d.toLong()).toInt()
fun Map<String, Any?>.bool(k: String, d: Boolean = false): Boolean = when (val v = this[k]) { is Boolean -> v; is Long -> v != 0L; else -> d }
