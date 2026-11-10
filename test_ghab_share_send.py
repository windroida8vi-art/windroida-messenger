"""Ghab «ارسال» → the post link lands as a REAL message in the friend's Windroida chat (server to server).
Two real servers, no browser. Run: python test_ghab_share_send.py"""
import hashlib, hmac, importlib.util, io, json, os, struct, sys, tempfile, threading, time, urllib.request, zlib
from pathlib import Path
HERE = os.path.dirname(os.path.abspath(__file__))
T = tempfile.mkdtemp(); SEC = "ef56" * 16
os.environ.update(GHAB_DATA=T, GHAB_PASSWORD_AUTH="0", GHAB_SSO_SECRET=SEC, GHAB_COMPRESS="0")
sys.path.insert(0, HERE)
import common
wtmp = Path(tempfile.mkdtemp()); common.DATA_DIR = wtmp; common.UPLOADS_DIR = wtmp/"u"; common.AVATARS_DIR = wtmp/"a"; common.WALLPAPERS_DIR = wtmp/"w"; common.ROOMAUDIO_DIR = wtmp/"r"; common.FILES_DIR = wtmp/"f"; (wtmp/"f").mkdir()
import server as wdsrv
from client_core import Client
WS = wdsrv.WindroidaServer("127.0.0.1", 0, db_path=wtmp/"t.db", web_port=0); wd_port = WS.start()
WS._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
WEB_PORT = WS.web_port
os.environ["WD_WEB_PORT"] = str(WEB_PORT)
# the real Ghab<->Windroida secret is Windroida's own ghab_sso.key; Ghab is given exactly that value (start.py does the same)
WS._ghab_secret = SEC

_spec = importlib.util.spec_from_file_location("ghab_server_pkg", os.path.join(HERE, "ghab", "server", "__init__.py"),
                                                submodule_search_locations=[os.path.join(HERE, "ghab", "server")])
gp = importlib.util.module_from_spec(_spec); sys.modules["ghab_server_pkg"] = gp
old = sys.path[:]; sys.path.insert(0, os.path.join(HERE, "ghab")); _spec.loader.exec_module(gp); sys.path[:] = old
gapp = gp.create_app()

bad = []; ok = 0
def check(n, c, x=""):
    global ok
    if c: ok += 1
    else: bad.append(n); print("FAIL", n, x)

def tok(u):
    e = int(time.time()) + 60; n = os.urandom(6).hex()
    return f"{u}.{e}.{n}." + hmac.new(SEC.encode(), f"{u}:{e}:{n}".encode(), hashlib.sha256).hexdigest()

def png():
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * 8 for _ in range(8))
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")

def reg(n):
    c = Client(); c.connect("127.0.0.1", wd_port)
    r = c.call("register", username=n, password="Str0ng-pass1", display_name=n, sec_question="سوال تستی؟", sec_answer="x1")
    return c, (r.get("session") or r.get("token"))
ca, _ = reg("alice"); cb, _ = reg("bob"); cc, _ = reg("carol")

A = gapp.test_client(); A.get("/sso?t=" + tok("alice"))
B = gapp.test_client(); B.get("/sso?t=" + tok("bob"))
C = gapp.test_client(); C.get("/sso?t=" + tok("carol"))
rp = B.post("/api/posts", data={"file": (io.BytesIO(png()), "a.png"), "caption": "salam"}, content_type="multipart/form-data")
pid = rp.get_json()["id"] if rp.get_json() and "id" in rp.get_json() else 1
def gid(c): return c.get("/api/me").get_json()["id"]
bob_id, carol_id = gid(B), gid(C)
A.post("/api/user/bob/follow")          # carol is deliberately NOT followed

def msgs_for(client, other):
    chats = client.call("chats")["chats"]
    for ch in chats:
        if ch.get("peer") and ch["peer"].get("username") == other:
            return [m for m in client.call("history", chat_id=ch["id"]).get("messages", [])]
    return []

print("== happy path")
r = A.post("/api/share/send", json={"post_id": pid, "to": bob_id, "origin": "http://localhost"})
check("200 ok", r.status_code == 200 and r.get_json().get("ok"), (r.status_code, r.get_data(as_text=True)))
m = msgs_for(cb, "alice")
check("bob got exactly one message in his chat with alice", len(m) == 1, m)
check("it's the post link", m and m[0]["body"].endswith(f"/p/{pid}"), m)
check("sender is alice", m and m[0].get("sender_id") == ca.call("me")["me"]["id"] if m and "me" in ca.call("me") else bool(m))
r = A.post("/api/share/send", json={"post_id": pid, "to": bob_id})
check("again works and adds a second message (no dedupe surprise)", r.status_code == 200 and len(msgs_for(cb, "alice")) == 2)

print("== refusals")
check("not-followed user refused", A.post("/api/share/send", json={"post_id": pid, "to": carol_id}).status_code == 400)
check("to=self refused", A.post("/api/share/send", json={"post_id": pid, "to": gid(A)}).status_code == 400)
check("garbage ids refused", A.post("/api/share/send", json={"post_id": "x", "to": "y"}).status_code == 400)
check("missing post 404", A.post("/api/share/send", json={"post_id": 99999, "to": bob_id}).status_code == 404)
anon = gapp.test_client()
check("not logged in -> 401", anon.post("/api/share/send", json={"post_id": pid, "to": bob_id}).status_code == 401)
check("carol got nothing", msgs_for(cc, "alice") == [])
r = A.post("/api/share/send", json={"post_id": pid, "to": bob_id, "origin": "http://evil.example"})
last = msgs_for(cb, "alice")[-1]["body"]
check("foreign origin ignored (link uses the real host)", "evil.example" not in last, last)

print("== the endpoint itself can't be abused")
def raw(payload):
    rq = urllib.request.Request(f"http://127.0.0.1:{WEB_PORT}/ghab-share", data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(rq, timeout=5) as r: return r.status
    except urllib.error.HTTPError as e: return e.code
def signed(frm, to, text, secret=SEC, exp=None, nonce=None):
    exp = exp or int(time.time()) + 60; nonce = nonce or os.urandom(4).hex()
    sig = hmac.new(secret.encode(), f"share:{frm}:{to}:{exp}:{nonce}:{hashlib.sha256(text.encode()).hexdigest()}".encode(), "sha256").hexdigest()
    return dict({"from": frm, "to": to, "text": text, "exp": exp, "nonce": nonce, "sig": sig})
check("wrong secret -> 403", raw(signed("alice", "bob", "hi", secret="00" * 32)) == 403)
p = signed("alice", "bob", "x"); p["text"] = "tampered"
check("tampered text -> 403", raw(p) == 403)
p = signed("alice", "bob", "x"); p["from"] = "carol"
check("changed sender -> 403", raw(p) == 403)
check("expired -> 400", raw(signed("alice", "bob", "x", exp=int(time.time()) - 5)) == 400)
p = signed("alice", "bob", "one-time")
check("valid -> 200", raw(p) == 200)
check("replay -> 400", raw(p) == 400)
check("unknown user -> 404", raw(signed("alice", "nobody", "x")) == 404)
check("garbage body -> 400", raw({"x": 1}) == 400)

print("== fallback flag when Windroida can't be reached")
import ghab_server_pkg.routes.messages as gm
real = gm.config.WD_PORT; gm.config.WD_PORT = 1
r = A.post("/api/share/send", json={"post_id": pid, "to": bob_id})
check("unreachable -> 502 with fb=true (browser then uses the old open-chat way)", r.status_code == 502 and r.get_json().get("fb") is True, (r.status_code, r.get_data(as_text=True)))
gm.config.WD_PORT = real

print(f"ghab share send: {ok} ok, {len(bad)} failed")
os._exit(1 if bad else 0)
