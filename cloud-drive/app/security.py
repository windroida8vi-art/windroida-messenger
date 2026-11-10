"""Password hashing, rate limiting, session/CSRF handling and access decorators."""
import base64
import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import current_app, g, request, session

from .db import get_db
from .errors import fail
from .services import iso_ago, log_event, now

try:  # Argon2id when argon2-cffi is installed, otherwise stdlib scrypt (also a memory-hard KDF)
    from argon2 import PasswordHasher
    _ph = PasswordHasher()
except Exception:  # pragma: no cover
    _ph = None

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
COMMON_WORDS = {"password", "passw0rd", "qwerty", "qwertyuiop", "letmein", "welcome", "admin", "administrator", "iloveyou",
                "abc", "abcdef", "monkey", "dragon", "football", "master", "login", "changeme", "secret", "azerty", "asdfgh",
                "asdfghjkl", "zxcvbnm", "trustno", "sunshine", "princess", "shadow", "whatever", "iranian", "tehran"}


def hash_password(pw):
    if _ph:
        return _ph.hash(pw)
    n = current_app.config.get("SCRYPT_N", 2 ** 15)
    salt = os.urandom(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=n, r=8, p=1, maxmem=128 * 1024 * 1024, dklen=32)
    return "scrypt$%d$%s$%s" % (n, base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(pw, stored):
    try:
        if stored.startswith("$argon2"):
            return bool(_ph and _ph.verify(stored, pw))
        if stored.startswith("scrypt$"):
            _, n, salt, dk = stored.split("$")
            calc = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt), n=int(n), r=8, p=1,
                                  maxmem=128 * 1024 * 1024, dklen=32)
            return hmac.compare_digest(calc, base64.b64decode(dk))
    except Exception:
        return False
    return False


def check_password_policy(pw, username=""):
    if not isinstance(pw, str) or len(pw) < 10 or len(pw) > 128:
        fail("weak_password", "رمز عبور باید حداقل ۱۰ و حداکثر ۱۲۸ نویسه باشد",
             "Password must be 10-128 characters", 400)
    if not (any(c.isalpha() for c in pw) and any(c.isdigit() for c in pw)):
        fail("weak_password", "رمز عبور باید هم حرف و هم عدد داشته باشد", "Password needs letters and digits", 400)
    low = pw.lower()
    stripped = "".join(ch for ch in low if ch.isalpha())
    if stripped in COMMON_WORDS or any(low.startswith(w) and low[len(w):].isdigit() for w in COMMON_WORDS) \
            or len(set(low)) < 5 \
            or any(seq in low for seq in ("1234567", "7654321", "qwerty", "asdfgh", "abcdefg", "0000000")):
        fail("weak_password", "این رمز بسیار رایج و قابل حدس است", "This password is too common", 400)
    if username and (low == username.lower() or username.lower() in low):
        fail("weak_password", "رمز عبور نباید با نام کاربری یکسان باشد", "Password must differ from username", 400)


class RateLimiter:
    def __init__(self):
        self.h = defaultdict(deque)
        self.lock = threading.Lock()
        self.last_prune = time.monotonic()

    def hit(self, key, limit, window):
        t = time.monotonic()
        with self.lock:
            dq = self.h[key]
            while dq and dq[0] <= t - window:
                dq.popleft()
            if len(dq) >= limit:
                return False
            dq.append(t)
            if t - self.last_prune > 300:
                self.last_prune = t
                for k in [k for k, v in self.h.items() if not v or v[-1] < t - 3600]:
                    del self.h[k]
            return True


def client_ip():
    if current_app.config.get("TRUSTED_PROXY"):
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()[:64]
    return (request.remote_addr or "?")[:64]


def limit_or_429(key, limit, window, kind=None):
    if not current_app.limiter.hit(key, limit, window):
        if kind:
            log_event(get_db(), "warning", "rate_limit", kind, client_ip())
        fail("rate_limited", "تعداد درخواست‌ها زیاد است؛ کمی بعد دوباره تلاش کنید",
             "Too many requests, try again shortly", 429)


# ---------------------------------------------------------------- sessions
def start_session(db, user_id):
    sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    db.execute("INSERT INTO sessions(id,user_id,csrf,created_at,last_seen,ip) VALUES(?,?,?,?,?,?)",
               (sid, user_id, csrf, now(), now(), client_ip()))
    db.execute("UPDATE users SET last_login=? WHERE id=?", (now(), user_id))
    session.clear()
    session["sid"] = sid
    session.permanent = True
    return csrf


def end_session(db):
    sid = session.get("sid")
    if sid:
        db.execute("UPDATE sessions SET revoked=1 WHERE id=?", (sid,))
    session.clear()


def current_user():
    if "user" in g:
        return g.user
    g.user = None
    sid = session.get("sid")
    if sid:
        db = get_db()
        row = db.execute(
            "SELECT u.*, s.csrf AS csrf, s.id AS sid, s.last_seen AS seen FROM sessions s "
            "JOIN users u ON u.id=s.user_id WHERE s.id=? AND s.revoked=0 AND u.is_active=1 AND s.created_at>?",
            (sid, iso_ago(days=14))).fetchone()
        if row:
            g.user = row
            if row["seen"] < iso_ago(seconds=60):
                db.execute("UPDATE sessions SET last_seen=? WHERE id=?", (now(), sid))
    return g.user


def _check_csrf(user):
    sent = request.headers.get("X-CSRF-Token", "")
    if not sent or not hmac.compare_digest(sent, user["csrf"]):
        log_event(get_db(), "warning", "csrf", request.path, client_ip())
        fail("csrf", "نشست نامعتبر است؛ صفحه را تازه کنید", "Invalid CSRF token", 403)


def login_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        u = current_user()
        if not u:
            fail("unauthorized", "ابتدا وارد شوید", "Please sign in", 401)
        if request.method not in SAFE_METHODS:
            _check_csrf(u)
        return f(*a, **k)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        u = current_user()
        if not u:
            fail("unauthorized", "ابتدا وارد شوید", "Please sign in", 401)
        if u["role"] != "admin":
            log_event(get_db(), "warning", "admin_denied", "user %s -> %s" % (u["username"], request.path),
                      client_ip())
            fail("forbidden", "دسترسی مجاز نیست", "Forbidden", 403)
        if request.method not in SAFE_METHODS:
            _check_csrf(u)
        return f(*a, **k)
    return wrapper


def require_reauth(user, data):
    """Sensitive admin actions need the admin's password again."""
    limit_or_429("reauth:%s" % user["id"], 6, 300, "reauth")
    pw = (data or {}).get("confirm_password", "")
    if not isinstance(pw, str) or not verify_password(pw, user["password_hash"]):
        log_event(get_db(), "warning", "reauth_failed", "admin %s" % user["username"], client_ip())
        fail("reauth_failed", "رمز عبور تأیید نادرست است", "Wrong confirmation password", 403)
