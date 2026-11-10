"""Real-browser test of the chess screen: two players in two browser contexts play a short game (needs playwright+chromium).
Run: python test_marks_ui.py"""
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
    print("marks ui: skipped (playwright not installed)"); os._exit(0)
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
    A = page(ta)
    A.evaluate("call('open_private',{username:'bobby'}).then(r=>{S.chats[r.chat.id]=r.chat;return openChat(r.chat.id)})"); A.wait_for_timeout(900)
    cid = A.evaluate("S.current")
    A.evaluate(f"call('send',{{chat_id:{cid},text:'آدرس خونه: خیابان آزادی'}}).then(r=>ingest(r.message))"); A.wait_for_timeout(700)
    A.locator("#msgs .bubble").last.click(button="right"); A.wait_for_timeout(300)
    check("menu has mark item", A.locator("#ctx").get_by_text("نشان کردن").count() == 1)
    A.locator("#ctx").get_by_text("نشان کردن").click(); A.wait_for_timeout(500)
    A.fill("#modal input[list]", "آدرس"); A.locator("#modal .btn", has_text="ذخیره").click(); A.wait_for_timeout(600)
    check("mark saved on server", A.evaluate("call('marks').then(r=>r.marks.length+':'+r.marks[0].tag)") == "1:آدرس")
    A.evaluate("buildDrawer();dlgMarks()"); A.wait_for_timeout(700)
    check("marks dialog lists it with tag chip", A.locator("#modal .srow").count() == 1 and A.locator("#modal .chip", has_text="آدرس").count() == 1)
    A.locator("#modal .srow").first.click(); A.wait_for_timeout(700)
    check("click opens the chat", A.evaluate("S.current") == cid and A.locator("#modal .dlg").count() == 0)
    A.evaluate("dlgAdvSearch()"); A.wait_for_timeout(300)
    A.fill("#modal input[placeholder^='متن']", "آزادی"); A.fill("#modal input[placeholder^='فرستنده']", "alice"); A.locator("#modal .btn", has_text="جستجو").click(); A.wait_for_timeout(900)
    check("advanced search finds it", A.locator("#modal .srow").count() == 1)
    A.fill("#modal input[placeholder^='فرستنده']", "nobody"); A.locator("#modal .btn", has_text="جستجو").click(); A.wait_for_timeout(700)
    check("wrong sender -> nothing", A.locator("#modal .srow").count() == 0)
    A.evaluate("closeDialog();dlgMarks()"); A.wait_for_timeout(500)
    A.locator("#modal .srow .iconbtn").first.click(); A.wait_for_timeout(600)
    check("remove from marks", A.locator("#modal .srow").count() == 0 and A.evaluate("call('marks').then(r=>r.marks.length)") == 0)
    # regression: the block button in the contact sheet must keep readable text (not red on red)
    col=A.evaluate("""(()=>{const b=document.createElement('button');b.className='btn danger';document.body.append(b);const s=getComputedStyle(b);const r=[s.color,s.backgroundColor];b.remove();return r})()""")
    def a(c):
        m=c.replace('rgba(','').replace('rgb(','').replace(')','').split(','); return float(m[3]) if len(m)>3 else 1.0
    check("danger button background stays translucent (text readable)", a(col[1]) < 0.5)
    r = A.evaluate("""(()=>{const u=Object.values(S.chats).find(c=>c.peer);const row=blockRow(u.peer);document.body.append(row);const b=row.querySelector('button')||row;const s=getComputedStyle(b);const o=[b.className,s.color,s.backgroundColor];row.remove();return o})()""")
    print("block button:", r)
    check("real block button is translucent, not solid red", r[2].startswith("rgba") and float(r[2].split(",")[3].strip(" )")) < 0.5)
    check("no page errors", not A.errs)
    if A.errs: print(A.errs[:3])
    b.close()
print("marks ui:", ok, "ok", len(bad), "failed")
os._exit(1 if bad else 0)
