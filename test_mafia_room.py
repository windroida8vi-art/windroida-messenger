"""Mafia in a room over the real server: flow, privacy per connection, chat/mic gating, abuse. Run: python test_mafia_room.py"""
import os, sys, tempfile, time, queue
os.environ["WINDROIDA_MAFIA_NIGHT"] = "3"; os.environ["WINDROIDA_MAFIA_DAY"] = "3"; os.environ["WINDROIDA_MAFIA_VOTE"] = "3"
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
    v = [e for e in c.ev if e.get("event") == "room_mafia"]
    return v[-1]["mafia"] if v else "none"
def mf(c, a, **kw): return c.call("room_mafia", room=RID, a=a, **kw)

import base64
from common import encode_frame
def fire(c, obj):
    with c._send_lock: c.sock.sendall(encode_frame(obj))
PCM = base64.b64encode(b"\x01\x02" * 400).decode()
def heard(listener, n0):
    time.sleep(0.4); drain(listener); return len([e for e in listener.ev if e.get("event") == "room_audio"]) - n0
def audio_n(c): drain(c); return len([e for e in c.ev if e.get("event") == "room_audio"])

names = ["amir", "bahar", "cyrus", "dara", "elham", "farid"]
P = [cl(n) for n in names[:5]]; SP = cl("spectator"); OUT = cl("outsider")
r = P[0].call("room_open", title="تست"); ok("room opened", r["ok"], r); RID = r["room"]["id"]
for c in P[1:] + [SP]: ok(f"{c.uid} joins", c.call("room_join", room=RID)["ok"])
ok("outsider cannot use the room's mafia", not OUT.call("room_mafia", room=RID, a="open").get("ok") and not OUT.call("room_mafia", room=RID, a="get").get("ok"))
ok("no game yet", mf(P[0], "get")["mafia"] is None)
ok("bad action refused", not mf(P[0], "hack").get("ok") and not mf(P[0], None).get("ok") and not mf(P[0], {"a": 1}).get("ok"))
ok("action on missing game refused", not mf(P[0], "start").get("ok") and not mf(P[0], "night", target=1).get("ok"))
r = mf(P[0], "open"); ok("host opens a lobby and is in it", r["ok"] and r["mafia"]["phase"] == "lobby" and len(r["mafia"]["players"]) == 1, r)
time.sleep(0.2); drain(SP)
ok("spectator got the lobby live", last_view(SP) not in (None, "none") and last_view(SP)["phase"] == "lobby")
for c in P[1:4]: ok("join lobby", mf(c, "join")["ok"])
ok("start refused with 4 players", not mf(P[0], "start").get("ok"))
ok("non-host cannot start", not mf(P[2], "start").get("ok"))
ok("spectator can join the lobby too (then he is a player)", mf(SP, "join")["ok"])
ok("leave lobby works", mf(SP, "leave")["ok"] and len(mf(P[0], "get")["mafia"]["players"]) == 4)
ok("join twice is harmless", mf(P[1], "join")["ok"] and len(mf(P[0], "get")["mafia"]["players"]) == 4)
mf(P[4], "join")
ok("room chat works before the game", P[1].call("room_chat", room=RID, text="hello").get("ok"))
r = mf(P[0], "start"); ok("host starts with 5", r["ok"] and r["mafia"]["phase"] == "night", r)
time.sleep(0.2)
V = {c.uid: last_view(c) for c in P}; sv = last_view(SP)
roles = {u: v["me"]["role"] for u, v in V.items()}
ok("everybody got a role view", all(v not in (None, "none") and v["me"] for v in V.values()), V)
ok("roles: 1 mafia, 1 doctor, 1 detective, 2 citizens", sorted(roles.values()) == ["citizen", "citizen", "detective", "doctor", "mafia"], roles)
ok("spectator sees no role and no 'me'", sv["me"] is None and all(p["role"] is None for p in sv["players"]))
for c in P:
    v = V[c.uid]
    others_revealed = [p for p in v["players"] if p["role"] and p["id"] != c.uid]
    ok(f"player {c.uid} sees nobody else's role (night 1)", not others_revealed, others_revealed)
ok("night timer is sent as seconds left", 0 < V[P[0].uid]["left"] <= 3)
ok("joining after the start refused", not mf(SP, "join").get("ok"))
byid = {c.uid: c for c in P}
mafia = [u for u, r in roles.items() if r == "mafia"][0]; doc = [u for u, r in roles.items() if r == "doctor"][0]
det = [u for u, r in roles.items() if r == "detective"][0]; cits = [u for u, r in roles.items() if r == "citizen"]
# chat / mic gating
ok("players cannot chat at night", not byid[cits[0]].call("room_chat", room=RID, text="psst").get("ok"))
ok("spectator can still chat", SP.call("room_chat", room=RID, text="watching").get("ok"))
# voice (microphone) follows the same rules as chat
for c in P + [SP]: c.call("room_flags", room=RID, mic=True)
n0 = audio_n(SP); fire(byid[cits[0]], {"op": "room_audio", "room": RID, "d": PCM, "sr": 16000}); ok("a player's voice is dropped at night", heard(SP, n0) == 0)
n0 = audio_n(P[0]); fire(SP, {"op": "room_audio", "room": RID, "d": PCM, "sr": 16000}); ok("a spectator's voice still goes through", heard(P[0], n0) >= 1)
# whispers
ok("mafia whisper ok", mf(byid[mafia], "team", text="ببریمش").get("ok"))
ok("citizen whisper refused", not mf(byid[cits[0]], "team", text="x").get("ok"))
time.sleep(0.2)
ok("mafia sees his whisper, nobody else has team_chat", last_view(byid[mafia])["me"].get("team_chat") and all("team_chat" not in last_view(byid[u])["me"] for u in roles if u != mafia) and "ببریمش" not in repr(last_view(SP)))
# action validation
c = byid[cits[0]]
ok("citizen night action refused", not mf(c, "night", target=mafia).get("ok"))
for bad in (True, "3", 1.5, [1], {"x": 1}, -1, 10**30, None):
    ok(f"garbage target refused {bad!r}", not mf(byid[mafia], "night", target=bad).get("ok"))
ok("mafia cannot target himself/teammate", not mf(byid[mafia], "night", target=mafia).get("ok"))
ok("detective cannot check himself", not mf(byid[det], "night", target=det).get("ok"))
ok("ready/vote in the night refused", not mf(c, "ready").get("ok") and not mf(c, "vote", target=mafia).get("ok"))
victim = cits[0]
mf(byid[doc], "night", target=doc); mf(byid[det], "night", target=mafia)
v = mf(byid[mafia], "night", target=victim)["mafia"]
time.sleep(0.3)
V = {u: last_view(byid[u]) for u in roles}
ok("day started (everybody acted)", all(v["phase"] == "day" for v in V.values()), [v["phase"] for v in V.values()])
ok("victim dead, role revealed to everybody", all(next(p for p in v["players"] if p["id"] == victim)["role"] == "citizen" and not next(p for p in v["players"] if p["id"] == victim)["alive"] for v in V.values()))
ok("detective has the private answer, others none", V[det]["me"]["private"] and all(not V[u]["me"]["private"] for u in roles if u != det))
ok("log is public and has no secret roles for the living", "مافیا" not in "".join(x["text"] for x in V[cits[1]]["log"] if "نقش" not in x["text"] and "شروع" not in x["text"]))
n0 = audio_n(SP); fire(byid[cits[1]], {"op": "room_audio", "room": RID, "d": PCM, "sr": 16000}); ok("an alive player's voice works by day", heard(SP, n0) >= 1)
n0 = audio_n(SP); fire(byid[victim], {"op": "room_audio", "room": RID, "d": PCM, "sr": 16000}); ok("a dead player's voice is dropped", heard(SP, n0) == 0)
ok("alive player may chat by day", byid[cits[1]].call("room_chat", room=RID, text="who?").get("ok"))
ok("dead player cannot chat", not byid[victim].call("room_chat", room=RID, text="ghost").get("ok"))
ok("dead player cannot act/ready", not mf(byid[victim], "ready").get("ok"))
# everybody ready -> vote; vote the mafia out
for u in roles:
    if u != victim: mf(byid[u], "ready")
time.sleep(0.3)
ok("vote phase", last_view(byid[doc])["phase"] == "vote")
ok("self-vote refused", not mf(byid[doc], "vote", target=doc).get("ok"))
for u in roles:
    if u != victim: mf(byid[u], "vote", target=mafia if u != mafia else doc)
time.sleep(0.4)
V = {u: last_view(byid[u]) for u in roles}
ok("mafia voted out: citizens win, all roles revealed", all(v["phase"] == "over" and v["winner"] == "citizens" for v in V.values()) and all(p["role"] for p in V[doc]["players"]), V[doc]["phase"])
ok("spectator also sees the roles after the end", all(p["role"] for p in last_view(SP)["players"]))
n0 = audio_n(SP); fire(byid[victim], {"op": "room_audio", "room": RID, "d": PCM, "sr": 16000}); ok("after the end everybody may talk again", heard(SP, n0) >= 1)
ok("after the end everybody may chat again", byid[victim].call("room_chat", room=RID, text="gg").get("ok"))
ok("spectator cannot close a running/finished game he is not part of... but anybody may dismiss a finished one", mf(SP, "end")["ok"] and mf(P[0], "get")["mafia"] is None)

# ---------------------------------------------------------------- the clock advances by itself (ticker)
mf(P[0], "open")
for c in P[1:]: mf(c, "join")
mf(P[0], "start"); t0 = time.time()
while time.time() - t0 < 12 and last_view(P[0])["phase"] not in ("day",): time.sleep(0.3)
ok("a silent night ends by the clock", last_view(P[0])["phase"] == "day" and not any(not p["alive"] for p in last_view(P[0])["players"]))
while time.time() - t0 < 20 and last_view(P[0])["phase"] != "night": time.sleep(0.3)
ok("day and vote also end by the clock (round 2 night)", last_view(P[0])["phase"] == "night" and last_view(P[0])["round"] == 2)
# a player leaves the room mid game -> he dies; the end of game can be forced by the host
leaver = P[3]; r = leaver.call("room_leave", room=RID); ok("player leaves the room", r["ok"])
time.sleep(0.3); v = last_view(P[0])
ok("the leaver is dead, role shown", any(p["id"] == leaver.uid and not p["alive"] and p["role"] for p in v["players"]), v["players"])
ok("a normal player cannot end a running game", not mf(P[2], "end").get("ok") and mf(P[0], "get")["mafia"] is not None)
ok("host ends the game", mf(P[0], "end")["ok"] and mf(P[0], "get")["mafia"] is None)
time.sleep(0.2)
ok("members were told the game is gone", last_view(P[1]) is None)

# ---------------------------------------------------------------- abuse
for i in range(80): P[1].call("room_mafia", room=RID, a="get")
r = P[1].call("room_mafia", room=RID, a="get"); ok("flooding is rate-limited", not r.get("ok"))
ok("unknown room refused", not P[0].call("room_mafia", room="nope", a="open").get("ok") and not P[0].call("room_mafia", room=None, a="open").get("ok"))

print(f"\n{sum(res)} passed, {len(res) - sum(res)} failed"); sys.exit(0 if all(res) else 1)
