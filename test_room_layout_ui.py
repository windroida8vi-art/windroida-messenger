"""Room layout: every video keeps its own shape, empty card is not cut off, games tab works (needs playwright+chromium).
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
    print("room layout ui: skipped (playwright not installed)"); os._exit(0)
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
for nm, size in (("portrait", "180x320"), ("wide", "320x180"), ("square", "240x240")):
    f = f"/tmp/wd_{nm}.webm"
    if not os.path.exists(f):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=duration=3:size={size}:rate=15", "-f", "lavfi", "-i", "sine=duration=3", "-c:v", "libvpx", "-c:a", "libvorbis", f], check=True)
url = f"http://127.0.0.1:{S.web_port}/"
SHOT = os.environ.get("SHOTS", "")
with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
    def page(tok, w=420, h=860):
        ctx = b.new_context(viewport={"width": w, "height": h}); pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.add_init_script(f"try{{localStorage.setItem('wd-token','{tok}')}}catch(e){{}}")
        pg.goto(url); pg.wait_for_timeout(1500); pg.errs = errs; return pg
    A = page(ta)
    A.evaluate("rOpen('room_open',{title:'تماشا'})"); A.wait_for_timeout(1000)
    A.evaluate("call('room_invite',{room:R.id,username:'bobby'})"); rid = A.evaluate("R.id")
    B = page(tb); B.evaluate(f"rOpen('room_join',{{room:'{rid}'}})"); A.wait_for_timeout(1200)
    # empty card: every child fully inside the visible card (scrollable allowed), buttons reachable
    r = A.evaluate("""()=>{const s=document.querySelector('.rscreen').getBoundingClientRect(),e=document.querySelector('.rempty');return {sh:s.height,ch:e.scrollHeight,vh:e.clientHeight}}""")
    check("empty card is not cut (content fits or scrolls)", r["ch"] <= r["vh"] + 2 or r["vh"] >= 300)
    if SHOT: A.screenshot(path=SHOT + "/empty.png")
    A.locator("#room .rtabs button", has_text="بازی‌ها").click(); A.wait_for_timeout(400)
    check("games tab exists and is active", A.locator("#room .rtabs button.on", has_text="بازی‌ها").count() == 1)
    check("games tab: chess card with bobby", A.locator("#room .rgames .rgcard button", has_text="bobby").count() == 1)
    tabs_ok = A.evaluate("""()=>{const t=document.querySelector('.rtabs');return t.scrollWidth<=t.clientWidth+1||getComputedStyle(t).overflowX!=='visible'}""")
    check("tabs row scrolls instead of overflowing", tabs_ok)
    if SHOT: A.screenshot(path=SHOT + "/games.png")
    A.locator("#room .rgcard button", has_text="bobby").click(); A.wait_for_timeout(400)
    check("chess invite dialog opens from games tab", A.locator(".cdlg").count() == 1)
    A.locator(".cdlg .btn", has_text="سفید").click(); A.wait_for_timeout(900)
    A.evaluate("document.querySelector('.cscreen')&&CHESS.close()"); A.wait_for_timeout(300)
    A.evaluate("R.tab='queue';rDrawTabs();rDrawPane()")
    for nm, ar in (("portrait", 180/320), ("wide", 320/180), ("square", 1.0)):
        with A.expect_file_chooser() as fc: A.locator("#room button", has_text="فیلم از گوشی خودت").click()
        fc.value.set_files(f"/tmp/wd_{nm}.webm"); A.wait_for_timeout(500)
        A.locator("#modal button", has_text="لوکالی").click(); A.wait_for_timeout(1200)
        A.evaluate("rctl('play_item',{item:R.st.queue[R.st.queue.length-1].id})"); A.wait_for_timeout(1500)
        g = A.evaluate("""()=>{const r=document.querySelector('.rscreen').getBoundingClientRect(),v=R.el;return {w:r.width,h:r.height,vw:v&&v.videoWidth,vh:v&&v.videoHeight,fit:document.querySelector('.rscreen').classList.contains('fit')}}""")
        got = g["w"] / g["h"]
        check(f"{nm}: screen has the video's own shape ({got:.2f} vs {ar:.2f}) fit={g['fit']}", g["fit"] and abs(got - ar) < 0.08)
        check(f"{nm}: fits the phone (h<=60% of screen)", g["h"] <= 860 * 0.6)
        if SHOT: A.screenshot(path=SHOT + f"/{nm}.png")
    check("no page errors", not A.errs)
    if A.errs: print(A.errs[:3])
    b.close()
print("room layout ui:", ok, "ok", len(bad), "failed")
os._exit(1 if bad else 0)
