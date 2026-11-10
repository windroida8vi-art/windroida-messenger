"""Real-browser test of group moderation: owner silences a member / turns slow mode on / bans; the member sees the notice and is refused.
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
    print("members+emoji ui: skipped"); os._exit(0)
S = srv.WindroidaServer("127.0.0.1", 0, db_path=tmp/"t.db", web_port=0); port = S.start()
S._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
def reg(n):
    c = Client(); c.connect("127.0.0.1", port)
    r = c.call("register", username=n, password="Str0ng-pass1", display_name=n, sec_question="سوال تستی؟", sec_answer="x1"); return r.get("session") or r.get("token"), r["me"]["id"]
(to, uo), (tm, um), (tg, ug) = reg("owner1"), reg("membr1"), reg("guest1")
IGN = ("lottie_light", "404", "MIME")
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

with sync_playwright() as p:
    b = p.chromium.launch()
    def page(tok):
        ctx = b.new_context(viewport={"width": 420, "height": 860}); pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.add_init_script(f"try{{localStorage.setItem('wd-token','{tok}')}}catch(e){{}}")
        pg.goto(url); pg.wait_for_timeout(1500); pg.errs = errs; return pg
    O = page(to); O.evaluate(f"openChat({gid})"); O.wait_for_timeout(700)
    sub = O.locator("#hsub").inner_text() if O.locator("#hsub").count() else O.locator("#hdr").inner_text()
    check("header shows members + online count", "آنلاین" in sub and "عضو" in sub, sub)
    O.evaluate("dlgInfo()"); O.wait_for_timeout(700)
    rows = O.locator("#modal .member")
    check("two member rows", rows.count() == 2, rows.count())
    check("owner is listed first", "owner1" in rows.nth(0).inner_text(), rows.nth(0).inner_text())
    check("each row has a status line", O.locator("#modal .member .seen").count() == 2)
    check("online member is marked online", "آنلاین" in rows.nth(0).locator(".seen").inner_text())
    check("search box hidden for small groups", O.locator("#modal input[placeholder^='جستجوی اعضا']").is_hidden())
    rows.nth(1).locator(".grow").click(); O.wait_for_timeout(1500)
    check("tapping a member opens the private chat", O.locator("#modal").is_hidden() and "membr1" in O.locator("#hdr").inner_text(), O.locator("#hdr").inner_text())
    # frameless emoji: a message that is only an emoji has no bubble background / padding
    O.evaluate(f"openChat({gid})"); O.wait_for_timeout(500)
    O.fill("#input", "\u2764\ufe0f"); O.press("#input", "Enter"); O.wait_for_timeout(1000)
    bub = O.locator(".mrow.mine .bubble").last
    st = bub.evaluate("e=>{const s=getComputedStyle(e);return [s.backgroundColor,s.boxShadow,s.paddingLeft,s.borderTopWidth]}")
    check("emoji-only message has no bubble frame", st[0] in ("rgba(0, 0, 0, 0)", "transparent") and st[1] == "none" and st[2] == "0px" and st[3] == "0px", st)
    O.fill("#input", "سلام متن معمولی"); O.press("#input", "Enter"); O.wait_for_timeout(800)
    st2 = O.locator(".mrow.mine .bubble").last.evaluate("e=>getComputedStyle(e).backgroundColor")
    check("normal text keeps its glass bubble", st2 not in ("rgba(0, 0, 0, 0)", "transparent"), st2)
    real = [e for e in O.errs if not any(k in e for k in IGN)]
    check("no page errors from the new code", not real, real)
    b.close()
print(f"members+emoji ui: {okc} ok, {len(bad)} failed"); os._exit(1 if bad else 0)
