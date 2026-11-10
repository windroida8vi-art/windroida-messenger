"""Tests for group calls (audio for everyone, video capped at a few concurrent cameras because it's all relayed
through this one server with no STUN/P2P). Run: python test_gcall.py"""
import os, sys, tempfile, time
os.environ["WINDROIDA_CALL_GRACE"] = "2"
os.environ["WINDROIDA_GCALL_MAX"] = "4"
os.environ["WINDROIDA_GCALL_MAX_VIDEO"] = "2"
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
from common import encode_frame
tmp = Path(tempfile.mkdtemp()); common.DATA_DIR = tmp; common.UPLOADS_DIR = tmp/"u"; common.AVATARS_DIR = tmp/"a"; common.WALLPAPERS_DIR = tmp/"w"; common.ROOMAUDIO_DIR = tmp/"r"; common.FILES_DIR = tmp/"f"; (tmp/"f").mkdir()
import server as srv
from client_core import Client

S = srv.WindroidaServer("127.0.0.1", 0, db_path=tmp/"t.db", web_port=0)
S._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
port = S.start()
PW = "Str0ng-pass1"
bad = []; ok = 0
def check(n, c, x=""):
    global ok
    if c: ok += 1
    else: bad.append(n); print("FAIL", n, x)

def client(name):
    c = Client(); c.seen = []; c.on_event = lambda e: c.seen.append(e)
    c.connect("127.0.0.1", port)
    r = c.call("register", username=name, password=PW, display_name=name, sec_question="سوال تستی؟", sec_answer="x1")
    assert r["ok"], r
    c.call("hello", caps=["call"])
    c.me_id = c.call("me")["me"]["id"]
    return c

def fire(c, op, **fields):
    """Send a fire-and-forget frame (no id, like real audio/video frames) — these never get an {ok,...} reply."""
    c.sock.sendall(encode_frame({"op": op, **fields}))

def drain(*cs):
    """Pump each client's inbox into .seen, then discard everything seen so far — so the next collect() can only
    match a fresh event, never one left over from an earlier step."""
    end = time.time() + 0.3
    while time.time() < end:
        for c in cs:
            try:
                while True: c.inbox.get_nowait()()
            except Exception: pass
    for c in cs:
        c.seen.clear()

def collect(c, kinds, wait=2.0, call_id=None):
    end = time.time() + wait
    while time.time() < end:
        try: c.inbox.get(timeout=0.05)()
        except Exception: pass
        for e in c.seen:
            if e["event"] in kinds and (call_id is None or e.get("call_id") == call_id):
                c.seen.remove(e); return e
    return None

names = ["amir", "bahar", "cyrus", "dara", "elli", "foad"]
C = {n: client(n) for n in names}
amir = C["amir"]
r = amir.call("create_group", title="گروه تست", usernames=["bahar", "cyrus", "dara", "elli", "foad"])
chat_id = r["chat"]["id"]

print("== basic start/join/roster")
r1 = amir.call("gcall_start", chat_id=chat_id)
cid = r1["call_id"]
check("caller is in the roster", r1["participants"] == [{"id": amir.me_id, "name": "amir", "avatar_at": 0, "video": False, "away": False}])
inc = collect(C["bahar"], ["gcall_incoming"], call_id=None)
check("others get gcall_incoming", inc is not None and inc["chat_id"] == chat_id)
r2 = C["bahar"].call("gcall_join", call_id=cid)
check("bahar joins, roster has 2", len(r2["participants"]) == 2)
ev = collect(amir, ["gcall_participants"], call_id=cid)
check("amir sees roster update", ev is not None and len(ev["participants"]) == 2)
r3 = C["cyrus"].call("gcall_join", call_id=cid)
r4 = C["dara"].call("gcall_join", call_id=cid)
check("4 participants now", len(r4["participants"]) == 4)

print("== max participants (set to 4)")
r = C["elli"].call("gcall_join", call_id=cid)
check("5th rejected (call full)", not r["ok"] and "پر" in r["error"], r)

print("== video slot cap (2)")
drain(*C.values())
fire(C["amir"], "gcall_video", call_id=cid, d="AAAA")
ev = collect(C["bahar"], ["gcall_participants"], call_id=cid)
check("video-on broadcast after 1st camera", ev and any(p["video"] for p in ev["participants"]), ev)
drain(*C.values())
fire(C["bahar"], "gcall_video", call_id=cid, d="BBBB")
collect(C["amir"], ["gcall_participants"], call_id=cid, wait=1.0)   # let bahar's video-on broadcast land
drain(*C.values())
fire(C["cyrus"], "gcall_video", call_id=cid, d="CCCC")
rej = collect(C["cyrus"], ["gcall_video_full"], call_id=cid)
check("3rd camera rejected (slots full)", rej is not None, rej)
drain(*C.values())
# turning one off frees a slot
fire(C["amir"], "gcall_video", call_id=cid, d="")
ev = collect(C["dara"], ["gcall_participants"], call_id=cid)
check("roster updates after camera off", ev is not None and not any(p["id"] == amir.me_id and p["video"] for p in ev["participants"]), ev)
drain(*C.values())
fire(C["cyrus"], "gcall_video", call_id=cid, d="CCCC")
ev = collect(C["dara"], ["gcall_participants"], call_id=cid)
check("3rd camera now accepted after a slot freed", ev is not None and any(p["id"] == C["cyrus"].me_id and p["video"] for p in ev["participants"]), ev)

print("== audio/video relay reaches other participants only")
drain(*C.values())
fire(C["bahar"], "gcall_audio", call_id=cid, d="ZZZZ", sr=16000)
got = collect(C["dara"], ["gcall_audio"], wait=1.5)
check("dara receives bahar's audio, tagged with sender", got is not None and got["from"] == C["bahar"].me_id and got["d"] == "ZZZZ", got)
time.sleep(0.3)
self_got = [e for e in C["bahar"].seen if e.get("event") == "gcall_audio"]
check("sender does not get its own audio echoed back", not self_got)
drain(*C.values())
fire(C["cyrus"], "gcall_video", call_id=cid, d="DDDD")   # cyrus already has a video slot (just claimed above)
vgot = collect(C["dara"], ["gcall_video"], wait=1.5)
check("dara receives cyrus's video frame too", vgot is not None and vgot["from"] == C["cyrus"].me_id and vgot["d"] == "DDDD", vgot)

print("== leaving and auto-end when empty")
drain(*C.values())
C["amir"].call("gcall_leave", call_id=cid)
ev = collect(C["bahar"], ["gcall_participants"], call_id=cid)
check("roster shrinks after amir leaves", ev is not None and len(ev["participants"]) == 3)
C["bahar"].call("gcall_leave", call_id=cid)
C["dara"].call("gcall_leave", call_id=cid)
r_last = C["cyrus"].call("gcall_leave", call_id=cid)
check("last leave returns ok", r_last["ok"])

print("== disconnect grace: a dropped socket keeps the call alive briefly, then is removed")
r1 = C["elli"].call("gcall_start", chat_id=chat_id)
cid2 = r1["call_id"]
C["foad"].call("gcall_join", call_id=cid2)
C["foad"].close()  # simulate a dropped connection without a clean leave (proper shutdown, like a real socket drop)
time.sleep(0.3)
check("call survives the drop immediately (grace period)", cid2 in S.gcalls)
time.sleep(3.0)  # grace is 2s in this test
with S.gcalls_lock:
    gone = cid2 not in S.gcalls or len(S.gcalls.get(cid2, {}).get("participants", {})) == 1
check("foad is removed from the call after the grace period", gone)

print("== a non-member cannot join the group's call")
outsider = client("ghost")
r1 = C["elli"].call("gcall_start", chat_id=chat_id)
cid3 = r1["call_id"]
r = outsider.call("gcall_join", call_id=cid3)
check("outsider rejected (not a member)", not r["ok"], r)

print("== can't be in a 1:1 call and a group call at the same time")
chat2 = amir.call("open_private", username="ghost")["chat"]["id"]
r_inv = amir.call("call_invite", chat_id=chat2)
r = amir.call("gcall_start", chat_id=chat_id)
check("busy with 1:1 call -> group call refused", not r["ok"] and "دیگه‌ای" in r["error"], r)
amir.call("call_end", call_id=r_inv["call_id"])

print(f"\ngcall: {ok} ok, {len(bad)} failed")
os._exit(1 if bad else 0)
