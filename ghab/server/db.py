"""دیتابیس: اتصال، میان‌بُرها و مهاجرت‌های شماره‌دار (migrations)."""
import glob
import os
import re
import sqlite3
import time

from flask import g

from . import config


def db():
    if 'db' not in g:
        g.db = sqlite3.connect(config.DB_PATH, timeout=15)
        g.db.row_factory = sqlite3.Row
        g.db.execute('pragma foreign_keys=on')
        g.db.execute('pragma synchronous=full')   # هر تماشا/لایک واقعاً روی دیسک نوشته شود؛ با خاموشی ناگهانی کامپیوتر هم نپرد
    return g.db


def close_db(_exc=None):
    d = g.pop('db', None)
    if d:
        d.close()


def q(sql, *a):
    return db().execute(sql, a).fetchall()


def q1(sql, *a):
    return db().execute(sql, a).fetchone()


def run(sql, *a):
    c = db().execute(sql, a)
    db().commit()
    return c


def migrate():
    """فایل‌های migrations/NNN_*.sql را به‌ترتیب اجرا می‌کند و شماره را در دیتابیس نگه می‌دارد.
    قبل از هر آپدیتِ دیتابیسِ موجود، خودکار یک نسخه پشتیبان در data/backups می‌سازد."""
    files = []
    for p in glob.glob(os.path.join(config.MIGRATIONS_DIR, '*.sql')):
        m = re.match(r'(\d+)_', os.path.basename(p))
        if m:
            files.append((int(m.group(1)), p))
    files.sort()
    con = sqlite3.connect(config.DB_PATH)
    con.execute('pragma synchronous=full')
    con.execute('pragma journal_mode=wal')  # خواندن و نوشتن هم‌زمان بدون قفل
    cur = con.execute('pragma user_version').fetchone()[0]
    pending = [(n, p) for n, p in files if n > cur]
    if not config.BACKUP:  # پشتیبان‌های خودکار قبلی هم پاک می‌شوند تا فضا آزاد شود
        for old in glob.glob(os.path.join(config.BACKUP_DIR, 'ghab-v*.db')):
            try:
                os.remove(old)
            except OSError:
                pass
    if config.BACKUP and pending and cur > 0:
        dst = os.path.join(config.BACKUP_DIR, f'ghab-v{cur}-{time.strftime("%Y%m%d-%H%M%S")}.db')
        bk = sqlite3.connect(dst)
        con.backup(bk)
        bk.close()
        for old in sorted(glob.glob(os.path.join(config.BACKUP_DIR, 'ghab-v*.db')))[:-10]:
            os.remove(old)  # فقط ۱۰ پشتیبان آخر نگه داشته می‌شود
    for n, p in pending:
        with open(p, encoding='utf-8') as f:
            con.executescript(f.read())
        con.execute(f'pragma user_version={n}')
        con.commit()
    con.close()
    return pending and pending[-1][0] or cur
