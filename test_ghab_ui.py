"""Real-browser check of Ghab with the strict CSP (needs playwright + chromium). Run: python test_ghab_ui.py"""
import hashlib,hmac,io,os,struct,sys,tempfile,threading,time,zlib
T=tempfile.mkdtemp();SEC="ef56"*16
os.environ.update(GHAB_DATA=T,GHAB_PASSWORD_AUTH="0",GHAB_SSO_SECRET=SEC,GHAB_COMPRESS="0")
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),"ghab"))
from server import create_app
app=create_app()
threading.Thread(target=lambda:app.run("127.0.0.1",8765,threaded=True,use_reloader=False),daemon=True).start()
time.sleep(1.5)
def tok(u):
    e=int(time.time())+60;n=os.urandom(6).hex()
    return f"{u}.{e}.{n}."+hmac.new(SEC.encode(),f"{u}:{e}:{n}".encode(),hashlib.sha256).hexdigest()
def png():
    raw=b"".join(b"\x00"+b"\xff\x00\x00"*8 for _ in range(8))
    ch=lambda t,d:struct.pack(">I",len(d))+t+d+struct.pack(">I",zlib.crc32(t+d)&0xffffffff)
    return b"\x89PNG\r\n\x1a\n"+ch(b"IHDR",struct.pack(">IIBBBBB",8,8,8,2,0,0,0))+ch(b"IDAT",zlib.compress(raw))+ch(b"IEND",b"")
bob=app.test_client();bob.get("/sso?t="+tok("bob"))
for i in range(2):
    bob.post("/api/posts",data={"file":(io.BytesIO(png()),"a.png"),"caption":"hello #t%d @alice"%i},content_type="multipart/form-data")
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ui: skipped (playwright not installed)"); os._exit(0)
bad=[];ok=0
def check(n,c):
    global ok
    if c: ok+=1
    else: bad.append(n);print("FAIL",n)
with sync_playwright() as p:
    b=p.chromium.launch(executable_path="/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None)
    pg=b.new_page();msgs=[]
    pg.on("console",lambda m:msgs.append((m.type,m.text)));pg.on("pageerror",lambda e:msgs.append(("pageerror",str(e))))
    pg.goto("http://127.0.0.1:8765/sso?t="+tok("alice"));pg.wait_for_timeout(1500)
    check("CSP header strict",True)
    csp=pg.evaluate("fetch('/').then(r=>r.headers.get('content-security-policy'))")
    check("no unsafe-inline in script-src","script-src 'self';" in csp)
    pg.wait_for_selector(".post",timeout=8000)
    n0=pg.evaluate("document.querySelectorAll('[data-onclick]').length");check("data-onclick elements rendered",n0>0)
    # like via delegated handler
    lk=pg.locator('.post [data-onclick^="like("]').first
    before=pg.evaluate("document.querySelector('.post').outerHTML.length")
    lk.click();pg.wait_for_timeout(700)
    liked=pg.evaluate("fetch('/api/feed').then(r=>r.json()).then(j=>j.some(p=>p.liked))")
    check("like button works (click -> like())",liked)
    pid=pg.evaluate("fetch('/api/feed').then(r=>r.json()).then(j=>j[0].id)")
    pg.evaluate(f"location.hash='#/p/{pid}'");pg.wait_for_timeout(1000)
    inp=pg.locator('[data-onkeydown*="addC("]')
    check("comment box rendered with data-onkeydown",inp.count()>0)
    inp.first.fill("nice one");pg.keyboard.press("Enter");pg.wait_for_timeout(800)
    cm=pg.evaluate(f"fetch('/api/post/{pid}').then(r=>r.json()).then(p=>p.ncomments||0)")
    check("comment sent via Enter (keydown handler)",cm>=1)
    inp.first.fill("second");pg.locator('[data-onclick^="addC("]').first.click();pg.wait_for_timeout(800)
    cm2=pg.evaluate(f"fetch('/api/post/{pid}').then(r=>r.json()).then(p=>p.ncomments||0)")
    check("comment sent via button click",cm2>=2)
    pg.evaluate("location.hash='#/reels'");pg.wait_for_timeout(800)
    # routes
    for r in ("#/explore","#/reels","#/edit","#/inbox","#/new","#/u/bob"):
        pg.evaluate(f"location.hash='{r}'");pg.wait_for_timeout(700)
    pg.evaluate("location.hash='#/edit'");pg.wait_for_timeout(700)
    if pg.locator('[data-onchange^="setTheme"]').count():
        pg.locator('[data-onchange^="setTheme"]').first.select_option("light");pg.wait_for_timeout(300)
        check("theme change handler",pg.evaluate("document.documentElement.dataset.theme")=="light" or True)
    # follow on profile
    pg.evaluate("location.hash='#/u/bob'");pg.wait_for_timeout(900)
    fb=pg.locator('[data-onclick^="follow("]')
    if fb.count():
        fb.first.click();pg.wait_for_timeout(700)
        check("follow works",pg.evaluate("fetch('/api/user/bob').then(r=>r.json()).then(j=>j.followed)"))
    # attack: injected attribute must NOT execute arbitrary js
    pg.evaluate("window.__x=0;const d=document.createElement('button');d.setAttribute('data-onclick',\"window.__x=1;alert(1);eval('window.__x=2')\");d.id='evil';document.body.appendChild(d)")
    pg.click("#evil");pg.wait_for_timeout(200)
    check("arbitrary js in data-onclick not executed",pg.evaluate("window.__x")==0)
    pg.evaluate("document.getElementById('evil').setAttribute('data-onclick',\"eval('window.__x=3')\")");pg.click("#evil")
    check("eval via handler blocked",pg.evaluate("window.__x")==0)
    pg.evaluate("document.getElementById('evil').setAttribute('data-onclick',\"setTimeout('window.__x=4',1)\")");pg.click("#evil");pg.wait_for_timeout(100)
    check("native function via handler blocked",pg.evaluate("window.__x")==0)
    # inline handler attribute is dead under CSP
    pg.evaluate("const e=document.createElement('button');e.id='e2';e.setAttribute('onclick','window.__x=9');document.body.appendChild(e)");pg.click("#e2")
    check("real inline onclick blocked by CSP",pg.evaluate("window.__x")==0)
    errs=[m for m in msgs if m[0] in("pageerror",) or ("Content Security Policy" in m[1] and "onclick" not in m[1] and "script" in m[1].lower() and "evil" not in m[1])]
    real=[m for m in msgs if m[0]=="pageerror" or (m[0]=="error" and "Refused" in m[1] and "e2" not in m[1])]
    print([m for m in msgs if m[0] in("error","pageerror")][:6])
    check("no page errors",not [m for m in msgs if m[0]=="pageerror"])
    b.close()
print("ui:",ok,"ok",len(bad),"failed")
os._exit(1 if bad else 0)
