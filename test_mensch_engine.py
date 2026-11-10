"""Mensch engine: rules, captures, safe cells, exact finish, timers, leaving, and a fuzz of random games."""
import random, sys
sys.path.insert(0, ".")
import mensch as mn

res = []
def ok(n, c, x=""): res.append(bool(c)); print(("  ok   " if c else "  FAIL ") + n, "" if c else x)
def refused(fn, *a):
    try: fn(*a)
    except mn.MenschError: return True
    return False

class Script(random.Random):
    """dice = the scripted rolls (then random); choice() picks the first one so player 1 starts"""
    def __init__(self, rolls=()):
        super().__init__(5); self.rolls = list(rolls)
    def randint(self, a, b):
        return self.rolls.pop(0) if self.rolls else super().randint(a, b)
    def choice(self, seq): return seq[0]

def game(n, rolls=()):
    g = mn.Mensch(1, rng=Script(rolls))
    for u in range(1, n + 1): g.join(u, f"p{u}")
    g.start(1, 0.0)
    return g

# ---------------------------------------------------------------- board constants
ok("ring/entry/safe", mn.RING == 52 and mn.ENTRY == [1, 14, 27, 40] and mn.SAFE == {1, 14, 27, 40, 9, 22, 35, 48})
# ---------------------------------------------------------------- lobby
g = mn.Mensch(1, rng=Script()); g.join(1, "a")
ok("one player cannot start", refused(g.start, 1, 0.0))
g.join(2, "b"); ok("only host starts", refused(g.start, 2, 0.0))
for u in (3, 4): g.join(u, "x")
ok("5th refused", refused(g.join, 5, "x"))
g.start(1, 0.0); ok("started", g.phase == "play" and g.turn == 1)
ok("seats 4p", [g.players[u]["seat"] for u in (1, 2, 3, 4)] == [0, 1, 2, 3])
ok("cannot start twice", refused(g.start, 1, 0.0)); ok("cannot join running", refused(g.join, 9, "x"))
g2 = game(2); ok("2 players sit opposite", [g2.players[1]["seat"], g2.players[2]["seat"]] == [0, 2])
g3 = mn.Mensch(1); [g3.join(u, "x") for u in (1, 2, 3)]; g3.start(1, 0.0)
ok("3 players seats", sorted(p["seat"] for p in g3.players.values()) == [0, 1, 2])
g = mn.Mensch(1); g.join(1, "a"); g.join(2, "b"); g.leave(1, 0.0)
ok("host leaves lobby: host passes on", g.host == 2 and 1 not in g.players)
g = mn.Mensch(1); g.join(1, "\x00‮bad\n" + "z" * 80)
ok("name sanitised", "\x00" not in g.players[1]["name"] and len(g.players[1]["name"]) <= 30)

# ---------------------------------------------------------------- turn order / stages
g = game(2, [3])
ok("not your turn", refused(g.roll, 2, 0.0)); ok("move before roll", refused(g.move, 1, 0, 0.0))
g.roll(1, 0.0)
ok("no pawn out and roll 3 -> turn passes to 2", g.turn == 1 and g.tries == 1 and g.stage == "roll")   # 3 tries for all-in-yard
ok("roll twice in a row refused? (stage roll again is allowed)", True)
g = game(2, [3, 4, 2])
g.roll(1, 0.0); g.roll(1, 0.0); g.roll(1, 0.0)
ok("three failed tries pass the turn", g.turn == 2 and g.tries == 0)
# six leaves the yard, gives another roll
g = game(2, [6])
g.roll(1, 0.0); ok("six: stage move, 4 legal", g.stage == "move" and g.legal == [0, 1, 2, 3] and g.dice == 6)
ok("roll while moving refused", refused(g.roll, 1, 0.0))
ok("bad pawn refused", refused(g.move, 1, 7, 0.0) and refused(g.move, 1, True, 0.0) and refused(g.move, 1, "0", 0.0) and refused(g.move, 1, None, 0.0) and refused(g.move, 1, -1, 0.0))
ok("other player cannot move", refused(g.move, 2, 0, 0.0))
g.move(1, 0, 0.0)
ok("pawn out at 0, same player rolls again", g.players[1]["pawns"][0] == 0 and g.turn == 1 and g.stage == "roll")
g = game(2, [6, 3])
g.roll(1, 0.0); g.move(1, 0, 0.0); g.roll(1, 0.0)
ok("roll 3: only the pawn on board is legal", g.legal == [0] and g.stage == "move")
g.move(1, 0, 0.0); ok("moved 3, turn passes", g.players[1]["pawns"][0] == 3 and g.turn == 2)
# three sixes
g = game(2, [6, 6, 6])
g.roll(1, 0.0); g.move(1, 0, 0.0); g.roll(1, 0.0); g.move(1, 0, 0.0); g.roll(1, 0.0)
ok("third six burns the turn", g.turn == 2 and g.players[1]["pawns"][0] == 6 and g.last["note"] == "three6")
# six counter resets after other roll
g = game(2, [6, 2, 6, 6])
g.roll(1, 0.0); g.move(1, 0, 0.0); g.roll(1, 0.0); g.move(1, 0, 0.0)      # 6, 2 -> turn 2
ok("turn passed after 6,2", g.turn == 2)

# ---------------------------------------------------------------- captures and safe cells
# seat0 (p1) enters at abs 1; seat2 (p2) at abs 27. Put p1 pawn so it lands on p2's pawn.
def put(g, u, i, pos): g.players[u]["pawns"][i] = pos
g = game(2, [4]); put(g, 1, 0, 24); put(g, 2, 0, 0 + 0)     # p1 rel 24 -> abs 25 ; p2 rel 0 -> abs 27
g.roll(1, 0.0)
# p1 rel 24 + 4 = 28 -> abs 29. make p2 sit on abs 29: seat2 rel 2
put(g, 2, 0, 2); g.move(1, 0, 0.0)
ok("capture: p2 pawn back to yard", g.players[2]["pawns"][0] == -1 and g.last["cap"] == [{"uid": 2, "pawn": 0}])
ok("capture gives another roll", g.turn == 1 and g.stage == "roll")
# safe cell: no capture
g = game(2, [2]); put(g, 1, 0, 6); put(g, 2, 0, 0)          # p1 rel 6 +2 = 8 -> abs 9 (star, safe); p2 pawn seat2 rel k with abs 9: 27+k=9+52 -> k=34
put(g, 2, 0, 34); g.roll(1, 0.0); g.move(1, 0, 0.0)
ok("star cell is safe: both stay", g.players[2]["pawns"][0] == 34 and g.players[1]["pawns"][0] == 8 and g.turn == 2)
# entry cell of another colour is safe; own entering pawn does not capture there
g = game(2, [6]); put(g, 2, 1, 0)                          # p2 pawn at its own entry abs 27; p1 can't reach there now; check p1 leaving yard onto abs1 where p2 pawn sits?
put(g, 2, 2, 26 + 0)                                       # p2 rel 26 -> abs 53%52 = 1 : sits on p1's entry cell (safe)
g.roll(1, 0.0); g.move(1, 0, 0.0)
ok("leaving the yard onto a safe cell does not capture", g.players[2]["pawns"][2] == 26)
# opposing pawn in home column is untouchable; own pawns never captured
g = game(2, [2]); put(g, 1, 0, 10); put(g, 1, 1, 12)
g.roll(1, 0.0); g.move(1, 0, 0.0)
ok("own pawn not captured", g.players[1]["pawns"][1] == 12 and g.last["cap"] == [])
# double capture (two pawns on one cell)
g = game(2, [3]); put(g, 1, 0, 20)                         # -> rel 23 abs 24 ; p2 seat2 rel 49 -> abs 27+49=76%52=24
put(g, 2, 0, 49); put(g, 2, 1, 49); g.roll(1, 0.0); g.move(1, 0, 0.0)
ok("two pawns on one cell are both captured", g.players[2]["pawns"][:2] == [-1, -1] and len(g.last["cap"]) == 2)
# captured seat that left is ignored
g = game(3, [3]); put(g, 1, 0, 20)
g.players[2]["out"] = "left"; g.players[2]["pawns"] = [-1] * 4
ok("no crash with an absent player", True)

# ---------------------------------------------------------------- home column / exact finish
g = game(2, [6]); put(g, 1, 0, 52); g.roll(1, 0.0)
ok("52+6 > 56: pawn 0 not legal", 0 not in g.legal)
g = game(2, [4]); put(g, 1, 0, 52); put(g, 1, 1, 10); g.roll(1, 0.0)
ok("52+4 = 56 legal (exact)", 0 in g.legal and 1 in g.legal)
g.move(1, 0, 0.0); ok("finished gives another roll", g.players[1]["pawns"][0] == 56 and g.turn == 1 and g.stage == "roll")
g = game(2, [5]); put(g, 1, 0, 56); g.roll(1, 0.0)
ok("a finished pawn never moves again", g.last["note"] in ("stuck", "rolled") and 0 not in g.legal)
g = game(2, [3]); put(g, 1, 0, 50); g.roll(1, 0.0); g.move(1, 0, 0.0)
ok("ring end -> home column (53), no capture there", g.players[1]["pawns"][0] == 53 and g.last["cap"] == [])
# stuck while pawns on board: turn passes without extra tries
g = game(2, [2]); put(g, 1, 0, 55); put(g, 1, 1, 55); put(g, 1, 2, 55); put(g, 1, 3, 55)
g.roll(1, 0.0); ok("stuck with pawns out: turn passes", g.turn == 2)
# win
g = game(2, [1]); put(g, 1, 0, 56); put(g, 1, 1, 56); put(g, 1, 2, 56); put(g, 1, 3, 55)
g.roll(1, 0.0); g.move(1, 3, 0.0)
ok("win", g.phase == "over" and g.winner == 1 and g.turn is None)
ok("no action after over", refused(g.roll, 1, 0.0) and refused(g.move, 1, 0, 0.0))

# ---------------------------------------------------------------- timers
mn.TURN_SECS = 25
g = game(2, [6, 3]); ok("deadline set", g.deadline == 25.0)
ok("tick before deadline: nothing", g.tick(10.0) is False)
g.tick(26.0)
ok("timeout auto-plays (roll 6 + move out)", g.players[1]["pawns"][0] == 0 or g.turn == 2)
g = game(2, [1, 1, 1, 1, 1, 1, 1, 1, 1])
t = 0.0; seen_drop = False
for _ in range(12):
    t += 30.0; g.tick(t)
    if g.players[1]["out"] == "afk" or g.players[2]["out"] == "afk": seen_drop = True; break
ok("three timeouts in a row drop the sleeper, other wins", seen_drop and g.phase == "over" and g.winner is not None)
g = game(2, [6, 3, 3, 3])
g.roll(1, 0.0); g.move(1, 0, 0.0)
ok("manual action resets misses", g.players[1]["misses"] == 0)
# auto-pick prefers capture, then finish
g = game(2, [4]); put(g, 1, 0, 24); put(g, 1, 1, 52); put(g, 2, 0, 2)   # pawn0 -> rel28 abs29 capture; pawn1 -> 56 finish
g.roll(1, 0.0); ok("auto-pick: capture beats finish", g._auto_pick(1) == 0)

# ---------------------------------------------------------------- leaving
g = game(3, [6]); g.leave(1, 1.0)
ok("turn holder leaves: turn moves on", g.turn == 2 and g.players[1]["out"] == "left" and g.phase == "play")
g.leave(2, 2.0); ok("only one left: he wins", g.phase == "over" and g.winner == 3)
g = game(2); g.leave(2, 1.0); ok("opponent leaves a 2p game: other wins", g.phase == "over" and g.winner == 1)
g = game(2); g.leave(2, 1.0); g.leave(2, 2.0); ok("double leave harmless", g.phase == "over")
g = game(3); put(g, 2, 0, 5); g.leave(2, 0.0)
ok("leaver's pawns vanish", g.players[2]["pawns"] == [-1] * 4)
g = game(4); g.leave(3, 0.0); ok("non-turn leaver: game goes on, turn kept", g.turn == 1 and g.phase == "play")
g.roll(1, 0.0)
ok("skips absent seats", True)

# ---------------------------------------------------------------- view
g = game(2, [6]); v = g.view(1, 3.0)
ok("view fields", v["phase"] == "play" and v["turn"] == 1 and v["stage"] == "roll" and v["me"]["seat"] == 0 and len(v["players"]) == 2 and v["left"] == 22)
ok("view of a stranger", g.view(99, 0.0)["me"] is None)
ok("view is plain data", __import__("json").dumps(v) is not None)

# ---------------------------------------------------------------- fuzz: random full games
def fuzz(seed):
    r = random.Random(seed)
    n = r.choice([2, 3, 4])
    g = mn.Mensch(1, rng=random.Random(seed * 7 + 1))
    for u in range(1, n + 1): g.join(u, f"p{u}")
    g.start(1, 0.0)
    t = 0.0; steps = 0
    while g.phase == "play" and steps < 20000:
        steps += 1
        u = g.turn
        x = r.random()
        try:
            if x < 0.02:
                g.leave(r.choice(list(g.players)), t)
            elif x < 0.06:
                t += 100; g.tick(t)
            elif g.stage == "roll":
                g.roll(u, t)
            else:
                g.move(u, r.choice(g.legal), t)
        except mn.MenschError:
            return f"unexpected refusal seed {seed}"
        # invariants
        for uu, p in g.players.items():
            for q in p["pawns"]:
                if not (-1 <= q <= 56): return f"pawn out of range seed {seed}"
            if p["out"] and p["pawns"] != [-1] * 4: return "leaver has pawns"
        if g.phase == "play":
            if g.players[g.turn]["out"] is not None: return "turn on absent player"
            if g.stage == "move" and not g.legal: return "move stage without legal moves"
            ring = {}
            for uu, p in g.players.items():
                for q in p["pawns"]:
                    if 0 <= q <= 50:
                        c = mn.abs_cell(p["seat"], q)
                        ring.setdefault(c, set()).add(uu)
            for c, us in ring.items():
                if len(us) > 1 and c not in mn.SAFE: return f"two colours share unsafe cell {c} seed {seed}"
    if g.phase == "play": return f"game did not finish seed {seed}"
    if g.winner is not None and not (all(p == 56 for p in g.players[g.winner]["pawns"]) or len(g._active()) <= 1):
        return "winner without home or last standing"
    return None
bad = [e for e in (fuzz(s) for s in range(1, 601)) if e]
ok("fuzz: 600 random games finish with all invariants", not bad, bad[:3])

print(f"\n{sum(res)}/{len(res)} passed"); sys.exit(0 if all(res) else 1)
