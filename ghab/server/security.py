"""ورود کاربر و ادمین، و خطای استاندارد JSON."""
import time
from functools import wraps

from flask import jsonify, session

from .db import q1


_hits = {}


def too_many(key, limit, window):
    """True اگر این کلید (مثلاً IP) در window ثانیه بیشتر از limit بار تلاش کرده باشد."""
    now = time.time()
    if len(_hits) > 5000:
        _hits.clear()
    lst = [t for t in _hits.get(key, []) if now - t < window] + [now]
    _hits[key] = lst
    return len(lst) > limit


def sso_only_block():
    """در حالت داخل ویندروید پاسخ 403 می‌دهد (برای مسیرهای رمز)، وگرنه None."""
    from . import config
    if not config.PASSWORD_AUTH:
        return err('ورود با رمز در قاب وجود ندارد؛ از منوی ویندروید «قاب» را بزن', 403)
    return None


def err(msg, code=400):
    return jsonify(error=msg), code


def cur_user():
    return q1('select * from users where id=?', session['uid'])


_seen = {}


def auth(f):
    @wraps(f)
    def wrapper(*a, **k):
        from .db import run
        uid = session.get('uid')
        u = q1('select banned from users where id=?', uid) if uid else None
        if not u:
            session.pop('uid', None)
            return err('وارد حساب شو', 401)
        if u['banned']:
            session.pop('uid', None)
            return err('این حساب مسدود شده است', 403)
        now = time.time()
        if now - _seen.get(uid, 0) > 60:  # آخرین بازدید: حداکثر دقیقه‌ای یک‌بار نوشته می‌شود
            _seen[uid] = now
            run('update users set last_seen=? where id=?', now, uid)
        return f(*a, **k)
    return wrapper


def user_ok():
    uid = session.get('uid')
    u = q1('select banned from users where id=?', uid) if uid else None
    return bool(u) and not u['banned']
