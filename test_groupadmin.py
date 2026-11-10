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

O, AD, M1, M2, X = cl("owner1"), cl("admin1"), cl("member1"), cl("member2"), cl("stranger")
g = O.call("create_group", title="گروه", usernames=["admin1", "member1", "member2"])["chat"]["id"]
ok("make admin1 admin", O.call("set_role", chat_id=g, user_id=AD.uid, admin=True)["ok"])
priv = O.call("open_private", username="member1")["chat"]["id"]

# ------------------------------------------------------------------ silence
ok("member cannot mute", not M1.call("mute_member", chat_id=g, user_id=M2.uid, secs=3600).get("ok"))
ok("stranger cannot mute", not X.call("mute_member", chat_id=g, user_id=M2.uid, secs=3600).get("ok"))
ok("cannot moderate a private chat", not O.call("mute_member", chat_id=priv, user_id=M1.uid, secs=3600).get("ok"))
ok("announcement channel is not moderated", not O.call("set_slow", chat_id=db("SELECT id FROM chats WHERE channel=1")[0]["id"], secs=10).get("ok"))
for bad in (True, "3600", 5, -5, 1.5, None, [3600], 10**12):
    ok(f"garbage duration refused {bad!r}", not AD.call("mute_member", chat_id=g, user_id=M1.uid, secs=bad).get("ok"))
for bad in (True, "2", 0, -1, None, [1], 1.5, 10**20):
    ok(f"garbage user id refused {bad!r}", not AD.call("mute_member", chat_id=g, user_id=bad, secs=3600).get("ok"))
ok("cannot mute yourself", not AD.call("mute_member", chat_id=g, user_id=AD.uid, secs=3600).get("ok"))
ok("admin cannot mute the owner", not AD.call("mute_member", chat_id=g, user_id=O.uid, secs=3600).get("ok"))
ok("owner cannot mute an admin (he is exempt)", not O.call("mute_member", chat_id=g, user_id=AD.uid, secs=3600).get("ok"))
ok("cannot mute a non-member", not AD.call("mute_member", chat_id=g, user_id=X.uid, secs=3600).get("ok"))
ok("member1 can talk before the mute", say(M1, g)["ok"])
r = AD.call("mute_member", chat_id=g, user_id=M1.uid, secs=3600); ok("admin mutes member1 for 1 h", r["ok"] and r["muted_until"] > time.time() + 3500, r)
ok("member1 cannot send text", not say(M1, g).get("ok"))
r = say(M1, g); ok("refusal explains why", "ساکت" in r.get("error", ""), r)
mid = say(M2, g, "x")["message"]["id"]
ok("member1 cannot reply", not M1.call("send", chat_id=g, text="r", reply_to=mid).get("ok"))
ok("member1 cannot forward into the group", not M1.call("forward", message_id=mid, chat_ids=[g]).get("ok"))
ok("member1 can still talk in other chats", say(M1, priv)["ok"])
ok("member1 can still read / react", M1.call("history", chat_id=g)["ok"] and M1.call("react", message_id=mid, emoji="👍").get("ok"))
cv = M1.call("chats")["chats"]; v = next(c for c in cv if c["id"] == g)
ok("chat view tells member1 he is silenced", v["my_muted_until"] > time.time() and v["slow"] == 0, v)
vo = next(c for c in O.call("chats")["chats"] if c["id"] == g); ok("owner's view has no silence", vo["my_muted_until"] == 0)
mem = {m["id"]: m for m in O.call("members", chat_id=g)["members"]}
ok("members list shows who is silenced", mem[M1.uid]["muted_until"] > time.time() and mem[M2.uid]["muted_until"] == 0)
ok("others got a system message", any("ساکت شد" in (e["message"].get("body") or "") for e in evs(M2, "message")))
# leave & rejoin does not help
tok = O.call("invite_link", chat_id=g)["invite"]
ok("member1 leaves", M1.call("leave", chat_id=g)["ok"])
ok("member1 rejoins by link", M1.call("join", token=tok)["ok"])
ok("silence survived leave + rejoin", not say(M1, g).get("ok"))
# a second session / device is also blocked
M1b = second_session("member1"); ok("a second device is blocked too", not say(M1b, g).get("ok"))
# expiry
db("UPDATE group_limits SET muted_until=? WHERE chat_id=? AND user_id=?", int(time.time()) - 1, g, M1.uid)
ok("after the time is over he can talk again", say(M1, g)["ok"])
ok("view clears", next(c for c in M1.call("chats")["chats"] if c["id"] == g)["my_muted_until"] == 0)
ok("mute forever", AD.call("mute_member", chat_id=g, user_id=M1.uid, secs=-1)["ok"] and not say(M1, g).get("ok"))
ok("forever message", "ساکت کرده" in say(M1, g).get("error", ""))
ok("owner lifts the silence (secs=0)", O.call("mute_member", chat_id=g, user_id=M1.uid, secs=0)["ok"] and say(M1, g)["ok"])
AD.call("mute_member", chat_id=g, user_id=M1.uid, secs=3600); O.call("set_role", chat_id=g, user_id=M1.uid, admin=True)
ok("an admin is never restricted (even with an old silence)", say(M1, g)["ok"])
O.call("set_role", chat_id=g, user_id=M1.uid, admin=False)
ok("demoted: the old silence applies again", not say(M1, g).get("ok"))
O.call("mute_member", chat_id=g, user_id=M1.uid, secs=0)

# ------------------------------------------------------------------ slow mode
ok("member cannot set slow mode", not M2.call("set_slow", chat_id=g, secs=30).get("ok"))
for bad in (True, "30", 7, -1, 1.5, None, [30], 10**9):
    ok(f"garbage slow value refused {bad!r}", not AD.call("set_slow", chat_id=g, secs=bad).get("ok"))
r = AD.call("set_slow", chat_id=g, secs=30); ok("admin turns slow mode on (30 s)", r["ok"] and r["slow"] == 30)
ok("chat view carries slow mode", next(c for c in M2.call("chats")["chats"] if c["id"] == g)["slow"] == 30)
ok("members got the system message", any("حالت آهسته" in (e["message"].get("body") or "") for e in evs(M1, "message")))
ok("first message passes", say(M2, g, "one")["ok"])
r = say(M2, g, "two"); ok("second message refused with the remaining seconds", not r.get("ok") and "ثانیه" in r.get("error", ""), r)
ok("forward is slowed too", not M2.call("forward", message_id=mid, chat_ids=[g]).get("ok"))
ok("chess invite is slowed too", not M2.call("game_invite", chat_id=g).get("ok"))
priv2 = M2.call("open_private", username="owner1")["chat"]["id"]
ok("other chats are not slowed", say(M2, priv2)["ok"] and say(M2, priv2)["ok"])
ok("owner and admin are exempt", all(say(c, g)["ok"] for c in (O, AD, O, AD)))
ok("a second device of the same user is blocked too", not say(second_session("member2"), g).get("ok"))
M2.call("leave", chat_id=g); M2.call("join", token=tok)
ok("leave + rejoin does not reset the clock", not say(M2, g).get("ok"))
db("UPDATE group_limits SET last_post=last_post-31 WHERE chat_id=? AND user_id=?", g, M2.uid)
ok("after 30 s he can send again", say(M2, g, "three")["ok"])
# atomic: two sessions of one user firing at once -> exactly one passes
db("UPDATE group_limits SET last_post=last_post-31 WHERE chat_id=? AND user_id=?", g, M2.uid)
M2b = second_session("member2"); out = []
def fire(c): out.append(say(c, g, "race").get("ok"))
ths = [threading.Thread(target=fire, args=(c,)) for c in (M2, M2b, M2, M2b, M2, M2b)]
[t.start() for t in ths]; [t.join() for t in ths]
ok("parallel sends: exactly one passes the slow-mode clock", out.count(True) == 1, out)
ok("a refused message left no trace", len([m for m in M2.call("history", chat_id=g, limit=100)["messages"] if m.get("body") == "race"]) == 1)
ok("slow mode off again", AD.call("set_slow", chat_id=g, secs=0)["ok"] and say(M2, g, "a")["ok"] and say(M2, g, "b")["ok"])
ok("setting the same value again is harmless", AD.call("set_slow", chat_id=g, secs=0)["ok"])

# ------------------------------------------------------------------ ban
ok("member cannot ban", not M1.call("ban_member", chat_id=g, user_id=M2.uid).get("ok"))
ok("admin cannot ban the owner / another admin", not AD.call("ban_member", chat_id=g, user_id=O.uid).get("ok"))
O.call("set_role", chat_id=g, user_id=M2.uid, admin=True)
ok("admin cannot ban another admin", not AD.call("ban_member", chat_id=g, user_id=M2.uid).get("ok"))
ok("owner can ban an admin", O.call("ban_member", chat_id=g, user_id=M2.uid)["ok"])
ok("banned admin is out of the group", g not in [c["id"] for c in M2.call("chats")["chats"]] and any(e["chat_id"] == g for e in evs(M2, "chat_removed")))
ok("banned user cannot rejoin by link", not M2.call("join", token=tok).get("ok"))
ok("banned user cannot be added by an admin", not AD.call("add_member", chat_id=g, username="member2").get("ok"))
ok("banned user cannot read the group", not M2.call("history", chat_id=g).get("ok"))
ok("ban twice refused", not AD.call("ban_member", chat_id=g, user_id=M2.uid).get("ok"))
bans = AD.call("bans", chat_id=g)["bans"]; ok("ban list shows him", [b["username"] for b in bans] == ["member2"], bans)
ok("member cannot read the ban list", not M1.call("bans", chat_id=g).get("ok"))
ok("ban a stranger (not a member) in advance", AD.call("ban_member", chat_id=g, user_id=X.uid)["ok"] and not X.call("join", token=tok).get("ok"))
ok("unban garbage refused", not AD.call("unban_member", chat_id=g, user_id=987654).get("ok"))
r1 = AD.call("unban_member", chat_id=g, user_id=M2.uid); r2 = AD.call("unban_member", chat_id=g, user_id=X.uid)
ok("unban works", r1["ok"] and r2["ok"], (r1, r2))
r1 = M2.call("join", token=tok); r2 = X.call("join", token=tok)
ok("unbanned user can rejoin", r1["ok"] and r2["ok"], (r1, r2))
ok("ban of an unknown user id refused", not AD.call("ban_member", chat_id=g, user_id=999999).get("ok"))
O.call("edit_group", chat_id=g, username="grp_pub"); AD.call("ban_member", chat_id=g, user_id=X.uid)
ok("banned user cannot join by the public @id", not X.call("join", username="grp_pub").get("ok"))
ok("remove_member (kick) still lets him back by link", AD.call("unban_member", chat_id=g, user_id=X.uid)["ok"] and X.call("join", username="grp_pub")["ok"] and AD.call("remove_member", chat_id=g, user_id=X.uid)["ok"] and X.call("join", token=tok)["ok"])
# deleting others' messages (existing rule, re-checked)
mm = say(M1, g, "bad words")["message"]["id"]
ok("admin can delete a member's message", AD.call("delete", message_id=mm)["ok"])
ok("member cannot delete another member's message", not M1.call("delete", message_id=say(M2, g, "mine")["message"]["id"]).get("ok"))
# flood
for i in range(100): AD.call("bans", chat_id=g)
ok("moderation ops are rate-limited", not AD.call("bans", chat_id=g).get("ok"))
# deleting the group removes limits and bans
O.call("delete_group", chat_id=g)
ok("group deleted: limits and bans are gone", not db("SELECT 1 FROM group_limits WHERE chat_id=?", g) and not db("SELECT 1 FROM group_bans WHERE chat_id=?", g))

print(f"\n{sum(res)} passed, {len(res) - sum(res)} failed"); sys.exit(0 if all(res) else 1)
