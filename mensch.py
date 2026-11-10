"""Mensch / Ludo (منچ) for watch/listen rooms: 2-4 players, the server rolls the dice and is the only judge.

Board: a ring of 52 cells; seat k (colour red/green/yellow/blue) enters the ring at cell 1+13*k. A pawn's position `p`:
  -1 = in the yard · 0..50 = steps on the ring from its own entry cell · 51..55 = its private home column · 56 = home (finished).
Rules: a 6 brings a pawn out; a pawn must finish with an exact roll; landing on a lone-colour cell that is not safe sends every
opponent pawn there back to the yard; entry cells and the star cells (entry+8) are safe. A 6, a capture or a pawn reaching home
gives another roll; three sixes in a row lose the turn. When nothing can leave the yard the player gets three tries per turn.
First to bring all four pawns home wins. Everything is public information, so `view()` is the same for everybody except `me`.
Pure state machine: no sockets, no threads; the room mixin calls `tick(now)` when a deadline passes.
"""
import os
import random
import re

MIN_PLAYERS = int(os.environ.get("WINDROIDA_MENSCH_MIN", "2"))
MAX_PLAYERS = 4
TURN_SECS = int(os.environ.get("WINDROIDA_MENSCH_TURN", "25"))
MAX_MISSES = 3                       # consecutive timeouts before a player is dropped
RING = 52
GOAL = 56
COLORS = ["red", "green", "yellow", "blue"]
COLOR_FA = {"red": "قرمز", "green": "سبز", "yellow": "زرد", "blue": "آبی"}
ENTRY = [1 + 13 * k for k in range(4)]
SAFE = set(ENTRY) | {e + 8 for e in ENTRY}
LOG_KEEP = 30
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f‎‏‪-‮⁦-⁩]")


class MenschError(Exception):
    """A refused action; the message is shown to the user as is."""


def seats_for(n):
    return {2: [0, 2], 3: [0, 1, 2], 4: [0, 1, 2, 3]}[n]


def abs_cell(seat, p):
    """ring cell of a pawn at ring-position p (0..50) of `seat`"""
    return (ENTRY[seat] + p) % RING


class Mensch:
    def __init__(self, host, rng=None):
        self.rng = rng or random.SystemRandom()
        self.host = host
        self.phase = "lobby"          # lobby | play | over
        self.serial = 0
        self.seq = 0                  # bumps on every roll/move (the UI animates by it)
        self.players = {}             # uid -> {"name","seat","pawns":[4],"out","misses"}   (out: None | "left" | "afk")
        self.order = []               # uids in turn order
        self.turn = None
        self.stage = "roll"           # roll | move
        self.dice = 0
        self.legal = []
        self.sixes = 0
        self.tries = 0
        self.deadline = 0.0
        self.winner = None
        self.last = None
        self.log = []

    # ------------------------------------------------------------------ helpers
    def _say(self, text):
        self.log.append(text)
        del self.log[:-LOG_KEEP]

    def _active(self):
        return [u for u in self.order if self.players[u]["out"] is None]

    @staticmethod
    def _name(name):
        n = _CTRL.sub("", str(name or "")).strip()[:30]
        return n or "بازیکن"

    def _bump(self):
        self.serial += 1

    # ------------------------------------------------------------------ lobby
    def join(self, uid, name):
        if self.phase != "lobby":
            raise MenschError("بازی شروع شده؛ بعد از تمومش می‌تونی بیای")
        if uid in self.players:
            return
        if len(self.players) >= MAX_PLAYERS:
            raise MenschError("جا پر شده (حداکثر ۴ نفر)")
        self.players[uid] = {"name": self._name(name), "seat": None, "pawns": [-1] * 4, "out": None, "misses": 0}
        self._bump()

    def leave(self, uid, now):
        p = self.players.get(uid)
        if p is None:
            return
        if self.phase == "lobby":
            del self.players[uid]
            if self.host == uid and self.players:
                self.host = next(iter(self.players))
            self._bump()
            return
        if self.phase == "over" or p["out"] is not None:
            return
        self._drop(uid, "left", now)

    def _drop(self, uid, why, now):
        p = self.players[uid]
        p["out"] = why
        p["pawns"] = [-1] * 4
        self._say(("🚪 %s از بازی رفت" if why == "left" else "💤 %s بیکار بود و از بازی بیرون رفت") % p["name"])
        act = self._active()
        if self.host == uid and act:
            self.host = act[0]
        if len(act) <= 1:
            self.phase = "over"
            self.winner = act[0] if act else None
            self.turn = None
            if act:
                self._say("🏆 %s برد (بقیه رفتن)" % self.players[act[0]]["name"])
        elif self.turn == uid:
            self._next_turn(now, after=uid)
        self._bump()

    def start(self, uid, now):
        if self.phase != "lobby":
            raise MenschError("بازی شروع شده")
        if uid != self.host:
            raise MenschError("فقط سازنده‌ی بازی می‌تونه شروع کنه")
        n = len(self.players)
        if n < MIN_PLAYERS:
            raise MenschError("حداقل %d بازیکن لازمه" % MIN_PLAYERS)
        uids = list(self.players)
        for u, s in zip(uids, seats_for(n)):
            self.players[u]["seat"] = s
        self.order = sorted(uids, key=lambda u: self.players[u]["seat"])
        self.phase = "play"
        self.turn = self.rng.choice(self.order)
        self.stage = "roll"
        self.dice, self.legal, self.sixes, self.tries = 0, [], 0, 0
        self.deadline = now + TURN_SECS
        self.log = []
        self._say("🎲 بازی شروع شد؛ نوبت %s" % self.players[self.turn]["name"])
        self._bump()

    # ------------------------------------------------------------------ rules
    def _legal(self, uid, r):
        pl = self.players[uid]
        out = []
        for i, p in enumerate(pl["pawns"]):
            if p == -1:
                if r == 6:
                    out.append(i)
            elif p < GOAL and p + r <= GOAL:
                out.append(i)
        return out

    def _next_turn(self, now, after=None):
        a = self.order.index(after if after is not None else self.turn)
        for k in range(1, len(self.order) + 1):
            u = self.order[(a + k) % len(self.order)]
            if self.players[u]["out"] is None:
                self.turn = u
                break
        self.stage, self.dice, self.legal, self.sixes, self.tries = "roll", 0, [], 0, 0
        self.deadline = now + TURN_SECS

    def _check_turn(self, uid, stage):
        if self.phase != "play":
            raise MenschError("بازی در جریان نیست")
        if uid not in self.players or self.players[uid]["out"] is not None:
            raise MenschError("تو تو این بازی نیستی")
        if uid != self.turn:
            raise MenschError("نوبت تو نیست")
        if self.stage != stage:
            raise MenschError("اول باید تاس بندازی" if stage == "move" else "اول مهره‌ات رو حرکت بده")

    def roll(self, uid, now, manual=True):
        self._check_turn(uid, "roll")
        if manual:
            self.players[uid]["misses"] = 0
        d = self.rng.randint(1, 6)
        self.seq += 1
        pl = self.players[uid]
        self.dice = d
        self.sixes = self.sixes + 1 if d == 6 else 0
        if self.sixes >= 3:
            self.last = {"seq": self.seq, "uid": uid, "roll": d, "pawn": None, "frm": None, "to": None, "cap": [], "note": "three6"}
            self._say("🎲 %s سه تا شش پشت‌هم آورد؛ نوبتش سوخت" % pl["name"])
            self._next_turn(now)
            self._bump()
            return d
        self.legal = self._legal(uid, d)
        if self.legal:
            self.stage = "move"
            self.deadline = now + TURN_SECS
            self.last = {"seq": self.seq, "uid": uid, "roll": d, "pawn": None, "frm": None, "to": None, "cap": [], "note": "rolled"}
        else:
            self.last = {"seq": self.seq, "uid": uid, "roll": d, "pawn": None, "frm": None, "to": None, "cap": [], "note": "stuck"}
            yard_only = all(p == -1 for p in pl["pawns"])
            if yard_only and self.tries < 2:
                self.tries += 1
                self.stage, self.legal, self.sixes = "roll", [], 0
                self.deadline = now + TURN_SECS
            else:
                self._next_turn(now)
        self._bump()
        return d

    def move(self, uid, pawn, now, manual=True):
        self._check_turn(uid, "move")
        if isinstance(pawn, bool) or not isinstance(pawn, int) or pawn not in self.legal:
            raise MenschError("این مهره الان نمی‌تونه حرکت کنه")
        pl = self.players[uid]
        if manual:
            pl["misses"] = 0
        r = self.dice
        frm = pl["pawns"][pawn]
        to = 0 if frm == -1 else frm + r
        pl["pawns"][pawn] = to
        cap = []
        if 0 <= to <= 50:
            cell = abs_cell(pl["seat"], to)
            if cell not in SAFE:
                for u in self.order:
                    if u == uid or self.players[u]["out"] is not None:
                        continue
                    q = self.players[u]
                    for j, qp in enumerate(q["pawns"]):
                        if 0 <= qp <= 50 and abs_cell(q["seat"], qp) == cell:
                            q["pawns"][j] = -1
                            cap.append({"uid": u, "pawn": j})
        self.seq += 1
        self.last = {"seq": self.seq, "uid": uid, "roll": r, "pawn": pawn, "frm": frm, "to": to, "cap": cap, "note": "moved"}
        for c in cap:
            self._say("💥 %s مهره‌ی %s رو زد" % (pl["name"], self.players[c["uid"]]["name"]))
        if to == GOAL:
            self._say("🏠 %s یه مهره‌اش رو به خونه رسوند" % pl["name"])
        if all(p == GOAL for p in pl["pawns"]):
            self.phase, self.winner, self.turn, self.legal = "over", uid, None, []
            self._say("🏆 %s برنده شد!" % pl["name"])
        elif r == 6 or cap or to == GOAL:
            self.stage, self.dice, self.legal, self.tries = "roll", 0, [], 0
            self.deadline = now + TURN_SECS
        else:
            self._next_turn(now)
        self._bump()

    def _auto_pick(self, uid):
        """what a sleeping player's pawn does: capture > finish > leave yard > furthest pawn"""
        pl = self.players[uid]
        best, score = None, -1
        for i in self.legal:
            p = pl["pawns"][i]
            to = 0 if p == -1 else p + self.dice
            s = to
            if 0 <= to <= 50:
                cell = abs_cell(pl["seat"], to)
                if cell not in SAFE and any(0 <= qp <= 50 and abs_cell(self.players[u]["seat"], qp) == cell
                                            for u in self.order if u != uid and self.players[u]["out"] is None
                                            for qp in self.players[u]["pawns"]):
                    s += 200
            if to == GOAL:
                s += 100
            if p == -1:
                s += 60
            if s > score:
                best, score = i, s
        return best

    def tick(self, now):
        """advance the clock; True when something changed"""
        if self.phase != "play" or now < self.deadline:
            return False
        uid = self.turn
        pl = self.players[uid]
        pl["misses"] += 1
        if pl["misses"] >= MAX_MISSES:
            self._drop(uid, "afk", now)
            return True
        if self.stage == "roll":
            self.roll(uid, now, manual=False)
        if self.phase == "play" and self.turn == uid and self.stage == "move":
            self.move(uid, self._auto_pick(uid), now, manual=False)
        return True

    # ------------------------------------------------------------------ view
    def view(self, uid, now):
        pls = []
        for u in (self.order if self.order else list(self.players)):
            p = self.players[u]
            pls.append({"id": u, "name": p["name"], "seat": p["seat"], "color": COLORS[p["seat"]] if p["seat"] is not None else None,
                        "pawns": list(p["pawns"]), "out": p["out"], "misses": p["misses"]})
        me = self.players.get(uid)
        return {"phase": self.phase, "host": self.host, "players": pls, "turn": self.turn, "stage": self.stage,
                "dice": self.dice, "legal": list(self.legal) if self.phase == "play" else [], "left": max(0, int(self.deadline - now + 0.999)) if self.phase == "play" else 0,
                "winner": self.winner, "last": self.last, "serial": self.serial, "log": list(self.log),
                "me": {"id": uid, "seat": me["seat"], "in": me["out"] is None} if me else None,
                "min": MIN_PLAYERS, "max": MAX_PLAYERS}
