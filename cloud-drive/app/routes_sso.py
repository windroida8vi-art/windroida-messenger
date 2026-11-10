"""Single sign-on bridge: lets a Windroida messenger account open Cloud Drive without a second password.

Windroida's own server mints a short-lived, signed token for whichever user is ALREADY logged in there and opens
this URL with it. This endpoint only has to check the signature - it never asks Windroida anything over the network
and never sees a password. Both sides are given the same random secret (CD_SSO_SECRET here, data/drive_sso.key on
the Windroida side); without that shared secret nobody can mint a token that passes the check below, so this cannot
be used to log in as someone else, pick an arbitrary username, or become admin (new accounts are always role=user).
"""
import hmac as hmac_lib
import secrets
import threading
import time

from flask import Blueprint, current_app, redirect, request

from .db import get_db
from .errors import fail
from .security import client_ip, hash_password, limit_or_429, start_session
from .services import get_int, log_activity, log_event, now

bp = Blueprint("sso", __name__)

_used_lock = threading.Lock()
_used = {}  # token signature -> epoch it stops mattering by (replay guard: each token is redeemable once)


def _check_replay(sig, keep_until):
    t = time.time()
    with _used_lock:
        for k in [k for k, exp in _used.items() if exp < t]:
            del _used[k]
        if sig in _used:
            return False
        _used[sig] = keep_until
        return True


@bp.get("/sso")
def sso_login():
    ip = client_ip()
    limit_or_429("sso:%s" % ip, 20, 60, "sso")
    secret = current_app.config.get("SSO_SECRET") or ""
    db = get_db()
    if not secret:
        fail("sso_disabled", "ورود یکپارچه از ویندروید روی این سرور فعال نیست", "SSO is not configured on this server", 403)
    token = request.args.get("t", "")
    parts = token.split(".")
    if len(parts) != 4:
        fail("bad_token", "لینک نامعتبر است", "Invalid link", 400)
    username, expiry_s, nonce, sig = parts
    if not (1 <= len(username) <= 32) or not expiry_s.isdigit() or not (1 <= len(nonce) <= 40) or len(sig) != 64:
        fail("bad_token", "لینک نامعتبر است", "Invalid link", 400)
    expiry = int(expiry_s)
    expected = hmac_lib.new(secret.encode(), ("%s:%d:%s" % (username, expiry, nonce)).encode(), "sha256").hexdigest()
    if not hmac_lib.compare_digest(expected, sig):
        log_event(db, "warning", "sso_bad_sig", "username=%s" % username[:32], ip)
        fail("bad_token", "لینک نامعتبر است", "Invalid link", 400)
    if time.time() > expiry:
        fail("expired", "این لینک منقضی شده؛ دوباره از ویندروید باز کن", "This link expired; open it again from Windroida", 400)
    if not _check_replay(sig, expiry + 5):
        log_event(db, "warning", "sso_replay", "username=%s" % username[:32], ip)
        fail("bad_token", "این لینک قبلاً استفاده شده", "This link was already used", 400)
    row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if row is None:
        # first time this Windroida user opens the drive: make a matching account here. The password hash is a
        # random value nobody (not even the user) knows, so this account can only ever be entered through SSO.
        quota = get_int(db, "default_quota_bytes")
        cur = db.execute(
            "INSERT INTO users(username,email,display_name,password_hash,role,quota_bytes,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (username, "", username, hash_password(secrets.token_urlsafe(32)), "user", quota, now()))
        row = db.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
        log_activity(db, row["id"], "sso_provision", "", ip)
    elif not row["is_active"]:
        reason = row["banned_reason"]
        fail("account_disabled", "این حساب غیرفعال شده است" + (" (دلیل: %s)" % reason if reason else ""),
             "This account is disabled", 403)
    start_session(db, row["id"])
    log_activity(db, row["id"], "sso_login", "", ip)
    return redirect("/")
