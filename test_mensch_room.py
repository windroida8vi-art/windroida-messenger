"""Mensch in a room over the real server: lobby, a whole game through the sockets, live views, leaving, abuse. Run: python test_mensch_room.py"""
import os, sys, tempfile, time, queue, random
os.environ["WINDROIDA_MENSCH_TURN"] = "2"
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
def last_view(c):
    time.sleep(0.05); drain(c)
    v = [e for e in c.ev if e.get("event") == "room_mensch"]
    return v[-1]["mensch"] if v else "none"
def mn(c, a, **kw): return c.call("room_mensch", room=RID, a=a, **kw)

P = [cl(n) for n in ("amir", "bahar", "cyrus")]; SP = cl("spectator"); OUT = cl("outsider")
r = P[0].call("room_open", title="تست"); ok("room opened", r["ok"], r); RID = r["room"]["id"]
for c in P[1:] + [SP]: ok("joins room", c.call("room_join", room=RID)["ok"])
ok("outsider locked out", not OUT.call("room_mensch", room=RID, a="open").get("ok") and not OUT.call("room_mensch", room=RID, a="get").get("ok"))
ok("no game yet", mn(P[0], "get")["mensch"] is None)
ok("bad actions refused", not mn(P[0], "hack").get("ok") and not mn(P[0], None).get("ok") and not mn(P[0], {"a": 1}).get("ok"))
ok("actions without game refused", not mn(P[0], "start").get("ok") and not mn(P[0], "roll").get("ok") and not mn(P[0], "move", pawn=0).get("ok"))
r = mn(P[0], "open"); ok("host opens lobby", r["ok"] and r["mensch"]["phase"] == "lobby" and len(r["mensch"]["players"]) == 1, r)
time.sleep(0.2); drain(SP)
ok("spectator sees the lobby live", last_view(SP) not in (None, "none") and last_view(SP)["phase"] == "lobby")
ok("start with one refused", not mn(P[0], "start").get("ok"))
mn(P[1], "join"); ok("second joins", len(mn(P[0], "get")["mensch"]["players"]) == 2)
ok("non-host cannot start", not mn(P[1], "start").get("ok"))
ok("join twice harmless", mn(P[1], "join")["ok"] and len(mn(P[0], "get")["mensch"]["players"]) == 2)
ok("spectator joins then leaves lobby", mn(SP, "join")["ok"] and mn(SP, "leave")["ok"] and len(mn(P[0], "get")["mensch"]["players"]) == 2)
mn(P[2], "join")
r = mn(P[0], "start"); ok("start with 3", r["ok"] and r["mensch"]["phase"] == "play", r)
ok("join after start refused", not mn(SP, "join").get("ok"))
time.sleep(0.2)
by = {c.uid: c for c in P}
v = last_view(P[0]); ok("everybody got the view", all(last_view(c)["phase"] == "play" for c in P) and last_view(SP)["phase"] == "play")
ok("spectator has no seat", last_view(SP)["me"] is None)
# abuse
cur = by[v["turn"]]; other = [c for c in P if c is not cur][0]
ok("not your turn refused", not mn(other, "roll").get("ok"))
ok("move before roll refused", not mn(cur, "move", pawn=0).get("ok"))
ok("spectator cannot roll", not mn(SP, "roll").get("ok"))
for bad in (True, "0", 1.5, [0], {"a": 1}, 99, -1):
    ok(f"bad pawn {bad!r} refused", not mn(cur, "move", pawn=bad).get("ok"))
ok("end by non-host refused", not mn(P[2], "end").get("ok"))
# play the game through the sockets: always do the legal thing, 30 s guard
t0 = time.time(); steps = 0
def unthrottle():
    for k in [k for k in list(S.ip_hits) if isinstance(k, tuple) and (k[:2] == ("room", "mensch") or k[0] == "op")]: S.ip_hits.pop(k, None)
while time.time() - t0 < 60:
    unthrottle()
    rr = mn(P[0], "get")
    if "mensch" not in rr: print("GET FAIL", rr); break
    g = rr["mensch"]
    if g["phase"] != "play": break
    c = by[g["turn"]]
    if g["stage"] == "roll": r = mn(c, "roll")
    else: r = mn(c, "move", pawn=random.choice(g["legal"]))
    ok_ = r.get("ok") or "نوبت" in str(r.get("error", "")) or True
    steps += 1
    if steps > 6000: break
g = mn(P[0], "get")["mensch"]
ok("a whole game finished over the sockets", g["phase"] == "over" and g["winner"] in by, (g["phase"], steps))
ok("winner has all pawns home", g["phase"] == "over" and all(p == 56 for pl in g["players"] if pl["id"] == g["winner"] for p in pl["pawns"]))
time.sleep(0.2); ok("spectator saw the end", last_view(SP)["phase"] == "over")
unthrottle()
ok("end after over: any player", mn(P[2], "end")["ok"] and mn(P[0], "get")["mensch"] is None)

# a second game: timers play for sleepers, leaving
mn(P[0], "open"); mn(P[1], "join"); mn(P[0], "start")
g = mn(P[0], "get")["mensch"]
t0 = time.time(); n0 = len([e for e in P[0].ev if e.get("event") == "room_mensch"])
time.sleep(2.8); drain(P[0])
n1 = len([e for e in P[0].ev if e.get("event") == "room_mensch"])
ok("ticker advances sleeping turns by itself (events arrive)", n1 > n0, (n0, n1))
r = P[1].call("room_leave", room=RID); ok("player leaves the room", r["ok"], r)
time.sleep(0.4); g = mn(P[0], "get")["mensch"]
ok("leaver leaves a 2-player game: other wins", g["phase"] == "over" and g["winner"] == P[0].uid, g)
mn(P[0], "end")
# rate limit
unthrottle(); bad = 0
for _ in range(80):
    r = mn(P[0], "get")
    if not r.get("ok"): bad += 1
ok("rate limit kicks in on floods", bad > 0)

print(f"\n{sum(res)}/{len(res)} passed"); S.stop() if hasattr(S, "stop") else None; os._exit(0 if all(res) else 1)
