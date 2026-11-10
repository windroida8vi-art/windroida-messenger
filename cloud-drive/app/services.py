"""Shared helpers: time, settings, quota, activity/audit/event logging, name handling, serializers."""
import mimetypes
import re
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath

from flask import current_app

from .errors import fail
from .storage import PREVIEW_MIMES


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def iso_in(**kw):
    return (datetime.now(timezone.utc) + timedelta(**kw)).isoformat(timespec="seconds")


def iso_ago(**kw):
    return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat(timespec="seconds")


# ---------------------------------------------------------------- settings
def setting_defaults():
    c = current_app.config
    return {
        "service_name": "Cloud Drive",
        "logo_data": "",
        "max_upload_bytes": str(c["MAX_UPLOAD_MB"] * 1024 * 1024),
        "default_quota_bytes": str(c["DEFAULT_QUOTA_MB"] * 1024 * 1024),
        "rate_login_per_min": "60",   # per IP (many people may share one router IP); each username is still limited separately
        "rate_api_per_min": "0",      # 0 = no request-rate limit for logged-in transfers
        "rate_public_per_min": "600",
        "file_retention_days": "0",   # 0 = files are kept forever (optional global auto-delete, set in Admin > Settings)
        "trash_enabled": "1",
        "trash_retention_days": "20",  # items in the trash are deleted for good after this many days
        "registration_open": "1",
        "incomplete_upload_hours": "24",
    }


def get_settings(db):
    s = setting_defaults()
    for r in db.execute("SELECT key, value FROM settings"):
        if r["key"] in s:
            s[r["key"]] = r["value"]
    return s


def get_setting(db, key):
    r = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else setting_defaults()[key]


def get_int(db, key):
    try:
        return int(get_setting(db, key))
    except ValueError:
        return int(setting_defaults()[key])


def set_setting(db, key, value):
    db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, str(value)))


# ---------------------------------------------------------------- logging
def log_activity(db, uid, action, detail="", ip=None, nbytes=0):
    db.execute("INSERT INTO activity(user_id,action,detail,ip,bytes,created_at) VALUES(?,?,?,?,?,?)",
               (uid, action, (detail or "")[:300], ip, nbytes, now()))


def log_audit(db, admin_id, action, target="", detail="", ip=None):
    db.execute("INSERT INTO audit(admin_id,action,target,detail,ip,created_at) VALUES(?,?,?,?,?,?)",
               (admin_id, action, str(target)[:200], (detail or "")[:500], ip, now()))


def log_event(db, level, kind, message="", ip=None):
    """Security / system events. Never pass passwords or tokens here."""
    db.execute("INSERT INTO events(level,kind,message,ip,created_at) VALUES(?,?,?,?,?)",
               (level, kind, (message or "")[:500], ip, now()))


# ---------------------------------------------------------------- quota
def used_bytes(db, uid):
    return db.execute("SELECT COALESCE(SUM(size),0) FROM files WHERE owner_id=?", (uid,)).fetchone()[0]


def reserved_bytes(db, uid):
    return db.execute("SELECT COALESCE(SUM(size),0) FROM uploads WHERE owner_id=?", (uid,)).fetchone()[0]


# ---------------------------------------------------------------- names
def sanitize_name(name):
    if not isinstance(name, str):
        fail("bad_name", "نام نامعتبر است", "Invalid name", 400)
    name = (name or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip().rstrip(" .")
    if not name or name in (".", ".."):
        fail("bad_name", "نام نامعتبر است", "Invalid name", 400)
    return name[:255]


def unique_name(db, table, owner, parent_id, name, exclude_id=None, strict=False):
    col = "folder_id" if table == "files" else "parent_id"
    sql = "SELECT name FROM %s WHERE owner_id=? AND %s IS ? AND trashed_at IS NULL" % (table, col)
    args = [owner, parent_id]
    if exclude_id:
        sql += " AND id!=?"
        args.append(exclude_id)
    taken = {r["name"].lower() for r in db.execute(sql, args)}
    if name.lower() not in taken:
        return name
    if strict:
        fail("name_exists", "این نام قبلاً استفاده شده است", "Name already exists", 409)
    p = PurePosixPath(name)
    stem, ext = (p.stem, p.suffix) if table == "files" and p.suffix else (name, "")
    n = 1
    while True:
        cand = "%s (%d)%s" % (stem, n, ext)
        if cand.lower() not in taken:
            return cand[:255]
        n += 1


def descendant_folders(db, folder_id):
    rows = db.execute(
        "WITH RECURSIVE t(id) AS (SELECT ? UNION ALL SELECT f.id FROM folders f JOIN t ON f.parent_id=t.id) "
        "SELECT id FROM t", (folder_id,)).fetchall()
    return [r["id"] for r in rows]


def folder_path(db, folder_id):
    out, seen = [], set()
    while folder_id and folder_id not in seen:
        seen.add(folder_id)
        r = db.execute("SELECT id,name,parent_id FROM folders WHERE id=?", (folder_id,)).fetchone()
        if not r:
            break
        out.append({"id": r["id"], "name": r["name"]})
        folder_id = r["parent_id"]
    return list(reversed(out))


# ---------------------------------------------------------------- serializers
DANGEROUS_EXT = {".exe", ".bat", ".cmd", ".com", ".scr", ".msi", ".ps1", ".vbs", ".js", ".jse", ".wsf",
                 ".jar", ".sh", ".dll", ".lnk", ".hta", ".reg", ".apk"}


def ext_of(name):
    return PurePosixPath(name).suffix.lower()


def guess_mime(name):
    m = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return "application/octet-stream" if m in PREVIEW_MIMES else m


def file_dict(r):
    return {"id": r["id"], "name": r["name"], "size": r["size"], "mime": r["mime"], "folder_id": r["folder_id"],
            "created_at": r["created_at"], "trashed_at": r["trashed_at"], "suspicious": bool(r["suspicious"]),
            "previewable": r["mime"] in PREVIEW_MIMES}


def folder_dict(r):
    return {"id": r["id"], "name": r["name"], "parent_id": r["parent_id"], "created_at": r["created_at"],
            "trashed_at": r["trashed_at"]}


def user_dict(r):
    return {"id": r["id"], "username": r["username"], "display_name": r["display_name"] or "",
            "email": r["email"] or "", "role": r["role"], "created_at": r["created_at"]}
