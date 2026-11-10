"""Power-cut safety of the server certificate (same fingerprint after damaged files). Run: python test_cert_powercut.py"""
import sys, tempfile, hashlib, ssl, shutil
from pathlib import Path
sys.path.insert(0, ".")
import common
tmp = Path(tempfile.mkdtemp()); common.DATA_DIR = tmp
import server as srv
srv.DATA_DIR = tmp
res = []
def ok(n, c): res.append(bool(c)); print(("  ok   " if c else "  FAIL ") + n)
def fp(): return hashlib.sha256(ssl.PEM_cert_to_DER_cert((tmp / "server.crt").read_text())).hexdigest()
def start():
    s = srv.WindroidaServer("127.0.0.1", 0, tls=True, db_path=tmp / "t.db"); s.start(); s.stop() if hasattr(s, "stop") else None; return s
s1 = start(); f0 = fp()
ok("certificate + backup created", s1.ssl_ctx is not None and (tmp / "cert-backup" / "server.crt").exists())
start(); ok("normal restart: same fingerprint", fp() == f0)
(tmp / "server.names").write_text("#v"); start(); ok("names file cut in half: same fingerprint", fp() == f0)
(tmp / "server.names").write_text(""); start(); ok("names file empty: same fingerprint", fp() == f0)
(tmp / "server.names").unlink(); start(); ok("names file missing: same fingerprint", fp() == f0)
(tmp / "server.crt").write_bytes(b""); start(); ok("certificate file emptied: restored from backup, same fingerprint", fp() == f0)
(tmp / "server.key").write_bytes(b"-----BEGIN"); start(); ok("key file cut: restored from backup, same fingerprint", fp() == f0)
(tmp / "server.crt").unlink(); (tmp / "server.key").unlink(); start(); ok("both missing: restored from backup", fp() == f0)
shutil.rmtree(tmp / "cert-backup"); (tmp / "server.crt").write_bytes(b"junk"); s = start()
ok("no backup and unusable files: a new valid certificate is made (the only case)", s.ssl_ctx is not None and fp() != f0)
ok("no half-written temp files left", not list(tmp.glob("*.tmp")) and not list(tmp.glob("*.new")))
print(f"\n{sum(res)} passed, {len(res)-sum(res)} failed"); sys.exit(0 if all(res) else 1)
