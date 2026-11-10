import re
import sys
import time
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request

from .db import get_db
from .errors import fail
from .fileops import purge_files
from .security import admin_required, client_ip, current_user, require_reauth
from .services import (file_dict, get_settings, iso_ago, log_audit, log_event, now, set_setting, setting_defaults)

bp = Blueprint("admin", __name__, url_prefix="/api/admin")
STARTED = time.time()

SPECS = {
    "service_name": ("str", 1, 60), "logo_data": ("logo",),
    "max_upload_bytes": ("int", 0, 1 << 50), "file_retention_days": ("int", 0, 3650), "default_quota_bytes": ("int", 0, 1 << 50),
    "rate_login_per_min": ("int", 1, 10000), "rate_api_per_min": ("int", 0, 10000000),
    "rate_public_per_min": ("int", 1, 10000), "trash_enabled": ("bool",),
    "trash_retention_days": ("int", 1, 3650), "registration_open": ("bool",),
    "incomplete_upload_hours": ("int", 1, 720),
}
LOGO_RE = re.compile(r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$")


def _admin_count(db):
    return db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1").fetchone()[0]


def _user_row(db, uid):
    r = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not r:
        fail("not_found", "کاربر پیدا نشد", "User not found", 404)
    return r


@bp.get("/stats")
@admin_required
def stats():
    db = get_db()
    day = iso_ago(hours=24)
    one = lambda sql, *a: db.execute(sql, a).fetchone()[0]
    du = current_app.storage.disk_usage()
    out = {
        "users_total": one("SELECT COUNT(*) FROM users"),
        "users_active": one("SELECT COUNT(*) FROM users WHERE is_active=1"),
        "users_online": one("SELECT COUNT(DISTINCT user_id) FROM sessions WHERE revoked=0 AND last_seen>?",
                            iso_ago(minutes=15)),
        "files_total": one("SELECT COUNT(*) FROM files"),
        "bytes_total": one("SELECT COALESCE(SUM(size),0) FROM files"),
        "suspicious_total": one("SELECT COUNT(*) FROM files WHERE suspicious=1"),
        "disk_total": du.total, "disk_free": du.free,
        "uploads_24h": one("SELECT COUNT(*) FROM activity WHERE action='upload' AND created_at>?", day),
        "upload_bytes_24h": one("SELECT COALESCE(SUM(bytes),0) FROM activity WHERE action='upload' AND created_at>?", day),
        "downloads_24h": one("SELECT COUNT(*) FROM activity WHERE action IN ('download','public_download') AND created_at>?", day),
        "download_bytes_24h": one("SELECT COALESCE(SUM(bytes),0) FROM activity WHERE action IN "
                                  "('download','public_download') AND created_at>?", day),
    }
    days = [(datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(29, -1, -1)]
    start = days[0]
    new_users = dict(db.execute("SELECT substr(created_at,1,10) d, COUNT(*) FROM users WHERE substr(created_at,1,10)>=? "
                                "GROUP BY d", (start,)).fetchall())
    add_bytes = dict(db.execute("SELECT substr(created_at,1,10) d, SUM(size) FROM files WHERE substr(created_at,1,10)>=? "
                                "GROUP BY d", (start,)).fetchall())
    u_base = one("SELECT COUNT(*) FROM users WHERE substr(created_at,1,10)<?", start)
    b_base = one("SELECT COALESCE(SUM(size),0) FROM files WHERE substr(created_at,1,10)<?", start)
    ug, sg = [], []
    for d in days:
        u_base += new_users.get(d, 0)
        b_base += add_bytes.get(d, 0)
        ug.append({"day": d, "total": u_base, "new": new_users.get(d, 0)})
        sg.append({"day": d, "bytes": b_base})
    out["user_growth"], out["storage_growth"] = ug, sg
    out["recent_activity"] = [dict(r) for r in db.execute(
        "SELECT a.action,a.detail,a.created_at,u.username FROM activity a LEFT JOIN users u ON u.id=a.user_id "
        "ORDER BY a.id DESC LIMIT 15")]
    out["errors"] = [dict(r) for r in db.execute(
        "SELECT level,kind,message,ip,created_at FROM events WHERE level IN ('warning','error') "
        "ORDER BY id DESC LIMIT 10")]
    return jsonify(out)


@bp.get("/health")
@admin_required
def health():
    db, ok_db, ok_storage = get_db(), True, True
    try:
        db.execute("SELECT 1").fetchone()
    except Exception:
        ok_db = False
    try:
        p = current_app.config["UPLOAD_DIR"] / ".healthcheck"
        p.write_text("ok")
        p.unlink()
    except Exception:
        ok_storage = False
    du = current_app.storage.disk_usage()
    return jsonify(api=True, database=ok_db, storage=ok_storage, disk_free=du.free, disk_total=du.total,
                   uptime_seconds=int(time.time() - STARTED), python=sys.version.split()[0],
                   pending_uploads=db.execute("SELECT COUNT(*) FROM uploads").fetchone()[0])


# ------------------------------------------------------------ users
@bp.get("/users")
@admin_required
def users():
    db = get_db()
    q, status = (request.args.get("q") or "").strip(), request.args.get("status", "")
    sql = ("SELECT u.id,u.username,u.display_name,u.email,u.role,u.is_active,u.banned_reason,u.quota_bytes,"
           "u.created_at,u.last_login,(SELECT COALESCE(SUM(size),0) FROM files WHERE owner_id=u.id) used,"
           "(SELECT COUNT(*) FROM files WHERE owner_id=u.id) files FROM users u WHERE 1=1")
    args = []
    if q:
        sql += " AND (u.username LIKE ? OR u.email LIKE ? OR u.display_name LIKE ?)"
        args += ["%" + q + "%"] * 3
    if status == "active":
        sql += " AND u.is_active=1"
    elif status == "disabled":
        sql += " AND u.is_active=0 AND u.banned_reason IS NULL"
    elif status == "banned":
        sql += " AND u.banned_reason IS NOT NULL"
    elif status == "admin":
        sql += " AND u.role='admin'"
    rows = db.execute(sql + " ORDER BY u.id DESC LIMIT 500", args).fetchall()
    return jsonify(items=[dict(r) for r in rows])


@bp.patch("/users/<int:uid>")
@admin_required
def update_user(uid):
    db, me = get_db(), current_user()
    d = request.get_json(silent=True) or {}
    require_reauth(me, d)
    u = _user_row(db, uid)
    changes = []
    if "quota_bytes" in d:
        q = d["quota_bytes"]
        if not isinstance(q, int) or q < 0:
            fail("bad_request", "سهمیه نامعتبر است", "Invalid quota", 400)
        db.execute("UPDATE users SET quota_bytes=? WHERE id=?", (q, uid))
        changes.append("quota=%d" % q)
    if "is_active" in d:
        if uid == me["id"]:
            fail("self_action", "نمی‌توانید حساب خودتان را غیرفعال کنید", "You cannot disable yourself", 400)
        active = 1 if d["is_active"] else 0
        if not active and u["role"] == "admin" and _admin_count(db) <= 1:
            fail("last_admin", "آخرین مدیر را نمی‌توان غیرفعال کرد", "Cannot disable the last admin", 400)
        db.execute("UPDATE users SET is_active=?, banned_reason=NULL WHERE id=?", (active, uid))
        if not active:
            db.execute("UPDATE sessions SET revoked=1 WHERE user_id=?", (uid,))
        changes.append("active=%d" % active)
    if "role" in d:
        if d["role"] not in ("user", "admin"):
            fail("bad_request", "نقش نامعتبر است", "Invalid role", 400)
        if uid == me["id"] and d["role"] != "admin":
            fail("self_action", "نمی‌توانید نقش خودتان را کاهش دهید", "You cannot demote yourself", 400)
        db.execute("UPDATE users SET role=? WHERE id=?", (d["role"], uid))
        changes.append("role=" + d["role"])
    log_audit(db, me["id"], "user_update", u["username"], ", ".join(changes), client_ip())
    return jsonify(ok=True)


@bp.post("/users/<int:uid>/ban")
@admin_required
def ban_user(uid):
    db, me = get_db(), current_user()
    d = request.get_json(silent=True) or {}
    require_reauth(me, d)
    u = _user_row(db, uid)
    reason = str(d.get("reason") or "").strip()[:300]
    if not reason:
        fail("reason_required", "دلیل مسدودسازی را بنویسید", "A reason is required", 400)
    if uid == me["id"]:
        fail("self_action", "نمی‌توانید خودتان را مسدود کنید", "You cannot ban yourself", 400)
    if u["role"] == "admin" and _admin_count(db) <= 1:
        fail("last_admin", "آخرین مدیر را نمی‌توان مسدود کرد", "Cannot ban the last admin", 400)
    db.execute("UPDATE users SET is_active=0, banned_reason=? WHERE id=?", (reason, uid))
    db.execute("UPDATE sessions SET revoked=1 WHERE user_id=?", (uid,))
    log_audit(db, me["id"], "user_ban", u["username"], reason, client_ip())
    return jsonify(ok=True)


@bp.post("/users/<int:uid>/unban")
@admin_required
def unban_user(uid):
    db, me = get_db(), current_user()
    require_reauth(me, request.get_json(silent=True) or {})
    u = _user_row(db, uid)
    db.execute("UPDATE users SET is_active=1, banned_reason=NULL WHERE id=?", (uid,))
    log_audit(db, me["id"], "user_unban", u["username"], "", client_ip())
    return jsonify(ok=True)


@bp.post("/users/<int:uid>/revoke-sessions")
@admin_required
def revoke_sessions(uid):
    db, me = get_db(), current_user()
    require_reauth(me, request.get_json(silent=True) or {})
    u = _user_row(db, uid)
    n = db.execute("UPDATE sessions SET revoked=1 WHERE user_id=? AND revoked=0", (uid,)).rowcount
    log_audit(db, me["id"], "sessions_revoke", u["username"], "count=%d" % n, client_ip())
    return jsonify(ok=True, revoked=n)


# ------------------------------------------------------------ files (metadata only; contents are never exposed)
@bp.get("/files")
@admin_required
def files():
    db = get_db()
    q = (request.args.get("q") or "").strip()
    sql = ("SELECT f.*, u.username FROM files f JOIN users u ON u.id=f.owner_id WHERE 1=1")
    args = []
    if request.args.get("suspicious") == "1":
        sql += " AND f.suspicious=1"
    if q:
        sql += " AND (f.name LIKE ? OR u.username LIKE ?)"
        args += ["%" + q + "%"] * 2
    rows = db.execute(sql + " ORDER BY f.id DESC LIMIT 300", args).fetchall()
    return jsonify(items=[dict(file_dict(r), owner=r["username"]) for r in rows])


@bp.delete("/files/<int:fid>")
@admin_required
def delete_file(fid):
    db, me = get_db(), current_user()
    d = request.get_json(silent=True) or {}
    require_reauth(me, d)
    f = db.execute("SELECT f.*, u.username FROM files f JOIN users u ON u.id=f.owner_id WHERE f.id=?", (fid,)).fetchone()
    if not f:
        fail("not_found", "فایل پیدا نشد", "File not found", 404)
    purge_files(db, current_app.storage, [fid])
    log_audit(db, me["id"], "file_delete", "%s (owner %s)" % (f["name"], f["username"]),
              str(d.get("reason") or "")[:300], client_ip())
    return jsonify(ok=True)


# ------------------------------------------------------------ settings / logs
@bp.get("/settings")
@admin_required
def get_all_settings():
    return jsonify(get_settings(get_db()))


@bp.put("/settings")
@admin_required
def put_settings():
    db, me = get_db(), current_user()
    d = request.get_json(silent=True) or {}
    require_reauth(me, d)
    changed = []
    for k, v in (d.get("settings") or {}).items():
        spec = SPECS.get(k)
        if not spec:
            fail("bad_request", "تنظیم ناشناخته: %s" % k, "Unknown setting: %s" % k, 400)
        kind = spec[0]
        if kind == "int":
            if isinstance(v, str) and v.isdigit():
                v = int(v)
            if not isinstance(v, int) or isinstance(v, bool) or not spec[1] <= v <= spec[2]:
                fail("bad_request", "مقدار نامعتبر برای %s" % k, "Invalid value for %s" % k, 400)
        elif kind == "str":
            v = str(v).strip()
            if not spec[1] <= len(v) <= spec[2]:
                fail("bad_request", "مقدار نامعتبر برای %s" % k, "Invalid value for %s" % k, 400)
        elif kind == "bool":
            v = "1" if v in (True, 1, "1", "true") else "0"
        elif kind == "logo":
            v = str(v or "")
            if v and (len(v) > 300000 or not LOGO_RE.match(v)):
                fail("bad_logo", "لوگو باید PNG/JPEG/WebP و کمتر از ۲۰۰ کیلوبایت باشد",
                     "Logo must be PNG/JPEG/WebP under 200 KB", 400)
        set_setting(db, k, v)
        changed.append(k)
    log_audit(db, me["id"], "settings_update", ", ".join(changed), "", client_ip())
    return jsonify(get_settings(db))


@bp.get("/audit")
@admin_required
def audit():
    rows = get_db().execute("SELECT a.action,a.target,a.detail,a.ip,a.created_at,u.username AS admin FROM audit a "
                            "LEFT JOIN users u ON u.id=a.admin_id ORDER BY a.id DESC LIMIT 300").fetchall()
    return jsonify(items=[dict(r) for r in rows])


@bp.get("/events")
@admin_required
def events():
    rows = get_db().execute("SELECT level,kind,message,ip,created_at FROM events ORDER BY id DESC LIMIT 300").fetchall()
    return jsonify(items=[dict(r) for r in rows])
