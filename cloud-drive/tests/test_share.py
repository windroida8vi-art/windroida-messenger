from datetime import datetime, timedelta, timezone

from .helpers import Base


class ShareTests(Base):
    def _file(self, c):
        return self.upload(c, "report.txt", b"public content")

    def test_public_link_download_no_login(self):
        c = self.register()
        f = self._file(c)
        s = self.call(c, "post", "/api/files/%d/shares" % f["id"], json={}).get_json()
        anon = self.new_client()
        info = anon.get("/api/public/" + s["token"]).get_json()
        self.assertEqual((info["name"], info["needs_password"]), ("report.txt", False))
        r = anon.get("/api/public/%s/download" % s["token"])
        self.assertEqual(r.data, b"public content")
        self.assertEqual(anon.get("/s/" + s["token"]).status_code, 200)
        self.assertEqual(c.get("/api/shares").get_json()["items"][0]["downloads"], 1)

    def test_password_protected_link(self):
        c = self.register()
        s = self.call(c, "post", "/api/files/%d/shares" % self._file(c)["id"], json={"password": "open-sesame"}).get_json()
        anon = self.new_client()
        r = anon.get("/api/public/%s/download" % s["token"])
        self.assertEqual((r.status_code, r.get_json()["error"]), (403, "password_required"))
        self.assertEqual(anon.post("/api/public/%s/unlock" % s["token"], json={"password": "wrong"}).status_code, 403)
        self.assertEqual(anon.post("/api/public/%s/unlock" % s["token"], json={"password": "open-sesame"}).status_code, 200)
        self.assertEqual(anon.get("/api/public/%s/download" % s["token"]).data, b"public content")
        # another visitor is still locked out
        self.assertEqual(self.new_client().get("/api/public/%s/download" % s["token"]).status_code, 403)

    def test_expiry(self):
        from app import db as dbm
        c = self.register()
        s = self.call(c, "post", "/api/files/%d/shares" % self._file(c)["id"], json={"expires_hours": 1}).get_json()
        anon = self.new_client()
        self.assertEqual(anon.get("/api/public/" + s["token"]).status_code, 200)
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
        conn = dbm.connect(self.app.config["DB_PATH"])
        conn.execute("UPDATE shares SET expires_at=?", (past,))
        conn.commit()
        self.assertEqual(anon.get("/api/public/" + s["token"]).status_code, 410)
        self.assertEqual(anon.get("/api/public/%s/download" % s["token"]).status_code, 410)

    def test_disable_and_trash_stops_access(self):
        c = self.register()
        f = self._file(c)
        s = self.call(c, "post", "/api/files/%d/shares" % f["id"], json={}).get_json()
        anon = self.new_client()
        self.call(c, "delete", "/api/shares/%d" % s["id"])
        self.assertEqual(anon.get("/api/public/" + s["token"]).status_code, 404)
        s2 = self.call(c, "post", "/api/files/%d/shares" % f["id"], json={}).get_json()
        self.call(c, "post", "/api/items/trash", json={"files": [f["id"]]})
        self.assertEqual(anon.get("/api/public/%s/download" % s2["token"]).status_code, 404)

    def test_unknown_token_and_bad_params(self):
        c = self.register()
        f = self._file(c)
        self.assertEqual(self.new_client().get("/api/public/nope").status_code, 404)
        self.assertEqual(self.call(c, "post", "/api/files/%d/shares" % f["id"], json={"expires_hours": -5}).status_code, 400)
        self.assertEqual(self.call(c, "post", "/api/files/%d/shares" % f["id"], json={"password": "ab"}).status_code, 400)

    def test_other_user_cannot_disable_my_link(self):
        c = self.register()
        s = self.call(c, "post", "/api/files/%d/shares" % self._file(c)["id"], json={}).get_json()
        bob = self.register(self.new_client(), username="bobby")
        self.assertEqual(self.call(bob, "delete", "/api/shares/%d" % s["id"]).status_code, 404)
