"""Real-browser test of polls: owner silences a member / turns slow mode on / bans; the member sees the notice and is refused.
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
    print("polls ui: skipped"); os._exit(0)
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
    O, M = page(to), page(tm)
    for pg in (O, M): pg.evaluate(f"openChat({gid})"); pg.wait_for_timeout(500)
    O.click("#attach"); O.wait_for_timeout(300)
    check("attach opens a menu with file + poll", O.locator("#ctx button", has_text="نظرسنجی").count() == 1)
    O.locator("#ctx button", has_text="نظرسنجی").click(); O.wait_for_timeout(400)
    check("poll dialog has question + 2 option inputs", O.locator("#modal input").count() >= 4)
    ins = O.locator("#modal input"); ins.nth(0).fill("رنگ؟"); ins.nth(1).fill("قرمز"); ins.nth(2).fill("آبی")
    O.locator("#modal .btn", has_text="ارسال").click(); O.wait_for_timeout(1000)
    check("owner sees the poll card", O.locator(".poll", has_text="رنگ؟").count() == 1 and O.locator(".popt").count() == 2)
    check("member sees it live", M.locator(".poll", has_text="رنگ؟").count() == 1)
    M.locator(".popt", has_text="آبی").click(); M.wait_for_timeout(900)
    check("member's own vote is marked", M.locator(".popt.on", has_text="آبی").count() == 1 and "۱۰۰٪" in M.locator(".popt.on").inner_text())
    check("owner sees the count live without reloading", "۱۰۰٪" in O.locator(".popt", has_text="آبی").inner_text() and "۱ نفر" in O.locator(".poll").inner_text())
    M.locator(".popt", has_text="قرمز").click(); M.wait_for_timeout(900)
    check("changing the vote moves it", M.locator(".popt.on", has_text="قرمز").count() == 1 and "۰٪" in O.locator(".popt", has_text="آبی").inner_text())
    M.locator(".popt", has_text="قرمز").click(); M.wait_for_timeout(900)
    check("tapping again withdraws", M.locator(".popt.on").count() == 0 and "۰ نفر" in O.locator(".poll").inner_text())
    M.locator(".popt", has_text="آبی").click(); M.wait_for_timeout(700)
    M.reload(); M.wait_for_timeout(1800); M.evaluate(f"openChat({gid})"); M.wait_for_timeout(1200)
    check("after reload my vote is still shown", M.locator(".popt.on", has_text="آبی").count() == 1)
    check("member has no close button, owner has", M.locator(".plink", has_text="بستن").count() == 0 and O.locator(".plink", has_text="بستن").count() == 1)
    check("voters list available for a public poll", O.locator(".plink", has_text="کی رأی داده").count() == 1)
    O.on("dialog", lambda d: d.accept()); O.locator(".plink", has_text="بستن").click(); O.wait_for_timeout(1000)
    check("closed for everybody", M.locator(".poll.closed").count() == 1 and M.locator(".popt[disabled]").count() == 2)
    check("no JS errors", not O.errs and not M.errs, (O.errs, M.errs))
    b.close()
print(f"polls ui: {okc} ok, {len(bad)} failed"); sys.exit(1 if bad else 0)
