"""Mensch (Ludo) inside a watch-room: glue between the pure engine (mensch.py) and the room/server machinery.

One game per room (`room["mensch"]`). Everything that changes the game happens under `rooms_lock`; afterwards every room member
gets the engine's view (all of a Ludo game is public; `me` differs per person). A half-second ticker advances the clocks."""
import threading
import time

import mensch as mn


def make_mensch(Fail):
    def _pawn(v):
        """a pawn number must be a real JSON integer 0..3 (never a bool / string / float)"""
        if v is None:
            return None
        if isinstance(v, bool) or not isinstance(v, int) or v < 0 or v > 3:
            raise Fail("مهره نامعتبر")
        return v

    class MenschMixin:
        def _mensch_init(self):
            threading.Thread(target=self._mensch_ticker, daemon=True, name="mensch-ticker").start()

        def _mensch_ticker(self):
            while True:
                time.sleep(0.5)
                try:
                    self._mensch_tick()
                except Exception:
                    pass

        def _mensch_tick(self):
            now = time.time()
            changed = []
            with self.rooms_lock:
                for room in list(self.rooms.values()):
                    g = room.get("mensch")
                    if g is not None and g.tick(now):
                        changed.append(room)
            for room in changed:
                self._mensch_push(room)

        def _mensch_push(self, room):
            """every member gets his own view (None = no game)"""
            now = time.time()
            with self.rooms_lock:
                g = room.get("mensch")
                views = {u: (g.view(u, now) if g is not None else None) for u in list(room["members"])}
            for u, v in views.items():
                with self.sessions_lock:
                    targets = [c for c in self.sessions.get(u, []) if c.alive and getattr(c, "room_id", None) == room["id"]]
                for c in targets:
                    c.send({"event": "room_mensch", "room": room["id"], "mensch": v})

        def _mensch_left(self, room, uid):
            """called when somebody really left the room (not just a connection blink)"""
            with self.rooms_lock:
                g = room.get("mensch")
                if g is None or uid not in g.players:
                    return
                g.leave(uid, time.time())
                if g.phase == "lobby" and not g.players:
                    room["mensch"] = None
            self._mensch_push(room)

        def op_room_mensch(self, conn, req):
            room = self._room_of(conn, req)
            self._room_guard(conn.uid, "mensch", 40, 10)
            a = req.get("a")
            uid = conn.uid
            now = time.time()
            if a not in ("get", "open", "join", "leave", "start", "roll", "move", "end"):
                raise Fail("درخواست نامعتبر")
            if a == "get":
                with self.rooms_lock:
                    g = room.get("mensch")
                    return {"mensch": g.view(uid, now) if g is not None else None}
            pawn = _pawn(req.get("pawn"))
            try:
                with self.rooms_lock:
                    g = room.get("mensch")
                    name = room["members"][uid]["name"]
                    if a == "open":
                        if g is None:
                            g = room["mensch"] = mn.Mensch(uid)
                        g.join(uid, name)
                    elif g is None:
                        raise Fail("بازی‌ای تو این اتاق نیست")
                    elif a == "join":
                        g.join(uid, name)
                    elif a == "leave":
                        g.leave(uid, now)
                        if g.phase == "lobby" and not g.players:
                            room["mensch"] = None
                    elif a == "start":
                        g.start(uid, now)
                    elif a == "roll":
                        g.roll(uid, now)
                    elif a == "move":
                        if pawn is None:
                            raise Fail("مهره نامعتبر")
                        g.move(uid, pawn, now)
                    elif a == "end":
                        if not (g.phase == "over" or uid == g.host or uid == room["host"]):
                            raise Fail("فقط سازنده‌ی بازی یا میزبان اتاق می‌تونه بازی رو ببنده")
                        room["mensch"] = None
            except mn.MenschError as e:
                raise Fail(str(e))
            self._mensch_push(room)
            with self.rooms_lock:
                g = room.get("mensch")
                return {"mensch": g.view(uid, time.time()) if g is not None else None}

    return MenschMixin
