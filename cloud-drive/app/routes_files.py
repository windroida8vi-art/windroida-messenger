import math
import os
import subprocess
import shlex
import uuid

from flask import Blueprint, current_app, jsonify, request, send_file

from .db import get_db
from .errors import fail
from .fileops import purge_files, purge_folder
from .security import client_ip, current_user, login_required
from .services import (DANGEROUS_EXT, descendant_folders, ext_of, file_dict, folder_dict, folder_path, get_int,
                       get_setting, guess_mime, log_activity, now, reserved_bytes, sanitize_name, unique_name,
                       used_bytes)
from .storage import PREVIEW_MIMES, sniff_mime

bp = Blueprint("files", __name__, url_prefix="/api")


# ------------------------------------------------------------ helpers
def _own_folder(db, fid, uid, allow_trashed=False):
    if fid is None:
        return None
    if not isinstance(fid, int) or isinstance(fid, bool):
        fail("bad_request", "شناسه نامعتبر است", "Invalid id", 400)
    r = db.execute("SELECT * FROM folders WHERE id=? AND owner_id=?", (fid, uid)).fetchone()
    if not r or (r["trashed_at"] and not allow_trashed):
        fail("not_found", "پوشه پیدا نشد", "Folder not found", 404)
    return r


def _own_file(db, fid, uid, allow_trashed=False):
    r = db.execute("SELECT * FROM files WHERE id=? AND owner_id=?", (fid, uid)).fetchone()
    if not r or (r["trashed_at"] and not allow_trashed):
        fail("not_found", "فایل پیدا نشد", "File not found", 404)
    return r


def _ids(d, key):
    v = d.get(key) or []
    if not isinstance(v, list) or not all(isinstance(x, int) for x in v):
        fail("bad_request", "درخواست نامعتبر", "Bad request", 400)
    return v


def send_stored(row, inline=False):
    path = current_app.storage.path(row["stored_name"])
    if not path.exists():
        fail("file_missing", "فایل روی دیسک پیدا نشد", "File missing on disk", 404)
    if inline and row["mime"] in PREVIEW_MIMES:
        resp = send_file(path, mimetype=row["mime"], as_attachment=False, conditional=True, max_age=0,
                         download_name=row["name"])
    else:
        resp = send_file(path, mimetype="application/octet-stream", as_attachment=True, conditional=True,
                         max_age=0, download_name=row["name"])
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'self'"
    # inline previews revalidate on every request (ETag -> 304) so access is always re-checked; downloads are never cached
    resp.headers["Cache-Control"] = "private, no-cache" if inline else "private, no-store"
    return resp


# ------------------------------------------------------------ listing
@bp.get("/items")
@login_required
def items():
    db, u = get_db(), current_user()
    view = request.args.get("view", "files")
    q = (request.args.get("q") or "").strip().lower()
    sort = request.args.get("sort", "name")
    desc = request.args.get("order", "asc") == "desc"
    fid = request.args.get("folder_id", type=int)
    cur, path = None, []
    if view == "trash":
        folders = db.execute(
            "SELECT * FROM folders WHERE owner_id=? AND trashed_at IS NOT NULL AND (parent_id IS NULL OR parent_id "
            "NOT IN (SELECT id FROM folders WHERE trashed_at IS NOT NULL))", (u["id"],)).fetchall()
        files = db.execute(
            "SELECT * FROM files WHERE owner_id=? AND trashed_at IS NOT NULL AND (folder_id IS NULL OR folder_id "
            "NOT IN (SELECT id FROM folders WHERE trashed_at IS NOT NULL))", (u["id"],)).fetchall()
    elif q:
        folders = [r for r in db.execute("SELECT * FROM folders WHERE owner_id=? AND trashed_at IS NULL LIMIT 5000",
                                         (u["id"],)) if q in r["name"].lower()]
        files = [r for r in db.execute("SELECT * FROM files WHERE owner_id=? AND trashed_at IS NULL LIMIT 5000",
                                       (u["id"],)) if q in r["name"].lower()]
    else:
        cur = _own_folder(db, fid, u["id"])
        folders = db.execute("SELECT * FROM folders WHERE owner_id=? AND parent_id IS ? AND trashed_at IS NULL",
                             (u["id"], fid)).fetchall()
        files = db.execute("SELECT * FROM files WHERE owner_id=? AND folder_id IS ? AND trashed_at IS NULL",
                           (u["id"], fid)).fetchall()
        path = folder_path(db, fid)
    keys = {"name": lambda r: r["name"].lower(), "date": lambda r: r["created_at"],
            "size": lambda r: (r["size"] if "size" in r.keys() else 0), "type": lambda r: ext_of(r["name"])}
    kf = keys.get(sort, keys["name"])
    folders = sorted(folders, key=(lambda r: r["name"].lower()) if sort == "name" else
                     (lambda r: r["created_at"]) if sort == "date" else (lambda r: r["name"].lower()), reverse=desc)
    files = sorted(files, key=kf, reverse=desc)
    return jsonify(folders=[folder_dict(r) for r in folders], files=[file_dict(r) for r in files], path=path,
                   folder=folder_dict(cur) if cur else None)


@bp.get("/folders/tree")
@login_required
def folder_tree():
    rows = get_db().execute("SELECT id,name,parent_id FROM folders WHERE owner_id=? AND trashed_at IS NULL "
                            "ORDER BY name", (current_user()["id"],)).fetchall()
    return jsonify(folders=[dict(r) for r in rows])


@bp.get("/usage")
@login_required
def usage():
    db, u = get_db(), current_user()
    return jsonify(used=used_bytes(db, u["id"]), quota=u["quota_bytes"],
                   files=db.execute("SELECT COUNT(*) FROM files WHERE owner_id=? AND trashed_at IS NULL",
                                    (u["id"],)).fetchone()[0])


# ------------------------------------------------------------ folders
@bp.post("/folders")
@login_required
def create_folder():
    db, u = get_db(), current_user()
    d = request.get_json(silent=True) or {}
    parent = d.get("parent_id")
    _own_folder(db, parent, u["id"])
    name = unique_name(db, "folders", u["id"], parent, sanitize_name(d.get("name")), strict=True)
    cur = db.execute("INSERT INTO folders(owner_id,parent_id,name,created_at) VALUES(?,?,?,?)",
                     (u["id"], parent, name, now()))
    log_activity(db, u["id"], "folder_create", name, client_ip())
    return jsonify(folder_dict(db.execute("SELECT * FROM folders WHERE id=?", (cur.lastrowid,)).fetchone())), 201


@bp.patch("/folders/<int:fid>")
@login_required
def update_folder(fid):
    db, u = get_db(), current_user()
    f = _own_folder(db, fid, u["id"])
    d = request.get_json(silent=True) or {}
    name, parent = f["name"], f["parent_id"]
    if "parent_id" in d:
        parent = d["parent_id"]
        _own_folder(db, parent, u["id"])
        if parent is not None and parent in descendant_folders(db, fid):
            fail("bad_move", "نمی‌توان پوشه را داخل خودش منتقل کرد", "Cannot move a folder into itself", 400)
    if "name" in d:
        name = sanitize_name(d["name"])
    name = unique_name(db, "folders", u["id"], parent, name, exclude_id=fid, strict=True)
    db.execute("UPDATE folders SET name=?, parent_id=? WHERE id=?", (name, parent, fid))
    log_activity(db, u["id"], "folder_update", name, client_ip())
    return jsonify(folder_dict(db.execute("SELECT * FROM folders WHERE id=?", (fid,)).fetchone()))


# ------------------------------------------------------------ files
@bp.patch("/files/<int:fid>")
@login_required
def update_file(fid):
    db, u = get_db(), current_user()
    f = _own_file(db, fid, u["id"])
    d = request.get_json(silent=True) or {}
    name, folder = f["name"], f["folder_id"]
    if "folder_id" in d:
        folder = d["folder_id"]
        _own_folder(db, folder, u["id"])
    if "name" in d:
        name = sanitize_name(d["name"])
    name = unique_name(db, "files", u["id"], folder, name, exclude_id=fid, strict=True)
    db.execute("UPDATE files SET name=?, folder_id=? WHERE id=?", (name, folder, fid))
    log_activity(db, u["id"], "file_update", name, client_ip())
    return jsonify(file_dict(db.execute("SELECT * FROM files WHERE id=?", (fid,)).fetchone()))


@bp.get("/files/<int:fid>/download")
@login_required
def download(fid):
    db, u = get_db(), current_user()
    f = _own_file(db, fid, u["id"], allow_trashed=False)
    if request.headers.get("Range") is None:
        log_activity(db, u["id"], "download", f["name"], client_ip(), f["size"])
    return send_stored(f, inline=False)


@bp.get("/files/<int:fid>/preview")
@login_required
def preview(fid):
    f = _own_file(get_db(), fid, current_user()["id"])
    if f["mime"] not in PREVIEW_MIMES:
        fail("not_previewable", "پیش‌نمایش برای این فایل ممکن نیست", "No preview for this file", 415)
    return send_stored(f, inline=True)


# ------------------------------------------------------------ trash
def _trash_folder(db, fid, ts):
    ids = descendant_folders(db, fid)
    q = ",".join("?" * len(ids))
    db.execute("UPDATE folders SET trashed_at=? WHERE id IN (%s) AND trashed_at IS NULL" % q, [ts] + ids)
    db.execute("UPDATE files SET trashed_at=? WHERE folder_id IN (%s) AND trashed_at IS NULL" % q, [ts] + ids)


@bp.post("/items/trash")
@login_required
def trash():
    db, u = get_db(), current_user()
    d = request.get_json(silent=True) or {}
    files, folders = _ids(d, "files"), _ids(d, "folders")
    enabled = get_setting(db, "trash_enabled") == "1"
    ts, count = now(), 0
    for fid in files:
        f = _own_file(db, fid, u["id"])
        if enabled:
            db.execute("UPDATE files SET trashed_at=? WHERE id=?", (ts, fid))
        else:
            purge_files(db, current_app.storage, [fid])
        log_activity(db, u["id"], "trash" if enabled else "delete", f["name"], client_ip())
        count += 1
    for fid in folders:
        f = _own_folder(db, fid, u["id"])
        if enabled:
            _trash_folder(db, fid, ts)
        else:
            purge_folder(db, current_app.storage, fid)
        log_activity(db, u["id"], "trash" if enabled else "delete", f["name"], client_ip())
        count += 1
    return jsonify(ok=True, count=count)


@bp.post("/items/restore")
@login_required
def restore():
    db, u = get_db(), current_user()
    d = request.get_json(silent=True) or {}
    for fid in _ids(d, "files"):
        f = _own_file(db, fid, u["id"], allow_trashed=True)
        folder = f["folder_id"]
        if folder is not None:
            p = db.execute("SELECT trashed_at FROM folders WHERE id=?", (folder,)).fetchone()
            if not p or p["trashed_at"]:
                folder = None
        name = unique_name(db, "files", u["id"], folder, f["name"], exclude_id=fid)
        db.execute("UPDATE files SET trashed_at=NULL, folder_id=?, name=? WHERE id=?", (folder, name, fid))
        log_activity(db, u["id"], "restore", name, client_ip())
    for fid in _ids(d, "folders"):
        f = _own_folder(db, fid, u["id"], allow_trashed=True)
        parent = f["parent_id"]
        if parent is not None:
            p = db.execute("SELECT trashed_at FROM folders WHERE id=?", (parent,)).fetchone()
            if not p or p["trashed_at"]:
                parent = None
        ts = f["trashed_at"]
        name = unique_name(db, "folders", u["id"], parent, f["name"], exclude_id=fid)
        ids = descendant_folders(db, fid)
        q = ",".join("?" * len(ids))
        db.execute("UPDATE folders SET trashed_at=NULL WHERE id IN (%s) AND trashed_at=?" % q, ids + [ts])
        db.execute("UPDATE files SET trashed_at=NULL WHERE folder_id IN (%s) AND trashed_at=?" % q, ids + [ts])
        db.execute("UPDATE folders SET parent_id=?, name=? WHERE id=?", (parent, name, fid))
        log_activity(db, u["id"], "restore", name, client_ip())
    return jsonify(ok=True)


@bp.post("/items/purge")
@login_required
def purge():
    """Permanently delete items that are already in the trash (or everything in it with {"all": true})."""
    db, u = get_db(), current_user()
    d = request.get_json(silent=True) or {}
    files, folders = _ids(d, "files"), _ids(d, "folders")
    if d.get("all") is True:
        files = [r["id"] for r in db.execute(
            "SELECT id FROM files WHERE owner_id=? AND trashed_at IS NOT NULL AND (folder_id IS NULL OR folder_id "
            "NOT IN (SELECT id FROM folders WHERE trashed_at IS NOT NULL))", (u["id"],))]
        folders = [r["id"] for r in db.execute(
            "SELECT id FROM folders WHERE owner_id=? AND trashed_at IS NOT NULL AND (parent_id IS NULL OR parent_id "
            "NOT IN (SELECT id FROM folders WHERE trashed_at IS NOT NULL))", (u["id"],))]
    for fid in files:
        f = _own_file(db, fid, u["id"], allow_trashed=True)
        if not f["trashed_at"]:
            fail("not_in_trash", "ابتدا فایل را به سطل زباله ببرید", "Move it to the trash first", 400)
        purge_files(db, current_app.storage, [fid])
        log_activity(db, u["id"], "purge", f["name"], client_ip())
    for fid in folders:
        f = _own_folder(db, fid, u["id"], allow_trashed=True)
        if not f["trashed_at"]:
            fail("not_in_trash", "ابتدا پوشه را به سطل زباله ببرید", "Move it to the trash first", 400)
        purge_folder(db, current_app.storage, fid)
        log_activity(db, u["id"], "purge", f["name"], client_ip())
    return jsonify(ok=True)


# ------------------------------------------------------------ chunked / resumable upload
def _upload_row(db, upload_id, uid):
    r = db.execute("SELECT * FROM uploads WHERE id=? AND owner_id=?", (upload_id, uid)).fetchone()
    if not r:
        fail("not_found", "آپلود پیدا نشد (ممکن است منقضی شده باشد)", "Upload not found (maybe expired)", 404)
    return r


def _status(db, r):
    got = [x["idx"] for x in db.execute("SELECT idx FROM upload_chunks WHERE upload_id=? ORDER BY idx", (r["id"],))]
    return {"upload_id": r["id"], "chunk_size": r["chunk_size"], "total_chunks": r["total_chunks"],
            "size": r["size"], "received": got}


@bp.post("/uploads")
@login_required
def upload_init():
    db, u = get_db(), current_user()
    d = request.get_json(silent=True) or {}
    name = sanitize_name(d.get("name"))
    size = d.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        fail("bad_size", "حجم فایل نامعتبر است", "Invalid size", 400)
    max_up = get_int(db, "max_upload_bytes")
    if max_up and size > max_up:
        fail("too_large", "حجم فایل از حداکثر مجاز بیشتر است", "File exceeds the maximum upload size", 413,
             max_bytes=max_up)
    folder = d.get("folder_id")
    _own_folder(db, folder, u["id"])
    db.execute("BEGIN IMMEDIATE")  # take the write lock BEFORE reading usage, so parallel inits cannot all pass the quota check
    if used_bytes(db, u["id"]) + reserved_bytes(db, u["id"]) + size > u["quota_bytes"]:
        fail("quota_exceeded", "فضای ذخیره‌سازی شما کافی نیست", "Storage quota exceeded", 413)
    if size > current_app.storage.free_bytes() - 50 * 1024 * 1024:
        fail("disk_full", "فضای دیسک سرور کافی نیست", "Server disk is full", 507)
    cs = current_app.config["CHUNK_SIZE"]
    total = max(1, math.ceil(size / cs))
    uid = uuid.uuid4().hex
    db.execute("INSERT INTO uploads(id,owner_id,folder_id,name,size,chunk_size,total_chunks,created_at,updated_at) "
               "VALUES(?,?,?,?,?,?,?,?,?)", (uid, u["id"], folder, name, size, cs, total, now(), now()))
    return jsonify(_status(db, _upload_row(db, uid, u["id"]))), 201


@bp.get("/uploads/<upload_id>")
@login_required
def upload_status(upload_id):
    db = get_db()
    return jsonify(_status(db, _upload_row(db, upload_id, current_user()["id"])))


@bp.put("/uploads/<upload_id>/chunks/<int:idx>")
@login_required
def upload_chunk(upload_id, idx):
    db = get_db()
    r = _upload_row(db, upload_id, current_user()["id"])
    if idx < 0 or idx >= r["total_chunks"]:
        fail("bad_chunk", "شماره قطعه نامعتبر است", "Invalid chunk index", 400)
    expected = r["chunk_size"] if idx < r["total_chunks"] - 1 else r["size"] - idx * r["chunk_size"]
    data = request.get_data()
    if len(data) != expected:
        fail("bad_chunk", "اندازه قطعه نامعتبر است", "Invalid chunk size", 400, expected=expected)
    current_app.storage.write_chunk(upload_id, idx, data)
    db.execute("INSERT INTO upload_chunks(upload_id,idx,size) VALUES(?,?,?) ON CONFLICT(upload_id,idx) "
               "DO UPDATE SET size=excluded.size", (upload_id, idx, len(data)))
    db.execute("UPDATE uploads SET updated_at=? WHERE id=?", (now(), upload_id))
    return jsonify(ok=True, idx=idx)


def _scan_ok(path):
    cmd = current_app.config.get("SCAN_COMMAND")
    if not cmd:
        return True
    args = [a.replace("{path}", str(path)) for a in shlex.split(cmd, posix=(os.name != "nt"))]
    try:
        return subprocess.run(args, capture_output=True, timeout=600).returncode == 0
    except Exception:
        return False


@bp.post("/uploads/<upload_id>/complete")
@login_required
def upload_complete(upload_id):
    db, u = get_db(), current_user()
    db.execute("BEGIN IMMEDIATE")
    r = _upload_row(db, upload_id, u["id"])
    got = {x["idx"] for x in db.execute("SELECT idx FROM upload_chunks WHERE upload_id=?", (upload_id,))}
    if got != set(range(r["total_chunks"])):
        fail("incomplete", "همه قطعه‌ها دریافت نشده‌اند", "Some chunks are missing", 409, received=sorted(got))
    if used_bytes(db, u["id"]) + r["size"] > u["quota_bytes"]:
        fail("quota_exceeded", "فضای ذخیره‌سازی شما کافی نیست", "Storage quota exceeded", 413)
    # claim the upload atomically: only ONE concurrent /complete can win, the others get 404
    if db.execute("DELETE FROM uploads WHERE id=?", (upload_id,)).rowcount != 1:
        fail("not_found", "آپلود پیدا نشد (ممکن است منقضی شده باشد)", "Upload not found (maybe expired)", 404)
    db.commit()
    storage = current_app.storage
    stored = storage.new_name()
    path = storage.assemble(upload_id, r["total_chunks"], stored)
    if path.stat().st_size != r["size"]:
        storage.delete(stored)
        storage.drop_upload(upload_id)
        fail("size_mismatch", "اندازه نهایی فایل با اعلام‌شده برابر نیست", "Final size mismatch", 400)
    if not _scan_ok(path):
        storage.delete(stored)
        storage.drop_upload(upload_id)
        fail("malware", "فایل توسط اسکنر ایمنی رد شد", "File rejected by the scanner", 422)
    mime = sniff_mime(path) or guess_mime(r["name"])
    db.execute("BEGIN IMMEDIATE")
    if used_bytes(db, u["id"]) + r["size"] > u["quota_bytes"]:  # re-check: the reservation was released at claim time
        db.rollback()
        storage.delete(stored)
        storage.drop_upload(upload_id)
        fail("quota_exceeded", "فضای ذخیره‌سازی شما کافی نیست", "Storage quota exceeded", 413)
    folder = r["folder_id"]
    if folder is not None and not db.execute("SELECT 1 FROM folders WHERE id=? AND trashed_at IS NULL",
                                             (folder,)).fetchone():
        folder = None
    name = unique_name(db, "files", u["id"], folder, r["name"])
    cur = db.execute("INSERT INTO files(owner_id,folder_id,name,stored_name,size,mime,suspicious,created_at) "
                     "VALUES(?,?,?,?,?,?,?,?)",
                     (u["id"], folder, name, stored, r["size"], mime, 1 if ext_of(name) in DANGEROUS_EXT else 0, now()))
    log_activity(db, u["id"], "upload", name, client_ip(), r["size"])
    db.commit()
    storage.drop_upload(upload_id)
    return jsonify(file_dict(db.execute("SELECT * FROM files WHERE id=?", (cur.lastrowid,)).fetchone())), 201


@bp.delete("/uploads/<upload_id>")
@login_required
def upload_cancel(upload_id):
    db = get_db()
    _upload_row(db, upload_id, current_user()["id"])
    db.execute("DELETE FROM uploads WHERE id=?", (upload_id,))
    current_app.storage.drop_upload(upload_id)
    return jsonify(ok=True)
