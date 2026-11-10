"""Real-browser test of the 3D Mensch board (own WebGL engine, no library): renders, picks pawns by tapping, die, 2D/3D toggle, fallback. Run: python test_mensch3d.py"""
import os, sys, tempfile, time
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
    print("mensch3d: skipped (playwright not installed)"); os._exit(0)
S = srv.WindroidaServer("127.0.0.1", 0, db_path=tmp/"t.db", web_port=0); port = S.start()
S._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
PW = "Str0ng-pass1"
def reg(n):
    c = Client(); c.connect("127.0.0.1", port)
    r = c.call("register", username=n, password=PW, display_name=n, sec_question="سوال تستی؟", sec_answer="x1"); assert r["ok"], r
    return r.get("session") or r.get("token")
toks = [reg(n) for n in ["amir", "bahar"]]
bad = []; okc = 0
def check(n, c, x=""):
    global okc
    if c: okc += 1
    else: bad.append(n); print("FAIL", n, x)
url = f"http://127.0.0.1:{S.web_port}/"
GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
def colorful(pg, sel):
    pg.wait_for_timeout(200)
    png = pg.locator(sel).screenshot()
    from PIL import Image; import io
    im = Image.open(io.BytesIO(png)).convert("RGB").resize((60, 60))
    return len(set(im.getdata()))
def setup(b, extra_init=""):
    pgs = []
    for t in toks:
        ctx = b.new_context(viewport={"width": 420, "height": 860}); pg = ctx.new_page(); pg.errs = []
        pg.on("pageerror", lambda e, pg=pg: pg.errs.append(str(e))); pg.on("console", lambda m, pg=pg: pg.errs.append(m.text) if m.type == "error" else None)
        pg.add_init_script(f"try{{localStorage.setItem('wd-token','{t}')}}catch(e){{}}" + extra_init); pg.goto(url); pg.wait_for_timeout(1400); pgs.append(pg)
    A, B = pgs
    A.evaluate("rOpen('room_open',{title:'x'})"); A.wait_for_timeout(900); rid = A.evaluate("R.id")
    B.evaluate(f"rOpen('room_join',{{room:'{rid}'}})"); A.wait_for_timeout(1000)
    for pg in pgs: pg.evaluate("R.tab='games';rDrawTabs();rDrawPane()")
    A.wait_for_timeout(500)
    A.locator(".mncard .btn", has_text="ساخت بازی منچ").click(); A.wait_for_timeout(600)
    B.locator(".mncard .btn", has_text="پیوستن").click(); A.wait_for_timeout(500)
    A.locator(".mncard .btn", has_text="شروع بازی").click(); A.wait_for_timeout(1500)
    return pgs
with sync_playwright() as p:
    b = p.chromium.launch(args=GL)
    pgs = setup(b); A, B = pgs
    check("webgl supported and the 3D canvas replaces the flat board", A.evaluate("MN3.supported()") and A.locator("canvas.mn3d").count() == 1 and A.locator(".mnsvg").count() == 0)
    check("board is really drawn (many colours)", colorful(A, ".mnboard") > 60)
    check("both seats see the 3D board", B.locator("canvas.mn3d").count() == 1)
    check("a die sits in the corner for each player (2 players, 4 corners, 2 empty)", A.locator(".mncd:not(.none)").count() == 2 and A.locator(".mncd.none").count() == 2 and A.locator(".mncd.me.mndiebtn").count() == 1)
    check("12 -> here 8 pawns exist in the scene", A.evaluate("Object.keys(MN3.pawns).length") == 8)
    check("toggle shows 3D", A.locator(".mn3t").inner_text() == "3D")
    def turn_page():
        for pg in pgs:
            if pg.locator(".mndiebtn.go").count(): return pg
    for rnd in range(40):
        tp = turn_page()
        if tp is None: A.wait_for_timeout(300); continue
        tp.locator(".mndiebtn.go").click(); tp.wait_for_timeout(1300)
        if tp.evaluate("MN3.legal.size") > 0:
            break
    else: tp = None
    check("a legal pawn glows after a roll", tp is not None and tp.evaluate("MN3.legal.size") > 0)
    if tp is not None:
        v0 = tp.evaluate("MN.v.me.id+'|'+JSON.stringify(MN.v.players.find(x=>x.id===MN.v.me.id).pawns)")
        # tap exactly where the first legal pawn is on screen
        pt = tp.evaluate("""(()=>{const k=[...MN3.legal][0],P=MN3.pawns[k],{vp}=MN3.vp(),x=P.x,y=.55,z=P.z;
          const c=[vp[0]*x+vp[4]*y+vp[8]*z+vp[12],vp[1]*x+vp[5]*y+vp[9]*z+vp[13],vp[3]*x+vp[7]*y+vp[11]*z+vp[15]];
          const r=MN3.canvas.getBoundingClientRect();return {x:r.left+(c[0]/c[2]*.5+.5)*r.width,y:r.top+(1-(c[1]/c[2]*.5+.5))*r.height,k}})()""")
        # a tap on empty board does nothing
        r = tp.evaluate("MN3.canvas.getBoundingClientRect().toJSON()")
        tp.mouse.click(r["x"] + r["width"] / 2, r["y"] + r["height"] * .55); tp.wait_for_timeout(400)
        check("tapping empty board does not move", tp.evaluate("JSON.stringify(MN.v.players.find(x=>x.id===MN.v.me.id).pawns)") == v0.split("|", 1)[1])
        tp.mouse.click(pt["x"], pt["y"]); tp.wait_for_timeout(1500)
        v1 = tp.evaluate("JSON.stringify(MN.v.players.find(x=>x.id===MN.v.me.id).pawns)")
        check("tapping the glowing pawn in 3D moves it on the server", v1 != v0.split("|", 1)[1], (v0, v1))
        check("both browsers agree afterwards", A.evaluate("JSON.stringify(MN.v.players.map(p=>p.pawns))") == B.evaluate("JSON.stringify(MN.v.players.map(p=>p.pawns))"))
        check("3D pawn ended where the server says (no stuck animation)", tp.evaluate("Object.values(MN3.pawns).every(P=>!P.dur)"))
    # toggle to 2D and back
    A.locator(".mn3t").click(); A.wait_for_timeout(400)
    check("2D toggle brings the flat board back", A.locator(".mnsvg").count() == 1 and A.locator("canvas.mn3d").count() == 0 and A.locator(".mn3t").inner_text() == "2D" and A.locator(".mndice").count() == 2)
    check("2D pawns still all there", A.locator(".mnp").count() == 8)
    A.locator(".mn3t").click(); A.wait_for_timeout(600)
    check("back to 3D", A.locator("canvas.mn3d").count() == 1 and colorful(A, ".mnboard") > 60)
    check("setting is remembered", A.evaluate("localStorage.getItem('wd-mn-3d')") == "1")
    # leaving the games tab and coming back keeps drawing
    A.evaluate("R.tab='chat';rDrawTabs();rDrawPane()"); A.wait_for_timeout(300)
    A.evaluate("R.tab='games';rDrawTabs();rDrawPane()"); A.wait_for_timeout(700)
    check("board is alive after tab switch", A.locator("canvas.mn3d").count() == 1 and colorful(A, ".mnboard") > 60)
    check("no page errors", not A.errs and not B.errs, (A.errs, B.errs))
    b.close()
    # no WebGL -> flat board, no errors
    b = p.chromium.launch(args=["--disable-gpu", "--disable-3d-apis"])
    pgs = setup(b); A, B = pgs
    check("without WebGL the flat board is used", A.locator(".mnsvg").count() == 1 and A.locator("canvas.mn3d").count() == 0 and A.locator(".mn3t").count() == 0 and A.locator(".mndice").count() == 2)
    check("and no errors", not A.errs, A.errs)
    b.close()
print(f"mensch3d: {okc} checks ok, {len(bad)} failed"); os._exit(1 if bad else 0)
