"""Mafia inside a watch-room: glue between the pure engine (mafia.py) and the room/server machinery.

One game per room (`room["mafia"]`). Everything that changes the game happens under `rooms_lock`; afterwards every room member
gets HIS OWN view (`Mafia.view(uid)` is the only function that decides what a person may know), so a spectator, a dead player
or a mafia member can never receive more than the engine allows. A one-second ticker advances the clocks."""
import threading
import time

import mafia as mf


def make_mafia(Fail):
    def _tid(v):
        """a target id must be a real JSON integer (never a bool / string / float)"""
        if v is None:
            return None
        if isinstance(v, bool) or not isinstance(v, int) or v < 0 or v > 2 ** 62:
            raise Fail("هدف نامعتبر")
        return v

    class MafiaMixin:
        def _mafia_init(self):
            threading.Thread(target=self._mafia_ticker, daemon=True, name="mafia-ticker").start()

        def _mafia_ticker(self):
            while True:
                time.sleep(1.0)
                try:
                    self._mafia_tick()
                except Exception:
                    pass

        def _mafia_tick(self):
            now = time.time()
            changed = []
            with self.rooms_lock:
                for room in list(self.rooms.values()):
                    g = room.get("mafia")
                    if g is not None and g.tick(now):
                        changed.append(room)
            for room in changed:
                self._mafia_push(room)

        def _mafia_push(self, room):
            """every member gets his own view (None = no game)"""
            now = time.time()
            with self.rooms_lock:
                g = room.get("mafia")
                views = {u: (g.view(u, now) if g is not None else None) for u in list(room["members"])}
            for u, v in views.items():
                with self.sessions_lock:
                    targets = [c for c in self.sessions.get(u, []) if c.alive and getattr(c, "room_id", None) == room["id"]]
                for c in targets:
                    c.send({"event": "room_mafia", "room": room["id"], "mafia": v})

        def _mafia_left(self, room, uid):
            """called when somebody really left the room (not just a connection blink)"""
            with self.rooms_lock:
                g = room.get("mafia")
                if g is None or uid not in g.players:
                    return
                g.leave(uid, time.time())
                if g.phase == "lobby" and not g.players:
                    room["mafia"] = None
            self._mafia_push(room)

        def _mafia_may_talk(self, room, uid):
            g = room.get("mafia")
            return g is None or g.may_talk(uid)

        def op_room_mafia(self, conn, req):
            room = self._room_of(conn, req)
            self._room_guard(conn.uid, "mafia", 60, 10)
            a = req.get("a")
            uid = conn.uid
            now = time.time()
            if a not in ("get", "open", "join", "leave", "start", "night", "ready", "vote", "team", "end"):
                raise Fail("درخواست نامعتبر")
            if a == "get":
                with self.rooms_lock:
                    g = room.get("mafia")
                    return {"mafia": g.view(uid, now) if g is not None else None}
            target = _tid(req.get("target"))
            try:
                with self.rooms_lock:
                    g = room.get("mafia")
                    name = room["members"][uid]["name"]
                    if a == "open":
                        if g is None:
                            g = room["mafia"] = mf.Mafia(uid)
                        g.join(uid, name)
                    elif g is None:
                        raise Fail("بازی‌ای تو این اتاق نیست")
                    elif a == "join":
                        g.join(uid, name)
                    elif a == "leave":
                        g.leave(uid, now)
                        if g.phase == "lobby" and not g.players:
                            room["mafia"] = None
                    elif a == "start":
                        g.start(uid, now)
                    elif a == "night":
                        if target is None:
                            raise Fail("هدف نامعتبر")
                        g.night_act(uid, target, now)
                    elif a == "ready":
                        g.set_ready(uid, now)
                    elif a == "vote":
                        g.vote(uid, target or 0, now)
                    elif a == "team":
                        g.team_say(uid, req.get("text"))
                    elif a == "end":
                        if not (g.phase == "over" or uid == g.host or uid == room["host"]):
                            raise Fail("فقط سازنده‌ی بازی یا میزبان اتاق می‌تونه بازی رو ببنده")
                        room["mafia"] = None
            except mf.MafiaError as e:
                raise Fail(str(e))
            self._mafia_push(room)
            with self.rooms_lock:
                g = room.get("mafia")
                return {"mafia": g.view(uid, time.time()) if g is not None else None}

    return MafiaMixin
