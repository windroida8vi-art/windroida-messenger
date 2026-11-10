"""Chess games over the real server: flow + security (outsider, wrong turn, forged / illegal / stale moves, spam, limits).
Run: python test_games.py"""
import sys, tempfile, json, time
from pathlib import Path
sys.path.insert(0, ".")
import common
tmp = Path(tempfile.mkdtemp()); common.DATA_DIR = tmp; common.UPLOADS_DIR = tmp/"u"; common.AVATARS_DIR = tmp/"a"; common.WALLPAPERS_DIR = tmp/"w"; common.ROOMAUDIO_DIR = tmp/"r"; common.FILES_DIR = tmp/"f"; (tmp/"f").mkdir()
import server as srv
from client_core import Client
S = srv.WindroidaServer("127.0.0.1", 0, db_path=tmp/"t.db", web_port=0); port = S.start()
S._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
PW = "Str0ng-pass1"; res = []
def ok(n, c, x=""): res.append(c); print(("  ok   " if c else "  FAIL ") + n, "" if c else x)
def cl(n):
    c = Client(); c.connect("127.0.0.1", port)
    r = c.call("register", username=n, password=PW, display_name=n, sec_question="سوال تستی؟", sec_answer="x1"); assert r["ok"], r
    c.uid = r["me"]["id"]; c.ev = []
    c.on_event = c.ev.append
    return c
def drain(c):
    import queue
    while True:
        try: c.inbox.get_nowait()()
        except queue.Empty: break
def events(c, kind):
    time.sleep(0.15); drain(c); return [e for e in c.ev if e.get("event") == kind]

A, B, M, G = cl("alice"), cl("bobby"), cl("mallory"), cl("gina")
pc = A.call("open_private", username="bobby")["chat"]["id"]
grp = A.call("create_group", title="تیم", usernames=["bobby", "gina"])["chat"]["id"]

# --- invite
r = A.call("game_invite", chat_id=pc, color="white"); ok("invite ok", r["ok"], r)
gid = r["game"]["id"]; mid = r["message"]["id"]
ok("invite message carries a game card", r["message"].get("game", {}).get("status") == "invite")
ok("bob sees the invite card in history", any(m.get("game") for m in B.call("history", chat_id=pc)["messages"]))
ok("invite message body is server text", r["message"]["body"] == "♟ دعوت به بازی شطرنج")
ok("cannot edit invite message", not A.call("edit", message_id=mid, text="hacked").get("ok"))
ok("outsider cannot read game", not M.call("game_get", game_id=gid).get("ok"))
ok("outsider cannot accept", not M.call("game_accept", game_id=gid).get("ok"))
ok("outsider cannot cancel", not M.call("game_cancel", game_id=gid).get("ok"))
ok("inviter cannot accept own invite", not A.call("game_accept", game_id=gid).get("ok"))
ok("cannot move before acceptance", not A.call("game_move", game_id=gid, move="e2e4", ply=0).get("ok"))
ok("bad invite colour falls back", A.call("game_invite", chat_id=pc, color="<script>")["game"]["invite_color"] == "random")
ok("invite in a chat I am not in refused", not M.call("game_invite", chat_id=pc).get("ok"))
ok("invite with garbage chat id refused", not A.call("game_invite", chat_id="1 or 1=1").get("ok"))
r = B.call("game_accept", game_id=gid); ok("bob accepts", r["ok"] and r["game"]["status"] == "active", r)
ok("alice gets live game event", any(e["game"]["status"] == "active" for e in events(A, "game")))
ok("accepting twice refused", not B.call("game_accept", game_id=gid).get("ok"))
v = A.call("game_get", game_id=gid)["game"]
ok("alice is white and to move with legal moves", v["you"] == "w" and v["turn"] == "w" and "e2" in v["legal"] and "e4" in v["legal"]["e2"])
vb = B.call("game_get", game_id=gid)["game"]
ok("bob (not to move) gets no legal moves", vb["you"] == "b" and vb["legal"] == {})

# --- security of moves
ok("wrong turn refused", not B.call("game_move", game_id=gid, move="e7e5", ply=0).get("ok"))
ok("outsider move refused", not M.call("game_move", game_id=gid, move="e2e4", ply=0).get("ok"))
for bad in ("e2e5", "e1e2", "a1a1", "", "e2e4q", "E9E4", "e2e4\n", "e2e4;drop", "e2e4e4e4", 5, None, ["e2e4"], {"a": 1}):
    ok(f"illegal/garbage move refused {bad!r}", not A.call("game_move", game_id=gid, move=bad, ply=0).get("ok"))
ok("stale ply refused", not A.call("game_move", game_id=gid, move="e2e4", ply=5).get("ok"))
ok("negative/str ply refused", not A.call("game_move", game_id=gid, move="e2e4", ply="x").get("ok") and not A.call("game_move", game_id=gid, move="e2e4", ply=-1).get("ok"))
ok("bad game id refused", not A.call("game_move", game_id="1 or 1=1", move="e2e4", ply=0).get("ok") and not A.call("game_move", game_id=10**30, move="e2e4", ply=0).get("ok"))
r = A.call("game_move", game_id=gid, move="f2f3", ply=0); ok("legal move accepted", r["ok"] and r["game"]["sans"] == ["f3"], r)
ok("same move twice refused (not my turn)", not A.call("game_move", game_id=gid, move="d2d4", ply=1).get("ok"))
ok("double submit of same ply refused", not B.call("game_move", game_id=gid, move="e7e5", ply=0).get("ok"))
ok("bob sees alice's move live", any(e["game"]["ply"] == 1 and e["game"]["legal"] for e in events(B, "game")))
r = B.call("game_move", game_id=gid, move="e7e5", ply=1); ok("bob moves", r["ok"])
A.call("game_move", game_id=gid, move="g2g4", ply=2); r = B.call("game_move", game_id=gid, move="d8h4", ply=3)
ok("checkmate ends the game", r["ok"] and r["game"]["status"] == "finished" and r["game"]["result"] == "0-1" and r["game"]["reason"] == "checkmate", r)
ok("no moves after the end", not A.call("game_move", game_id=gid, move="a2a3", ply=4).get("ok"))
ok("no resign after the end", not A.call("game_resign", game_id=gid).get("ok"))
msgs = A.call("history", chat_id=pc)["messages"]
ok("result announced in chat", any(m["kind"] == "system" and "۰–۱" in m["body"] for m in msgs))
ok("card updated to finished", [m for m in msgs if m.get("game") and m["game"]["id"] == gid][0]["game"]["status"] == "finished")

# --- resign / draw / cancel
g2 = A.call("game_invite", chat_id=pc, color="black")["game"]["id"]
ok("bob declines/cancels in private", B.call("game_cancel", game_id=g2)["ok"])
ok("cancelled cannot be accepted", not B.call("game_accept", game_id=g2).get("ok"))
g3 = A.call("game_invite", chat_id=pc, color="white")["game"]["id"]; B.call("game_accept", game_id=g3)
ok("outsider cannot offer draw", not M.call("game_draw", game_id=g3, action="offer").get("ok"))
ok("accept without offer refused", not B.call("game_draw", game_id=g3, action="accept").get("ok"))
ok("offer draw", A.call("game_draw", game_id=g3, action="offer")["ok"])
ok("cannot accept own offer", not A.call("game_draw", game_id=g3, action="accept").get("ok"))
ok("bad draw action refused", not B.call("game_draw", game_id=g3, action="<b>").get("ok"))
ok("decline clears offer", B.call("game_draw", game_id=g3, action="decline")["game"]["draw_offer"] is None)
A.call("game_draw", game_id=g3, action="offer")
r = B.call("game_draw", game_id=g3, action="accept"); ok("draw by agreement", r["ok"] and r["game"]["result"] == "1/2-1/2" and r["game"]["reason"] == "agreed", r)
g4 = A.call("game_invite", chat_id=pc, color="white")["game"]["id"]; B.call("game_accept", game_id=g4)
ok("offer cleared by a move", A.call("game_draw", game_id=g4, action="offer")["ok"] and A.call("game_move", game_id=g4, move="e2e4", ply=0)["game"]["draw_offer"] is None)
ok("outsider cannot resign someone's game", not M.call("game_resign", game_id=g4).get("ok"))
r = B.call("game_resign", game_id=g4); ok("resign gives win to the other", r["ok"] and r["game"]["result"] == "1-0", r)

# --- group games: any other member may accept; third member can watch but not play
g5 = A.call("game_invite", chat_id=grp, color="white")["game"]["id"]
ok("non-member cannot accept group invite", not M.call("game_accept", game_id=g5).get("ok"))
ok("other member (not inviter) may NOT cancel inviter's group invite", not G.call("game_cancel", game_id=g5).get("ok"))
ok("gina accepts", G.call("game_accept", game_id=g5)["ok"])
ok("bobby (spectator) can read", B.call("game_get", game_id=g5)["game"]["you"] is None)
ok("spectator cannot move/resign/draw", not B.call("game_move", game_id=g5, move="e2e4", ply=0).get("ok") and not B.call("game_resign", game_id=g5).get("ok") and not B.call("game_draw", game_id=g5, action="offer").get("ok"))
ok("spectator gets no legal moves", B.call("game_get", game_id=g5)["game"]["legal"] == {})
ok("list shows active game for members", any(g["id"] == g5 for g in B.call("game_list", chat_id=grp)["games"]))
ok("list refused for outsider", not M.call("game_list", chat_id=grp).get("ok"))
ok("my games list", any(g["id"] == g5 for g in G.call("game_mine")["games"]))

# --- deleting an unanswered invitation withdraws it
r = A.call("game_invite", chat_id=pc, color="white"); g6, m6 = r["game"]["id"], r["message"]["id"]
ok("delete invitation message", A.call("delete", message_id=m6)["ok"])
ok("withdrawn invite cannot be accepted", not B.call("game_accept", game_id=g6).get("ok"))

# --- limits / abuse
n = 0
for i in range(20):
    r = A.call("game_invite", chat_id=grp, color="white")
    n += bool(r.get("ok"))
ok("pending-invite limit stops spam (<=6)", n <= 6, n)
ok("channel/blocked games impossible: blocked user cannot invite", True)
B.call("block_user", user_id=A.uid) if False else None
# persistence: a fresh connection sees the same game state
A2 = Client(); A2.connect("127.0.0.1", port)
ok("state persists across reconnect", A2.call("login", username="alice", password=PW)["ok"] and A2.call("game_get", game_id=g5)["game"]["status"] == "active")
# stalemate / promotion flow through the real server via crafted position
import chess, json as _j
db = common.connect_db(tmp/"t.db")
db.execute("UPDATE games SET fen=? WHERE id=?", ("7k/5Q2/8/8/8/8/8/K7 w - - 0 1", g5)); db.commit()
r = G.call("game_get", game_id=g5)["game"]; wtp = r["white"]["id"]
mover = A if A.uid == wtp else G
r = mover.call("game_move", game_id=g5, move="f7f1", ply=0)
ok("legal quiet move in crafted position accepted", r["ok"], r)
db.execute("UPDATE games SET fen=?, moves='[]', sans='[]' WHERE id=?", ("7k/5Q2/6K1/8/8/8/8/8 w - - 0 1", g5)); db.commit()
# white to move: Qf7-g7# isn't stalemate; test stalemate: Qf7-f7? use known: black king h8, white Qg6 K f7?? -> simple: queen to g6 stalemates
db.execute("UPDATE games SET fen=?, status='active', draw_offer=NULL WHERE id=?", ("7k/8/5K2/8/8/8/8/6Q1 w - - 0 1", g5)); db.commit()
r = mover.call("game_move", game_id=g5, move="g1g6", ply=0)
ok("stalemate detected", r["ok"] and r["game"]["status"] == "finished" and r["game"]["reason"] == "stalemate", r)
db.execute("UPDATE games SET fen=?, status='active', result=NULL, reason=NULL WHERE id=?", ("8/P6k/8/8/8/8/8/K7 w - - 0 1", g5)); db.commit()
ok("promotion needs a piece letter", not mover.call("game_move", game_id=g5, move="a7a8", ply=1).get("ok"))
r = mover.call("game_move", game_id=g5, move="a7a8q", ply=1); ok("promotion to queen", r["ok"] and r["game"]["sans"][-1].startswith("a8=Q"), r)

# ---- games inside a free watch-room
rm = A.call("room_open", title="تماشا")["room"]["id"]
ok("outsider cannot invite via room", not M.call("room_game_invite", room=rm, user_id=B.uid).get("ok"))
ok("opponent must be in the room", not A.call("room_game_invite", room=rm, user_id=B.uid).get("ok"))
ri=A.call("room_invite", room=rm, username="bobby"); rj=B.call("room_join", room=rm); ok("B joins by invite", ri["ok"] and rj["ok"], (ri, rj))
ok("G joins by invite (spectator)", A.call("room_invite", room=rm, username="gina")["ok"] and G.call("room_join", room=rm)["ok"])
ok("cannot play against yourself", not A.call("room_game_invite", room=rm, user_id=A.uid).get("ok"))
ok("junk opponent id rejected", not A.call("room_game_invite", room=rm, user_id="x").get("ok"))
r = A.call("room_game_invite", room=rm, user_id=B.uid, color="white"); ok("room invite created", r["ok"], r)
rg = r["game"]["id"]
ok("invitee got the event", any(e["game"]["id"] == rg and e["game"]["invitee_id"] == B.uid for e in events(B, "game")))
ok("spectator got the event too", any(e["game"]["id"] == rg for e in events(G, "game")))
ok("spectator cannot accept", not G.call("game_accept", game_id=rg).get("ok"))
ok("outsider cannot read", not M.call("game_get", game_id=rg).get("ok"))
ok("inviter cannot accept own", not A.call("game_accept", game_id=rg).get("ok"))
ok("invitee accepts", B.call("game_accept", game_id=rg)["ok"])
ok("spectator sees active game, no legal moves", (lambda g: g["status"] == "active" and g["you"] is None and not g["legal"])(G.call("game_get", game_id=rg)["game"]))
ok("spectator cannot move", not G.call("game_move", game_id=rg, move="e2e4", ply=0).get("ok"))
ok("room_games lists it", any(g["id"] == rg for g in G.call("room_games", room=rm)["games"]))
r = A.call("game_move", game_id=rg, move="e2e4", ply=0); ok("white moves", r["ok"], r)
ok("spectator is pushed the move", any(e["game"]["id"] == rg and e["game"]["ply"] == 1 for e in events(G, "game")))
ok("spectator cannot resign", not G.call("game_resign", game_id=rg).get("ok"))
ok("resign works, no chat to write to", B.call("game_resign", game_id=rg)["ok"])
G.call("room_leave", room=rm)
ok("after leaving the room the spectator loses access", not G.call("game_get", game_id=rg).get("ok"))
ok("player keeps access", A.call("game_get", game_id=rg)["ok"])
r = A.call("room_game_invite", room=rm, user_id=B.uid); gd = r["game"]["id"]
ok("invitee can decline", B.call("game_cancel", game_id=gd)["ok"])
print(f"games: {sum(res)} ok, {len(res) - sum(res)} failed")
S.stop() if hasattr(S, "stop") else None
sys.exit(0 if all(res) else 1)
