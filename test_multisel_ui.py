"""Real-browser test of multi-select forward/delete in the web chat (long-press/right-click a bubble -> "انتخاب
چندتایی" -> pick more bubbles -> forward several at once, or delete several at once). Needs playwright+chromium.
Run: python test_multisel_ui.py"""
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
    print("multisel ui: skipped (playwright not installed)"); os._exit(0)
S = srv.WindroidaServer("127.0.0.1", 0, db_path=tmp/"t.db", web_port=0); port = S.start()
S._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
PW = "Str0ng-pass1"
def reg(n):
    c = Client(); c.connect("127.0.0.1", port)
    r = c.call("register", username=n, password=PW, display_name=n, sec_question="سوال تستی؟", sec_answer="x1"); assert r["ok"], r
    c.me = r["me"]; return (r["token"] if "token" in r else r.get("session")), c
ta, ca = reg("alice"); tb, cb = reg("bobby"); tcarol, ccarol = reg("carol")

bad = []; ok = 0
def check(n, c, extra=""):
    global ok
    if c: ok += 1
    else: bad.append(n); print("FAIL", n, extra)

url = f"http://127.0.0.1:{S.web_port}/"
with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
    ctx = b.new_context(viewport={"width": 420, "height": 860})
    A = ctx.new_page()
    errs = []
    A.on("pageerror", lambda e: errs.append(str(e)))
    A.add_init_script(f"try{{localStorage.setItem('wd-token','{ta}')}}catch(e){{}}")
    A.goto(url); A.wait_for_timeout(1500)
    A.evaluate("call('open_private',{username:'bobby'}).then(r=>{S.chats[r.chat.id]=r.chat;return openChat(r.chat.id)})"); A.wait_for_timeout(900)
    cid = A.evaluate("S.current")
    A.evaluate("call('open_private',{username:'carol'}).then(r=>{S.chats[r.chat.id]=r.chat})"); A.wait_for_timeout(300)  # so carol shows up as a forward target
    for t in ["پیام یک", "پیام دو", "پیام سه"]:
        A.evaluate(f"call('send',{{chat_id:{cid},text:{t!r}}}).then(r=>ingest(r.message))"); A.wait_for_timeout(300)
    A.wait_for_timeout(500)
    bubbles = A.locator("#msgs .bubble")
    check("3 messages sent", bubbles.count() == 3, bubbles.count())

    print("== enter select mode from the context menu, select a 2nd message")
    bubbles.nth(0).click(button="right"); A.wait_for_timeout(300)
    A.locator("#ctx").get_by_text("انتخاب چندتایی").click(); A.wait_for_timeout(300)
    check("select bar shows, header hidden", A.locator("#selbar").is_visible() and not A.locator("#hdr").is_visible())
    check("#msgs got selmode class", "selmode" in (A.locator("#msgs").get_attribute("class") or ""))
    check("count shows 1 message", "۱" in A.locator("#selcnt").inner_text())
    bubbles.nth(1).click(); A.wait_for_timeout(200)
    check("count shows 2 messages after tapping another bubble", "۲" in A.locator("#selcnt").inner_text())
    check("tapping a bubble in select mode did NOT open a reply/menu", A.locator("#ctx").is_hidden())

    print("== forward both selected messages to carol")
    A.locator("#selfwd").click(); A.wait_for_timeout(400)
    A.locator(".dlg .srow").filter(has_text="carol").first.click(); A.wait_for_timeout(300)
    A.locator(".dlg button.btn").last.click(); A.wait_for_timeout(700)
    carol_cid = [c["id"] for c in ccarol.call("chats")["chats"] if (c.get("peer") or {}).get("username") == "alice"]
    fwd_count = 0
    if carol_cid:
        fwd_count = len([m for m in ccarol.call("history", chat_id=carol_cid[0], limit=20)["messages"] if m.get("fwd")])
    check("carol received exactly the 2 forwarded messages", fwd_count == 2, fwd_count)
    check("selection closed itself after forwarding", not A.locator("#selbar").is_visible())

    print("== select 2 messages again and delete them")
    bubbles = A.locator("#msgs .bubble")
    bubbles.nth(0).click(button="right"); A.wait_for_timeout(300)
    A.locator("#ctx").get_by_text("انتخاب چندتایی").click(); A.wait_for_timeout(300)
    bubbles.nth(1).click(); A.wait_for_timeout(200)
    A.once("dialog", lambda d: d.accept())
    A.locator("#seldel").click(); A.wait_for_timeout(700)
    remaining = [m for m in ca.call("history", chat_id=cid, limit=20)["messages"] if not m.get("deleted")]
    check("exactly 1 of the 3 messages is left (2 were bulk-deleted)", len(remaining) == 1, len(remaining))
    check("selection closed after deleting", not A.locator("#selbar").is_visible())

    print("== console/page errors")
    check("no uncaught JS errors", not errs, errs)
    b.close()

print(f"multisel ui: {ok} ok, {len(bad)} failed")
os._exit(1 if bad else 0)
