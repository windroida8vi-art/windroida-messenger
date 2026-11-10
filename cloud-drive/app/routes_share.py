import secrets

from flask import Blueprint, current_app, jsonify, request, send_from_directory, session

from .db import get_db
from .errors import fail
from .routes_files import _own_file, send_stored
from .security import (check_password_policy, client_ip, current_user, hash_password, limit_or_429, login_required,
                       verify_password)
from .services import get_int, iso_in, log_activity, now

bp = Blueprint("share", __name__)


def _share_dict(r):
    return {"id": r["id"], "token": r["token"], "url": "/s/" + r["token"], "file_id": r["file_id"],
            "file_name": r["file_name"] if "file_name" in r.keys() else None,
            "has_password": bool(r["password_hash"]), "expires_at": r["expires_at"], "active": bool(r["active"]),
            "created_at": r["created_at"], "downloads": r["downloads"],
            "expired": bool(r["expires_at"] and r["expires_at"] < now())}


@bp.post("/api/files/<int:fid>/shares")
@login_required
def create_share(fid):
    db, u = get_db(), current_user()
    f = _own_file(db, fid, u["id"])
    d = request.get_json(silent=True) or {}
    pw, hours = d.get("password") or None, d.get("expires_hours")
    if pw is not None:
        if not isinstance(pw, str) or len(pw) < 4 or len(pw) > 128:
            fail("weak_password", "رمز لینک باید حداقل ۴ نویسه باشد", "Link password needs 4+ characters", 400)
    if hours is not None:
        if not isinstance(hours, int) or not 1 <= hours <= 24 * 365:
            fail("bad_expiry", "مدت انقضا نامعتبر است", "Invalid expiry", 400)
    cur = db.execute("INSERT INTO shares(token,file_id,owner_id,password_hash,expires_at,created_at) VALUES(?,?,?,?,?,?)",
                     (secrets.token_urlsafe(24), fid, u["id"], hash_password(pw) if pw else None,
                      iso_in(hours=hours) if hours else None, now()))
    log_activity(db, u["id"], "share_create", f["name"], client_ip())
    r = db.execute("SELECT s.*, f.name AS file_name FROM shares s JOIN files f ON f.id=s.file_id WHERE s.id=?",
                   (cur.lastrowid,)).fetchone()
    return jsonify(_share_dict(r)), 201


@bp.get("/api/shares")
@login_required
def list_shares():
    rows = get_db().execute("SELECT s.*, f.name AS file_name FROM shares s JOIN files f ON f.id=s.file_id "
                            "WHERE s.owner_id=? AND f.trashed_at IS NULL ORDER BY s.id DESC", (current_user()["id"],))
    return jsonify(items=[_share_dict(r) for r in rows])


@bp.delete("/api/shares/<int:sid>")
@login_required
def disable_share(sid):
    db, u = get_db(), current_user()
    r = db.execute("SELECT s.*, f.name AS file_name FROM shares s JOIN files f ON f.id=s.file_id "
                   "WHERE s.id=? AND s.owner_id=?", (sid, u["id"])).fetchone()
    if not r:
        fail("not_found", "لینک پیدا نشد", "Link not found", 404)
    db.execute("UPDATE shares SET active=0 WHERE id=?", (sid,))
    log_activity(db, u["id"], "share_disable", r["file_name"], client_ip())
    return jsonify(ok=True)


# ------------------------------------------------------------ public side (no login)
def _public(token):
    db = get_db()
    limit_or_429("pub:%s" % client_ip(), get_int(db, "rate_public_per_min"), 60, "public rate")
    r = db.execute("SELECT s.*, f.name AS name, f.size AS size, f.mime AS mime, f.stored_name AS stored_name, "
                   "f.trashed_at AS ftrash, u.is_active AS uactive FROM shares s JOIN files f ON f.id=s.file_id "
                   "JOIN users u ON u.id=s.owner_id WHERE s.token=?", (token,)).fetchone()
    if not r or not r["active"] or r["ftrash"] or not r["uactive"]:
        fail("not_found", "این لینک وجود ندارد یا غیرفعال شده است", "This link does not exist or was disabled", 404)
    if r["expires_at"] and r["expires_at"] < now():
        fail("expired", "این لینک منقضی شده است", "This link has expired", 410)
    return r


def _unlocked(r):
    return not r["password_hash"] or r["token"] in session.get("unlocked", [])


@bp.get("/s/<token>")
def share_page(token):
    return send_from_directory(current_app.static_folder, "public.html", max_age=0)


@bp.get("/api/public/<token>")
def public_info(token):
    r = _public(token)
    if not _unlocked(r):  # protected links reveal nothing (not even the file name) before the password is accepted
        return jsonify(needs_password=True, unlocked=False)
    return jsonify(name=r["name"], size=r["size"], mime=r["mime"], needs_password=bool(r["password_hash"]),
                   unlocked=True, previewable=r["mime"].startswith("image/") or r["mime"] == "application/pdf",
                   expires_at=r["expires_at"])


@bp.post("/api/public/<token>/unlock")
def public_unlock(token):
    r = _public(token)
    limit_or_429("unlock:%s:%s" % (client_ip(), token[:12]), 6, 300, "share unlock")
    pw = (request.get_json(silent=True) or {}).get("password")
    if not r["password_hash"] or (isinstance(pw, str) and verify_password(pw, r["password_hash"])):
        lst = [t for t in session.get("unlocked", []) if t != token][-19:] + [token]
        session["unlocked"] = lst
        return jsonify(ok=True)
    fail("bad_password", "رمز نادرست است", "Wrong password", 403)


@bp.get("/api/public/<token>/download")
def public_download(token):
    db = get_db()
    r = _public(token)
    if not _unlocked(r):
        fail("password_required", "رمز عبور لازم است", "Password required", 403)
    if request.headers.get("Range") is None:
        db.execute("UPDATE shares SET downloads=downloads+1 WHERE id=?", (r["id"],))
        log_activity(db, r["owner_id"], "public_download", r["name"], client_ip(), r["size"])
    return send_stored(r, inline=request.args.get("inline") == "1")
