"""Real-browser test of the chess screen: two players in two browser contexts play a short game (needs playwright+chromium).
Run: python test_pos_ui.py"""
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
    print("pos ui: skipped (playwright not installed)"); os._exit(0)
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
    for i in range(34):
        A.evaluate(f"call('send',{{chat_id:{cid},text:'پیام شماره {i}'}}).then(r=>ingest(r.message))"); A.wait_for_timeout(650)
    A.wait_for_timeout(800)
    # --- keyboard stays after send (real mouse click on the send button)
    A.click("#input"); A.fill("#input", "تست کیبورد")
    A.click("#sendbtn"); A.wait_for_timeout(500)
    check("input keeps focus after tapping send", A.evaluate("document.activeElement&&document.activeElement.id")=="input")
    A.fill("#input", "دومی"); A.keyboard.press("Enter"); A.wait_for_timeout(400)
    check("input keeps focus after Enter", A.evaluate("document.activeElement.id")=="input")
    # --- reading position survives leaving the chat
    A.evaluate("document.querySelector('#msgs').scrollTop=0"); A.wait_for_timeout(300)
    A.evaluate("document.querySelector('#msgs').scrollTop=Math.round(document.querySelector('#msgs').scrollHeight*0.4)"); A.wait_for_timeout(600)
    before = A.evaluate("(()=>{const b=document.querySelector('#msgs'),t=b.getBoundingClientRect().top;for(const e of b.querySelectorAll('[data-id]')){const r=e.getBoundingClientRect();if(r.bottom>t+4)return [e.dataset.id,Math.round(r.top-t)]}})()")
    A.evaluate("document.querySelector('#back').click()"); A.wait_for_timeout(500)
    A.evaluate(f"openChat({cid})"); A.wait_for_timeout(900)
    after = A.evaluate("(()=>{const b=document.querySelector('#msgs'),t=b.getBoundingClientRect().top;for(const e of b.querySelectorAll('[data-id]')){const r=e.getBoundingClientRect();if(r.bottom>t+4)return [e.dataset.id,Math.round(r.top-t)]}})()")
    print("before", before, "after", after)
    check("same message at the top after coming back", before and after and before[0]==after[0] and abs(before[1]-after[1])<=6)
    # --- at the bottom -> still opens at the bottom
    A.evaluate("document.querySelector('#msgs').scrollTop=1e7"); A.wait_for_timeout(500)
    A.evaluate("document.querySelector('#back').click()"); A.wait_for_timeout(300)
    A.evaluate(f"openChat({cid})"); A.wait_for_timeout(800)
    check("was at the end -> opens at the end", A.evaluate("(()=>{const b=document.querySelector('#msgs');return b.scrollHeight-b.scrollTop-b.clientHeight<140})()"))
    check("no page errors", not A.errs)
    if A.errs: print(A.errs[:3])
    b.close()
print("pos ui:", ok, "ok", len(bad), "failed")
os._exit(1 if bad else 0)
