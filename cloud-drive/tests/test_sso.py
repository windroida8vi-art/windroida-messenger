"""Single sign-on bridge (Windroida -> Cloud Drive): signature checks, replay, provisioning, access control."""
import hashlib
import hmac
import shutil
import tempfile
import time
import unittest

from app import create_app
from app import db as dbm


class SsoBase(unittest.TestCase):
    secret = "test-sso-secret-not-real"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app(DATA_DIR=self.tmp, TESTING=True, HOUSEKEEPING=False, SCRYPT_N=1024,
                              SSO_SECRET=self.secret)
        c = dbm.connect(self.app.config["DB_PATH"])
        c.execute("INSERT INTO settings(key,value) VALUES('rate_login_per_min','1000')")
        c.commit()
        c.close()
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def token(self, username, ttl=60, secret=None, expiry=None, nonce=None):
        import secrets as _secrets
        exp = expiry if expiry is not None else int(time.time()) + ttl
        n = nonce if nonce is not None else _secrets.token_hex(8)
        sig = hmac.new((secret or self.secret).encode(), ("%s:%d:%s" % (username, exp, n)).encode(), "sha256").hexdigest()
        return "%s.%d.%s.%s" % (username, exp, n, sig)


class TestSso(SsoBase):
    def test_valid_token_logs_in_and_creates_account(self):
        r = self.client.get("/sso?t=" + self.token("alice"), follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        r2 = self.client.get("/api/me")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.get_json()["user"]["username"], "alice")

    def test_second_login_reuses_same_account_not_a_new_one(self):
        self.client.get("/sso?t=" + self.token("bob"))
        uid1 = self.client.get("/api/me").get_json()["user"]["id"]
        c2 = self.app.test_client()
        c2.get("/sso?t=" + self.token("bob"))
        uid2 = c2.get("/api/me").get_json()["user"]["id"]
        self.assertEqual(uid1, uid2)

    def test_provisioned_account_cannot_be_logged_into_with_a_password(self):
        self.client.get("/sso?t=" + self.token("carol"))
        c2 = self.app.test_client()
        for guess in ("carol", "password123", "", "12345678ab"):
            r = c2.post("/api/login", json={"username": "carol", "password": guess})
            self.assertEqual(r.status_code, 401, guess)

    def test_new_sso_account_is_never_admin(self):
        self.client.get("/sso?t=" + self.token("dave"))
        r = self.client.get("/api/me")
        self.assertEqual(r.get_json()["user"]["role"], "user")

    def test_wrong_signature_rejected(self):
        ev_tok = self.token("eve"); bad = ev_tok[:-1] + ("0" if ev_tok[-1] != "0" else "1")
        r = self.client.get("/sso?t=" + bad)
        self.assertEqual(r.status_code, 400)
        self.assertIsNone(self.client.get("/api/me").get_json().get("user"))

    def test_signed_with_wrong_secret_rejected(self):
        r = self.client.get("/sso?t=" + self.token("mallory", secret="not-the-real-secret"))
        self.assertEqual(r.status_code, 400)

    def test_expired_token_rejected(self):
        r = self.client.get("/sso?t=" + self.token("frank", expiry=int(time.time()) - 5))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "expired")

    def test_token_cannot_be_replayed(self):
        tok = self.token("grace")
        r1 = self.client.get("/sso?t=" + tok)
        self.assertEqual(r1.status_code, 302)
        c2 = self.app.test_client()
        r2 = c2.get("/sso?t=" + tok)
        self.assertEqual(r2.status_code, 400)
        self.assertEqual(r2.get_json()["error"], "bad_token")

    def test_malformed_token_rejected(self):
        for bad in ("", "nodots", "a.b", "a.b.c.d.e", "x" * 200 + ".999999999999.nonce." + "0" * 64):
            r = self.client.get("/sso?t=" + bad)
            self.assertEqual(r.status_code, 400, bad)

    def test_cannot_log_in_as_banned_account(self):
        self.client.get("/sso?t=" + self.token("hank"))
        c = dbm.connect(self.app.config["DB_PATH"])
        c.execute("UPDATE users SET is_active=0 WHERE username='hank'")
        c.commit()
        c.close()
        c2 = self.app.test_client()
        r = c2.get("/sso?t=" + self.token("hank"))
        self.assertEqual(r.status_code, 403)

    def test_disabled_when_no_secret_configured(self):
        app2 = create_app(DATA_DIR=tempfile.mkdtemp(), TESTING=True, HOUSEKEEPING=False, SCRYPT_N=1024, SSO_SECRET="")
        cl = app2.test_client()
        sig = hmac.new(b"guessed", b"ivy:9999999999:abc", "sha256").hexdigest()
        r = cl.get("/sso?t=ivy.9999999999.abc." + sig)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["error"], "sso_disabled")

    def test_username_length_bounds_enforced(self):
        r = self.client.get("/sso?t=" + self.token("x" * 40))
        self.assertEqual(r.status_code, 400)

    def test_sha1_or_short_signature_rejected(self):
        exp = int(time.time()) + 60
        short_sig = hashlib.sha256(b"whatever").hexdigest()[:32]  # right-looking but too short
        r = self.client.get("/sso?t=judy.%d.nonce.%s" % (exp, short_sig))
        self.assertEqual(r.status_code, 400)


class AdminHiddenWhenFolded(unittest.TestCase):
    def test_admin_page_and_api_404(self):
        from app import create_app
        import tempfile
        d = tempfile.mkdtemp()
        app = create_app(DATA_DIR=d, TESTING=True, HOUSEKEEPING=False, SCRYPT_N=1024, PASSWORD_AUTH=False, SSO_SECRET="ab" * 16)
        c = app.test_client()
        self.assertEqual(c.get("/admin").status_code, 404)
        self.assertEqual(c.get("/api/admin/stats").status_code, 404)


class HstsSwitch(unittest.TestCase):
    def _hdr(self, hsts):
        d = tempfile.mkdtemp()
        app = create_app(DATA_DIR=d, TESTING=True, HOUSEKEEPING=False, SCRYPT_N=1024, COOKIE_SECURE=True, HSTS=hsts)
        return app.test_client().get("/api/health").headers.get("Strict-Transport-Security")

    def test_hsts_off_for_self_signed(self):
        self.assertIsNone(self._hdr(False))

    def test_hsts_on_by_default_when_secure(self):
        self.assertIsNotNone(self._hdr(True))
