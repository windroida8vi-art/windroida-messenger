"""Real-browser test of the chess screen: two players in two browser contexts play a short game (needs playwright+chromium).
Run: python test_stickers_ui.py"""
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
    A.evaluate("call('open_private',{username:'bobby'}).then(r=>{S.chats[r.chat.id]=r.chat;return openChat(r.chat.id)})"); A.wait_for_timeout(900)
    cid = A.evaluate("S.current")
    check("sticker button exists", A.locator("#stkbtn").count() == 1)
    A.click("#stkbtn"); A.wait_for_timeout(400)
    check("picker shows 26 stickers", A.locator("#stkpanel .stk-pick").count() == 26)
    A.locator("#stkpanel .stk-pick").nth(1).click(); A.wait_for_timeout(900)
    check("picker closed after sending", A.locator("#stkpanel").count() == 0)
    check("alice sees an animated sticker bubble", A.locator("#msgs .stk-msg svg").count() == 1)
    check("not shown as raw text", ":st_" not in A.locator("#msgs").inner_text())
    B.evaluate(f"openChat({cid})"); B.wait_for_timeout(1200)
    check("bobby sees the sticker", B.locator("#msgs .stk-msg svg").count() == 1)
    check("chat list preview is friendly", "استیکر" in B.evaluate("preview(S.chats[%d])" % cid))
    # a fake id stays plain text, and the server stores plain text only
    A.evaluate(f"call('send',{{chat_id:{cid},text:':st_nope:'}}).then(r=>ingest(r.message))"); A.wait_for_timeout(700)
    check("unknown sticker id stays text", A.locator("#msgs .stk-msg").count() == 1 and ":st_nope:" in A.locator("#msgs").inner_text())
    A.evaluate(f"call('send',{{chat_id:{cid},text:':st_<img src=x onerror=alert(1)>:'}}).then(r=>ingest(r.message))"); A.wait_for_timeout(500)
    check("markup in the id is inert", A.locator("#msgs img[src='x']").count() == 0)
    A.evaluate(f"call('send',{{chat_id:{cid},text:'😂'}}).then(r=>ingest(r.message))"); A.wait_for_timeout(700)
    check("single 😂 renders as animated sticker", A.locator("#msgs .stk-emo svg").count() == 1)
    A.evaluate(f"call('send',{{chat_id:{cid},text:'🦖'}}).then(r=>ingest(r.message))"); A.wait_for_timeout(700)
    check("rare emoji stays static big emoji", A.locator("#msgs .bigemo").count() == 1)
    check("no page errors", not A.errs and not B.errs)
    if A.errs or B.errs: print(A.errs[:3], B.errs[:3])
    b.close()
print("stickers ui:", ok, "ok", len(bad), "failed")
os._exit(1 if bad else 0)
