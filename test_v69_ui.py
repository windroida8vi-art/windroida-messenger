"""v6.9 web: drag-to-seek on song/voice bars, link cards for own services, #game=… deep link opens a room on the games tab. Run: python test_v69_ui.py"""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
tmp = Path(tempfile.mkdtemp()); common.DATA_DIR = tmp; common.UPLOADS_DIR = tmp/"u"; common.AVATARS_DIR = tmp/"a"; common.WALLPAPERS_DIR = tmp/"w"; common.ROOMAUDIO_DIR = tmp/"r"; common.FILES_DIR = tmp/"f"; (tmp/"f").mkdir()
import server as srv
from client_core import Client
from playwright.sync_api import sync_playwright
S = srv.WindroidaServer("127.0.0.1", 0, db_path=tmp/"t.db", web_port=0); port = S.start()
S._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
c = Client(); c.connect("127.0.0.1", port)
r = c.call("register", username="amir", password="Str0ng-pass1", display_name="amir", sec_question="سوال تستی؟", sec_answer="x1"); tok = r.get("session") or r.get("token")
bad = []; okc = 0
def check(n, cnd, x=""):
    global okc
    if cnd: okc += 1
    else: bad.append(n); print("FAIL", n, x)
url = f"http://127.0.0.1:{S.web_port}/"
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 420, "height": 860}); pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.add_init_script(f"try{{localStorage.setItem('wd-token','{tok}')}}catch(e){{}}")
    pg.goto(url); pg.wait_for_timeout(1800)
    # --- scrub on a song bar
    pg.evaluate("""()=>{window.__seeks=[];playToggle=()=>{};const m={id:99,chat_id:0,sender_id:S.me.id,file:{name:'song.mp3',size:2048000,kind:'audio',dur:200}};
      const el=musicBlock(m);el.id='tm';el.style.cssText='position:fixed;top:100px;left:20px;width:360px;background:#223';document.body.append(el);
      const ui=window.__ui=(typeof UIS!=='undefined'?null:null);}""")
    box = pg.locator("#tm .mbar").bounding_box()
    check("song bar is a comfortable touch target", pg.locator("#tm .mhit").bounding_box()["height"] >= 20, pg.locator("#tm .mhit").bounding_box())
    pg.mouse.move(box["x"] + 5, box["y"] + 3); pg.mouse.down(); pg.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + 3, steps=6)
    w = pg.evaluate("parseFloat(document.querySelector('#tm .mbar i').style.width)")
    check("bar follows the pointer while dragging (~50%)", 40 < w < 60, w)
    pg.mouse.move(box["x"] + box["width"] * 0.8, box["y"] + 3, steps=4)
    w2 = pg.evaluate("parseFloat(document.querySelector('#tm .mbar i').style.width)")
    check("and keeps following (~80%)", 70 < w2 < 90, w2)
    pg.mouse.up(); pg.wait_for_timeout(100)
    check("no page errors after seeking", not errs, errs)
    # --- voice waveform scrub
    pg.evaluate("""()=>{const m={id:98,chat_id:0,sender_id:S.me.id,file:{name:'v.webm',size:5000,kind:'audio',voice:true,dur:20,wave:Array.from({length:32},(_,i)=>i)}};
      const el=voiceBlock(m);el.id='tv';el.style.cssText='position:fixed;top:300px;left:20px;width:300px;background:#223';document.body.append(el)}""")
    vb = pg.locator("#tv .wv").bounding_box()
    pg.mouse.move(vb["x"] + 3, vb["y"] + 5); pg.mouse.down(); pg.mouse.move(vb["x"] + vb["width"] * 0.5, vb["y"] + 5, steps=5)
    on = pg.evaluate("document.querySelectorAll('#tv .wv i.on').length")
    check("waveform lights up while dragging (about half)", 10 <= on <= 22, on); pg.mouse.up()
    # --- link cards
    own = pg.evaluate("(()=>{const e=linkCard('نگا کن https://'+location.hostname+':8084/p/664');return e?e.innerText:null})()")
    check("Ghab post link gets its own card", own and "قاب" in own and "۶۶۴" in own, own)
    drv = pg.evaluate("(()=>{const e=linkCard('https://'+location.hostname+':8082/s/abc');return e?e.innerText:null})()")
    check("Cloud Drive link gets its own card", drv and "فضای ابری" in drv, drv)
    ext = pg.evaluate("(()=>{const e=linkCard('see https://example.com/page?x=1.');return e?e.innerText:null})()")
    check("external link gets a plain card with the site name", ext and "example.com" in ext, ext)
    check("no link, no card", pg.evaluate("linkCard('hello')") is None)
    check("javascript: is never turned into a card", pg.evaluate("linkCard('javascript:alert(1)')") is None)
    # --- deep link
    pg2 = ctx.new_page(); pg2.on("pageerror", lambda e: errs.append(str(e)))
    pg2.goto(url + "#game=mensch"); pg2.wait_for_timeout(4500)
    check("#game=mensch opens a room on the games tab with a mensch lobby", pg2.evaluate("R.on&&R.tab==='games'") and pg2.locator(".mncard .mnlp").count() == 1, pg2.evaluate("JSON.stringify({on:R.on,tab:R.tab})"))
    pg3 = ctx.new_page(); pg3.on("pageerror", lambda e: errs.append(str(e)))
    pg3.goto(url + "#game=room"); pg3.wait_for_timeout(4500)
    check("#game=room opens a plain room", pg3.evaluate("R.on"))
    check("hash was cleaned from the address bar", "#game" not in pg2.url and "#game" not in pg3.url)
    check("no page errors", not errs, errs[:3])
    b.close()
print(f"{okc} ok, {len(bad)} failed"); os._exit(1 if bad else 0)
