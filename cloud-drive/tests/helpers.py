import shutil
import tempfile
import unittest

from app import create_app
from app import db as dbm
from app.security import hash_password
from app.services import now

PW = "Str0ng-pass-123"


class Base(unittest.TestCase):
    """Each test gets a fresh app, data dir and database."""

    chunk_mb = 1

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app(DATA_DIR=self.tmp, TESTING=True, HOUSEKEEPING=False, SCRYPT_N=1024)
        self.app.config["CHUNK_SIZE"] = 1024  # tiny chunks so tests exercise multi-chunk uploads
        c = dbm.connect(self.app.config["DB_PATH"])
        c.execute("INSERT INTO settings(key,value) VALUES('rate_login_per_min','1000')")
        c.commit()
        c.close()
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- helpers
    def new_client(self):
        return self.app.test_client()

    def register(self, client=None, username="alice", pw=PW):
        client = client or self.client
        r = client.post("/api/register", json={"username": username, "password": pw})
        self.assertEqual(r.status_code, 201, r.get_json())
        client.csrf = r.get_json()["csrf"]
        return client

    def make_admin(self, username="boss", pw=PW):
        c = dbm.connect(self.app.config["DB_PATH"])
        with self.app.app_context():
            h = hash_password(pw)
        c.execute("INSERT INTO users(username,display_name,password_hash,role,quota_bytes,created_at) "
                  "VALUES(?,?,?,?,?,?)", (username, username, h, "admin", 10 ** 9, now()))
        c.commit()
        c.close()
        cl = self.new_client()
        r = cl.post("/api/login", json={"username": username, "password": pw})
        self.assertEqual(r.status_code, 200, r.get_json())
        cl.csrf = r.get_json()["csrf"]
        return cl

    def call(self, client, method, url, **kw):
        h = kw.pop("headers", {})
        h["X-CSRF-Token"] = getattr(client, "csrf", "")
        return getattr(client, method)(url, headers=h, **kw)

    def upload(self, client, name, data, folder_id=None):
        r = self.call(client, "post", "/api/uploads", json={"name": name, "size": len(data), "folder_id": folder_id})
        self.assertEqual(r.status_code, 201, r.get_json())
        st = r.get_json()
        cs = st["chunk_size"]
        for i in range(st["total_chunks"]):
            rr = self.call(client, "put", "/api/uploads/%s/chunks/%d" % (st["upload_id"], i),
                           data=data[i * cs:(i + 1) * cs], content_type="application/octet-stream")
            self.assertEqual(rr.status_code, 200, rr.get_json())
        r = self.call(client, "post", "/api/uploads/%s/complete" % st["upload_id"])
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()
