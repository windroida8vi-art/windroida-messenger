"""Polls over the real server. Run: python test_polls.py"""
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
def drain(c):
    while True:
        try: c.inbox.get_nowait()()
        except queue.Empty: break
def evs(c, kind):
    time.sleep(0.15); drain(c); return [e for e in c.ev if e.get("event") == kind]
def db(sql, *a):
    d = sqlite3.connect(tmp/"t.db"); d.row_factory = sqlite3.Row
    try:
        with d: return d.execute(sql, a).fetchall()
    finally: d.close()

O, AD, A, B, X = cl("owner1"), cl("admin1"), cl("alice1"), cl("bobby1"), cl("stranger")
g = O.call("create_group", title="گروه", usernames=["admin1", "alice1", "bobby1"])["chat"]["id"]
O.call("set_role", chat_id=g, user_id=AD.uid, admin=True)
priv = A.call("open_private", username="bobby1")["chat"]["id"]
NORESET = False
def create(c, chat, q="بهترین رنگ؟", opts=("قرمز", "آبی", "سبز"), **kw):
    if not NORESET: S.ip_hits.pop(("room", "pollc", c.uid), None); S.ip_hits.pop(("room", "pollv", c.uid), None)
    return c.call("poll_create", chat_id=chat, question=q, options=list(opts), **kw)

# ------------------------------------------------------------------ create
r = create(A, g); ok("member creates a poll in a group", r["ok"], r)
m = r["message"]; p = m["poll"]; pid = p["id"]
ok("message is a normal message with a poll card", m["body"] == "📊 بهترین رنگ؟" and p["opts"] == ["قرمز", "آبی", "سبز"] and p["counts"] == [0, 0, 0] and p["voters"] == 0 and not p["multi"] and not p["anon"] and not p["closed"], m)
ok("others got it live", any(e["message"].get("poll") for e in evs(B, "message")))
ok("history carries the card", any(x.get("poll") and x["poll"]["id"] == pid for x in B.call("history", chat_id=g)["messages"]))
ok("poll in a private chat is refused (polls are for groups only)", not A.call("poll_create", chat_id=priv, question="ناهار؟", options=["پیتزا", "کباب"]).get("ok"))
for bad_q in ("", "   ", "\x00\x01", None, 5, ["x"], {"a": 1}, "q" * 201):
    ok(f"bad question refused {bad_q!r}"[:50], not create(A, g, q=bad_q).get("ok"))
_r = create(A, g, q="a\x00b\u202e c", opts=("x\x07y", "z")); ok("control characters are stripped from text", _r.get("ok") and _r["message"]["poll"]["q"] == "ab c", _r)
for bad_o in (["only"], [], list("abcdefghijk"), "abc", None, 5, {"a": 1}, ["a", ""], ["a", "  "], ["a", 5], ["a", None], ["a", "b" * 101], ["a", "A"], ["a", "a"]):
    ok(f"bad options refused {str(bad_o)[:30]!r}", not A.call("poll_create", chat_id=g, question="q", options=bad_o).get("ok"))
ok("exactly 10 options ok, 2 options ok", create(A, g, opts=[f"o{i}" for i in range(10)])["ok"] and create(A, g, opts=("a", "b"))["ok"])
for bad_f in ("yes", 2, [1], {"a": 1}, "1"):
    ok(f"garbage multi/anon flag refused {bad_f!r}", not create(A, g, multi=bad_f).get("ok") and not create(A, g, anon=bad_f).get("ok"))
ok("outsider cannot create", not create(X, g).get("ok"))
ok("garbage chat id refused", not create(A, "1 or 1=1").get("ok") and not create(A, None).get("ok"))

# ------------------------------------------------------------------ voting (single choice)
ok("alice votes red", A.call("poll_vote", poll_id=pid, options=[0])["ok"])
ok("bobby votes blue", B.call("poll_vote", poll_id=pid, options=[1])["ok"])
card = lambda c: next(x for x in c.call("history", chat_id=g, limit=100)["messages"] if x.get("poll") and x["poll"]["id"] == pid)["poll"]
ok("counts are right", card(O)["counts"] == [1, 1, 0] and card(O)["voters"] == 2)
ok("others get the live update", any(e["message"].get("poll", {}).get("counts") == [1, 1, 0] for e in evs(O, "message_updated")))
ok("poll_get tells each user his own vote", A.call("poll_get", poll_id=pid)["mine"] == [0] and B.call("poll_get", poll_id=pid)["mine"] == [1] and O.call("poll_get", poll_id=pid)["mine"] == [])
ok("changing the vote moves it", A.call("poll_vote", poll_id=pid, options=[2])["ok"] and card(O)["counts"] == [0, 1, 1])
ok("voting the same again changes nothing", A.call("poll_vote", poll_id=pid, options=[2])["ok"] and card(O)["counts"] == [0, 1, 1])
ok("withdraw with []", A.call("poll_vote", poll_id=pid, options=[])["ok"] and card(O)["counts"] == [0, 1, 0] and card(O)["voters"] == 1)
for bad in ([3], [-1], [True], ["0"], [1.5], [None], [0, 1], "0", 0, None, {"0": 1}, [0, 0], [[0]]):
    ok(f"bad vote refused {bad!r}", not A.call("poll_vote", poll_id=pid, options=bad).get("ok"))
ok("failed votes changed nothing", card(O)["counts"] == [0, 1, 0])
for bad in (True, "1", -1, 0, 10**30, None, [1], 1.5):
    ok(f"bad poll id refused {bad!r}", not A.call("poll_vote", poll_id=bad, options=[0]).get("ok") and not A.call("poll_get", poll_id=bad).get("ok"))
ok("outsider cannot vote / read / close", all(not X.call(op, poll_id=pid, **kw).get("ok") for op, kw in (("poll_vote", {"options": [0]}), ("poll_get", {}), ("poll_close", {}))))
ok("poll_get shows no voters for an unknown flag", "voters" not in A.call("poll_get", poll_id=pid))
# public voters
v = A.call("poll_get", poll_id=pid, voters=True)
ok("public poll: voter names per option", v["voters"] == {"1": ["bobby1"]}, v)
ok("the broadcast card never contains who voted", "bobby1" not in repr(card(O)) and "voters" in card(O) and isinstance(card(O)["voters"], int))

# ------------------------------------------------------------------ anonymous + multiple
r = create(A, g, q="چندتایی", opts=("a", "b", "c"), multi=True, anon=True); pid2 = r["message"]["poll"]["id"]
ok("multi + anon flags stored", r["message"]["poll"]["multi"] and r["message"]["poll"]["anon"])
ok("multiple choice accepted", B.call("poll_vote", poll_id=pid2, options=[0, 2])["ok"])
ok("anonymous poll never lists voters (even when asked)", "voters" not in B.call("poll_get", poll_id=pid2, voters=True) and "bobby1" not in repr(O.call("poll_get", poll_id=pid2, voters=True)))
ok("single-choice poll refuses two options", not B.call("poll_vote", poll_id=pid, options=[0, 1]).get("ok"))
ok("anonymous counts still visible", O.call("poll_get", poll_id=pid2)["poll"]["counts"] == [1, 0, 1])

# ------------------------------------------------------------------ closing
ok("plain member cannot close another's poll", not B.call("poll_close", poll_id=pid).get("ok"))
ok("group admin can close", AD.call("poll_close", poll_id=pid)["message"]["poll"]["closed"])
ok("closed: vote refused", not B.call("poll_vote", poll_id=pid, options=[0]).get("ok") and not B.call("poll_vote", poll_id=pid, options=[]).get("ok"))
ok("closed: results stay", card(O)["counts"] == [0, 1, 0] and card(O)["closed"])
ok("closing twice refused", not AD.call("poll_close", poll_id=pid).get("ok"))
ok("everybody got the 'closed' update", any(e["message"].get("poll", {}).get("closed") for e in evs(B, "message_updated")))
ok("creator can close his own", A.call("poll_close", poll_id=pid2)["ok"])

# ------------------------------------------------------------------ misc rules
r = create(A, g, q="حذفی"); pd = r["message"]["poll"]["id"]
ok("poll message cannot be edited", not A.call("edit", message_id=r["message"]["id"], text="hacked").get("ok"))
ok("poll message cannot be forwarded", not B.call("forward", message_id=r["message"]["id"], chat_ids=[priv]).get("ok"))
ok("creator deletes the message", A.call("delete", message_id=r["message"]["id"])["ok"])
ok("deleted poll takes no votes and is not readable", not B.call("poll_vote", poll_id=pd, options=[0]).get("ok") and not B.call("poll_get", poll_id=pd).get("ok") and not A.call("poll_close", poll_id=pd).get("ok"))
r = create(A, g, q="ترک"); pl = r["message"]["poll"]["id"]
B.call("leave", chat_id=g)
ok("somebody who left cannot vote", not B.call("poll_vote", poll_id=pl, options=[0]).get("ok") and not B.call("poll_get", poll_id=pl).get("ok"))
B.call("join", token=O.call("invite_link", chat_id=g)["invite"])
ok("silenced member cannot create a poll but can vote", O.call("mute_member", chat_id=g, user_id=B.uid, secs=3600)["ok"] and not create(B, g).get("ok") and B.call("poll_vote", poll_id=pl, options=[0])["ok"])
O.call("mute_member", chat_id=g, user_id=B.uid, secs=0)
O.call("set_slow", chat_id=g, secs=60); create(B, g, q="یک")
ok("slow mode applies to polls", not create(B, g, q="دو").get("ok"))
O.call("set_slow", chat_id=g, secs=0)
ok("announcement channel: a normal user cannot post a poll", not create(A, db("SELECT id FROM chats WHERE channel=1")[0]["id"]).get("ok"))
# race: the same user voting from many threads leaves exactly one row on a single-choice poll
rp = create(A, g, q="مسابقه", opts=("a", "b", "c", "d"))["message"]["poll"]["id"]
B2 = Client(); B2.connect("127.0.0.1", port); B2.call("login", username="bobby1", password=PW)
ths = [threading.Thread(target=lambda c=c, i=i: c.call("poll_vote", poll_id=rp, options=[i % 4])) for i, c in enumerate([B, B2] * 8)]
[t.start() for t in ths]; [t.join() for t in ths]
ok("parallel votes of one user: exactly one vote", len(db("SELECT * FROM poll_votes WHERE poll_id=? AND user_id=?", rp, B.uid)) == 1)
ok("poll rows are removed with the group", O.call("delete_group", chat_id=g)["ok"] and not db("SELECT 1 FROM polls WHERE chat_id=?", g) and not db("SELECT 1 FROM poll_votes WHERE poll_id=?", pid))
# flood
NORESET = True; S.ip_hits.pop(("room", "pollc", A.uid), None)
for i in range(15): A.call("poll_create", chat_id=g, question="f", options=["a", "b"])
ok("creating polls is rate-limited", not A.call("poll_create", chat_id=g, question="f", options=["a", "b"]).get("ok"))
print(f"\n{sum(res)} passed, {len(res) - sum(res)} failed"); sys.exit(0 if all(res) else 1)
