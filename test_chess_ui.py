"""Real-browser test of the chess screen: two players in two browser contexts play a short game (needs playwright+chromium).
Run: python test_chess_ui.py"""
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
ta, tb = reg("alice"), reg("bobby")
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
    A, B = page(ta), page(tb)
    # open the private chat both ways via the app's own helpers
    A.evaluate("call('open_private',{username:'bobby'}).then(r=>{S.chats[r.chat.id]=r.chat;return openChat?openChat(r.chat.id):0})"); A.wait_for_timeout(800)
    cid = A.evaluate("S.current")
    check("chat open", cid is not None)
    check("game button exists", A.locator("#gamebtn").count() == 1)
    A.click("#gamebtn"); A.wait_for_timeout(300)
    check("chooser lists chess", A.locator(".cdlg .cmini").count() >= 1)
    A.locator(".cdlg .btn", has_text="سفید").first.click(); A.wait_for_timeout(900)
    check("invite card in alice's chat", A.locator(".gcard").count() == 1)
    B.evaluate(f"openChat({cid})"); B.wait_for_timeout(1200)
    check("invite card in bobby's chat with accept button", B.locator(".gcard .btn", has_text="قبول").count() == 1)
    B.locator(".gcard .btn", has_text="قبول").click(); B.wait_for_timeout(1200)
    check("bobby's game screen opened", B.locator(".cscreen .chb").count() == 1 and B.locator(".cp").count() == 32)
    check("alice sees the note / can open", A.locator("#cnote").count() == 1 or A.locator(".cscreen").count() == 1)
    if A.locator(".cscreen").count() == 0:
        A.locator("#cnote").click(); A.wait_for_timeout(600)
    check("alice (white) bottom bar has turn glow", A.locator(".cbar.me.chturn").count() == 1)
    check("alice sees 32 pieces", A.locator(".cp").count() == 32)
    def sq(pg, name):  # centre of a square in page coordinates
        return pg.evaluate("""n=>{const f='abcdefgh'.indexOf(n[0]),r=+n[1]-1;const flip=G_flip();const c=flip?7-f:f,rw=flip?r:7-r;const b=document.querySelector('.chb').getBoundingClientRect();return [b.left+(c+.5)*b.width/8,b.top+(rw+.5)*b.height/8]}""".replace("G_flip()", "document.querySelector('.cbar.me .cn').textContent.includes('⚫')"), name)
    def move(pg, a, c):
        x, y = sq(pg, a); pg.mouse.click(x, y); pg.wait_for_timeout(150)
        x2, y2 = sq(pg, c); pg.mouse.click(x2, y2); pg.wait_for_timeout(500)
    A.mouse.click(*sq(A, "e2")); A.wait_for_timeout(200)
    check("legal targets shown (2)", A.locator(".chsq.chtg").count() == 2)
    A.mouse.click(*sq(A, "e3")); A.wait_for_timeout(300)   # tap-to-move e2-e3
    check("alice moved (pawn at e3, turn passes)", A.locator(".cbar.opp.chturn").count() == 1)
    B.wait_for_timeout(700)
    check("bobby sees the move live + his turn", B.locator(".cbar.me.chturn").count() == 1 and B.locator(".cmoves .chmv").count() == 1)
    move(B, "e7", "e5"); A.wait_for_timeout(600)
    check("alice sees reply", A.locator(".cmoves .chmv").count() == 2 and A.locator(".cbar.me.chturn").count() == 1)
    # illegal tap: select a pinned/empty square does nothing; tap a piece with no moves
    A.mouse.click(*sq(A, "a1")); A.wait_for_timeout(150)
    check("piece without moves gives no hints", A.locator(".chsq.chtg,.chsq.chtc").count() == 0)
    # drag a piece: d2 -> d4
    x, y = sq(A, "d2"); x2, y2 = sq(A, "d4")
    A.mouse.move(x, y); A.mouse.down(); A.mouse.move((x + x2) / 2, (y + y2) / 2, steps=4); A.mouse.move(x2, y2, steps=4); A.mouse.up(); A.wait_for_timeout(600)
    check("drag and drop move accepted", A.locator(".cmoves .chmv").count() == 3)
    # capture: black e5xd4
    B.wait_for_timeout(500); move(B, "e5", "d4"); A.wait_for_timeout(500)
    check("capture removes a piece (31 left)", A.locator(".cp:not(.cap)").count() == 31)
    # play to scholar's-style mate quickly is long; instead resign flow
    B.locator("#cres").click(); B.wait_for_timeout(300); B.locator(".cpbox .btn.danger").click(); B.wait_for_timeout(900)
    check("resign ends game on both screens", B.locator(".cover .cob").count() == 1 and A.locator(".cover:not([hidden]) .cob").count() == 1)
    check("alice sees a win message", "بردی" in A.locator(".cot").inner_text())
    check("rematch button present", A.locator(".cob .btn", has_text="بازی دوباره").count() == 1)
    A.locator(".cob .btn", has_text="بازی دوباره").click(); A.wait_for_timeout(900)
    check("rematch invite arrives as a new card", B.locator(".gcard").count() >= 1)
    check("no page errors", not A.errs and not B.errs)
    if A.errs or B.errs: print(A.errs[:3], B.errs[:3])
    b.close()
print("chess ui:", ok, "ok", len(bad), "failed")
os._exit(1 if bad else 0)
