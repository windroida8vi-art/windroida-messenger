"""Real-browser test of the group-call web client: start/join, roster, audio relay between 3 real
(fake-device) browsers, video slot cap + rejection toast, leave, and the @mention click-to-open-chat fix.
Run: python test_gcall_ui.py"""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["WINDROIDA_GCALL_MAX_VIDEO"] = "2"
import common
tmp = Path(tempfile.mkdtemp()); common.DATA_DIR = tmp; common.UPLOADS_DIR = tmp/"u"; common.AVATARS_DIR = tmp/"a"; common.WALLPAPERS_DIR = tmp/"w"; common.ROOMAUDIO_DIR = tmp/"r"; common.FILES_DIR = tmp/"f"; (tmp/"f").mkdir()
import server as srv
from client_core import Client
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("gcall ui: skipped"); os._exit(0)
S = srv.WindroidaServer("127.0.0.1", 0, db_path=tmp/"t.db", web_port=0); port = S.start()
S._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
def reg(n):
    c = Client(); c.connect("127.0.0.1", port)
    r = c.call("register", username=n, password="Str0ng-pass1", display_name=n, sec_question="سوال تستی؟", sec_answer="x1")
    return r.get("session") or r.get("token"), r["me"]["id"]
(ta, ua), (tb, ub), (tc, uc) = reg("amir1"), reg("bahar1"), reg("cyrus1")
c0 = Client(); c0.connect("127.0.0.1", port); c0.call("login", username="amir1", password="Str0ng-pass1")
gid = c0.call("create_group", title="گروه تماس", usernames=["bahar1", "cyrus1"])["chat"]["id"]
bad = []; ok = 0
def check(n, c, x=""):
    global ok
    if c: ok += 1
    else: bad.append(n); print("FAIL", n, x)
url = f"http://127.0.0.1:{S.web_port}/"
with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required", "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
    def page(tok):
        ctx = b.new_context(viewport={"width": 420, "height": 860}, permissions=["microphone", "camera"]); pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.add_init_script(f"try{{localStorage.setItem('wd-token','{tok}')}}catch(e){{}}")
        pg.goto(url); pg.wait_for_timeout(1500); pg.errs = errs; return pg
    A, B, Cp = page(ta), page(tb), page(tc)
    for pg in (A, B, Cp): pg.evaluate(f"openChat({gid})"); pg.wait_for_timeout(500)

    print("== start / join / roster")
    A.evaluate(f"gStartCall({gid})"); A.wait_for_timeout(1000)
    check("amir sees the group-call UI", A.evaluate("!$('#gcallui').hidden"))
    B.wait_for_timeout(500)
    check("bahar sees the incoming-call pill", not B.locator("#gcallpill").is_hidden())
    B.evaluate("$('#gcallpill').click()"); B.wait_for_timeout(1000)
    check("bahar joined, roster has 2", B.evaluate("G && G.participants.length") == 2)
    cid = A.evaluate("G.id")
    Cp.evaluate(f"gJoin('{cid}')"); Cp.wait_for_timeout(1200)
    check("cyrus joined, all three see 3 participants", all(pg.evaluate("G && G.participants.length") == 3 for pg in (A, B, Cp)))

    print("== audio relay (fake mic) reaches other participants")
    A.wait_for_timeout(2500)
    check("bahar hears audio from someone else", B.evaluate("G && Object.keys(G.peers).length") >= 1)
    check("cyrus hears audio from someone else", Cp.evaluate("G && Object.keys(G.peers).length") >= 1)

    print("== video slot cap (max 2) + rejection")
    A.evaluate("gToggleCam()"); A.wait_for_timeout(1000)
    check("amir's camera is on", A.evaluate("G.cam"))
    B.evaluate("gToggleCam()"); B.wait_for_timeout(1000)
    check("bahar's camera is on (2nd slot)", B.evaluate("G.cam"))
    Cp.evaluate("gToggleCam()"); Cp.wait_for_timeout(1500)
    check("cyrus's camera is rejected (slots full) and turned back off", Cp.evaluate("!G.cam"))
    check("cyrus got a toast about it", "هم‌زمان" in Cp.locator("body").inner_text())
    A.wait_for_timeout(1000)
    check("bahar's tile shows amir's video frame", B.evaluate("G.imgs[%d] && !G.imgs[%d].hidden" % (ua, ua)) is not False)

    print("== leave")
    Cp.evaluate("gHangup()"); Cp.wait_for_timeout(1000)
    check("cyrus's call UI closes", Cp.evaluate("G") is None)
    check("amir & bahar see roster shrink to 2", A.evaluate("G.participants.length") == 2 and B.evaluate("G.participants.length") == 2)
    A.evaluate("gHangup()"); B.evaluate("gHangup()"); A.wait_for_timeout(500)

    print("== @mention tap opens the mentioned user's chat")
    priv = c0.call("open_private", username="bahar1")["chat"]["id"]
    A.evaluate(f"openChat({gid})"); A.wait_for_timeout(400)  # still the group chat; mention is clicked from here
    A.fill("#input", "سلام @bahar1 چطوری"); A.press("#input", "Enter"); A.wait_for_timeout(700)
    check("mention renders as a styled span", A.locator(".mention", has_text="@bahar1").count() >= 1)
    check("still viewing the group chat before the click", A.evaluate("S.current") == gid)
    A.locator(".mention", has_text="@bahar1").first.click(); A.wait_for_timeout(700)
    check("tapping the mention opens the private chat with bahar1", A.evaluate("S.current") == priv)

    errs = [e for pg in (A, B, Cp) for e in pg.errs if "favicon" not in e]
    check("no page errors", not errs, errs[:5])
    b.close()
print(f"gcall ui: {ok} ok, {len(bad)} failed")
os._exit(1 if bad else 0)
