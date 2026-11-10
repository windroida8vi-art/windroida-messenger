"""Mafia engine: rules, privacy of roles, and a fuzz of random games. Run: python test_mafia_engine.py"""
import random, sys
sys.path.insert(0, ".")
import mafia as mf

res = []
def ok(n, c, x=""): res.append(bool(c)); print(("  ok   " if c else "  FAIL ") + n, "" if c else x)
def refused(fn, *a):
    try: fn(*a)
    except mf.MafiaError: return True
    return False

def game(n, seed=1, host=1):
    g = mf.Mafia(host, rng=random.Random(seed))
    for u in range(1, n + 1): g.join(u, f"p{u}")
    return g
def started(n, seed=1):
    g = game(n, seed); g.start(1, 0.0); return g
def role_of(g, u): return g.players[u]["role"]
def by_role(g, r, alive=True): return [u for u, p in g.players.items() if p["role"] == r and (p["alive"] or not alive)]

# ---------------------------------------------------------------- lobby
g = game(4); ok("fewer than 5 cannot start", refused(g.start, 1, 0.0))
g = game(5); ok("only the host starts", refused(g.start, 2, 0.0))
g.start(1, 0.0); ok("started: night 1", g.phase == "night" and g.round == 1)
ok("cannot start twice", refused(g.start, 1, 0.0))
ok("cannot join a running game", refused(g.join, 99, "late"))
g = mf.Mafia(1)
for u in range(1, 16): g.join(u, "x")
ok("16th player refused", refused(g.join, 16, "x"))
g = mf.Mafia(1); g.join(1, "a‮\x00bad\n" + "n" * 100)
ok("names are cleaned and cut", "‮" not in g.players[1]["name"] and "\x00" not in g.players[1]["name"] and len(g.players[1]["name"]) <= 40)
g = game(5); g.join(2, "again"); ok("joining twice changes nothing", len(g.players) == 5 and g.players[2]["name"] == "p2")
g = game(5); g.leave(1); ok("host leaves the lobby: next player becomes host", g.host == 2 and len(g.players) == 4)
for n in range(5, 16):
    plan = mf.role_plan(n)
    ok(f"role plan for {n}: {n//4} mafia, 1 doctor, 1 detective", len(plan) == n and plan.count("mafia") == max(1, n // 4) and plan.count("doctor") == 1 and plan.count("detective") == 1)

# ---------------------------------------------------------------- night rules
g = started(7, 3)
m, d, de = by_role(g, "mafia")[0], by_role(g, "doctor")[0], by_role(g, "detective")[0]
cit = by_role(g, "citizen")[0]
ok("a citizen has no night action", refused(g.night_act, cit, m, 1.0))
ok("target must exist", refused(g.night_act, m, 999, 1.0))
ok("mafia cannot shoot a teammate", len(by_role(g, "mafia")) < 2 or refused(g.night_act, m, by_role(g, "mafia")[1], 1.0))
ok("detective cannot check himself", refused(g.night_act, de, de, 1.0))
ok("nothing but night actions in the night", refused(g.vote, cit, m, 1.0) and refused(g.set_ready, cit, 1.0))
g.night_act(d, d, 1.0); ok("doctor may save himself once", g.self_saved is False and g.night[d] == d)
# resolve: all three actors acted
g.night_act(m, cit, 1.0); g.night_act(de, m, 1.0)
ok("night resolved as soon as everybody acted -> day", g.phase == "day" or g.phase == "over")
ok("the shot citizen is dead (doctor saved himself)", not g.players[cit]["alive"] and g.players[cit]["out"] == "shot")
ok("doctor used his self-save", g.self_saved is True)
ok("detective learned the answer privately", g.private[de][0].endswith("مافیاست ✅"))
ok("nobody else has private notes", all(u == de or not g.view(u)["me"]["private"] for u in g.players))
# second night: doctor cannot self-save again
for u in g._alive(): g.set_ready(u, 2.0)
ok("all ready -> vote", g.phase == "vote")
for u in g._alive(): g.vote(u, 0, 3.0)
ok("all abstained -> nobody out, night 2", g.phase == "night" and g.round == 2 and len([1 for p in g.players.values() if p["alive"]]) == 6)
ok("doctor cannot save himself twice", refused(g.night_act, d, d, 4.0))

# doctor saves the victim
g = started(7, 5)
m, d, de = by_role(g, "mafia")[0], by_role(g, "doctor")[0], by_role(g, "detective")[0]
victim = by_role(g, "citizen")[0]
g.night_act(d, victim, 1.0); g.night_act(m, victim, 1.0); g.night_act(de, m, 1.0)
ok("doctor saves the victim: nobody dies", all(p["alive"] for p in g.players.values()) and "نجاتش داد" in g.log[-1]["text"])
ok("doctor kept his self-save", g.self_saved is False)

# mafia tie / silence / timeout
g = started(9, 7)   # 2 mafia
ms = by_role(g, "mafia"); assert len(ms) == 2
cs = by_role(g, "citizen")
g.night_act(ms[0], cs[0], 1.0); g.night_act(ms[1], cs[1], 1.0)
ok("night waits for the other actors", g.phase == "night")
ok("tick before the deadline changes nothing", g.tick(5.0) is False and g.phase == "night")
ok("tick after the deadline resolves the night", g.tick(1000.0) is True and g.phase == "day")
ok("mafia tie: nobody shot", all(p["alive"] for p in g.players.values()))
ok("tick in the day -> vote -> night", g.tick(2000.0) and g.phase == "vote" and g.tick(3000.0) and g.phase == "night" and g.round == 2)
g.night_act(ms[0], cs[0], 5.0); g.night_act(ms[1], cs[0], 5.0)
g.tick(10 ** 6)
ok("both mafia agree: victim dies (no doctor action)", not g.players[cs[0]]["alive"])
ok("serial counts phase changes", g.serial >= 5)

# ---------------------------------------------------------------- day / vote
g = started(7, 11); m = by_role(g, "mafia")[0]; cs = by_role(g, "citizen")
g.tick(10 ** 6)                                   # silent night
ok("silent night: nobody dies", len(g._alive()) == 7 and g.phase == "day")
ok("ready only in the day, only alive", refused(g.vote, 1, 2, 5.0))
for u in list(g._alive())[:-1]: g.set_ready(u, 5.0)
ok("not everybody ready: still day", g.phase == "day")
g.set_ready(g._alive()[-1], 5.0); ok("everybody ready -> vote", g.phase == "vote")
ok("cannot vote for yourself", refused(g.vote, cs[0], cs[0], 6.0))
ok("cannot vote for a stranger", refused(g.vote, cs[0], 424242, 6.0))
for u in g._alive(): g.vote(u, m if u != m else cs[0], 6.0)
ok("mafia voted out by the town", not g.players[m]["alive"] and g.players[m]["out"] == "voted")
ok("last mafia gone: citizens win", g.phase == "over" and g.winner == "citizens")
ok("nothing works after the end", refused(g.night_act, 1, 2, 7.0) and refused(g.vote, 1, 2, 7.0) and g.tick(10 ** 9) is False)

g = started(7, 11); g.tick(10 ** 6); [g.set_ready(u, 5.0) for u in g._alive()]
a = g._alive()
for i, u in enumerate(a): g.vote(u, a[(i + 1) % len(a)], 6.0)              # a perfect circle: everybody has one vote
ok("vote tie: nobody out", len(g._alive()) == 7 and g.phase == "night")

# ---------------------------------------------------------------- win conditions
g = started(5, 2); m = by_role(g, "mafia")[0]
now = 0.0; first_day = False
for i in range(30):
    if g.phase == "over": break
    now += 1000
    if g.phase == "night":
        victims = [u for u in g._alive() if u != m]
        g.night_act(m, victims[0], now)
    g.tick(now + 500)
    if i == 0: first_day = (g.phase == "day" and len(g._alive()) == 4)
ok("mafia kills one of 5 -> 4 alive (1 vs 3), game goes on", first_day)
ok("mafia wins when it is at least half of the living", g.phase == "over" and g.winner == "mafia" and g.players[m]["alive"])

# leaving
g = started(6, 4); m = by_role(g, "mafia")[0]
g.leave(m, 1.0)
ok("last mafia leaves: citizens win, role revealed in log", g.phase == "over" and g.winner == "citizens" and "مافیا" in "".join(x["text"] for x in g.log))
g = started(6, 4); cs = by_role(g, "citizen")[0]
g.leave(cs, 1.0); ok("a citizen leaving does not end the game", g.phase == "night" and not g.players[cs]["alive"])
ok("a dead player cannot act", refused(g.night_act, cs, 1, 1.0))
g = started(6, 4)
actors = g._night_actors()
for u in actors[:-1]: g.night_act(u, [x for x in g._alive() if x != u and g.players[x]["role"] != "mafia"][0], 1.0)
g.leave(actors[-1], 1.0)
ok("the last undecided actor leaves: night resolves at once", g.phase in ("day", "over"))
g = started(6, 4); g.tick(10**6); u = g._alive()
for x in u[:-1]: g.set_ready(x, 5.0)
g.leave(u[-1], 5.0); ok("last unready leaves: vote starts", g.phase in ("vote", "over"))

# ---------------------------------------------------------------- talking rights
g = started(6, 4)
cs = by_role(g, "citizen")[0]; m = by_role(g, "mafia")[0]
ok("nobody talks at night", not g.may_talk(cs) and not g.may_talk(m))
ok("spectators are not restricted", g.may_talk(9999))
ok("mafia whispers only at night", g.is_mafia_alive(m) and not g.is_mafia_alive(cs))
g.team_say(m, "hello\x00 team"); ok("team whisper stored", g.team_log[-1]["text"] == "hello team")
ok("citizen cannot whisper", refused(g.team_say, cs, "x") and refused(g.team_say, m, "   "))
ok("only the mafia sees the whispers", g.view(m)["me"].get("team_chat") and "team_chat" not in g.view(cs)["me"] and g.view(9999)["me"] is None)
g.tick(10 ** 6); ok("day: alive players may talk, whispers gone", g.may_talk(cs) and g.team_log == [])

# ---------------------------------------------------------------- privacy of roles (every phase, every viewer)
def check_privacy(g):
    for viewer in list(g.players) + [None]:
        v = g.view(viewer)
        me = g.players.get(viewer)
        for pl in v["players"]:
            real = g.players[pl["id"]]["role"]
            show = pl["role"] is not None
            if show:
                allowed = (g.phase == "over" or (not real is None and not g.players[pl["id"]]["alive"] and g.players[pl["id"]]["out"] != "")
                           or pl["id"] == viewer or (me and me["role"] == "mafia" and real == "mafia"))
                if not allowed: return False, (viewer, pl)
                if pl["role"] != real: return False, "wrong role"
        if viewer is None and v["me"] is not None: return False, "spectator has me"
        txt = repr(v)
        if viewer is not None and me and me["role"] != "mafia" and "team_votes" in txt: return False, "team votes leak"
        if viewer is not None and me and me["role"] not in ("detective",) and v["me"] and v["me"]["private"]: return False, "private leak"
        if g.phase in ("night", "day", "vote") and "winner" in v and v["winner"]: return False, "early winner"
    return True, ""

# ---------------------------------------------------------------- fuzz
rng = random.Random(20240101)
bad = 0; finished = 0; maxsteps = 0
for seed in range(400):
    n = rng.randint(5, 15)
    g = game(n, seed)
    g.start(1, 0.0)
    now = 0.0; steps = 0
    while g.phase != "over" and steps < 400:
        steps += 1
        now += rng.choice([1, 5, 50])
        al = g._alive()
        for _ in range(rng.randint(0, 6)):
            u = rng.choice(list(g.players))
            t = rng.choice(list(g.players) + [0, 999])
            try:
                c = rng.random()
                if g.phase == "night": g.night_act(u, t, now) if c < .8 else g.team_say(u, "hi")
                elif g.phase == "day": g.set_ready(u, now) if c < .8 else g.vote(u, t, now)
                elif g.phase == "vote": g.vote(u, t, now)
                if rng.random() < .03: g.leave(u, now)
            except mf.MafiaError:
                pass
            except Exception as e:
                bad += 1; print("   exception", repr(e)); break
            ok_p, why = check_privacy(g)
            if not ok_p: bad += 1; print("   privacy", why); break
        g.tick(now + rng.choice([0, 0, 200]))
        if not g._alive() and g.phase != "over": bad += 1; print("   nobody alive but game running"); break
    if g.phase == "over":
        finished += 1
        al = g._alive(); m = sum(1 for u in al if g.players[u]["role"] == "mafia")
        if g.winner == "citizens" and m != 0: bad += 1; print("   wrong winner (citizens)")
        if g.winner == "mafia" and not (m >= len(al) - m and m > 0): bad += 1; print("   wrong winner (mafia)")
    maxsteps = max(maxsteps, steps)
ok(f"fuzz: 400 random games, no exception, no leak, no wrong winner ({finished} finished)", bad == 0 and finished >= 380, f"bad={bad} finished={finished}")
ok("fuzz: games end (no endless loops)", maxsteps < 400)

print(f"\n{sum(res)} passed, {len(res) - sum(res)} failed"); sys.exit(0 if all(res) else 1)
