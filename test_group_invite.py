"""Adding people to groups: direct add only when the person allows it (everybody / contacts), otherwise an invite link goes to his private chat. Run: python test_group_invite.py"""
import sys, tempfile, time, threading, sqlite3, queue
from pathlib import Path
sys.path.insert(0, ".")
import common
tmp = Path(tempfile.mkdtemp()); common.DATA_DIR = tmp; common.UPLOADS_DIR = tmp/"u"; common.AVATARS_DIR = tmp/"a"; common.WALLPAPERS_DIR = tmp/"w"; common.ROOMAUDIO_DIR = tmp/"r"; common.FILES_DIR = tmp/"f"; (tmp/"f").mkdir()
import server as srv
from client_core import Client
S = srv.WindroidaServer("127.0.0.1", 0, db_path=tmp/"t.db", web_port=0); port = S.start()
PW = "Str0ng-pass1"; res = []
def ok(n, c, x=""): res.append(bool(c)); print(("  ok   " if c else "  FAIL ") + n, "" if c else x)
def cl(n):
    c = Client(); c.connect("127.0.0.1", port)
    r = c.call("register", username=n, password=PW, display_name=n, sec_question="سوال تستی؟", sec_answer="x1"); assert r["ok"], r
    c.uid = r["me"]["id"]; c.ev = []; c.on_event = c.ev.append
    return c
def second_session(name):
    c = Client(); c.connect("127.0.0.1", port); r = c.call("login", username=name, password=PW); assert r["ok"], r; return c
def drain(c):
    while True:
        try: c.inbox.get_nowait()()
        except queue.Empty: break
def evs(c, kind):
    time.sleep(0.15); drain(c); return [e for e in c.ev if e.get("event") == kind]
def db(sql, *a):
    d = sqlite3.connect(tmp/"t.db"); d.row_factory = sqlite3.Row
    try:
        with d: r = d.execute(sql, a); return r.fetchall()
    finally: d.close()
def say(c, chat, t="hi"): return c.call("send", chat_id=chat, text=t)

def private_msgs(a, b):
    r = a.call("open_private", username=b); cid = r["chat"]["id"]
    return [m["body"] for m in db("SELECT body FROM messages WHERE chat_id=? ORDER BY id", cid)]
def members(g): return {r["user_id"] for r in db("SELECT user_id FROM members WHERE chat_id=?", g)}

A, B, C, D = cl("own1"), cl("bob1"), cl("cat1"), cl("dan1")
g = A.call("create_group", title="گروه", usernames=[])["chat"]["id"]
ok("default: nobody may add me directly", B.call("privacy_get")["priv_add"] == "nobody")
r = A.call("add_member", chat_id=g, username="bob1", origin="https://10.0.0.5:8081")
ok("default: not added, invited instead", r.get("ok") and r.get("invited") and (r.get("ok") and r.get("invited")), r)
ok("bob is not a member", B.uid not in members(g))
msgs = private_msgs(A, "bob1")
ok("the invite link is in their private chat", any("#join=" in m and "https://10.0.0.5:8081" in m for m in msgs), msgs)
tok = db("SELECT invite FROM chats WHERE id=?", g)[0]["invite"]
ok("the link joins the group", B.call("join", token=tok).get("ok") and B.uid in members(g))
# everybody
ok("set everybody", C.call("privacy_set", priv_add="all").get("priv_add") == "all")
r = A.call("add_member", chat_id=g, username="cat1")
ok("everybody: added directly", r.get("ok") and not r.get("invited") and C.uid in members(g), r)
# contacts only
ok("set contacts", D.call("privacy_set", priv_add="contacts").get("priv_add") == "contacts")
r = A.call("add_member", chat_id=g, username="dan1")
ok("contacts: a stranger only gets a link", r.get("invited") and D.uid not in members(g), r)
D.call("remove_member", chat_id=g, user_id=D.uid) if False else None
ok("bad value refused", not D.call("privacy_set", priv_add="everyone").get("ok"))
# a contact (somebody who wrote to him) adds directly
g2 = A.call("create_group", title="دو", usernames=[])["chat"]["id"]
D.call("open_private", username="own1"); cid = D.call("open_private", username="own1")["chat"]["id"]; D.call("send", chat_id=cid, text="سلام")
r = A.call("add_member", chat_id=g2, username="dan1")
ok("contacts: a contact is added directly", r.get("ok") and not r.get("invited") and D.uid in members(g2), r)
# creating a group applies the same rule
E = cl("eve1")
g3 = A.call("create_group", title="سه", usernames=["eve1"])
ok("create_group: eve (nobody) is invited, not added", g3.get("ok") and E.uid not in members(g3["chat"]["id"]) and any("#join=" in m for m in private_msgs(A, "eve1")), g3)
# a blocked adder cannot even send the link
F = cl("fay1"); ok("fay blocks own1", F.call("block", user_id=A.uid).get("ok"))
r = A.call("add_member", chat_id=g, username="fay1")
ok("blocked: no link, clear error", not r.get("ok"), r)
print("%d passed, %d failed" % (sum(res), len(res) - sum(res))); sys.exit(0 if all(res) else 1)
