"""هوش مصنوعی پیشنهاد ویدیو (فقط برای ریلز). سبک است: بدون دانلود مدل، روی CPU قدیمی هم در چند میلی‌ثانیه.

سه سیگنال یاد می‌گیرد و با یک مدل لجستیک که با هر تماشا آموزش می‌بیند ترکیب می‌کند:
  • محتوا   پروفایل سلیقه‌ی هر کاربر از کلمه‌ها و هشتگ‌های کپشنِ ویدیوهایی که دوست داشته (کسینوس TF)
  • هم‌تماشایی  «کسانی که این ویدیو را تا آخر دیدند / لایک کردند، این یکی را هم دیدند» (item-item CF)
  • رفتار   سلیقه‌ی نویسنده، کیفیت کلی ویدیو (میانگین تماشا)، تازگی، محبوبیت، دنبال‌شده بودن
برچسب آموزش: تماشا ≥۷۰٪ یا لایک = مثبت، تماشا <۳۵٪ = منفی. وزن‌ها در data/reco.json می‌مانند.
"""
import json
import math
import os
import random
import re
import threading
import time
import unicodedata

from . import config
from .db import q, q1
from .notify import HASHTAG

PATH = os.path.join(config.DATA_DIR, 'reco.json')
DEFAULT = dict(content=1.6, cf=1.2, taste=1.0, quality=1.0, aff=0.9, fresh=0.6, pop=0.4, follow=0.7, bias=-0.3)
_lock = threading.Lock()
_ctx_cache = {}
_state = {'w': dict(DEFAULT), 'updates': 0}
_TOK = re.compile(r'#?[\w\u0600-\u06FF]{2,}')
STOP = {'را', 'که', 'این', 'از', 'با', 'در', 'به', 'هم', 'تو', 'من', 'the', 'and', 'for', 'you', 'with'}


def _load():
    try:
        with open(PATH, encoding='utf-8') as f:
            d = json.load(f)
        _state['w'] = {**DEFAULT, **{k: float(v) for k, v in d.get('w', {}).items() if k in DEFAULT}}
        _state['updates'] = int(d.get('updates', 0))
    except Exception:
        pass


def _save():
    tmp = PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(_state, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, PATH)


_load()


def stats():
    return dict(updates=_state['updates'], weights={k: round(v, 2) for k, v in _state['w'].items()})


def tokens(text, author=None):
    t = unicodedata.normalize('NFKC', text or '').lower().replace('ي', 'ی').replace('ك', 'ک')
    out = {}
    for w in _TOK.findall(t):
        if w in STOP:
            continue
        out[w] = out.get(w, 0) + (2.0 if w.startswith('#') else 1.0)
    if author:
        out['@' + author] = 1.5
    return out


def _cos(a, b, na):
    if not a or not b or not na:
        return 0.0
    nb = math.sqrt(sum(v * v for v in b.values()))
    return sum(v * b.get(k, 0) for k, v in a.items()) / (na * nb) if nb else 0.0


def _completion(r):
    return min(r['secs'] / max(r['plays'], 1) / r['dur'], 1.5)


def user_ctx(me_, exclude=None):
    """سلیقه‌ی کاربر از تاریخچه تماشا/لایک/ذخیره/نظر. ۳۰ ثانیه کش می‌شود (برای آموزش، بدون کش و بدون پستِ فعلی)."""
    hit = _ctx_cache.get(me_)
    if exclude is None and hit and time.time() - hit[0] < 30:
        return hit[1]
    liked = {r['post_id'] for r in q('select post_id from likes where user_id=?', me_)}
    saved = {r['post_id'] for r in q('select post_id from saves where user_id=?', me_)}
    commented = {r['post_id'] for r in q('select distinct post_id from comments where user_id=?', me_)}
    profile, taste, pos, seen = {}, {}, set(), set()
    rows = q('select w.post_id, w.secs, w.dur, w.plays, p.caption, p.user_id, u.username from watch w '
             'join posts p on p.id=w.post_id join users u on u.id=p.user_id where w.user_id=? and w.dur>0 '
             'order by w.created desc limit 150', me_)
    for r in rows:
        if r['post_id'] == exclude:
            continue
        seen.add(r['post_id'])
        c = _completion(r)
        w = max(-0.9, min(1.5, (c - 0.45) * 2))
        w += (1.0 if r['post_id'] in liked else 0) + (0.7 if r['post_id'] in saved else 0) + (0.5 if r['post_id'] in commented else 0)
        for k, v in tokens(r['caption'], r['username']).items():
            profile[k] = profile.get(k, 0) + v * w
        taste[r['user_id']] = taste.get(r['user_id'], 0) + (c - 0.45)
        if c >= 0.7 or r['post_id'] in liked:
            pos.add(r['post_id'])
    extra = (liked | saved) - seen - ({exclude} if exclude else set())
    if extra:
        for r in q(f'select p.id, p.caption, p.user_id, u.username from posts p join users u on u.id=p.user_id '
                   f'where p.id in ({",".join("?" * len(extra))})', *extra):
            w = (1.0 if r['id'] in liked else 0) + (0.7 if r['id'] in saved else 0)
            for k, v in tokens(r['caption'], r['username']).items():
                profile[k] = profile.get(k, 0) + v * w
            pos.add(r['id'])
    ctx = dict(profile=profile, norm=math.sqrt(sum(v * v for v in profile.values())), taste=taste, pos=pos, liked=liked)
    if exclude is None:
        if len(_ctx_cache) > 500:
            _ctx_cache.clear()
        _ctx_cache[me_] = (time.time(), ctx)
    return ctx


def _co_users(post_ids, me_):
    ids = list(post_ids)
    users = {}
    if not ids:
        return users
    ph = ','.join('?' * len(ids))
    for r in q(f'select post_id, user_id from watch where dur>0 and secs/plays/dur>=0.7 and post_id in ({ph})', *ids):
        users.setdefault(r['post_id'], set()).add(r['user_id'])
    for r in q(f'select post_id, user_id from likes where post_id in ({ph})', *ids):
        users.setdefault(r['post_id'], set()).add(r['user_id'])
    for s in users.values():
        s.discard(me_)
    return users


def features(rows, me_, aff, fol, ctx=None):
    """برای هر ردیف کاندید یک دیکشنری ویژگی (همه در بازه ~۰..۱ یا -۱..۱) برمی‌گرداند."""
    ctx = ctx or user_ctx(me_)
    now = time.time()
    ids = [p['id'] for p in rows]
    users = _co_users(set(ids) | ctx['pos'], me_)
    glob = {}
    if ids:
        for r in q(f'select post_id, sum(min(secs/plays/dur, 1.5)) s, count(*) n from watch where dur>0 and post_id in '
                   f'({",".join("?" * len(ids))}) group by post_id', *ids):
            glob[r['post_id']] = (r['s'], r['n'])
    names = {r['id']: r['username'] for r in q(
        f'select id, username from users where id in ({",".join("?" * len({p["user_id"] for p in rows}))})',
        *{p['user_id'] for p in rows})} if rows else {}
    out = []
    for p in rows:
        uj_ = users.get(p['id'], set())
        cf = 0.0
        for i in ctx['pos']:
            ui = users.get(i, set())
            if ui and uj_ and i != p['id']:
                cf = max(cf, len(ui & uj_) / math.sqrt(len(ui) * len(uj_)))
        gs, gn = glob.get(p['id'], (0, 0))
        age = max(now - p['created'], 0) / 3600
        out.append(dict(
            content=_cos(ctx['profile'], tokens(p['caption'], names.get(p['user_id'])), ctx['norm']),
            cf=cf,
            taste=max(-1.0, min(1.0, ctx['taste'].get(p['user_id'], 0) / 2)),
            quality=((gs + 0.55 * 3) / (gn + 3)) / 1.5,
            aff=min(aff.get(p['user_id'], 0), 12) / 12,
            fresh=0.5 ** (age / 72),
            pop=min(math.log1p(p['lk'] + 2 * p['cm'] + 3 * p['sv']) / 4, 1.0),
            follow=1.0 if p['user_id'] in fol else 0.0,
            bias=1.0))
    return out


def predict(f):
    z = sum(_state['w'][k] * v for k, v in f.items())
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


def train_event(me_, post_id, lr=0.2):
    """بعد از هر تماشا یک قدم SGD: مدل یاد می‌گیرد کدام ویژگی‌ها پیش‌بینی‌کننده‌ی علاقه‌اند."""
    from .ranking import CAND, affinity, following
    w = q1('select secs, dur, plays from watch where user_id=? and post_id=? and dur>0', me_, post_id)
    row = q1(CAND + 'where p.id=?', post_id)
    if not w or not row or row['kind'] != 'video' or row['user_id'] == me_:
        return None
    c = _completion(w)
    liked = bool(q1('select 1 from likes where user_id=? and post_id=?', me_, post_id))
    y = 1.0 if (c >= 0.7 or liked) else 0.0 if c < 0.35 else None
    if y is None:
        return None
    f = features([row], me_, affinity(me_), following(me_), user_ctx(me_, exclude=post_id))[0]
    with _lock:
        p = predict(f)
        for k, v in f.items():
            wk = _state['w'][k] + lr * (y - p) * v - 0.002 * _state['w'][k]
            _state['w'][k] = max(-3.0 if k == 'bias' else 0.0, min(6.0, wk))
        _state['updates'] += 1
        _save()
    _ctx_cache.pop(me_, None)
    return y, round(p, 3)


def personalize(rows, me_):
    """ضریب شخصی‌سازی برای هر پست (کاوش): شباهت کپشن با پروفایل سلیقه‌ی کاربر (لایک/ذخیره/تماشا)."""
    ctx = user_ctx(me_)
    if not ctx['norm']:
        return {}
    return {p['id']: 1 + 1.5 * max(0.0, _cos(ctx['profile'], tokens(p['caption']), ctx['norm'])) for p in rows}


def explain(me_, post_id):
    """برای دیباگ/ادمین: ویژگی‌ها و احتمال پیش‌بینی‌شده برای یک ویدیو."""
    from .ranking import CAND, affinity, following
    row = q1(CAND + 'where p.id=?', post_id)
    f = features([row], me_, affinity(me_), following(me_))[0]
    return dict(features={k: round(v, 3) for k, v in f.items()}, p=round(predict(f), 3))


def _topic(p):
    m = HASHTAG.search((p['caption'] or '').lower())
    return m.group(1) if m else None


def _diversify(items):
    """تنوع: دو ریل پشت‌سرهم از یک نفر نه، و بیش از دو ریل پشت‌سرهم با یک هشتگ هم نه."""
    rest, out = list(items), []
    while rest:
        last, prev = (out[-1] if out else None), (out[-2] if len(out) > 1 else None)

        def bad(p):
            if last and p['user_id'] == last['user_id']:
                return True
            t = _topic(p)
            return bool(t and last and prev and _topic(last) == t and _topic(prev) == t)
        out.append(rest.pop(next((i for i, p in enumerate(rest[:24]) if not bad(p)), 0)))
    return out


def rank_reels(rows, me_, aff, fol, half_h=72):
    """ریلزها بر اساس احتمال علاقه مرتب می‌شوند، با الگوریتم «تکراری نشان نده»:
      ۱) آپلودهای تکراریِ یک فایل (sha یکسان) فقط یک‌بار (قدیمی‌ترین) می‌آیند؛
      ۲) هرچه کاربر دیده (یا فایل یکسانش را دیده) فقط بعد از تمام شدن ویدیوهای تازه برمی‌گردد، آن هم قدیمی‌ترین‌دیده‌شده اول؛
      ۳) کاوش (نویسنده‌های تازه) و تنوع (نویسنده/هشتگ) هم اعمال می‌شود."""
    if not rows:
        return []
    first, uniq = {}, []
    for p in sorted(rows, key=lambda x: x['id']):
        if p['sha'] and p['sha'] in first:
            continue
        if p['sha']:
            first[p['sha']] = p['id']
        uniq.append(p)
    ctx = user_ctx(me_)
    feats = features(uniq, me_, aff, fol, ctx)
    now = time.time()
    watched = {r['post_id']: r['created'] or 0 for r in q('select post_id, created from watch where user_id=?', me_)}
    seen_sha = {}
    for r in q('select p.sha, max(w.created) c from watch w join posts p on p.id=w.post_id '
               'where w.user_id=? and p.sha is not null group by p.sha', me_):
        seen_sha[r['sha']] = r['c'] or 0
    unseen, seen = [], []
    for p, f in zip(uniq, feats):
        age = max(now - p['created'], 0) / 3600
        eng = math.log1p(p['lk'] + 2 * p['cm'] + 3 * p['sv'])
        s = (0.1 + predict(f)) * (1 + 0.4 * eng) * 0.5 ** (age / (half_h * 3))
        if p['id'] in ctx['liked']:
            s *= 0.4
        if p['user_id'] not in ctx['taste'] and p['user_id'] not in fol and random.random() < 0.15:
            s *= 1 + 2 * random.random()  # کاوش
        s *= 0.9 + random.random() * 0.2
        last = watched.get(p['id'], seen_sha.get(p['sha']) if p['sha'] else None)
        (seen if last is not None else unseen).append((s, last, p))
    unseen.sort(key=lambda x: -x[0])
    seen.sort(key=lambda x: (x[1], -x[0]))  # قدیمی‌ترین دیده‌شده اول
    return _diversify([p for _, _, p in unseen]) + _diversify([p for _, _, p in seen])
