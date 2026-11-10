"""الگوریتم‌ها: نزدیکی کاربرها (affinity) و رتبه‌بندی پست‌ها."""
import math
import random
import time

from .db import q


_cache = {}  # {user_id: (زمان، امتیازها)}؛ ۴۵ ثانیه نگه داشته می‌شود تا هر درخواست کوئری سنگین نزند


def invalidate(uid):
    _cache.pop(uid, None)


def affinity(me_):
    hit = _cache.get(me_)
    if hit and time.time() - hit[0] < 45:
        return hit[1]
    sc = _affinity(me_)
    if len(_cache) > 2000:
        _cache.clear()
    _cache[me_] = (time.time(), sc)
    return sc


def _affinity(me_):
    """امتیاز نزدیکی من با هر کاربر: پیام‌های اخیر (با کاهش نمایی)، فالو/فالوبک، لایک و نظر روی پست‌هایش."""
    now = time.time()
    sc = {}

    def add(k, v):
        sc[k] = sc.get(k, 0) + v
    for r in q('select sender,receiver,created from messages where sender=? or receiver=? order by id desc limit 600', me_, me_):
        peer = r['receiver'] if r['sender'] == me_ else r['sender']
        add(peer, 4 * math.exp(-((now - r['created']) / 86400) / 7))
    for r in q('select p.user_id u, count(*) c from likes l join posts p on p.id=l.post_id where l.user_id=? group by p.user_id', me_):
        add(r['u'], 0.6 * min(r['c'], 10))
    for r in q('select p.user_id u, count(*) c from comments c join posts p on p.id=c.post_id where c.user_id=? group by p.user_id', me_):
        add(r['u'], 1.0 * min(r['c'], 10))
    for r in q('select followee from follows where follower=?', me_):
        add(r['followee'], 2)
    for r in q('select follower from follows where followee=?', me_):
        add(r['follower'], 1.5)
    sc.pop(me_, None)
    return sc


CAND = ("select p.*, (select count(*) from likes where post_id=p.id) lk, (select count(*) from comments where post_id=p.id) cm, "
        "(select count(*) from saves where post_id=p.id) sv from posts p ")


def following(me_):
    return {r['followee'] for r in q('select followee from follows where follower=?', me_)}


def reach_of(ids):
    """چند نفر هر پست را واقعاً دیده‌اند (جدول impressions؛ هر کاربر یک‌بار)."""
    ids = list(ids)
    out = {}
    for i in range(0, len(ids), 400):
        part = ids[i:i + 400]
        for r in q(f'select post_id, count(*) c from impressions where post_id in ({marks(len(part))}) group by post_id', *part):
            out[r['post_id']] = r['c']
    return out


def diversify(scored, decay=0.72):
    """پست‌های پشت‌سرهمِ یک نویسنده نباید فید را پر کنند: هر پست بعدیِ همان نویسنده در رتبه‌بندی ضریب decay می‌گیرد
    (حریصانه؛ بهترین پستِ هر نفر سر جاش می‌ماند، بقیه‌اش پایین‌تر می‌رود و نفر بعدی جا می‌شود)."""
    pool = sorted(scored, key=lambda x: -x[0])
    out, used = [], {}
    while pool:
        best_i, best_v = 0, -1.0
        for i, (s, p) in enumerate(pool[:60]):          # فقط ۶۰ نامزد اول را بررسی می‌کند (سریع می‌ماند)
            v = s * decay ** used.get(p['user_id'], 0)
            if v > best_v:
                best_i, best_v = i, v
        s, p = pool.pop(best_i)
        used[p['user_id']] = used.get(p['user_id'], 0) + 1
        out.append(p)
    return out


def rank(rows, me_, aff, half_h, boost=(), extra=None):
    """امتیاز = (۱+لگاریتم تعامل) × کیفیت (نرخ تعامل نسبت به دیده‌شدن) × (۱+۱٫۵×نزدیکی نویسنده) × کاهش زمانی نیمه‌عمر
    × ضریب فالو × ضریب لایک‌شده × شانس پست تازه × کمی تصادف؛ در آخر تنوع نویسنده."""
    liked = {r['post_id'] for r in q('select post_id from likes where user_id=?', me_)}
    reach = reach_of(p['id'] for p in rows)
    now = time.time()
    out = []
    for p in rows:
        age = max(now - p['created'], 0) / 3600
        raw = p['lk'] + 2 * p['cm'] + 3 * p['sv']
        eng = math.log1p(raw)
        seen_by = reach.get(p['id'], 0)
        quality = 0.8 + min((raw + 1) / (seen_by + 15) * 4, 0.6)     # ۰٫۸ تا ۱٫۴؛ پست خوب‌ِ کم‌دیده بالا می‌رود، پست پرنمایشِ بی‌تعامل پایین
        a = min(aff.get(p['user_id'], 0), 12) / 12
        s = (1 + eng) * quality * (1 + 1.5 * a) * 0.5 ** (age / half_h)
        if age < 3 and seen_by < 30:                                    # پست تازه یک شانسِ اولیه برای دیده‌شدن می‌گیرد
            s *= 1.25
        if p['user_id'] in boost:
            s *= 1.6
        if p['id'] in liked:
            s *= 0.4
        if extra:
            s *= extra.get(p['id'], 1.0)
        out.append((s * (0.85 + random.random() * 0.3), p))
    return diversify(out)


def seen_ids(me_):
    """پست‌هایی که این کاربر قبلاً دیده (جدول impressions، همه‌ی زمان‌ها)."""
    return {r['post_id'] for r in q('select post_id from impressions where user_id=?', me_)}


def unseen_first(ranked, seen):
    """دیده‌نشده‌ها اول، دیده‌شده‌ها ته لیست؛ ترتیب نسبی داخل هر دسته حفظ می‌شود. هیچ پستی حذف نمی‌شود."""
    return [p for p in ranked if p['id'] not in seen] + [p for p in ranked if p['id'] in seen]


def marks(n): return ','.join('?' * n)


def rank_reels(rows, me_, aff, fol, half_h=72):
    """ریلز: مدل پیشنهاد هوشمند (server/reco.py)."""
    from .reco import rank_reels as _rank
    return _rank(rows, me_, aff, fol, half_h)
