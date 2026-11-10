from .helpers import Base


class AccessTests(Base):
    def test_cannot_touch_other_users_files(self):
        alice = self.register(username="alice")
        bob = self.register(self.new_client(), username="bobby")
        f = self.upload(alice, "private.txt", b"secret")
        folder = self.call(alice, "post", "/api/folders", json={"name": "mine"}).get_json()
        for method, url, kw in [
            ("get", "/api/files/%d/download" % f["id"], {}),
            ("get", "/api/files/%d/preview" % f["id"], {}),
            ("patch", "/api/files/%d" % f["id"], {"json": {"name": "hacked"}}),
            ("post", "/api/files/%d/shares" % f["id"], {"json": {}}),
            ("patch", "/api/folders/%d" % folder["id"], {"json": {"name": "hacked"}}),
            ("post", "/api/items/trash", {"json": {"files": [f["id"]]}}),
            ("post", "/api/items/restore", {"json": {"files": [f["id"]]}}),
            ("post", "/api/items/purge", {"json": {"files": [f["id"]]}}),
        ]:
            r = self.call(bob, method, url, **kw)
            self.assertEqual(r.status_code, 404, url)
        # bob cannot upload into alice's folder, nor read her listing
        r = self.call(bob, "post", "/api/uploads", json={"name": "x", "size": 1, "folder_id": folder["id"]})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(bob.get("/api/items?folder_id=%d" % folder["id"]).status_code, 404)
        self.assertEqual(bob.get("/api/items").get_json()["files"], [])
        # bob cannot touch alice's upload session
        uid = self.call(alice, "post", "/api/uploads", json={"name": "z", "size": 5}).get_json()["upload_id"]
        self.assertEqual(self.call(bob, "put", "/api/uploads/%s/chunks/0" % uid, data=b"12345").status_code, 404)

    def test_uploads_not_served_statically(self):
        c = self.register()
        self.upload(c, "a.txt", b"zzz")
        stored = next(p for p in self.app.config["UPLOAD_DIR"].rglob("*") if p.is_file()).name
        for url in ("/static/" + stored, "/data/uploads/" + stored, "/uploads/" + stored, "/static/../data/x"):
            self.assertEqual(self.new_client().get(url).status_code, 404)

    def test_session_cookie_flags(self):
        r = self.new_client().post("/api/register", json={"username": "cookie", "password": "Str0ng-pass-123"})
        cookie = r.headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)

    def test_sql_injection_attempts(self):
        c = self.register()
        r = self.new_client().post("/api/login", json={"username": "' OR 1=1 --", "password": "x"})
        self.assertEqual(r.status_code, 401)
        r = c.get("/api/items?q=' OR 1=1 --")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["files"], [])


class AdminTests(Base):
    def test_admin_endpoints_need_admin_role_server_side(self):
        user = self.register()
        for url in ("/api/admin/stats", "/api/admin/users", "/api/admin/files", "/api/admin/settings",
                    "/api/admin/audit", "/api/admin/health"):
            self.assertEqual(user.get(url).status_code, 403, url)
        self.assertEqual(self.new_client().get("/api/admin/stats").status_code, 401)
        r = self.call(user, "patch", "/api/admin/users/1", json={"role": "admin", "confirm_password": "x"})
        self.assertEqual(r.status_code, 403)

    def test_dashboard_and_user_management(self):
        admin = self.make_admin()
        alice = self.register(self.new_client(), username="alice")
        self.upload(alice, "a.txt", b"12345")
        s = admin.get("/api/admin/stats").get_json()
        self.assertEqual((s["users_total"], s["files_total"], s["bytes_total"]), (2, 1, 5))
        self.assertEqual(len(s["user_growth"]), 30)
        users = admin.get("/api/admin/users?q=ali").get_json()["items"]
        self.assertEqual(users[0]["used"], 5)
        uid = users[0]["id"]
        # sensitive action needs re-auth
        r = self.call(admin, "patch", "/api/admin/users/%d" % uid, json={"quota_bytes": 100})
        self.assertEqual(r.status_code, 403)
        r = self.call(admin, "patch", "/api/admin/users/%d" % uid, json={"quota_bytes": 100, "confirm_password": "nope"})
        self.assertEqual(r.get_json()["error"], "reauth_failed")
        r = self.call(admin, "patch", "/api/admin/users/%d" % uid, json={"quota_bytes": 100, "confirm_password": "Str0ng-pass-123"})
        self.assertEqual(r.status_code, 200)
        r = self.call(alice, "post", "/api/uploads", json={"name": "b", "size": 200})
        self.assertEqual(r.get_json()["error"], "quota_exceeded")

    def test_ban_revokes_sessions_and_blocks_login(self):
        admin = self.make_admin()
        alice = self.register(self.new_client(), username="alice")
        uid = admin.get("/api/admin/users?q=alice").get_json()["items"][0]["id"]
        r = self.call(admin, "post", "/api/admin/users/%d/ban" % uid, json={"confirm_password": "Str0ng-pass-123"})
        self.assertEqual(r.status_code, 400)  # reason required
        r = self.call(admin, "post", "/api/admin/users/%d/ban" % uid, json={"reason": "spam", "confirm_password": "Str0ng-pass-123"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(alice.get("/api/me").status_code, 401)
        r = self.new_client().post("/api/login", json={"username": "alice", "password": "Str0ng-pass-123"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("spam", r.get_json()["message_en"])
        self.call(admin, "post", "/api/admin/users/%d/unban" % uid, json={"confirm_password": "Str0ng-pass-123"})
        self.assertEqual(self.new_client().post("/api/login", json={"username": "alice", "password": "Str0ng-pass-123"}).status_code, 200)

    def test_revoke_sessions(self):
        admin = self.make_admin()
        alice = self.register(self.new_client(), username="alice")
        uid = admin.get("/api/admin/users?q=alice").get_json()["items"][0]["id"]
        r = self.call(admin, "post", "/api/admin/users/%d/revoke-sessions" % uid, json={"confirm_password": "Str0ng-pass-123"})
        self.assertEqual(r.get_json()["revoked"], 1)
        self.assertEqual(alice.get("/api/me").status_code, 401)

    def test_last_admin_and_self_protection(self):
        admin = self.make_admin()
        me = admin.get("/api/me").get_json()["user"]["id"]
        for body in ({"is_active": False}, {"role": "user"}):
            body["confirm_password"] = "Str0ng-pass-123"
            self.assertEqual(self.call(admin, "patch", "/api/admin/users/%d" % me, json=body).status_code, 400)

    def test_admin_delete_file_audited_and_settings(self):
        admin = self.make_admin()
        alice = self.register(self.new_client(), username="alice")
        f = self.upload(alice, "run.exe", b"MZ")
        sus = admin.get("/api/admin/files?suspicious=1").get_json()["items"]
        self.assertEqual([x["name"] for x in sus], ["run.exe"])
        r = self.call(admin, "delete", "/api/admin/files/%d" % f["id"], json={"confirm_password": "bad"})
        self.assertEqual(r.status_code, 403)
        r = self.call(admin, "delete", "/api/admin/files/%d" % f["id"], json={"confirm_password": "Str0ng-pass-123", "reason": "malware"})
        self.assertEqual(r.status_code, 200)
        audit = admin.get("/api/admin/audit").get_json()["items"]
        self.assertEqual(audit[0]["action"], "file_delete")
        r = self.call(admin, "put", "/api/admin/settings", json={"settings": {"service_name": "My Drive", "trash_retention_days": 7}, "confirm_password": "Str0ng-pass-123"})
        self.assertEqual(r.get_json()["service_name"], "My Drive")
        r = self.call(admin, "put", "/api/admin/settings", json={"settings": {"hack": 1}, "confirm_password": "Str0ng-pass-123"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.get("/api/config").get_json()["service_name"], "My Drive")
        h = admin.get("/api/admin/health").get_json()
        self.assertTrue(h["database"] and h["storage"])
