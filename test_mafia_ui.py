"""Real-browser test of the mafia panel in a room: 5 players + 1 spectator in separate browser contexts play a whole game.
Run: python test_mafia_ui.py"""
import os, sys, tempfile, time, re
os.environ["WINDROIDA_MAFIA_NIGHT"] = "20"; os.environ["WINDROIDA_MAFIA_DAY"] = "20"; os.environ["WINDROIDA_MAFIA_VOTE"] = "20"
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
tmp = Path(tempfile.mkdtemp()); common.DATA_DIR = tmp; common.UPLOADS_DIR = tmp/"u"; common.AVATARS_DIR = tmp/"a"; common.WALLPAPERS_DIR = tmp/"w"; common.ROOMAUDIO_DIR = tmp/"r"; common.FILES_DIR = tmp/"f"; (tmp/"f").mkdir()
import server as srv
from client_core import Client
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("mafia ui: skipped (playwright not installed)"); os._exit(0)
S = srv.WindroidaServer("127.0.0.1", 0, db_path=tmp/"t.db", web_port=0); port = S.start()
S._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
PW = "Str0ng-pass1"
def reg(n):
    c = Client(); c.connect("127.0.0.1", port)
    r = c.call("register", username=n, password=PW, display_name=n, sec_question="سوال تستی؟", sec_answer="x1"); assert r["ok"], r
    return r.get("session") or r.get("token")
names = ["amir", "bahar", "cyrus", "dara", "elham", "spectator"]
toks = [reg(n) for n in names]
bad = []; okc = 0
def check(n, c, x=""):
    global okc
    if c: okc += 1
    else: bad.append(n); print("FAIL", n, x)
url = f"http://127.0.0.1:{S.web_port}/"
with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
    def page(tok):
        ctx = b.new_context(viewport={"width": 420, "height": 860}); pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.add_init_script(f"try{{localStorage.setItem('wd-token','{tok}')}}catch(e){{}}")
        pg.goto(url); pg.wait_for_timeout(1500); pg.errs = errs; return pg
    pgs = [page(t) for t in toks]; A = pgs[0]; SP = pgs[5]
    A.evaluate("rOpen('room_open',{title:'مافیا'})"); A.wait_for_timeout(900)
    rid = A.evaluate("R.id"); check("room opened", bool(rid))
    for pg in pgs[1:]: pg.evaluate(f"rOpen('room_join',{{room:'{rid}'}})")
    A.wait_for_timeout(1200)
    for pg in pgs: pg.evaluate("R.tab='games';rDrawTabs();rDrawPane()")
    A.wait_for_timeout(600)
    check("games tab has the mafia card", A.locator(".mfcard").count() == 1 and "ساخت بازی مافیا" in A.locator(".mfcard").inner_text())
    A.locator(".mfcard .btn", has_text="ساخت بازی مافیا").click(); A.wait_for_timeout(700)
    check("alice sees the lobby with herself", "منتظر بازیکن" in A.locator(".mfcard").inner_text() and A.locator(".mfp").count() == 1)
    check("spectator sees the lobby live", SP.locator(".mfp").count() == 1)
    check("start button disabled with 1 player", A.locator(".mfcard .btn", has_text="شروع بازی").is_disabled())
    for pg in pgs[1:5]:
        pg.locator(".mfcard .btn", has_text="پیوستن به بازی").click(); pg.wait_for_timeout(250)
    A.wait_for_timeout(700)
    check("lobby lists 5 players", A.locator(".mfp").count() == 5)
    check("only the host sees an enabled start button", A.locator(".mfcard .btn", has_text="شروع بازی").is_enabled() and pgs[1].locator(".mfcard .btn", has_text="شروع بازی").count() == 0)
    A.locator(".mfcard .btn", has_text="شروع بازی").click(); A.wait_for_timeout(1200)
    roles = {}
    for n, pg in zip(names[:5], pgs[:5]):
        txt = pg.locator(".mfrole").inner_text(); m = re.search(r"نقش تو: (\S+)", txt); roles[n] = m.group(1) if m else None
    check("every player sees his own role", all(roles.values()), roles)
    check("roles are 1 mafia / 1 doctor / 1 detective / 2 citizens", sorted(roles.values()) == sorted(["مافیا", "دکتر", "کارآگاه", "شهروند", "شهروند"]), roles)
    for n, pg in zip(names[:5], pgs[:5]):
        small = [t for t in pg.locator(".mfp small").all_inner_texts() if t.strip()]
        check(f"{n}: sees only his own role (and teammates) in the player list", len(small) <= 1, small)
    check("spectator sees no roles", all(not t.strip() for t in SP.locator(".mfp small").all_inner_texts()) and "تماشاچی" in SP.locator(".mfcard").inner_text())
    check("the games tab shows the live dot", "🔴" in A.locator(".rtabs").inner_text())
    check("a clock is shown", "ثانیه" in A.locator(".mfclock").inner_text())
    check("no horizontal overflow on a phone", A.evaluate("document.documentElement.scrollWidth<=window.innerWidth+1"))
    who = {r: n for n, r in roles.items() if r != "شهروند"}; cit = [n for n, r in roles.items() if r == "شهروند"]
    pmap = dict(zip(names[:5], pgs[:5]))
    check("a citizen has no target buttons at night", pmap[cit[0]].locator(".mfp.act").count() == 0 and "همه خوابن" in pmap[cit[0]].locator(".mfcard").inner_text())
    check("the mafia sees his team chat box", pmap[who["مافیا"]].locator("#mfin").count() == 1 and all(pmap[c].locator("#mfin").count() == 0 for c in cit))
    mp = pmap[who["مافیا"]]
    mp.fill("#mfin", "سلام تیم"); mp.press("#mfin", "Enter"); mp.wait_for_timeout(600)
    check("whisper shows in the mafia's panel", "سلام تیم" in mp.locator(".mfwh").inner_text())
    check("whisper invisible to others", all("سلام تیم" not in pg.locator("body").inner_text() for pg in pgs if pg is not mp))
    # night actions through the UI: mafia shoots citizen 0, doctor saves nobody-relevant (self), detective checks the mafia
    victim = cit[0]
    mp.locator(".mfp.act", has_text=victim).click(); mp.wait_for_timeout(300)
    check("mafia's chosen target is highlighted", mp.locator(".mfp.pick", has_text=victim).count() == 1)
    pmap[who["دکتر"]].locator(".mfp.act", has_text=who["دکتر"]).click()
    pmap[who["کارآگاه"]].locator(".mfp.act", has_text=who["مافیا"]).click()
    A.wait_for_timeout(1500)
    check("day started", all("روز" in pg.locator(".mfph").inner_text() for pg in pgs))
    check("the victim is shown dead with his role to everybody", all(pg.locator(".mfp.dead", has_text=victim).count() == 1 and "شهروند" in pg.locator(".mfp.dead", has_text=victim).inner_text() for pg in pgs))
    check("the detective sees the private answer", "مافیاست" in pmap[who["کارآگاه"]].locator(".mfpriv").inner_text() and all(pmap[n].locator(".mfpriv").count() == 0 for n in names[:5] if n != who["کارآگاه"]))
    check("dead player has no ready button", pmap[victim].locator(".mfcard .btn", has_text="آماده").count() == 0 and "بیرون رفتی" in pmap[victim].locator(".mfrole").inner_text())
    alive = [n for n in names[:5] if n != victim]
    for n in alive: pmap[n].locator(".mfcard .btn", has_text="آماده‌ی رأی‌گیری").click(); pmap[n].wait_for_timeout(150)
    A.wait_for_timeout(1200)
    check("vote phase", all("رأی‌گیری" in pmap[n].locator(".mfph").inner_text() for n in alive))
    check("no self-vote button", all(pmap[n].locator(".mfp.act", has_text=re.compile(rf"^{n} \(تو\)")).count() == 0 for n in alive))
    for n in alive:
        target = who["مافیا"] if n != who["مافیا"] else who["دکتر"]
        pmap[n].locator(".mfp.act", has_text=target).first.click(); pmap[n].wait_for_timeout(150)
    A.wait_for_timeout(1500)
    check("game over: citizens win banner for everybody incl. spectator", all("شهروندها بردن" in pg.locator(".mfcard").inner_text() for pg in pgs))
    check("all roles are shown at the end", all(len([t for t in pg.locator(".mfp small").all_inner_texts() if "شهروند" in t or "مافیا" in t or "دکتر" in t or "کارآگاه" in t]) == 5 for pg in pgs[:5]))
    A.locator(".mfcard .btn", has_text="بستن و بازی جدید").click(); A.wait_for_timeout(800)
    check("game closed for everybody", all("ساخت بازی مافیا" in pg.locator(".mfcard").inner_text() for pg in pgs))
    errs = [e for pg in pgs for e in pg.errs if "favicon" not in e]
    check("no page errors", not errs)
    if errs: print(errs[:5])
    b.close()
print(f"{okc} ok, {len(bad)} failed"); os._exit(1 if bad else 0)
