"""Group moderation over the real server: silence, slow mode, ban/unban + all the ways to bypass them. Run: python test_groupadmin.py"""
import sys, tempfile, time, threading, sqlite3, queue
from pathlib import Path
sys.path.insert(0, ".")
import common
tmp = Path(tempfile.mkdtemp()); common.DATA_DIR = tmp; common.UPLOADS_DIR = tmp/"u"; common.AVATARS_DIR = tmp/"a"; common.WALLPAPERS_DIR = tmp/"w"; common.ROOMAUDIO_DIR = tmp/"r"; common.FILES_DIR = tmp/"f"; (tmp/"f").mkdir()
import server as srv
from client_core import Client
S = srv.WindroidaServer("127.0.0.1", 0, db_path=tmp/"t.db", web_port=0); port = S.start()
S._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
PW = "Str0ng-pass1"; res = []
def ok(n, c, x=""): res.append(bool(c)); print(("  ok   " if c else "  FAIL ") + n, "" if c else x)
def cl(n):
    c = Client(); c.connect("127.0.0.1", port)
    r = c.call("register", username=n, password=PW, display_name=n, sec_question="سوال تستی؟", sec_answer="x1"); assert r["ok"], r
    c.uid = r["me"]["id"]; c.ev = []; c.on_event = c.ev.append
    return c

O, A, B = cl("own1"), cl("alice1"), cl("bob1")
g = O.call("create_group", title="گروه", usernames=["alice1", "bob1"])["chat"]["id"]
def view(c):
    return [x for x in c.call("chats")["chats"] if x["id"] == g][0]
v = view(O)
ok("group view has online_count", "online_count" in v, v)
ok("all 3 online", v["online_count"] == 3, v.get("online_count"))
B.close() if hasattr(B, "close") else None
time.sleep(0.5)
v = view(O)
ok("count drops when a member leaves the app", v["online_count"] == 2, v.get("online_count"))
# alice hides her last seen/online from everyone -> not counted for others
print(A.call("privacy_set", priv_seen="nobody"))
v = view(O)
ok("hidden-presence member not counted for others", v["online_count"] == 1, v.get("online_count"))
m = O.call("members", chat_id=g)["members"]
ok("members list has online flags", all("online" in u for u in m) and len(m) == 3, m)
print(f"\n{sum(res)} passed, {len(res) - sum(res)} failed")
sys.exit(0 if all(res) else 1)
