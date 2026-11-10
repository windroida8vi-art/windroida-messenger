"""Check that deleting one photo from the profile-photo gallery removes exactly THAT photo, leaving the current
(front) one untouched unless it's the one picked — the reported bug was that only the front photo could ever be
removed, no matter which one you were looking at. Run: python test_avatar_pic.py"""
import os; os.environ.setdefault("WINDROIDA_ADMIN", "admin_user")
import http.client, io, ssl, tempfile, time
from pathlib import Path
import common
tmp = Path(tempfile.mkdtemp(prefix="windroida_test_avpic_"))
common.DATA_DIR = tmp
common.FILES_DIR = tmp / "files"; (tmp / "files").mkdir()
common.UPLOADS_DIR = tmp / "uploads"; common.AVATARS_DIR = tmp / "avatars"
common.WALLPAPERS_DIR = tmp / "w"; common.ROOMAUDIO_DIR = tmp / "r"
import server as srv
from client_core import Client
from PIL import Image

passed = failed = 0
def check(name, cond, extra=""):
    global passed, failed
    passed += bool(cond); failed += not cond
    print("  ok  " if cond else "  FAIL", name, "" if cond else extra)

server = srv.WindroidaServer("127.0.0.1", 0, True, db_path=tmp / "t.db", web_port=0)
server._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
port = server.start(); web = server.web_port
ctx = ssl._create_unverified_context()
def https(method, path, body=None):
    conn = http.client.HTTPSConnection("127.0.0.1", web, context=ctx, timeout=10)
    conn.request(method, path, body=body); r = conn.getresponse(); d = r.read(); conn.close(); return r.status, d

def cl(name):
    c = Client(); c.connect("127.0.0.1", port, tls=True)
    r = c.call("register", username=name, password="Str0ng-pass1", display_name=name.title(), sec_question="q q q q?", sec_answer="a1", device="t")
    assert r["ok"], r; c.me = r["me"]; return c

a, b = cl("alice"), cl("bob")
ka = a.call("media_key")["media_key"]; kb = b.call("media_key")["media_key"]

def png():
    buf = io.BytesIO(); Image.new("RGB", (300, 300), (200, 30, 30)).save(buf, "PNG"); return buf.getvalue()

print("== delete a specific (non-front) photo from the gallery")
for _ in range(3):
    https("POST", f"/avatar?k={ka}&target=me", png()); time.sleep(1.1)
pics = b.call("avatar_list", user_id=a.me["id"])["pics"]
check("3 photos uploaded, newest first", len(pics) == 3, pics)
front = pics[0]; oldest = pics[-1]

r = a.call("remove_avatar_pic", pic=oldest)
check("deleting the OLDEST photo succeeds", r["ok"], r)
after = b.call("avatar_list", user_id=a.me["id"])["pics"]
check("exactly the oldest one is gone, the rest stay", after == pics[:-1], after)
check("the current/front photo is untouched (not what got deleted)",
      a.call("me")["me"]["avatar_at"] != 0 and front in after, after)

print("== deleting the CURRENT (front) photo does detach it as the profile photo too")
r = a.call("remove_avatar_pic", pic=front)
check("deleting the front photo succeeds", r["ok"], r)
check("front photo is detached from the profile", a.call("me")["me"]["avatar_at"] == 0)
after2 = b.call("avatar_list", user_id=a.me["id"])["pics"]
check("front photo left the gallery too", front not in after2, after2)

print("== can't touch someone else's photos")
https("POST", f"/avatar?k={kb}&target=me", png())
bob_pic = b.call("avatar_list", user_id=b.me["id"])["pics"][0]
r = a.call("remove_avatar_pic", pic=bob_pic)
check("alice can't delete bob's photo by filename alone (deletes from HER OWN folder, a no-op)", r["ok"])
check("bob's photo is still there", bob_pic in b.call("avatar_list", user_id=b.me["id"])["pics"])

print("== bad / path-traversal pic name rejected")
r = a.call("remove_avatar_pic", pic="../../etc/passwd")
check("path-traversal name refused", not r["ok"], r)
r = a.call("remove_avatar_pic", pic="")
check("empty name refused", not r["ok"], r)

print(f"\navatar pic delete: {passed} ok, {failed} failed")
os._exit(1 if failed else 0)
