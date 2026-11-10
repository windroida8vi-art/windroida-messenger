"""Stress / race / fuzz test. Starts its own server on port 8095 with a temporary data dir (your real data is never touched).
Run: python scripts/stress_test.py"""
import os, sys, json, tempfile, shutil, time, random, hashlib, threading, http.client, string, sqlite3, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="cd-stress-")  # isolated: never touches your real data/
os.environ["CD_DATA_DIR"] = TMP; os.environ["CD_PORT"] = "8095"
from app import create_app
from app import db as dbm
from app.security import hash_password
from app.services import now
app = create_app(HOUSEKEEPING=False)
PW = "Brutal-pass-98765"
with app.app_context(): H = hash_password(PW)
c = dbm.connect(app.config["DB_PATH"])
for k, v in (("rate_login_per_min", "100000"), ("rate_api_per_min", "10000000"), ("rate_public_per_min", "10000000")):
    c.execute("INSERT INTO settings VALUES(?,?)", (k, v))
for i in range(20):
    c.execute("INSERT INTO users(username,display_name,password_hash,role,quota_bytes,created_at) VALUES(?,?,?,?,?,?)", ("user%d" % i, "u", H, "user", 50 * 1024 * 1024, now()))
c.execute("INSERT INTO users(username,display_name,password_hash,role,quota_bytes,created_at) VALUES('boss','b',?,'admin',10000000000,?)", (H, now()))
c.execute("INSERT INTO users(username,display_name,password_hash,role,quota_bytes,created_at) VALUES('tiny','t',?,'user',3000000,?)", (H, now()))
c.commit(); c.close()
log = open(os.path.join(TMP, "srv.log"), "w")
srv = subprocess.Popen([sys.executable, "wsgi.py"], cwd=ROOT, stdout=log, stderr=log, env=os.environ)
for _ in range(50):
    try: http.client.HTTPConnection("127.0.0.1", 8095, timeout=1).request("GET", "/api/health"); break
    except Exception: time.sleep(.2)

class Cl:
    def __init__(s, user):
        s.cookie = ""; s.csrf = ""
        r = s.req("POST", "/api/login", {"username": user, "password": PW}); s.csrf = r[1]["csrf"]
    def req(s, m, p, body=None, raw=None, headers=None):
        con = http.client.HTTPConnection("127.0.0.1", 8095, timeout=60)
        h = {"X-CSRF-Token": s.csrf, "Cookie": s.cookie}; h.update(headers or {})
        data = raw
        if body is not None: data = json.dumps(body).encode(); h["Content-Type"] = "application/json"
        con.request(m, p, data, h); r = con.getresponse(); b = r.read()
        for k, v in r.getheaders():
            if k.lower() == "set-cookie": s.cookie = v.split(";")[0]
        try: j = json.loads(b)
        except Exception: j = b
        con.close(); return r.status, j
    def upload(s, name, data, folder=None):
        st, j = s.req("POST", "/api/uploads", {"name": name, "size": len(data), "folder_id": folder})
        if st != 201: return st, j
        cs = j["chunk_size"]
        for i in range(j["total_chunks"]):
            st2, j2 = s.req("PUT", "/api/uploads/%s/chunks/%d" % (j["upload_id"], i), raw=data[i*cs:(i+1)*cs])
            if st2 != 200: return st2, j2
        return s.req("POST", "/api/uploads/%s/complete" % j["upload_id"])

AN = Cl.__new__(Cl); AN.csrf = ""; AN.cookie = ""
results = []; fails = []
def check(name, ok, info=""):
    results.append((name, ok)); print(("PASS " if ok else "FAIL ") + name + (" -> " + str(info) if info and not ok else ""))
    if not ok: fails.append(name)

# 1. 20 users in parallel, 6 files each (mixed sizes, multi-chunk), verify hashes
t0 = time.time(); errs = []
def worker(i):
    try:
        cl = Cl("user%d" % i); sums = {}
        for k in range(6):
            data = os.urandom(random.choice([0, 1, 4096, 4194304, 4194305, 9000000]))
            st, j = cl.upload("f%d.bin" % k, data)
            if st != 201: errs.append((i, k, st, j)); continue
            sums[j["id"]] = hashlib.sha256(data).hexdigest()
        for fid, sh in sums.items():
            st, b = cl.req("GET", "/api/files/%d/download" % fid)
            raw = b if isinstance(b, bytes) else json.dumps(b).encode()
            if hashlib.sha256(raw).hexdigest() != sh: errs.append((i, "hash", fid))
    except Exception as e: errs.append((i, repr(e)))
ths = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
[t.start() for t in ths]; [t.join() for t in ths]
check("20 users x 6 files parallel upload+download integrity (%.1fs)" % (time.time() - t0), not errs, errs[:3])

# 2. quota race: 12 parallel inits of 1MB on a 3MB-quota account -> at most 3 may be reserved
tiny = Cl("tiny"); codes = []
def init():
    codes.append(tiny.req("POST", "/api/uploads", {"name": "x", "size": 1000000})[0])
ths = [threading.Thread(target=init) for _ in range(12)]; [t.start() for t in ths]; [t.join() for t in ths]
check("quota race on upload init (accepted=%d, limit 3)" % codes.count(201), codes.count(201) <= 3, codes)

# 3. double-complete race on same upload -> exactly one file
u = Cl("user0"); st, j = u.req("POST", "/api/uploads", {"name": "race.bin", "size": 10})
u.req("PUT", "/api/uploads/%s/chunks/0" % j["upload_id"], raw=b"0123456789")
outs = []
def comp(): outs.append(u.req("POST", "/api/uploads/%s/complete" % j["upload_id"])[0])
ths = [threading.Thread(target=comp) for _ in range(8)]; [t.start() for t in ths]; [t.join() for t in ths]
n = sqlite3.connect(os.path.join(TMP, "cloud_drive.db")).execute("SELECT COUNT(*) FROM files WHERE name LIKE 'race.bin%'").fetchone()[0]
check("double-complete race creates exactly 1 file (got %d, codes %s)" % (n, sorted(outs)), n == 1, outs)

# 4. parallel trash/restore/purge on same file
f = u.upload("tp.bin", b"abc")[1]["id"]; outs = []
def churn():
    for _ in range(10):
        for p in ("/api/items/trash", "/api/items/restore", "/api/items/purge"):
            outs.append(u.req("POST", p, {"files": [f]})[0])
ths = [threading.Thread(target=churn) for _ in range(6)]; [t.start() for t in ths]; [t.join() for t in ths]
check("trash/restore/purge race: no 5xx", all(c < 500 for c in outs), sorted(set(outs)))

# 5. shares under parallel download + counter
f = u.upload("pub.bin", b"hello world")[1]["id"]
sh = u.req("POST", "/api/files/%d/shares" % f, {})[1]; tok = sh["token"]; outs = []
def dl():
    for _ in range(15): outs.append(Cl.req(AN, "GET", "/api/public/%s/download" % tok)[0])
ths = [threading.Thread(target=dl) for _ in range(10)]; [t.start() for t in ths]; [t.join() for t in ths]
cnt = u.req("GET", "/api/shares")[1]["items"][0]["downloads"]
check("150 parallel public downloads all 200 (counter=%d)" % cnt, outs.count(200) == 150 and cnt == 150, (set(outs), cnt))

# 6. fuzz: random methods/paths/bodies on all routes, expect no 5xx
ws = ["files", "items", "folders", "uploads", "admin", "users", "shares", "public", "me", "settings", "stats", "trash", "chunks", "download", "preview", "audit", "events", "health", "ban", "unban", "login", "register", "activity"]
def rnd_val(d=0):
    return random.choice([None, True, False, 0, -1, 2**63, 1.5, "", "a" * random.randint(1, 300), "../../x", "' OR 1=1--", "\x00", "<b>", [], {}, [1, "a", None], {"a": {"b": [1]}}]) if d > 2 else random.choice([lambda: rnd_val(3), lambda: [rnd_val(d + 1) for _ in range(3)], lambda: {k: rnd_val(d + 1) for k in random.sample(["name", "size", "folder_id", "parent_id", "files", "folders", "password", "expires_hours", "role", "quota_bytes", "is_active", "reason", "settings", "confirm_password", "username", "email", "display_name", "all", "current_password", "new_password"], 4)}])()
boss = Cl("boss"); bad = []; total = 0
def fuzz(cl, n):
    global total
    for _ in range(n):
        p = "/api/" + "/".join(random.choice(ws + [str(random.randint(-2, 9999)), "x", "..", "%00", "%2e%2e"]) for _ in range(random.randint(1, 4)))
        m = random.choice(["GET", "POST", "PUT", "PATCH", "DELETE"]); body = rnd_val() if m != "GET" else None
        try:
            st, j = cl.req(m, p, body if isinstance(body, (dict, list, str, int, float, bool)) or body is None else None)
        except Exception as e: bad.append((m, p, repr(e))); continue
        total += 1
        if st >= 500: bad.append((m, p, body, st))
        if isinstance(j, (bytes, str)) and (b"Traceback" in (j if isinstance(j, bytes) else j.encode())): bad.append((m, p, "traceback"))
ths = [threading.Thread(target=fuzz, args=(random.choice([boss, u, Cl("user5"), Cl("user6")]), 400)) for _ in range(8)]
[t.start() for t in ths]; [t.join() for t in ths]
check("fuzz %d random requests (user+admin): no 5xx/tracebacks" % total, not bad, bad[:3])

# 7. unauthenticated fuzz
anon = Cl.__new__(Cl); anon.csrf = ""; anon.cookie = ""; bad = []; total = 0
ths = [threading.Thread(target=fuzz, args=(anon, 300)) for _ in range(5)]; [t.start() for t in ths]; [t.join() for t in ths]
check("anonymous fuzz %d requests: no 5xx" % total, not bad, bad[:3])

# 8. big file 120MB end-to-end
t0 = time.time(); data = os.urandom(120 * 1024 * 1024)
adm = Cl("boss"); st, j = adm.upload("huge.bin", data)
ok = st == 201
if ok:
    con = http.client.HTTPConnection("127.0.0.1", 8095, timeout=120); con.request("GET", "/api/files/%d/download" % j["id"], headers={"Cookie": adm.cookie}); r = con.getresponse()
    h = hashlib.sha256()
    while True:
        b = r.read(1 << 20)
        if not b: break
        h.update(b)
    ok = h.hexdigest() == hashlib.sha256(data).hexdigest()
check("120MB file upload+download hash (%.1fs)" % (time.time() - t0), ok, st)

# 9. brute-force + header injection sanity
r = [anon.req("POST", "/api/login", {"username": "user1", "password": "Nope-%d-xyz" % i})[0] for i in range(25)]
check("password guessing on real account is blocked (429 seen=%s, 200 seen=%s)" % (429 in r, 200 in r), 429 in r and 200 not in r)

# 10. integrity: db + disk consistency + leftovers
time.sleep(1); srv.terminate(); srv.wait(); log.close()
d = sqlite3.connect(os.path.join(TMP, "cloud_drive.db"))
check("SQLite integrity_check == ok", d.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
check("foreign_key_check clean", d.execute("PRAGMA foreign_key_check").fetchall() == [])
db_files = {r[0] for r in d.execute("SELECT stored_name FROM files")}
disk = {p for p in os.listdir(os.path.join(TMP, "uploads")) for p in os.listdir(os.path.join(TMP, "uploads", p))}
check("no orphan files on disk (%d disk / %d db)" % (len(disk), len(db_files)), disk - {x for x in disk if x.endswith('.tmp')} == db_files, (len(disk - db_files), len(db_files - disk)))
q = d.execute("SELECT u.username,u.quota_bytes,COALESCE(SUM(f.size),0) FROM users u LEFT JOIN files f ON f.owner_id=u.id GROUP BY u.id HAVING SUM(f.size)>u.quota_bytes").fetchall()
check("no user exceeds quota", not q, q)
srvlog = open(os.path.join(TMP, "srv.log")).read(); print(srvlog[srvlog.find("Traceback"):][:1500] if "Traceback" in srvlog else "")
check("server log has no unhandled exceptions", "Traceback" not in srvlog, srvlog[srvlog.find("Traceback"):][:600])
shutil.rmtree(TMP, ignore_errors=True)
print("\nTOTAL %d  PASSED %d  FAILED %d" % (len(results), sum(1 for _, o in results if o), len(fails)))
