"""Mafia (مافیا) for watch/listen rooms: the server is the narrator and the only judge.

Roles:  mafia (knows the other mafia, picks one victim per night) · doctor (saves one person per night, himself only once)
        · detective (asks "is X mafia?" each night, only he learns the answer) · citizen.
Flow:   lobby -> night -> day (talk) -> vote -> night -> ... until the mafia is gone (citizens win) or the mafia is at least
        as many as everybody else alive (mafia wins).
Nobody - not even a spectator - can see anybody's role except through `view(uid)`: that is the single place that decides
what a user may know. This module is a pure state machine (no sockets, no threads, no clock of its own): the room mixin
below it calls `tick(now)` when a deadline passes and pushes `view()` to every member.
"""
import os
import random
import re
import time

MIN_PLAYERS = int(os.environ.get("WINDROIDA_MAFIA_MIN", "5"))
MAX_PLAYERS = 15
NIGHT_SECS = int(os.environ.get("WINDROIDA_MAFIA_NIGHT", "45"))
DAY_SECS = int(os.environ.get("WINDROIDA_MAFIA_DAY", "100"))
VOTE_SECS = int(os.environ.get("WINDROIDA_MAFIA_VOTE", "40"))
ROLE_FA = {"mafia": "مافیا", "doctor": "دکتر", "detective": "کارآگاه", "citizen": "شهروند"}
LOG_KEEP = 40
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f‎‏‪-‮⁦-⁩]")


class MafiaError(Exception):
    """A refused action; the message is shown to the user as is."""


def role_plan(n):
    """Roles for n players: n//4 mafia (at least 1), one doctor, one detective, the rest citizens."""
    m = max(1, n // 4)
    return ["mafia"] * m + ["doctor", "detective"] + ["citizen"] * (n - m - 2)


class Mafia:
    def __init__(self, host, rng=None):
        self.rng = rng or random.SystemRandom()
        self.host = host
        self.phase = "lobby"          # lobby | night | day | vote | over
        self.round = 0
        self.deadline = 0.0
        self.serial = 0               # bumps on every phase change (stale timers compare it)
        self.players = {}             # uid -> {"name", "role", "alive", "out"}  (out: how he left the game)
        self.night = {}               # uid -> target (mafia: victim vote, doctor: save, detective: check)
        self.votes = {}               # voter -> target uid, or 0 = abstain
        self.ready = set()
        self.log = []                 # public history [{"r": round, "text": ...}]
        self.private = {}             # uid -> [text]  (detective answers)
        self.team_log = []            # the mafia's whispers during the current night [{"name","text"}]
        self.self_saved = False       # the doctor may save himself only once
        self.winner = None

    # ------------------------------------------------------------------ small helpers
    def _say(self, text):
        self.log.append({"r": self.round, "text": text})
        del self.log[:-LOG_KEEP]

    def _alive(self):
        return [u for u, p in self.players.items() if p["alive"]]

    def _name(self, uid):
        return self.players[uid]["name"]

    def _set_phase(self, phase, now, secs):
        self.phase = phase
        self.serial += 1
        self.deadline = now + secs if secs else 0.0

    def _night_actors(self):
        return [u for u in self._alive() if self.players[u]["role"] in ("mafia", "doctor", "detective")]

    # ------------------------------------------------------------------ lobby
    def join(self, uid, name):
        if self.phase != "lobby":
            raise MafiaError("بازی شروع شده")
        if uid in self.players:
            return
        if len(self.players) >= MAX_PLAYERS:
            raise MafiaError(f"حداکثر {MAX_PLAYERS} بازیکن")
        self.players[uid] = {"name": _CTRL.sub("", str(name))[:40] or "بازیکن", "role": None, "alive": True, "out": ""}

    def leave(self, uid, now=0.0):
        """In the lobby he is simply removed; in a running game he is out (dies, role shown) and the game goes on."""
        if uid not in self.players:
            return
        if self.phase == "lobby":
            del self.players[uid]
            if uid == self.host and self.players:
                self.host = next(iter(self.players))
            return
        p = self.players[uid]
        if self.phase == "over" or not p["alive"]:
            return
        p["alive"], p["out"] = False, "left"
        self._say(f"{p['name']} بازی رو ترک کرد (نقش: {ROLE_FA[p['role']]})")
        self.night.pop(uid, None)
        self.votes.pop(uid, None)
        self.ready.discard(uid)
        self._after_death(now)

    def start(self, uid, now):
        if uid != self.host:
            raise MafiaError("فقط سازنده بازی می‌تونه شروع کنه")
        if self.phase != "lobby":
            raise MafiaError("بازی شروع شده")
        n = len(self.players)
        if n < MIN_PLAYERS:
            raise MafiaError(f"حداقل {MIN_PLAYERS} بازیکن لازمه")
        roles = role_plan(n)
        self.rng.shuffle(roles)
        for u, r in zip(list(self.players), roles):
            self.players[u]["role"] = r
        self.round = 0
        self._say(f"بازی شروع شد: {n} بازیکن")
        self._begin_night(now)

    # ------------------------------------------------------------------ night
    def _begin_night(self, now):
        self.round += 1
        self.night, self.votes, self.ready = {}, {}, set()
        self.team_log = []
        self._set_phase("night", now, NIGHT_SECS)
        self._say(f"شب {self.round} شد؛ همه چشماشونو می‌بندن")

    def night_act(self, uid, target, now):
        if self.phase != "night":
            raise MafiaError("الان شب نیست")
        p = self.players.get(uid)
        if not p or not p["alive"]:
            raise MafiaError("تو تو بازی نیستی")
        role = p["role"]
        if role not in ("mafia", "doctor", "detective"):
            raise MafiaError("شهروند شب کاری نداره")
        t = self.players.get(target)
        if not t or not t["alive"]:
            raise MafiaError("هدف معتبر نیست")
        if role == "mafia" and t["role"] == "mafia":
            raise MafiaError("نمی‌تونی هم‌تیمی‌ت رو بزنی")
        if role == "detective" and target == uid:
            raise MafiaError("از خودت نمی‌تونی بپرسی")
        if role == "doctor" and target == uid and self.self_saved:
            raise MafiaError("فقط یه بار می‌تونی خودت رو نجات بدی")
        self.night[uid] = target
        if all(a in self.night for a in self._night_actors()):
            self._resolve_night(now)

    def _resolve_night(self, now):
        mafias = [u for u in self._alive() if self.players[u]["role"] == "mafia"]
        tally = {}
        for u in mafias:
            if u in self.night:
                tally[self.night[u]] = tally.get(self.night[u], 0) + 1
        victim = None
        if tally:
            top = max(tally.values())
            best = [t for t, c in tally.items() if c == top]
            victim = best[0] if len(best) == 1 else None          # a tie among the mafia: nobody is shot
        doctor = next((u for u in self._alive() if self.players[u]["role"] == "doctor"), None)
        saved = doctor is not None and doctor in self.night and self.night[doctor] == victim and victim is not None
        if doctor is not None and doctor in self.night and self.night[doctor] == doctor:
            self.self_saved = True
        det = next((u for u in self._alive() if self.players[u]["role"] == "detective"), None)
        if det is not None and det in self.night:
            t = self.night[det]
            self.private.setdefault(det, []).append(
                f"شب {self.round}: {self._name(t)} " + ("مافیاست ✅" if self.players[t]["role"] == "mafia" else "مافیا نیست ❌"))
        self.night = {}
        self.team_log = []
        if victim is not None and not saved:
            v = self.players[victim]
            v["alive"], v["out"] = False, "shot"
            self._say(f"صبح شد؛ {v['name']} شب کشته شد (نقش: {ROLE_FA[v['role']]})")
        elif victim is not None:
            self._say("صبح شد؛ مافیا شلیک کرد ولی دکتر نجاتش داد، کسی نمرد")
        else:
            self._say("صبح شد؛ کسی کشته نشد")
        if not self._check_win():
            self.ready = set()
            self._set_phase("day", now, DAY_SECS)

    # ------------------------------------------------------------------ day / vote
    def set_ready(self, uid, now):
        if self.phase != "day":
            raise MafiaError("الان وقت بحث نیست")
        p = self.players.get(uid)
        if not p or not p["alive"]:
            raise MafiaError("تو تو بازی نیستی")
        self.ready.add(uid)
        if all(u in self.ready for u in self._alive()):
            self._begin_vote(now)

    def _begin_vote(self, now):
        self.votes = {}
        self._set_phase("vote", now, VOTE_SECS)
        self._say("رأی‌گیری شروع شد")

    def vote(self, uid, target, now):
        if self.phase != "vote":
            raise MafiaError("الان رأی‌گیری نیست")
        p = self.players.get(uid)
        if not p or not p["alive"]:
            raise MafiaError("تو تو بازی نیستی")
        if target:
            t = self.players.get(target)
            if not t or not t["alive"] or target == uid:
                raise MafiaError("رأی نامعتبر")
        else:
            target = 0
        self.votes[uid] = target
        if all(u in self.votes for u in self._alive()):
            self._resolve_vote(now)

    def _resolve_vote(self, now):
        tally = {}
        for t in self.votes.values():
            if t:
                tally[t] = tally.get(t, 0) + 1
        out = None
        if tally:
            top = max(tally.values())
            best = [t for t, c in tally.items() if c == top]
            out = best[0] if len(best) == 1 else None
        if out is None:
            self._say("رأی‌ها به نتیجه نرسید؛ کسی اخراج نشد")
        else:
            v = self.players[out]
            v["alive"], v["out"] = False, "voted"
            self._say(f"{v['name']} با رأی مردم اخراج شد (نقش: {ROLE_FA[v['role']]})")
        self.votes = {}
        if not self._check_win():
            self._begin_night(now)

    # ------------------------------------------------------------------ end of game / clock
    def _check_win(self):
        alive = self._alive()
        m = sum(1 for u in alive if self.players[u]["role"] == "mafia")
        if m == 0:
            self.winner = "citizens"
        elif m >= len(alive) - m:
            self.winner = "mafia"
        else:
            return False
        self._set_phase("over", 0, 0)
        self._say("شهروندها بردن 🎉" if self.winner == "citizens" else "مافیا برد 😈")
        return True

    def _after_death(self, now):
        """Someone left in the middle of the game: maybe the game is over, maybe a waiting phase can now finish."""
        if self.phase in ("lobby", "over"):
            return
        if self._check_win():
            return
        if self.phase == "night" and all(a in self.night for a in self._night_actors()):
            self._resolve_night(now)
        elif self.phase == "day" and all(u in self.ready for u in self._alive()):
            self._begin_vote(now)
        elif self.phase == "vote" and all(u in self.votes for u in self._alive()):
            self._resolve_vote(now)

    def tick(self, now):
        """Called when the clock passes `deadline`: whoever did not act simply did nothing. True if the state changed."""
        if self.phase not in ("night", "day", "vote") or now < self.deadline:
            return False
        if self.phase == "night":
            self._resolve_night(now)
        elif self.phase == "day":
            self._begin_vote(now)
        else:
            self._resolve_vote(now)
        return True

    # ------------------------------------------------------------------ chat rights (used by the room chat / mic)
    def may_talk(self, uid):
        """Players talk only while alive and only by day; spectators are not in the game and are not restricted."""
        p = self.players.get(uid)
        if p is None or self.phase in ("lobby", "over"):
            return True
        return p["alive"] and self.phase in ("day", "vote")

    def team_say(self, uid, text):
        """Night whisper between the living mafia (the only way they can talk while everybody else sleeps)."""
        if not self.is_mafia_alive(uid):
            raise MafiaError("الان نمی‌تونی با تیم حرف بزنی")
        text = " ".join(_CTRL.sub("", str(text or "")).split())[:200]
        if not text:
            raise MafiaError("پیام خالیه")
        self.team_log.append({"name": self._name(uid), "text": text})
        del self.team_log[:-30]

    def is_mafia_alive(self, uid):
        p = self.players.get(uid)
        return bool(p and p["alive"] and p["role"] == "mafia" and self.phase == "night")

    # ------------------------------------------------------------------ what a user may know
    def view(self, uid, now=None):
        if now is None:
            now = time.time()
        over = self.phase == "over"
        me = self.players.get(uid)
        mafia_eyes = bool(me and me["role"] == "mafia")
        players = []
        for u, p in self.players.items():
            reveal = over or (not p["alive"] and p["out"] != "") or (mafia_eyes and p["role"] == "mafia") or u == uid
            players.append({"id": u, "name": p["name"], "alive": p["alive"], "out": p["out"],
                            "role": p["role"] if reveal and p["role"] else None})
        v = {"phase": self.phase, "round": self.round, "left": max(0, int(self.deadline - now + 0.999)) if self.deadline else 0,
             "serial": self.serial, "host": self.host,
             "winner": self.winner, "players": players, "log": list(self.log), "min": MIN_PLAYERS, "max": MAX_PLAYERS,
             "me": None}
        if self.phase == "vote" or (over and self.votes):
            v["votes"] = dict(self.votes)                                  # voting is open: everybody sees who voted whom
        if self.phase == "day":
            v["ready"] = len(self.ready)
            v["alive_n"] = len(self._alive())
        if me:
            mine = {"role": me["role"], "alive": me["alive"], "private": list(self.private.get(uid, [])),
                    "ready": uid in self.ready, "night_target": self.night.get(uid) if self.phase == "night" else None}
            if mafia_eyes and self.phase == "night" and me["alive"]:
                mine["team_votes"] = {u: t for u, t in self.night.items() if self.players[u]["role"] == "mafia"}
                mine["team_chat"] = list(self.team_log)
            if me["role"] == "doctor":
                mine["can_self_save"] = not self.self_saved
            v["me"] = mine
        return v
