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
    O, M = page(to), page(tm)
    for pg in (O, M): pg.evaluate(f"openChat({gid})"); pg.wait_for_timeout(500)
    check("no notice for a normal member at first", M.locator("#gnote").is_hidden())
    O.evaluate("dlgInfo()"); O.wait_for_timeout(600)
    check("owner sees the slow-mode select and the bans button", O.locator("#modal select").count() == 1 and O.locator("#modal .btn", has_text="مسدودشده‌ها").count() == 1)
    check("owner sees silence + ban buttons for the member only", O.locator("#modal .member", has_text="membr1").locator(".iconbtn", has_text="🔈").count() == 1 and O.locator("#modal .member", has_text="owner1").locator(".iconbtn", has_text="🔈").count() == 0)
    O.select_option("#modal select", "30"); O.wait_for_timeout(800)
    check("member sees the slow-mode notice live", "حالت آهسته" in M.locator("#gnote").inner_text() and M.locator("#gnote").is_visible())
    M.fill("#input", "یک"); M.press("#input", "Enter"); M.wait_for_timeout(600)
    M.fill("#input", "دو"); M.press("#input", "Enter"); M.wait_for_timeout(800)
    check("second quick message is refused with a toast", "حالت آهسته" in M.locator("body").inner_text() and M.locator(".mrow.mine", has_text="یک").count() >= 1)
    O.locator("#modal .member", has_text="membr1").locator(".iconbtn", has_text="🔈").click(); O.wait_for_timeout(400)
    check("silence dialog offers durations", O.locator("#modal .btn", has_text="۱ ساعت").count() == 1 and O.locator("#modal .btn", has_text="برای همیشه").count() == 1)
    O.locator("#modal .btn", has_text="۱ ساعت").click(); O.wait_for_timeout(1000)
    check("member sees he is silenced", "ساکت کرده" in M.locator("#gnote").inner_text())
    O.evaluate("dlgInfo()"); O.wait_for_timeout(600)
    check("member row shows silenced + 🔇 button", O.locator("#modal .member", has_text="ساکت").count() >= 1 and O.locator("#modal .member", has_text="membr1").locator(".iconbtn", has_text="🔇").count() == 1)
    M.fill("#input", "سلام"); M.press("#input", "Enter"); M.wait_for_timeout(700)
    check("a silenced member's message is refused", "ساکت" in M.locator("body").inner_text() and M.locator(".mrow.mine", has_text="سلام").count() == 0)
    O.locator("#modal .member", has_text="membr1").locator(".iconbtn", has_text="🔇").click(); O.wait_for_timeout(400)
    O.locator("#modal .btn", has_text="برداشتن ساکت‌بودن").click(); O.wait_for_timeout(900)
    check("lifting the silence clears the member's notice (slow mode remains)", "ساکت کرده" not in M.locator("#gnote").inner_text() and "حالت آهسته" in M.locator("#gnote").inner_text())
    # ban
    O.evaluate("dlgInfo()"); O.wait_for_timeout(600)
    O.on("dialog", lambda d: d.accept())
    O.locator("#modal .member", has_text="membr1").locator(".iconbtn", has_text="⛔").click(); O.wait_for_timeout(1000)
    check("banned member lost the group", M.evaluate(f"!S.chats[{gid}]"))
    O.evaluate("dlgInfo()"); O.wait_for_timeout(500)
    O.locator("#modal .btn", has_text="مسدودشده‌ها").click(); O.wait_for_timeout(700)
    check("ban list shows him with an unban button", O.locator("#modal .member", has_text="membr1").locator(".btn", has_text="رفع مسدودی").count() == 1)
    O.locator("#modal .btn", has_text="رفع مسدودی").click(); O.wait_for_timeout(600)
    check("unban empties the list", "کسی مسدود نیست" in O.locator("#modal").inner_text())
    check("no page errors", not [e for pg in (O, M) for e in pg.errs if "favicon" not in e], [e for pg in (O, M) for e in pg.errs][:3])
    b.close()
print(f"{okc} ok, {len(bad)} failed"); os._exit(1 if bad else 0)
