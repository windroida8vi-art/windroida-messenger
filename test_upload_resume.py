"""Resumable /upload (the Android app continues after the internet was cut): python test_upload_resume.py"""
import http.client, json, sys, tempfile, time, socket
from pathlib import Path
import common
import server as srv
from client_core import Client

tmp = Path(tempfile.mkdtemp(prefix="windroida_test_resume_"))
(tmp / "files").mkdir()
common.FILES_DIR = tmp / "files"
common.UPLOADS_DIR = tmp / "uploads"
passed = failed = 0
def check(name, cond, extra=""):
    global passed, failed
    if cond: passed += 1; print("  ok  ", name)
    else: failed += 1; print("  FAIL", name, extra)

server = srv.WindroidaServer("127.0.0.1", 0, db_path=tmp / "t.db", web_port=0)
server._may_add_directly = lambda db, adder, target: True
port = server.start(); web = server.web_port
PW = "Str0ng-pass1"
def client():
    c = Client(); c.seen = []; c.on_event = lambda e: c.seen.append(e); c.connect("127.0.0.1", port); return c
def req(method, path, body=None):
    cn = http.client.HTTPConnection("127.0.0.1", web, timeout=10); cn.request(method, path, body=body)
    r = cn.getresponse(); d = r.read(); cn.close(); return r.status, d

a = client(); a.call("register", username="alice", password=PW, display_name="Alice", sec_question="سوال تستی؟", sec_answer="x1", device="t")
b = client(); b.call("register", username="bob", password=PW, display_name="Bob", sec_question="سوال تستی؟", sec_answer="y1")
key = a.call("hello", caps=[])["media_key"]
chat = a.call("open_private", username="bob")["chat"]["id"]

payload = bytes(range(256)) * 4096          # 1 MiB
total = len(payload); cut = 300_000
rid = "abcdef0123456789abcdef"
base = f"/upload?k={key}&chat_id={chat}&name=clip.mp4&rid={rid}"

# 1) connection dies after `cut` bytes (declared length is the full size)
s = socket.create_connection(("127.0.0.1", web))
s.sendall((f"POST {base}&offset=0&total={total} HTTP/1.1\r\nHost: x\r\nContent-Length: {total}\r\n\r\n").encode() + payload[:cut])
time.sleep(0.4); s.close(); time.sleep(0.6)
st, body = req("GET", f"/upload-status?k={key}&rid={rid}")
have = json.loads(body).get("have")
check("server kept the part that arrived", st == 200 and 0 < have <= cut, (st, body))

# 2) wrong offset is refused with the real count
st, body = req("POST", f"{base}&offset=5&total={total}", payload[5:])
check("wrong offset -> 409 + have", st == 409 and json.loads(body).get("have") == have, (st, body[:100]))

# 3) continue from `have`: the message must be the complete file
st, body = req("POST", f"{base}&offset={have}&total={total}", payload[have:])
j = json.loads(body)
check("resume finishes the upload", st == 200 and j.get("ok") and j["message"]["file"]["size"] == total, (st, body[:200]))
mid = j["message"]["id"]
st, data = req("GET", f"/media/{mid}?k={key}")
check("stored file is byte-identical", st == 200 and data == payload)
st, body = req("GET", f"/upload-status?k={key}&rid={rid}")
check("temp part removed after success", json.loads(body).get("have") == 0)
st, _ = req("GET", f"/upload-status?k=bogus&rid={rid}")
check("status needs a valid key", st == 403)

# 4) normal (non-resumable) upload still works
st, body = req("POST", f"/upload?k={key}&chat_id={chat}&name=x.txt", b"hello")
check("plain upload unchanged", st == 200 and json.loads(body)["ok"])

print(f"\n{passed} passed, {failed} failed")
server.stop()
sys.exit(1 if failed else 0)
