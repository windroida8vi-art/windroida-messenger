import re
import sqlite3

from flask import Blueprint, current_app, g, jsonify, request

from .db import get_db
from .errors import fail
from .security import (check_password_policy, client_ip, current_user, end_session, hash_password,
                       limit_or_429, login_required, start_session, verify_password)
from .services import (get_int, get_setting, get_settings, log_activity, log_event, now, used_bytes, user_dict)

bp = Blueprint("auth", __name__, url_prefix="/api")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
_DUMMY = None


def _dummy_hash():
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password("dummy-password-1234")
    return _DUMMY


def me_payload(csrf):
    db, u = get_db(), current_user()
    s = get_settings(db)
    return {"user": user_dict(u), "csrf": csrf,
            "usage": {"used": used_bytes(db, u["id"]), "quota": u["quota_bytes"]},
            "max_upload_bytes": int(s["max_upload_bytes"]), "trash_enabled": s["trash_enabled"] == "1", "retention_days": int(s["file_retention_days"]), "trash_days": int(s["trash_retention_days"]),
            "service_name": s["service_name"], "logo_data": s["logo_data"]}


@bp.get("/config")
def public_config():
    s = get_settings(get_db())
    return jsonify(service_name=s["service_name"], logo_data=s["logo_data"],
                   registration_open=s["registration_open"] == "1",
                   password_auth=bool(current_app.config.get("PASSWORD_AUTH", True)))


@bp.post("/register")
def register():
    if not current_app.config.get("PASSWORD_AUTH", True):
        fail("sso_only", "ثبت‌نام مستقیم غیرفعال است؛ فقط از لینک «فضای ابری» تو ویندروید وارد شو",
             "Direct registration is disabled; sign in from Windroida's Cloud Drive link instead", 403)
    db = get_db()
    if get_setting(db, "registration_open") != "1":
        fail("registration_closed", "ثبت‌نام فعلاً بسته است", "Registration is closed", 403)
    limit_or_429("reg:%s" % client_ip(), 200, 3600, "register")
    d = request.get_json(silent=True) or {}
    username = str(d.get("username") or "").strip()
    email = str(d.get("email") or "").strip()[:120]
    if not USERNAME_RE.match(username):
        fail("bad_username", "نام کاربری ۳ تا ۳۲ نویسه (حروف انگلیسی، عدد، . _ -) باشد",
             "Username: 3-32 chars (letters, digits, . _ -)", 400)
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        fail("bad_email", "ایمیل نامعتبر است", "Invalid email", 400)
    pw = d.get("password")
    check_password_policy(pw, username)
    quota = get_int(db, "default_quota_bytes")
    try:
        cur = db.execute("INSERT INTO users(username,email,display_name,password_hash,role,quota_bytes,created_at) "
                         "VALUES(?,?,?,?,?,?,?)",
                         (username, email, str(d.get("display_name") or username)[:60], hash_password(pw), "user",
                          quota, now()))
    except sqlite3.IntegrityError:
        fail("username_taken", "این نام کاربری قبلاً ثبت شده است", "Username already taken", 409)
    uid = cur.lastrowid
    log_activity(db, uid, "register", "", client_ip())
    csrf = start_session(db, uid)
    g.pop("user", None)
    return jsonify(me_payload(csrf)), 201


@bp.post("/login")
def login():
    if not current_app.config.get("PASSWORD_AUTH", True):
        fail("sso_only", "ورود با رمز غیرفعال است؛ فقط از لینک «فضای ابری» تو ویندروید وارد شو",
             "Password login is disabled; sign in from Windroida's Cloud Drive link instead", 403)
    db = get_db()
    ip = client_ip()
    d = request.get_json(silent=True) or {}
    username = str(d.get("username") or "").strip()[:64]
    pw = d.get("password") if isinstance(d.get("password"), str) else ""
    limit_or_429("login:%s" % ip, get_int(db, "rate_login_per_min"), 60, "login ip")
    limit_or_429("loginu:%s" % username.lower(), 10, 600, "login user")
    row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    ok = verify_password(pw, row["password_hash"] if row else _dummy_hash())
    if not row or not ok:
        log_event(db, "info", "login_failed", "username=%s" % username[:32], ip)
        fail("bad_credentials", "نام کاربری یا رمز عبور نادرست است", "Wrong username or password", 401)
    if not row["is_active"]:
        reason = row["banned_reason"]
        fail("account_disabled",
             "حساب شما غیرفعال شده است" + (" (دلیل: %s)" % reason if reason else ""),
             "Your account is disabled" + (" (reason: %s)" % reason if reason else ""), 403)
    csrf = start_session(db, row["id"])
    g.pop("user", None)
    log_activity(db, row["id"], "login", "", ip)
    return jsonify(me_payload(csrf))


@bp.post("/logout")
@login_required
def logout():
    end_session(get_db())
    return jsonify(ok=True)


@bp.get("/me")
@login_required
def me():
    return jsonify(me_payload(current_user()["csrf"]))


@bp.patch("/me")
@login_required
def update_me():
    db, u = get_db(), current_user()
    d = request.get_json(silent=True) or {}
    name = str(d.get("display_name", u["display_name"] or "")).strip()[:60]
    email = str(d.get("email", u["email"] or "")).strip()[:120]
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        fail("bad_email", "ایمیل نامعتبر است", "Invalid email", 400)
    db.execute("UPDATE users SET display_name=?, email=? WHERE id=?", (name, email, u["id"]))
    log_activity(db, u["id"], "profile_update", "", client_ip())
    g.pop("user", None)
    return jsonify(me_payload(u["csrf"]))


@bp.post("/me/password")
@login_required
def change_password():
    db, u = get_db(), current_user()
    d = request.get_json(silent=True) or {}
    limit_or_429("pwchange:%s" % u["id"], 6, 600, "password change")
    if not verify_password(str(d.get("current_password") or ""), u["password_hash"]):
        fail("bad_credentials", "رمز فعلی نادرست است", "Current password is wrong", 403)
    check_password_policy(d.get("new_password"), u["username"])
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(d["new_password"]), u["id"]))
    db.execute("UPDATE sessions SET revoked=1 WHERE user_id=? AND id!=?", (u["id"], u["sid"]))
    log_activity(db, u["id"], "password_change", "", client_ip())
    return jsonify(ok=True)


@bp.get("/activity")
@login_required
def activity():
    u = current_user()
    limit = min(request.args.get("limit", 100, type=int), 500)
    rows = get_db().execute("SELECT action,detail,ip,bytes,created_at FROM activity WHERE user_id=? "
                            "ORDER BY id DESC LIMIT ?", (u["id"], limit)).fetchall()
    return jsonify(items=[dict(r) for r in rows])
