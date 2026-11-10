#!/usr/bin/env python3
"""Management CLI: create the first admin, reset passwords, backup/restore, maintenance."""
import argparse
import getpass
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from app import create_app
from app import db as dbm
from app.fileops import cleanup_stale_uploads, purge_expired_files, purge_expired_trash
from app.security import check_password_policy, hash_password
from app.services import get_int, now
from app.errors import ApiError


def _ask_password():
    while True:
        p1 = getpass.getpass("Password / رمز عبور: ")
        p2 = getpass.getpass("Repeat / تکرار رمز: ")
        if p1 != p2:
            print("Passwords do not match / رمزها یکسان نیستند")
            continue
        return p1


def cmd_create_admin(app, a):
    with app.app_context():
        c = dbm.connect(app.config["DB_PATH"])
        username = a.username or input("Admin username / نام کاربری مدیر: ").strip()
        if c.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            sys.exit("User already exists / این کاربر قبلاً وجود دارد")
        pw = _ask_password()
        try:
            check_password_policy(pw, username)
        except ApiError as e:
            sys.exit("%s / %s" % (e.en, e.fa))
        quota = get_int(c, "default_quota_bytes") if False else app.config["DEFAULT_QUOTA_MB"] * 1024 * 1024
        c.execute("INSERT INTO users(username,display_name,password_hash,role,quota_bytes,created_at) VALUES(?,?,?,?,?,?)",
                  (username, username, hash_password(pw), "admin", quota, now()))
        c.commit()
        print("Admin '%s' created / مدیر ساخته شد" % username)


def cmd_reset_password(app, a):
    with app.app_context():
        c = dbm.connect(app.config["DB_PATH"])
        row = c.execute("SELECT id FROM users WHERE username=?", (a.username,)).fetchone()
        if not row:
            sys.exit("No such user / چنین کاربری نیست")
        pw = _ask_password()
        try:
            check_password_policy(pw, a.username)
        except ApiError as e:
            sys.exit("%s / %s" % (e.en, e.fa))
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(pw), row["id"]))
        c.execute("UPDATE sessions SET revoked=1 WHERE user_id=?", (row["id"],))
        c.commit()
        print("Password updated / رمز عبور تغییر کرد")


def cmd_set_quota(app, a):
    c = dbm.connect(app.config["DB_PATH"])
    n = c.execute("UPDATE users SET quota_bytes=?", (a.mb * 1024 * 1024,)).rowcount
    c.commit()
    print("Quota set to %d MB for %d account(s) / سهمیه %d مگابایت برای %d حساب" % (a.mb, n, a.mb, n))


def cmd_has_admin(app, a):
    c = dbm.connect(app.config["DB_PATH"])
    sys.exit(0 if c.execute("SELECT 1 FROM users WHERE role='admin' LIMIT 1").fetchone() else 1)


def cmd_backup(app, a):
    out_dir = Path(a.out or "backups")
    out_dir.mkdir(parents=True, exist_ok=True)
    name = out_dir / ("backup-%s.zip" % datetime.now().strftime("%Y%m%d-%H%M%S"))
    snap = app.config["DATA_DIR"] / "backup-snapshot.db"
    src = dbm.connect(app.config["DB_PATH"])
    dst = dbm.connect(snap)
    src.backup(dst)  # consistent online copy
    dst.close()
    src.close()
    with zipfile.ZipFile(name, "w", zipfile.ZIP_STORED) as z:
        z.write(snap, "cloud_drive.db")
        for p in app.config["UPLOAD_DIR"].rglob("*"):
            if p.is_file() and not p.name.endswith(".tmp"):
                z.write(p, "uploads/" + str(p.relative_to(app.config["UPLOAD_DIR"])))
        sk = app.config["DATA_DIR"] / "secret.key"
        if sk.exists():
            z.write(sk, "secret.key")
    snap.unlink()
    print("Backup written: %s" % name)


def cmd_restore(app, a):
    data = app.config["DATA_DIR"]
    if (data / "cloud_drive.db").stat().st_size > 0 and not a.into_empty_only_ok:
        pass
    target = Path(a.target).resolve()
    if target.exists() and any(target.iterdir()):
        sys.exit("Target directory is not empty. Restore only into a NEW or empty directory (nothing is overwritten).\n"
                 "پوشه مقصد خالی نیست؛ بازیابی فقط در پوشه جدید/خالی انجام می‌شود تا چیزی بازنویسی نشود.")
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(a.zipfile) as z:
        for m in z.namelist():
            dest = (target / m).resolve()
            if target not in dest.parents:
                sys.exit("Unsafe path in archive: %s" % m)
        z.extractall(target)
    print("Restored into %s. Start with CD_DATA_DIR=%s" % (target, target))
    print("(uploads/ goes inside as data/uploads — see README)")


def cmd_maintenance(app, a):
    c = dbm.connect(app.config["DB_PATH"])
    n1 = cleanup_stale_uploads(c, app.storage, get_int_safe(c, "incomplete_upload_hours", 24))
    n2 = purge_expired_trash(c, app.storage, get_int_safe(c, "trash_retention_days", 30))
    n3 = purge_expired_files(c, app.storage, get_int_safe(c, "file_retention_days", 20))
    print("stale uploads removed: %d, expired trash items purged: %d, files past retention deleted: %d" % (n1, n2, n3))


def get_int_safe(c, key, default):
    r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    try:
        return int(r["value"]) if r else default
    except ValueError:
        return default


def main():
    p = argparse.ArgumentParser(description="Cloud Drive management")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("create-admin"); s.add_argument("--username"); s.set_defaults(f=cmd_create_admin)
    s = sub.add_parser("reset-password"); s.add_argument("username"); s.set_defaults(f=cmd_reset_password)
    s = sub.add_parser("set-quota-all"); s.add_argument("mb", type=int); s.set_defaults(f=cmd_set_quota)
    s = sub.add_parser("has-admin"); s.set_defaults(f=cmd_has_admin)
    s = sub.add_parser("backup"); s.add_argument("--out"); s.set_defaults(f=cmd_backup)
    s = sub.add_parser("restore"); s.add_argument("zipfile"); s.add_argument("target")
    s.set_defaults(f=cmd_restore, into_empty_only_ok=True)
    s = sub.add_parser("maintenance"); s.set_defaults(f=cmd_maintenance)
    a = p.parse_args()
    app = create_app(HOUSEKEEPING=False)
    a.f(app, a)


if __name__ == "__main__":
    main()
