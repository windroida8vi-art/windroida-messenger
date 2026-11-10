import os

from .helpers import Base


class FileTests(Base):
    def test_upload_download_roundtrip_multichunk(self):
        c = self.register()
        data = os.urandom(5000)  # 5 chunks of 1024
        f = self.upload(c, "photo.bin", data)
        self.assertEqual(f["size"], 5000)
        r = c.get("/api/files/%d/download" % f["id"])
        self.assertEqual(r.data, data)
        self.assertIn("attachment", r.headers["Content-Disposition"])
        r = c.get("/api/files/%d/download" % f["id"], headers={"Range": "bytes=10-19"})
        self.assertEqual((r.status_code, r.data), (206, data[10:20]))

    def test_stored_name_random_and_on_disk(self):
        c = self.register()
        f = self.upload(c, "secret-name.txt", b"hello")
        files = [p for p in self.app.config["UPLOAD_DIR"].rglob("*") if p.is_file()]
        self.assertEqual(len(files), 1)
        self.assertNotIn("secret-name", str(files[0]))
        self.assertEqual(files[0].read_bytes(), b"hello")
        # same name twice -> auto-renamed, no collision
        f2 = self.upload(c, "secret-name.txt", b"again")
        self.assertEqual(f2["name"], "secret-name (1).txt")

    def test_resume_after_interruption(self):
        c = self.register()
        data = os.urandom(3000)
        r = self.call(c, "post", "/api/uploads", json={"name": "big.bin", "size": 3000})
        st = r.get_json()
        uid = st["upload_id"]
        self.call(c, "put", "/api/uploads/%s/chunks/0" % uid, data=data[:1024])
        # connection "drops"; client asks what the server already has
        st2 = c.get("/api/uploads/" + uid).get_json()
        self.assertEqual(st2["received"], [0])
        r = self.call(c, "post", "/api/uploads/%s/complete" % uid)
        self.assertEqual(r.status_code, 409)  # incomplete
        for i in (1, 2):
            self.call(c, "put", "/api/uploads/%s/chunks/%d" % (uid, i), data=data[i * 1024:(i + 1) * 1024])
        r = self.call(c, "post", "/api/uploads/%s/complete" % uid)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(c.get("/api/files/%d/download" % r.get_json()["id"]).data, data)

    def test_wrong_chunk_size_rejected(self):
        c = self.register()
        uid = self.call(c, "post", "/api/uploads", json={"name": "a", "size": 2048}).get_json()["upload_id"]
        r = self.call(c, "put", "/api/uploads/%s/chunks/0" % uid, data=b"short")
        self.assertEqual(r.status_code, 400)

    def test_max_upload_size_and_quota(self):
        from app import db as dbm
        c = self.register()
        conn = dbm.connect(self.app.config["DB_PATH"])
        conn.execute("INSERT INTO settings(key,value) VALUES('max_upload_bytes','2000')")
        conn.execute("UPDATE users SET quota_bytes=3000")
        conn.commit()
        r = self.call(c, "post", "/api/uploads", json={"name": "x", "size": 2001})
        self.assertEqual((r.status_code, r.get_json()["error"]), (413, "too_large"))
        self.upload(c, "ok.bin", b"a" * 2000)
        r = self.call(c, "post", "/api/uploads", json={"name": "y", "size": 1500})
        self.assertEqual((r.status_code, r.get_json()["error"]), (413, "quota_exceeded"))

    def test_folders_rename_move_and_cycle_guard(self):
        c = self.register()
        a = self.call(c, "post", "/api/folders", json={"name": "A"}).get_json()
        b = self.call(c, "post", "/api/folders", json={"name": "B", "parent_id": a["id"]}).get_json()
        self.assertEqual(self.call(c, "post", "/api/folders", json={"name": "A"}).status_code, 409)
        r = self.call(c, "patch", "/api/folders/%d" % a["id"], json={"parent_id": b["id"]})
        self.assertEqual(r.status_code, 400)  # cannot move into own descendant
        f = self.upload(c, "doc.txt", b"x", folder_id=b["id"])
        r = self.call(c, "patch", "/api/files/%d" % f["id"], json={"name": "renamed.txt", "folder_id": None})
        self.assertEqual(r.get_json()["name"], "renamed.txt")
        listing = c.get("/api/items").get_json()
        self.assertEqual([x["name"] for x in listing["files"]], ["renamed.txt"])
        inside = c.get("/api/items?folder_id=%d" % a["id"]).get_json()
        self.assertEqual([x["name"] for x in inside["folders"]], ["B"])
        self.assertEqual([p["name"] for p in inside["path"]], ["A"])

    def test_sort_and_search(self):
        c = self.register()
        self.upload(c, "b.txt", b"12345")
        self.upload(c, "a.png", b"1")
        names = lambda q: [x["name"] for x in c.get("/api/items?" + q).get_json()["files"]]
        self.assertEqual(names("sort=name"), ["a.png", "b.txt"])
        self.assertEqual(names("sort=size&order=desc"), ["b.txt", "a.png"])
        self.assertEqual(names("sort=type"), ["a.png", "b.txt"])
        self.assertEqual(names("q=B.T"), ["b.txt"])

    def test_trash_restore_purge(self):
        c = self.register()
        d = self.call(c, "post", "/api/folders", json={"name": "dir"}).get_json()
        f1 = self.upload(c, "in-dir.txt", b"1", folder_id=d["id"])
        f2 = self.upload(c, "solo.txt", b"22")
        self.call(c, "post", "/api/items/trash", json={"files": [f2["id"]], "folders": [d["id"]]})
        self.assertEqual(c.get("/api/items").get_json()["files"], [])
        trash = c.get("/api/items?view=trash").get_json()
        self.assertEqual(len(trash["folders"]), 1)
        self.assertEqual(len(trash["files"]), 1)  # only top-level trashed items
        self.assertEqual(c.get("/api/files/%d/download" % f2["id"]).status_code, 404)
        self.call(c, "post", "/api/items/restore", json={"files": [f2["id"]], "folders": [d["id"]]})
        back = c.get("/api/items?folder_id=%d" % d["id"]).get_json()
        self.assertEqual([x["name"] for x in back["files"]], ["in-dir.txt"])
        # purge requires trash first
        r = self.call(c, "post", "/api/items/purge", json={"files": [f2["id"]]})
        self.assertEqual(r.status_code, 400)
        self.call(c, "post", "/api/items/trash", json={"files": [f2["id"]]})
        self.call(c, "post", "/api/items/purge", json={"files": [f2["id"]]})
        self.assertEqual(len([p for p in self.app.config["UPLOAD_DIR"].rglob("*") if p.is_file()]), 1)
        self.assertEqual(c.get("/api/usage").get_json()["used"], 1)

    def test_preview_only_for_real_images_and_pdf(self):
        c = self.register()
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
        f = self.upload(c, "pic.png", png)
        r = c.get("/api/files/%d/preview" % f["id"])
        self.assertEqual((r.status_code, r.mimetype), (200, "image/png"))
        fake = self.upload(c, "evil.png", b"<script>alert(1)</script>")  # not a real PNG
        self.assertFalse(fake["previewable"])
        self.assertEqual(c.get("/api/files/%d/preview" % fake["id"]).status_code, 415)
        html = self.upload(c, "page.html", b"<script>alert(1)</script>")
        r = c.get("/api/files/%d/download" % html["id"])
        self.assertEqual(r.mimetype, "application/octet-stream")
        self.assertIn("attachment", r.headers["Content-Disposition"])

    def test_path_traversal_names(self):
        c = self.register()
        f = self.upload(c, "../../etc/passwd", b"x")
        self.assertEqual(f["name"], "passwd")
        from app.storage import LocalStorage
        st = self.app.storage
        for bad in ("../x", "..", "a" * 32 + "/../b", "zz" * 16):
            with self.assertRaises(ValueError):
                st.path(bad)

    def test_activity_log(self):
        c = self.register()
        self.upload(c, "a.txt", b"1")
        acts = [a["action"] for a in c.get("/api/activity").get_json()["items"]]
        self.assertIn("upload", acts)
        self.assertIn("register", acts)

    def test_stale_upload_cleanup(self):
        from app import db as dbm
        from app.fileops import cleanup_stale_uploads
        c = self.register()
        uid = self.call(c, "post", "/api/uploads", json={"name": "a", "size": 2000}).get_json()["upload_id"]
        self.call(c, "put", "/api/uploads/%s/chunks/0" % uid, data=b"x" * 1024)
        conn = dbm.connect(self.app.config["DB_PATH"])
        conn.execute("UPDATE uploads SET updated_at='2000-01-01T00:00:00+00:00'")
        conn.commit()
        self.assertEqual(cleanup_stale_uploads(conn, self.app.storage, 24), 1)
        self.assertEqual(self.app.storage.list_upload_dirs(), [])


class RetentionTests(Base):
    def test_no_upload_limit_by_default(self):
        from app import db as dbm
        from app.services import get_int
        c = self.register()
        conn = dbm.connect(self.app.config["DB_PATH"])
        with self.app.app_context():
            self.assertEqual(get_int(conn, "max_upload_bytes"), 0)  # 0 = unlimited
        conn.execute("UPDATE users SET quota_bytes=?", (5 * 1024 ** 3,)); conn.commit()
        r = self.call(c, "post", "/api/uploads", json={"name": "huge.iso", "size": 6 * 1024 ** 3})
        self.assertEqual(r.get_json().get("error"), "quota_exceeded")  # only the per-user quota can stop a big file
        self.assertEqual(self.call(c, "post", "/api/uploads", json={"name": "big.iso", "size": 100 * 1024 ** 2}).status_code, 201)

    def test_files_deleted_after_20_days_only(self):
        from app import db as dbm
        from app.fileops import purge_expired_files
        from app.services import get_int
        c = self.register()
        old = self.upload(c, "old.txt", b"old")
        new = self.upload(c, "new.txt", b"new")
        share = self.call(c, "post", "/api/files/%d/shares" % old["id"], json={}).get_json()
        conn = dbm.connect(self.app.config["DB_PATH"])
        with self.app.app_context():
            self.assertEqual(get_int(conn, "file_retention_days"), 0)      # files are kept forever by default
            self.assertEqual(get_int(conn, "trash_retention_days"), 20)  # only the trash expires
        conn.execute("UPDATE files SET created_at='2000-01-01T00:00:00+00:00' WHERE id=?", (old["id"],))
        from datetime import datetime, timedelta, timezone
        conn.execute("UPDATE files SET created_at=? WHERE id=?", ((datetime.now(timezone.utc) - timedelta(days=19)).isoformat(), new["id"]))
        conn.commit()
        self.assertEqual(purge_expired_files(conn, self.app.storage, 20), 1)
        names = [f["name"] for f in c.get("/api/items").get_json()["files"]]
        self.assertEqual(names, ["new.txt"])
        self.assertEqual(len([p for p in self.app.config["UPLOAD_DIR"].rglob("*") if p.is_file()]), 1)  # removed from disk too
        self.assertEqual(self.new_client().get("/api/public/" + share["token"]).status_code, 404)   # share link died with it
        self.assertEqual(c.get("/api/me").get_json()["trash_days"], 20)
        self.assertEqual(purge_expired_files(conn, self.app.storage, 0), 0)  # 0 = disabled

    def test_normal_files_are_never_auto_deleted_but_old_trash_is(self):
        from app import db as dbm, run_housekeeping
        c = self.register()
        keep = self.upload(c, "keep-forever.txt", b"x")
        gone = self.upload(c, "trashed-long-ago.txt", b"y")
        fresh = self.upload(c, "trashed-today.txt", b"z")
        self.call(c, "post", "/api/items/trash", json={"files": [gone["id"], fresh["id"]]})
        conn = dbm.connect(self.app.config["DB_PATH"])
        conn.execute("UPDATE files SET created_at='2000-01-01T00:00:00+00:00'")            # everything is ancient...
        conn.execute("UPDATE files SET trashed_at='2000-01-02T00:00:00+00:00' WHERE id=?", (gone["id"],))  # ...but only this was trashed >20 days ago
        conn.commit()
        run_housekeeping(self.app)  # exactly what the background thread runs
        self.assertEqual([f["name"] for f in c.get("/api/items").get_json()["files"]], ["keep-forever.txt"])
        self.assertEqual([f["name"] for f in c.get("/api/items?view=trash").get_json()["files"]], ["trashed-today.txt"])
        self.assertEqual(len([p for p in self.app.config["UPLOAD_DIR"].rglob("*") if p.is_file()]), 2)
