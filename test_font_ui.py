"""Real-browser test of font: owner silences a member / turns slow mode on / bans; the member sees the notice and is refused.
Run: python test_groupadmin_ui.py"""
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
    print("groupadmin ui: skipped"); os._exit(0)
S = srv.WindroidaServer("127.0.0.1", 0, db_path=tmp/"t.db", web_port=0); port = S.start()
S._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
def reg(n):
    c = Client(); c.connect("127.0.0.1", port)
    r = c.call("register", username=n, password="Str0ng-pass1", display_name=n, sec_question="سوال تستی؟", sec_answer="x1"); return r.get("session") or r.get("token"), r["me"]["id"]
(to, uo), (tm, um), (tg, ug) = reg("owner1"), reg("membr1"), reg("guest1")
c0 = Client(); c0.connect("127.0.0.1", port); c0.call("login", username="owner1", password="Str0ng-pass1")
gid = c0.call("create_group", title="گروه تست", usernames=["membr1"])["chat"]["id"]
bad = []; okc = 0
def check(n, c, x=""):
    global okc
    if c: okc += 1
    else: bad.append(n); print("FAIL", n, x)
url = f"http://127.0.0.1:{S.web_port}/"
with sync_playwright() as p:
    b = p.chromium.launch()
    def page(tok):
        ctx = b.new_context(viewport={"width": 420, "height": 860}); pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.add_init_script(f"try{{localStorage.setItem('wd-token','{tok}')}}catch(e){{}}")
        pg.goto(url); pg.wait_for_timeout(1500); pg.errs = errs; return pg
    P = page(to); P.wait_for_timeout(1500)
    r = P.evaluate("""async()=>{await document.fonts.ready;const ok=[...document.fonts].map(f=>f.family+' '+f.weight+' '+f.status);
      const cs=getComputedStyle(document.body).fontFamily;return {ok,cs,loaded:document.fonts.check('15px Vazirmatn'),w700:document.fonts.check('700 15px Vazirmatn')}}""")
    print(r)
    check("Vazirmatn declared + loaded (regular and bold)", r["loaded"] and r["w700"] and all("loaded" in x for x in r["ok"]) and len(r["ok"]) == 3, r)
    check("body uses Vazirmatn first", r["cs"].startswith("Vazirmatn"), r)
    check("no JS errors", not P.errs, P.errs)
    b.close()
print(f"font ui: {okc} ok, {len(bad)} failed"); sys.exit(1 if bad else 0)
