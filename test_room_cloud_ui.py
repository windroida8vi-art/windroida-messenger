"""Real-browser test of the chess screen: two players in two browser contexts play a short game (needs playwright+chromium).
Run: python test_room_cloud_ui.py"""
import os, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
tmp = Path(tempfile.mkdtemp()); common.DATA_DIR = tmp; common.UPLOADS_DIR = tmp/"u"; common.AVATARS_DIR = tmp/"a"; common.WALLPAPERS_DIR = tmp/"w"; common.ROOMAUDIO_DIR = tmp/"r"; common.FILES_DIR = tmp/"f"; (tmp/"f").mkdir()
import server as srv
from client_core import Client
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("chess ui: skipped (playwright not installed)"); os._exit(0)
S = srv.WindroidaServer("127.0.0.1", 0, db_path=tmp/"t.db", web_port=0); port = S.start()
S._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
PW = "Str0ng-pass1"
def reg(n):
    c = Client(); c.connect("127.0.0.1", port)
    r = c.call("register", username=n, password=PW, display_name=n, sec_question="سوال تستی؟", sec_answer="x1"); assert r["ok"], r
    return r["token"] if "token" in r else r.get("session")
ta, tb, tc = reg("alice"), reg("bobby"), reg("gina")
bad = []; ok = 0
def check(n, c):
    global ok
    if c: ok += 1
    else: bad.append(n); print("FAIL", n)
import subprocess
if not os.path.exists("/tmp/t.webm"):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=4:size=160x120:rate=15", "-f", "lavfi", "-i", "sine=duration=4", "-c:v", "libvpx", "-c:a", "libvorbis", "/tmp/t.webm"], check=True)
url = f"http://127.0.0.1:{S.web_port}/"
with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
    def page(tok):
        ctx = b.new_context(viewport={"width": 420, "height": 860}); pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.add_init_script(f"try{{localStorage.setItem('wd-token','{tok}')}}catch(e){{}}")
        pg.goto(url); pg.wait_for_timeout(1500); pg.errs = errs; return pg
    A, B = page(ta), page(tb)
    A.evaluate("rOpen('room_open',{title:'تماشا'})"); A.wait_for_timeout(1000)
    A.evaluate("call('room_invite',{room:R.id,username:'bobby'})"); rid=A.evaluate("R.id")
    B.evaluate(f"rOpen('room_join',{{room:'{rid}'}})"); B.wait_for_timeout(1200)
    A.evaluate("R.tab='queue';rDrawTabs();rDrawPane()"); A.wait_for_timeout(300)
    with A.expect_file_chooser() as fc: A.locator("#room button", has_text="فیلم از گوشی خودت").click()
    fc.value.set_files("/tmp/t.webm"); A.wait_for_timeout(600)
    check("asks how to share the movie", A.locator("#modal button", has_text="آپلود به سرور").count() == 1)
    A.locator("#modal button", has_text="آپلود به سرور").click(); A.wait_for_timeout(3000)
    check("queue item is a server movie", A.evaluate("R.st.queue.length==1&&!!R.st.queue[0].lib&&R.st.queue[0].kind==='video'"))
    check("bobby has a video element that loaded", B.evaluate("!!R.el&&R.el.readyState>=1&&!R.err"))
    A.evaluate("rctl('play')"); A.wait_for_timeout(2500)
    check("bobby is really playing in sync", B.evaluate("R.el&&!R.el.paused&&R.el.currentTime>1") and abs(A.evaluate("R.el.currentTime")-B.evaluate("R.el.currentTime"))<1.5)
    # local choice keeps old behaviour
    A.evaluate("rctl('remove',{item:R.st.queue[0].id})"); A.wait_for_timeout(500)
    with A.expect_file_chooser() as fc: A.locator("#room button", has_text="فیلم از گوشی خودت").click()
    fc.value.set_files("/tmp/t.webm"); A.wait_for_timeout(500)
    A.locator("#modal button", has_text="لوکالی").click(); A.wait_for_timeout(1500)
    check("local choice: queued without lib", A.evaluate("R.st.queue.length===1&&!R.st.queue[0].lib"))
    check("local choice: bobby has no file", B.evaluate("!R.el"))
    check("no page errors", not A.errs and not B.errs)
    if A.errs or B.errs: print(A.errs[:3], B.errs[:3])
    b.close()
print("room cloud ui:", ok, "ok", len(bad), "failed")
os._exit(1 if bad else 0)
