"""Permanent deletion + housekeeping (stale uploads, expired trash). Used by routes, admin and the background thread."""
from .services import descendant_folders, iso_ago, now


def purge_files(db, storage, file_ids):
    file_ids = list(file_ids)
    if not file_ids:
        return 0
    q = ",".join("?" * len(file_ids))
    names = [r["stored_name"] for r in db.execute("SELECT stored_name FROM files WHERE id IN (%s)" % q, file_ids)]
    db.execute("DELETE FROM files WHERE id IN (%s)" % q, file_ids)  # shares cascade
    db.commit()
    for n in names:
        storage.delete(n)
    return len(names)


def purge_folder(db, storage, folder_id):
    ids = descendant_folders(db, folder_id)
    q = ",".join("?" * len(ids))
    fids = [r["id"] for r in db.execute("SELECT id FROM files WHERE folder_id IN (%s)" % q, ids)]
    n = purge_files(db, storage, fids)
    db.execute("DELETE FROM folders WHERE id=?", (folder_id,))  # children cascade
    return n


def cleanup_stale_uploads(db, storage, hours):
    cutoff = iso_ago(hours=hours)
    stale = [r["id"] for r in db.execute("SELECT id FROM uploads WHERE updated_at<?", (cutoff,))]
    for uid in stale:
        db.execute("DELETE FROM uploads WHERE id=?", (uid,))
        storage.drop_upload(uid)
    known = {r["id"] for r in db.execute("SELECT id FROM uploads")}
    for d in storage.list_upload_dirs():  # orphan staging dirs (older than the window: no DB row at all)
        if d not in known:
            storage.drop_upload(d)
    db.commit()
    return len(stale)


def purge_expired_files(db, storage, days):
    """Retention policy: permanently delete every file older than `days` (0 disables). Share links die with the file."""
    if not days or days <= 0:
        return 0
    old = [r["id"] for r in db.execute("SELECT id FROM files WHERE created_at<?", (iso_ago(days=days),))]
    n = purge_files(db, storage, old)
    if n:
        db.execute("INSERT INTO events(level,kind,message,ip,created_at) VALUES('info','retention',?,NULL,?)",
                   ("auto-deleted %d file(s) older than %d days" % (n, days), now()))
        db.commit()
    return n


def purge_expired_trash(db, storage, days):
    cutoff = iso_ago(days=days)
    n = 0
    old_files = [r["id"] for r in db.execute("SELECT id FROM files WHERE trashed_at IS NOT NULL AND trashed_at<?",
                                              (cutoff,))]
    n += purge_files(db, storage, old_files)
    for r in db.execute("SELECT id FROM folders WHERE trashed_at IS NOT NULL AND trashed_at<? AND "
                        "(parent_id IS NULL OR parent_id NOT IN (SELECT id FROM folders WHERE trashed_at IS NOT NULL))",
                        (cutoff,)).fetchall():
        n += purge_folder(db, storage, r["id"])
    db.commit()
    return n
