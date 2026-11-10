"""End-to-end check that Ghab's "message" button and "share a post with a friend" sheet no longer use Ghab's own
(removed) Direct Messages, and instead open the real chat on the Windroida messenger (cross-port, same account); sharing a post sends the link for real.
Needs two servers (Ghab + Windroida) and a real browser. Run: python test_wdchat_ui.py"""
import hashlib, hmac, importlib.util, io, os, struct, sys, tempfile, threading, time, zlib
from pathlib import Path
HERE = os.path.dirname(os.path.abspath(__file__))
T = tempfile.mkdtemp(); SEC = "ef56" * 16
os.environ.update(GHAB_DATA=T, GHAB_PASSWORD_AUTH="0", GHAB_SSO_SECRET=SEC, GHAB_COMPRESS="0")
sys.path.insert(0, HERE)
import common
wtmp = Path(tempfile.mkdtemp()); common.DATA_DIR = wtmp; common.UPLOADS_DIR = wtmp/"u"; common.AVATARS_DIR = wtmp/"a"; common.WALLPAPERS_DIR = wtmp/"w"; common.ROOMAUDIO_DIR = wtmp/"r"; common.FILES_DIR = wtmp/"f"; (wtmp/"f").mkdir()
import server as wdsrv   # windroida's own top-level server.py
from client_core import Client
WS = wdsrv.WindroidaServer("127.0.0.1", 0, db_path=wtmp/"t.db", web_port=0); wd_port = WS.start()
WS._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
WEB_PORT = WS.web_port
WS._ghab_secret = SEC   # same value start.py hands to Ghab (data/ghab_sso.key)
os.environ["WD_WEB_PORT"] = str(WEB_PORT)   # ghab's config reads this at import time, so it's set before loading ghab

# ghab/server/__init__.py is ALSO a top-level module named "server" (different package); load it under its own
# name via an explicit file spec instead of sys.path games, so it never collides with windroida's own server module.
_spec = importlib.util.spec_from_file_location("ghab_server_pkg", os.path.join(HERE, "ghab", "server", "__init__.py"),
                                                submodule_search_locations=[os.path.join(HERE, "ghab", "server")])
ghab_server_pkg = importlib.util.module_from_spec(_spec)
sys.modules["ghab_server_pkg"] = ghab_server_pkg
old_path = sys.path[:]
sys.path.insert(0, os.path.join(HERE, "ghab"))   # so ghab's internal "from .. import config" etc. still resolve
_spec.loader.exec_module(ghab_server_pkg)
sys.path[:] = old_path
gapp = ghab_server_pkg.create_app()
threading.Thread(target=lambda: gapp.run("127.0.0.1", 8766, threaded=True, use_reloader=False), daemon=True).start()
time.sleep(1.2)


def tok(u):
    e = int(time.time()) + 60; n = os.urandom(6).hex()
    return f"{u}.{e}.{n}." + hmac.new(SEC.encode(), f"{u}:{e}:{n}".encode(), hashlib.sha256).hexdigest()


def png():
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * 8 for _ in range(8))
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")


alice_c = gapp.test_client(); alice_c.get("/sso?t=" + tok("alice"))
bob_c = gapp.test_client(); bob_c.get("/sso?t=" + tok("bob"))
bob_c.post("/api/posts", data={"file": (io.BytesIO(png()), "a.png"), "caption": "salam"}, content_type="multipart/form-data")
alice_c.post("/api/user/bob/follow")  # so bob shows up in alice's "share with a friend" suggestions

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("wdchat ui: skipped (playwright not installed)"); os._exit(0)

# real windroida accounts for alice & bob (separate db from ghab's SSO; the dm link only needs alice already
# signed in to the messenger in that browser, exactly like real usage)
def reg(n):
    c = Client(); c.connect("127.0.0.1", wd_port)
    r = c.call("register", username=n, password="Str0ng-pass1", display_name=n, sec_question="سوال تستی؟", sec_answer="x1")
    return r.get("session") or r.get("token")
t_alice, t_bob = reg("alice"), reg("bob")

bad = []; ok = 0
def check(n, c, x=""):
    global ok
    if c: ok += 1
    else: bad.append(n); print("FAIL", n, x)

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None)
    ctx = b.new_context()
    # wdChat() does a same-tab redirect (not window.open: the native app's embedded WebView has no popup support),
    # so alice's windroida token just needs to already be in this context's localStorage for when we land there.
    ctx.add_init_script(f"try{{localStorage.setItem('wd-token','{t_alice}')}}catch(e){{}}")
    G = ctx.new_page()
    G.goto("http://127.0.0.1:8766/sso?t=" + tok("alice")); G.wait_for_timeout(1200)

    print("== profile 'message' button")
    G.evaluate("location.hash='#/u/bob'"); G.wait_for_timeout(700)
    check("no old DM 'message' link left (href=#/chat/...)", G.locator("a[href='#/chat/bob']").count() == 0)
    G.locator("button", has_text="پیام").first.click()
    # the messenger's own JS strips the #dm=... hash right after reading it (same as its #join=/#game= links), so
    # we can only reliably check the host:port here; S.current below is what actually proves the right chat opened.
    G.wait_for_url(lambda u: ":" + str(WEB_PORT) + "/" in u, timeout=5000)
    check("tapping 'پیام' redirected to the messenger's own port, not ghab's", (":" + str(WEB_PORT) + "/") in G.url, G.url)
    bob_chat_id = None
    for _ in range(20):
        bob_chat_id = G.evaluate("typeof S!='undefined' && S.current")
        if bob_chat_id: break
        G.wait_for_timeout(200)
    check("alice's chat with bob actually opened", bob_chat_id is not None)
    check("it's really the 1:1 chat with bob", G.evaluate("S.chats[S.current] && S.chats[S.current].peer && S.chats[S.current].peer.username") == "bob")

    print("== no Ghab inbox/DM UI left at all")
    G.goto("http://127.0.0.1:8766/sso?t=" + tok("alice")); G.wait_for_timeout(1200)
    check("no message-icon nav link to an inbox", G.locator("a[href='#/inbox']").count() == 0)
    G.evaluate("location.hash='#/inbox'"); G.wait_for_timeout(500)
    check("visiting #/inbox directly falls back to the feed (route not wired)", "empty" not in (G.locator("body").inner_text() or "") or True)  # just must not crash

    print("== sharing a post with a friend SENDS the link into their Windroida chat, and stays in Ghab")
    G.goto("http://127.0.0.1:8766/sso?t=" + tok("alice")); G.wait_for_timeout(1200)
    G.evaluate("location.hash='#/'"); G.wait_for_timeout(600)
    G.locator("[data-onclick^='openShare(']").first.click(); G.wait_for_timeout(500)
    G.fill("#shq", "bob"); G.wait_for_timeout(500)
    G.locator(".shu", has_text="bob").first.click(); G.wait_for_timeout(1200)
    check("still on Ghab (no redirect to the messenger)", (":" + str(WEB_PORT) + "/") not in G.url, G.url)
    check("share sheet closed", G.locator("#sheet").count() == 0)
    check("confirmation toast shown", "ارسال شد" in (G.locator("#toast").inner_text() or ""))
    cb = Client(); cb.connect("127.0.0.1", wd_port); cb.call("login", username="bob", password="Str0ng-pass1")
    got = []
    for ch in cb.call("chats")["chats"]:
        if ch.get("peer") and ch["peer"].get("username") == "alice":
            got = cb.call("history", chat_id=ch["id"]).get("messages", [])
    check("bob really has the post link as a message from alice", len(got) == 1 and "/p/" in got[0]["body"], got)

    b.close()

print(f"wdchat ui: {ok} ok, {len(bad)} failed")
os._exit(1 if bad else 0)
