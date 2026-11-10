"""Movies uploaded to the server for watch-rooms (cloud): streaming upload, quota, privacy, Range. Run: python test_roomvideo.py"""
import os; os.environ.setdefault("WINDROIDA_ADMIN", "admin_user")
import os
os.environ["WINDROIDA_ROOM_GRACE"] = "2"
import http.client, io, json, ssl, tempfile, time
from pathlib import Path
import common
tmp = Path(tempfile.mkdtemp(prefix="windroida_test5_"))
common.DATA_DIR = tmp
common.FILES_DIR = tmp / "files"; (tmp / "files").mkdir()
common.UPLOADS_DIR = tmp / "uploads"; common.AVATARS_DIR = tmp / "avatars"; common.WALLPAPERS_DIR = tmp / "wallpapers"; common.ROOMAUDIO_DIR = tmp / "roomaudio"
import server as srv
from client_core import Client
passed = failed = 0
def check(name, cond, extra=""):
    global passed, failed
    passed += bool(cond); failed += not cond
    print("  ok  " if cond else "  FAIL", name, "" if cond else extra)
server = srv.WindroidaServer("127.0.0.1", 0, True, db_path=tmp / "t.db", web_port=0)
server._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
port = server.start(); web = server.web_port
PW = "Str0ng-pass1"
def cl(name):
    c = Client(); c.connect("127.0.0.1", port, tls=True); c.seen = []
    c.on_event = lambda e: c.seen.append(e)
    r = c.call("register", username=name, password=PW, display_name=name.title(), sec_question="q q q q?", sec_answer="a1", device="t")
    assert r["ok"], r; c.me = r["me"]; c.call("hello", caps=[]); return c
def events(c, kind, wait=1.0):
    end = time.time() + wait
    while time.time() < end:
        try: c.inbox.get(timeout=0.05)()
        except Exception: pass
    return [e for e in c.seen if e.get("event") == kind]
from common import encode_frame
def fire(c, obj):
    with c._send_lock: c.sock.sendall(encode_frame(obj))
import os
os.environ.setdefault('WINDROIDA_ROOM_GRACE','2')
admin, a, b = cl("admin_user"), cl("alice"), cl("bob")
ctx = ssl._create_unverified_context()
def https(method, path, body=None):
    conn = http.client.HTTPSConnection("127.0.0.1", web, context=ctx, timeout=10)
    conn.request(method, path, body=body); r = conn.getresponse(); d = r.read(); conn.close(); return r.status, d
key = lambda c: c.call("media_key")["media_key"]
ka, kb, kadm = key(a), key(b), key(admin)



MP4 = b"\x00\x00\x00\x18ftypmp42" + bytes(range(256)) * 400
MKV = b"\x1a\x45\xdf\xa3" + b"\x00" * 5000
st, d = https("POST", "/roomupload?k=" + ka + "&name=film%201.mp4", body=MP4); j = json.loads(d)
check("alice uploads an mp4", st == 200 and j["ok"] and j["rel"] == "_uploads/alice/film 1.mp4" and j["size"] == len(MP4), (st, d))
check("file is exactly what was sent", (common.ROOMAUDIO_DIR / j["rel"]).read_bytes() == MP4)
REL = j["rel"]
check("no .part leftovers", not list(common.ROOMAUDIO_DIR.rglob(".part-*")))
st, d = https("POST", "/roomupload?k=" + ka + "&name=a.mkv", body=MKV); check("mkv accepted", st == 200, (st, d))
check("fake video refused", https("POST", "/roomupload?k=" + ka + "&name=fake.mp4", body=b"MZ" + b"\x00" * 400)[0] == 400)
check("fake video leaves no file", not list(common.ROOMAUDIO_DIR.rglob(".part-*")) and not (common.ROOMAUDIO_DIR / "_uploads/alice/fake.mp4").exists())
check("exe still refused", https("POST", "/roomupload?k=" + ka + "&name=v.exe", body=MP4)[0] == 400)
check("needs key", https("POST", "/roomupload?k=bad&name=b.mp4", body=MP4)[0] == 403)
check("path in name is neutralised", json.loads(https("POST", "/roomupload?k=" + ka + "&name=..%2F..%2Fevil.mp4", body=MP4)[1])["rel"].startswith("_uploads/alice/"))
lst = a.call("roomaudio_list")
check("alice sees her movies flagged video", any(x["rel"] == REL and x["video"] and x["mine"] for x in lst["songs"]))
check("usage reports movies separately", lst["vusage"]["count"] >= 2 and lst["usage"]["count"] == 0)
check("bob does not see alice's movie", not any(x["rel"] == REL for x in b.call("roomaudio_list")["songs"]))
conn_ = http.client.HTTPSConnection("127.0.0.1", web, context=ctx, timeout=10)
conn_.request("GET", "/roomaudio/" + REL.replace(" ", "%20") + "?k=" + ka, headers={"Range": "bytes=4-11"}); r_ = conn_.getresponse(); d_ = r_.read(); ct = r_.getheader("Content-Type"); conn_.close()
check("owner streams with Range as video/mp4", r_.status == 206 and d_ == MP4[4:12] and ct == "video/mp4", (r_.status, ct))
check("stranger cannot stream it", https("GET", "/roomaudio/" + REL.replace(" ", "%20") + "?k=" + kb)[0] == 404)
cid = a.call("open_private", username="bob")["chat"]["id"]
RID = a.call("room_open", chat_id=cid)["room"]["id"]; b.call("room_join", room=RID)
check("bob cannot queue alice's private movie", b.call("room_ctl", room=RID, a="add", items=[{"lib": REL}]).get("ok") is False)
r = a.call("room_ctl", room=RID, a="add", items=[{"lib": REL}]); check("alice queues it", r["ok"], r)
q = a.call("room_sync", room=RID)["state"]["queue"]
check("queue item is kind video", q and q[0]["kind"] == "video" and q[0]["lib"] == REL, q)
check("now bob (in room, queued) can stream it", https("GET", "/roomaudio/" + REL.replace(" ", "%20") + "?k=" + kb)[0] == 200)
check("bob cannot delete it", not b.call("roomaudio_delete", rel=REL).get("ok"))
check("alice deletes it", a.call("roomaudio_delete", rel=REL)["ok"] and not (common.ROOMAUDIO_DIR / REL).exists())
# quota: shrink limits for the test
common.VIDEO_QUOTA_COUNT = 3
st, d = https("POST", "/roomupload?k=" + ka + "&name=q1.mp4", body=MP4)
st2, d2 = https("POST", "/roomupload?k=" + ka + "&name=q2.mp4", body=MP4)
check("count quota stops the next upload", st2 == 400 and "سهمیه" in json.loads(d2)["error"], (st, st2, d2))
common.VIDEO_MAX = 1000
check("single-file limit", https("POST", "/roomupload?k=" + kb + "&name=big.mp4", body=MP4)[0] == 400)
print(f"\n{passed} passed, {failed} failed")
os._exit(1 if failed else 0)
