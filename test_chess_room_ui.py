"""Real-browser test of the chess screen: two players in two browser contexts play a short game (needs playwright+chromium).
Run: python test_chess_room_ui.py"""
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
url = f"http://127.0.0.1:{S.web_port}/"
with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
    def page(tok):
        ctx = b.new_context(viewport={"width": 420, "height": 860}); pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.add_init_script(f"try{{localStorage.setItem('wd-token','{tok}')}}catch(e){{}}")
        pg.goto(url); pg.wait_for_timeout(1500); pg.errs = errs; return pg
    A, B, C = page(ta), page(tb), page(tc)
    A.evaluate("rOpen('room_open',{title:'تماشا'})"); A.wait_for_timeout(900)
    rid = A.evaluate("R.id"); check("alice opened a room", bool(rid))
    for u in ("bobby", "gina"): A.evaluate(f"call('room_invite',{{room:R.id,username:'{u}'}})")
    for pg in (B, C): pg.evaluate(f"rOpen('room_join',{{room:'{rid}'}})")
    A.wait_for_timeout(900)
    A.evaluate("R.tab='people';rDrawTabs();rDrawPane()"); A.wait_for_timeout(500)
    check("♟ button next to each other member (2)", A.locator("#room .rqi .iconbtn", has_text="♟").count() == 2)
    A.locator("#room .rqi", has_text="bobby").locator(".iconbtn", has_text="♟").click(); A.wait_for_timeout(300)
    A.locator(".cdlg .btn", has_text="سفید").click(); A.wait_for_timeout(900)
    check("bobby gets the invite note", B.locator("#cnote").count() == 1)
    check("gina (spectator) gets no invite note", C.locator("#cnote").count() == 0)
    B.locator("#cnote").click(); B.wait_for_timeout(1200)
    check("bobby's game screen opened (accepted)", B.locator(".cscreen .chb").count() == 1)
    check("alice's screen opened by itself", A.locator(".cscreen .chb").count() == 1)
    check("gina is offered to watch", C.locator("#cnote").count() == 1)
    C.locator("#cnote").click(); C.wait_for_timeout(1000)
    check("gina watches: board + 32 pieces", C.locator(".cscreen .chb").count() == 1 and C.locator(".cp").count() == 32)
    check("gina sees 'spectator'", "تماشاچی" in C.locator("#cstat").inner_text())
    check("gina has no resign button / hints", C.locator("#cres").count() == 0 or not C.locator("#cres").is_visible())
    def sq(pg, name):
        return pg.evaluate("""n=>{const f='abcdefgh'.indexOf(n[0]),r=+n[1]-1;const b=document.querySelector('.chb').getBoundingClientRect();return [b.left+(f+.5)*b.width/8,b.top+(7-r+.5)*b.height/8]}""", name)
    A.mouse.click(*sq(A, "e2")); A.wait_for_timeout(150); A.mouse.click(*sq(A, "e4")); A.wait_for_timeout(800)
    C.wait_for_timeout(500)
    check("gina sees alice's move live", C.locator(".cmoves .chmv").count() == 1)
    C.mouse.click(*sq(C, "e7")); C.wait_for_timeout(200)
    check("spectator click shows no hints", C.locator(".chsq.chtg").count() == 0)
    check("no page errors", not A.errs and not B.errs and not C.errs)
    if A.errs or B.errs or C.errs: print(A.errs[:3], B.errs[:3], C.errs[:3])
    b.close()
print("chess room ui:", ok, "ok", len(bad), "failed")
os._exit(1 if bad else 0)
