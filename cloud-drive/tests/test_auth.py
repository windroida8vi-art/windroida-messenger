from .helpers import PW, Base


class AuthTests(Base):
    def test_register_login_logout(self):
        c = self.register()
        self.assertEqual(c.get("/api/me").get_json()["user"]["username"], "alice")
        self.call(c, "post", "/api/logout")
        self.assertEqual(c.get("/api/me").status_code, 401)
        c2 = self.new_client()
        r = c2.post("/api/login", json={"username": "ALICE", "password": PW})  # case-insensitive username
        self.assertEqual(r.status_code, 200)

    def test_bad_login_and_weak_password(self):
        self.register()
        r = self.new_client().post("/api/login", json={"username": "alice", "password": "wrong-pass-1"})
        self.assertEqual(r.status_code, 401)
        r = self.new_client().post("/api/register", json={"username": "bob", "password": "short1"})
        self.assertEqual(r.status_code, 400)
        r = self.new_client().post("/api/register", json={"username": "alice", "password": PW})
        self.assertEqual(r.status_code, 409)

    def test_requires_login_and_csrf(self):
        self.assertEqual(self.client.get("/api/items").status_code, 401)
        c = self.register()
        r = c.post("/api/folders", json={"name": "x"})  # no CSRF header
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["error"], "csrf")

    def test_login_rate_limit(self):
        from app import db as dbm
        conn = dbm.connect(self.app.config["DB_PATH"])
        conn.execute("UPDATE settings SET value='3' WHERE key='rate_login_per_min'")
        conn.commit()
        codes = [self.client.post("/api/login", json={"username": "nobody", "password": "x"}).status_code
                 for _ in range(5)]
        self.assertEqual(codes[:3], [401, 401, 401])
        self.assertEqual(codes[3], 429)

    def test_password_change_and_profile(self):
        c = self.register()
        r = self.call(c, "post", "/api/me/password", json={"current_password": "bad", "new_password": "NewPass-12345"})
        self.assertEqual(r.status_code, 403)
        r = self.call(c, "post", "/api/me/password", json={"current_password": PW, "new_password": "NewPass-12345"})
        self.assertEqual(r.status_code, 200)
        r = self.call(c, "patch", "/api/me", json={"display_name": "Alice A", "email": "a@example.com"})
        self.assertEqual(r.get_json()["user"]["display_name"], "Alice A")
        self.assertEqual(self.new_client().post("/api/login", json={"username": "alice", "password": "NewPass-12345"}).status_code, 200)

    def test_security_headers_and_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
