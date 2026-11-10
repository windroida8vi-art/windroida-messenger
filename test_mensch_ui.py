"""Real-browser test of the Mensch panel in a room: 3 players + a spectator in separate browsers; board, dice, moves, sync, win. Run: python test_mensch_ui.py"""
import os, sys, tempfile, time, re, random
os.environ["WINDROIDA_MENSCH_TURN"] = "60"
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
tmp = Path(tempfile.mkdtemp()); common.DATA_DIR = tmp; common.UPLOADS_DIR = tmp/"u"; common.AVATARS_DIR = tmp/"a"; common.WALLPAPERS_DIR = tmp/"w"; common.ROOMAUDIO_DIR = tmp/"r"; common.FILES_DIR = tmp/"f"; (tmp/"f").mkdir()
import server as srv
from client_core import Client
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("mensch ui: skipped (playwright not installed)"); os._exit(0)
S = srv.WindroidaServer("127.0.0.1", 0, db_path=tmp/"t.db", web_port=0); port = S.start()
S._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
PW = "Str0ng-pass1"
def reg(n):
    c = Client(); c.connect("127.0.0.1", port)
    r = c.call("register", username=n, password=PW, display_name=n, sec_question="سوال تستی؟", sec_answer="x1"); assert r["ok"], r
    return r.get("session") or r.get("token")
names = ["amir", "bahar", "cyrus", "spectator"]
toks = [reg(n) for n in names]
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
        pg.add_init_script(f"try{{localStorage.setItem('wd-token','{tok}');localStorage.setItem('wd-mn-3d','0')}}catch(e){{}}")
        pg.goto(url); pg.wait_for_timeout(1500); pg.errs = errs; return pg
    pgs = [page(t) for t in toks]; A = pgs[0]; SP = pgs[3]; players = pgs[:3]
    A.evaluate("rOpen('room_open',{title:'منچ'})"); A.wait_for_timeout(900)
    rid = A.evaluate("R.id"); check("room opened", bool(rid))
    for pg in pgs[1:]: pg.evaluate(f"rOpen('room_join',{{room:'{rid}'}})")
    A.wait_for_timeout(1200)
    for pg in pgs: pg.evaluate("R.tab='games';rDrawTabs();rDrawPane()")
    A.wait_for_timeout(600)
    check("games tab has the mensch card", A.locator(".mncard").count() == 1 and "ساخت بازی منچ" in A.locator(".mncard").inner_text())
    check("mafia card is still there", A.locator(".mfcard").count() == 1)
    A.locator(".mncard .btn", has_text="ساخت بازی منچ").click(); A.wait_for_timeout(700)
    check("host sees the lobby with himself", A.locator(".mnlp").count() == 1)
    check("spectator sees the lobby live", SP.locator(".mnlp").count() == 1)
    check("start disabled with one player", A.locator(".mncard .btn", has_text="شروع بازی").is_disabled())
    for pg in pgs[1:3]:
        pg.locator(".mncard .btn", has_text="پیوستن").click(); pg.wait_for_timeout(250)
    A.wait_for_timeout(600)
    check("lobby lists 3", A.locator(".mnlp").count() == 3 and SP.locator(".mnlp").count() == 3)
    check("only host has an enabled start button", A.locator(".mncard .btn", has_text="شروع بازی").is_enabled() and pgs[1].locator(".mncard .btn", has_text="شروع بازی").count() == 0)
    A.locator(".mncard .btn", has_text="شروع بازی").click(); A.wait_for_timeout(1200)
    check("everybody sees the board with 12 pawns", all(pg.locator(".mnsvg").count() == 1 and pg.locator(".mnp").count() == 12 for pg in pgs))
    check("3 player chips, exactly one is the current turn", all(pg.locator(".mnpl").count() == 3 and pg.locator(".mnpl.cur").count() == 1 for pg in pgs))
    check("games tab has the dice dot", "🎲" in A.locator(".rtabs").inner_text())
    check("spectator is told so and has a disabled dice", "تماشاچی" in SP.locator(".mncard").inner_text() and SP.locator(".mndiebtn").count() == 0 and SP.locator(".mncd").count() == 4)
    check("board is square and fits a phone", A.evaluate("(()=>{const r=document.querySelector('.mnboard').getBoundingClientRect();return Math.abs(r.width-r.height)<2&&r.width<=420&&document.documentElement.scrollWidth<=window.innerWidth+1})()"))
    check("all pawns start in the yards (positions differ per pawn)", len(set(A.evaluate("[...document.querySelectorAll('.mnp')].map(g=>g.style.transform)"))) == 12)
    def turn_page():
        for pg in players:
            if pg.locator(".mndiebtn.go").count(): return pg
        return None
    A.wait_for_timeout(300)
    tp = turn_page(); check("exactly one player can roll", tp is not None and sum(pg.locator(".mndiebtn.go").count() for pg in players) == 1)
    # a non-turn player cannot roll even by forcing the button
    other = [pg for pg in players if pg is not tp][0]
    other.evaluate("document.querySelector('.mndiebtn').click()"); other.wait_for_timeout(400)
    check("tapping the die out of turn explains why (toast) and does nothing", "نوبت" in other.locator("#toast").inner_text() and sum(pg.locator(".mndiebtn.go").count() for pg in players) == 1)
    check("board of the player whose turn it is glows", tp.locator(".mnboard.mine").count() == 1 and other.locator(".mnboard.mine").count() == 0)
    check("timer bar is shown", tp.locator(".mntbar").count() == 1)
    tp.locator(".mnsnd").click(); tp.wait_for_timeout(200)
    check("sound toggle exists and switches", tp.locator(".mnsnd").inner_text() == "🔇")
    tp.locator(".mnsnd").click()
    check("forced click by a non-turn player is refused by the server", sum(pg.locator(".mndiebtn.go").count() for pg in players) == 1)
    # play about 40 actions through the UI
    acts = 0; t0 = time.time(); saw_roll_anim = False; saw_can = False
    while acts < 40 and time.time() - t0 < 90:
        tp = turn_page()
        if tp is not None:
            tp.locator(".mndiebtn.go").click(); acts += 1
            tp.wait_for_timeout(60)
            saw_roll_anim = saw_roll_anim or tp.locator(".mndice.roll").count() > 0
            tp.wait_for_timeout(900)
            continue
        for pg in players:
            if pg.locator(".mnp.can").count():
                saw_can = True
                pg.evaluate("document.querySelector('.mnp.can').dispatchEvent(new MouseEvent('click',{bubbles:true}))"); acts += 1
                pg.wait_for_timeout(1500)
                break
        else:
            A.wait_for_timeout(300)
    check("played 40 actions", acts >= 40, acts)
    check("dice rolling animation appeared", saw_roll_anim)
    check("legal pawns were highlighted and clickable", saw_can)
    A.wait_for_timeout(3500)
    tr = [pg.evaluate("Object.fromEntries([...document.querySelectorAll('.mnp')].map(g=>[g.dataset.u+':'+g.dataset.i,g.style.transform]))") for pg in pgs]
    check("all four browsers draw identical pawn positions", all(t == tr[0] for t in tr), [sum(1 for k in tr[0] if tr[0][k] != t.get(k)) for t in tr])
    srvstate = None
    with S.rooms_lock:
        for r in S.rooms.values():
            if r.get("mensch"): srvstate = {u: list(pl["pawns"]) for u, pl in r["mensch"].players.items()}
    domok = False
    if srvstate:
        # compare the DOM with the server: a pawn in the yard has a slot position; count pawns that left the yard
        out_srv = sum(1 for u in srvstate for q in srvstate[u] if q >= 0)
        yard_xy = A.evaluate("(()=>{let n=0;for(const g of document.querySelectorAll('.mnp')){const m=/translate\\(([\\d.]+)px, ?([\\d.]+)px\\)/.exec(g.style.transform);if(!m)continue;const x=+m[1],y=+m[2];const inY=(x%9<=5.1)&&(y%9<=5.1)&&((x<6||x>9)&&(y<6||y>9));if(inY)n++}return n})()")
        check("pawns out of the yards in the DOM equals the server's count", 12 - yard_xy == out_srv, (12 - yard_xy, out_srv))
    # force a finish: first player has 3 home and one pawn on 55; he rolls a 1
    with S.rooms_lock:
        for r in S.rooms.values():
            g = r.get("mensch")
            if g:
                import random as _r
                class One(_r.Random):
                    def randint(self, a, b): return 1
                g.rng = One()
                u = g.order[0]
                for v_ in g.players.values(): v_["pawns"] = [-1] * 4
                g.players[u]["pawns"] = [56, 56, 56, 55]; g.turn = u; g.stage = "roll"; g.legal = []; g.sixes = 0
                g.deadline = time.time() + 60; g._bump()
        S._mensch_push(r)
    A.wait_for_timeout(1000)
    winner_pg = turn_page(); check("the prepared player can roll", winner_pg is not None)
    winner_pg.locator(".mndiebtn.go").click(); winner_pg.wait_for_timeout(1500)
    check("one pawn is highlighted", winner_pg.locator(".mnp.can").count() == 1)
    winner_pg.evaluate("document.querySelector('.mnp.can').dispatchEvent(new MouseEvent('click',{bubbles:true}))"); winner_pg.wait_for_timeout(2500)
    check("winner banner for everybody incl. spectator", all("برنده شد" in pg.locator(".mncard").inner_text() for pg in pgs))
    check("dice is disabled after the end", all(pg.locator(".mndiebtn.go").count() == 0 for pg in pgs))
    winner_pg.locator(".mncard .btn", has_text="بستن بازی").click(); winner_pg.wait_for_timeout(900)
    check("game closed for everybody", all("ساخت بازی منچ" in pg.locator(".mncard").inner_text() for pg in pgs))
    # reconnect mid-game: reload a page, board returns without animation errors
    A.locator(".mncard .btn", has_text="ساخت بازی منچ").click(); A.wait_for_timeout(500)
    pgs[1].locator(".mncard .btn", has_text="پیوستن").click(); A.wait_for_timeout(400)
    A.locator(".mncard .btn", has_text="شروع بازی").click(); A.wait_for_timeout(900)
    pgs[1].evaluate("mnReset();mnLoad()"); pgs[1].wait_for_timeout(700)
    check("a reloaded view shows the board again", pgs[1].locator(".mnp").count() == 8)
    errs = [e for pg in pgs for e in pg.errs if "favicon" not in e]
    check("no page errors", not errs)
    if errs: print(errs[:5])
    b.close()
print(f"{okc} ok, {len(bad)} failed"); os._exit(1 if bad else 0)
