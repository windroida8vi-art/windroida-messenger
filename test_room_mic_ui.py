"""Real-browser test of room voice: A's (fake) microphone is heard by B; mic off stops it. Run: python test_room_mic_ui.py"""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
tmp = Path(tempfile.mkdtemp()); common.DATA_DIR = tmp; common.UPLOADS_DIR = tmp/"u"; common.AVATARS_DIR = tmp/"a"; common.WALLPAPERS_DIR = tmp/"w"; common.ROOMAUDIO_DIR = tmp/"r"; common.FILES_DIR = tmp/"f"; (tmp/"f").mkdir()
import server as srv
from client_core import Client
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("room mic ui: skipped"); os._exit(0)
S = srv.WindroidaServer("127.0.0.1", 0, db_path=tmp/"t.db", web_port=0); port = S.start()
S._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
def reg(n):
    c = Client(); c.connect("127.0.0.1", port)
    r = c.call("register", username=n, password="Str0ng-pass1", display_name=n, sec_question="سوال تستی؟", sec_answer="x1"); return r.get("session") or r.get("token")
ta, tb = reg("alice"), reg("bobby")
bad = []; ok = 0
def check(n, c, x=""):
    global ok
    if c: ok += 1
    else: bad.append(n); print("FAIL", n, x)
url = f"http://127.0.0.1:{S.web_port}/"
with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required", "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
    def page(tok):
        ctx = b.new_context(viewport={"width": 420, "height": 860}, permissions=["microphone", "camera"]); pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.add_init_script(f"try{{localStorage.setItem('wd-token','{tok}')}}catch(e){{}}")
        pg.goto(url); pg.wait_for_timeout(1500); pg.errs = errs; return pg
    A, B = page(ta), page(tb)
    A.evaluate("rOpen('room_open',{title:'voice'})"); A.wait_for_timeout(900); rid = A.evaluate("R.id")
    B.evaluate(f"rOpen('room_join',{{room:'{rid}'}})"); B.wait_for_timeout(1200)
    A.evaluate("rMic()"); A.wait_for_timeout(3500)
    check("alice's mic is on", A.evaluate("!!R.mic"))
    st = B.evaluate("Object.keys(R.voices).length")
    check("bobby receives alice's voice", st >= 1, st)
    check("members list shows alice's mic flag", B.evaluate("R.members.some(m=>m.mic)"))
    A.evaluate("rMicOff()"); A.wait_for_timeout(1500)
    check("mic off: flag cleared for bobby", B.evaluate("!R.members.some(m=>m.mic)"))
    errs = [e for pg in (A, B) for e in pg.errs if "favicon" not in e]
    check("no page errors", not errs, errs[:3])
    b.close()
print(f"{ok} ok, {len(bad)} failed"); os._exit(1 if bad else 0)
