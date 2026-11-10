"""SQLite access + versioned migrations (PRAGMA user_version). Schema is plain SQL so it ports to PostgreSQL easily."""
import sqlite3

from flask import current_app, g

MIGRATIONS = [
    """
CREATE TABLE users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE COLLATE NOCASE,
  email TEXT, display_name TEXT,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')),
  is_active INTEGER NOT NULL DEFAULT 1,
  banned_reason TEXT,
  quota_bytes INTEGER NOT NULL,
  created_at TEXT NOT NULL, last_login TEXT);
CREATE TABLE sessions(
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  csrf TEXT NOT NULL, created_at TEXT NOT NULL, last_seen TEXT NOT NULL, ip TEXT,
  revoked INTEGER NOT NULL DEFAULT 0);
CREATE INDEX ix_sessions_user ON sessions(user_id);
CREATE TABLE folders(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  parent_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
  name TEXT NOT NULL, created_at TEXT NOT NULL, trashed_at TEXT);
CREATE INDEX ix_folders_owner ON folders(owner_id, parent_id);
CREATE TABLE files(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  folder_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
  name TEXT NOT NULL, stored_name TEXT NOT NULL UNIQUE,
  size INTEGER NOT NULL, mime TEXT NOT NULL,
  suspicious INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, trashed_at TEXT);
CREATE INDEX ix_files_owner ON files(owner_id, folder_id);
CREATE TABLE uploads(
  id TEXT PRIMARY KEY,
  owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  folder_id INTEGER, name TEXT NOT NULL, size INTEGER NOT NULL,
  chunk_size INTEGER NOT NULL, total_chunks INTEGER NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE upload_chunks(
  upload_id TEXT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
  idx INTEGER NOT NULL, size INTEGER NOT NULL,
  PRIMARY KEY(upload_id, idx));
CREATE TABLE shares(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token TEXT NOT NULL UNIQUE,
  file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  password_hash TEXT, expires_at TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, downloads INTEGER NOT NULL DEFAULT 0);
CREATE TABLE activity(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
  action TEXT NOT NULL, detail TEXT, ip TEXT, bytes INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL);
CREATE INDEX ix_activity_user ON activity(user_id, id);
CREATE TABLE audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  admin_id INTEGER, action TEXT NOT NULL, target TEXT, detail TEXT, ip TEXT,
  created_at TEXT NOT NULL);
CREATE TABLE events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  level TEXT NOT NULL, kind TEXT NOT NULL, message TEXT, ip TEXT, created_at TEXT NOT NULL);
CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
]


def connect(path):
    c = sqlite3.connect(str(path), timeout=15, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=FULL")
    c.execute("PRAGMA busy_timeout=15000")
    return c


def migrate(path):
    c = connect(path)
    v = c.execute("PRAGMA user_version").fetchone()[0]
    for i, sql in enumerate(MIGRATIONS[v:], start=v + 1):
        c.executescript(sql)
        c.execute("PRAGMA user_version=%d" % i)
    c.commit()
    c.close()


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def commit_db():
    c = g.get("db")
    if c is not None:
        c.commit()


def close_db(exc):
    c = g.pop("db", None)
    if c is not None:
        try:
            if exc is not None:
                c.rollback()
        finally:
            c.close()
