"""Chess games between chat members. The server is the only judge: a client may only *ask* for a move, and the move is
accepted only if (a) the sender is a player of this game, (b) it is his turn, (c) the game is active, (d) the move is
among the engine's legal moves for the stored position, (e) the client's idea of the move number matches the server's
(no double / stale moves). Everything lives in the `games` table, so a game survives restarts and reconnects.

Chat integration: an invitation is an ordinary text message whose `meta` carries {"game": id}; clients draw it as a card.
"""
import hashlib
import json
import re

UCI_RE = re.compile(r"^[a-h][1-8][a-h][1-8][qrbn]?$")
MAX_PLIES = 600            # absolute safety cap (a draw is declared)
MAX_ACTIVE = 12            # unfinished games per user
MAX_PENDING = 6            # open invitations per user


def make_games(Fail, common, chess):
    now = common.now

    def _h(pos):
        return hashlib.md5(pos.key().encode()).hexdigest()[:12]

    class GamesMixin:
        # ------------------------------------------------------------------ helpers
        def _g_id(self, v):
            try:
                gid = int(v)
            except (TypeError, ValueError):
                raise Fail("بازی نامعتبر")
            if gid <= 0 or gid > 2 ** 62:
                raise Fail("بازی نامعتبر")
            return gid

        def _g_load(self, db, gid, uid):
            """The game, only if `uid` is a member of its chat (same generic error for 'missing' and 'not yours')."""
            gid = self._g_id(gid)
            g = db.execute("SELECT * FROM games WHERE id=?", (gid,)).fetchone()
            if not g or not self._g_can_see(db, g, uid):
                raise Fail("بازی پیدا نشد")
            return g

        def _g_room_members(self, g):
            """Users who are in the game's watch-room right now (they may watch)."""
            if not g["room_id"]:
                return set()
            room = self._room_get(g["room_id"])
            return set(room["members"]) if room else set()

        def _g_can_see(self, db, g, uid):
            if uid in (g["white_id"], g["black_id"], g["inviter_id"], g["invitee_id"]) and uid:
                return True
            if g["chat_id"] is not None and db.execute("SELECT 1 FROM members WHERE chat_id=? AND user_id=?",
                                                       (g["chat_id"], uid)).fetchone():
                return True
            return uid in self._g_room_members(g)

        @staticmethod
        def _g_json(s, default):
            try:
                v = json.loads(s) if s else default
                return v if isinstance(v, type(default)) else default
            except ValueError:
                return default

        def _g_user(self, db, uid):
            if not uid:
                return {"id": None, "name": "کاربر حذف‌شده", "avatar_at": 0}
            r = db.execute("SELECT id, display_name, avatar_at FROM users WHERE id=?", (uid,)).fetchone()
            return {"id": r["id"], "name": r["display_name"], "avatar_at": r["avatar_at"]} if r else \
                {"id": None, "name": "کاربر حذف‌شده", "avatar_at": 0}

        def _g_card(self, db, gid):
            """Small public summary drawn inside the chat bubble."""
            g = db.execute("SELECT * FROM games WHERE id=?", (gid,)).fetchone()
            if not g:
                return None
            moves = self._g_json(g["moves"], [])
            inv = self._g_user(db, g["inviter_id"])
            return {"id": g["id"], "kind": "chess", "status": g["status"], "inviter": inv["name"],
                    "white": self._g_user(db, g["white_id"])["name"] if g["white_id"] else None,
                    "black": self._g_user(db, g["black_id"])["name"] if g["black_id"] else None,
                    "result": g["result"], "reason": g["reason"], "plies": len(moves), "fen": g["fen"]}

        def _g_view(self, db, g, uid):
            pos = chess.Position.from_fen(g["fen"])
            moves = self._g_json(g["moves"], [])
            sans = self._g_json(g["sans"], [])
            you = "w" if uid == g["white_id"] else "b" if uid == g["black_id"] else None
            turn = "w" if pos.turn else "b"
            v = {"id": g["id"], "chat_id": g["chat_id"], "kind": "chess", "status": g["status"],
                 "inviter_id": g["inviter_id"], "inviter": self._g_user(db, g["inviter_id"])["name"], "white": self._g_user(db, g["white_id"]) if g["white_id"] else None,
                 "black": self._g_user(db, g["black_id"]) if g["black_id"] else None,
                 "invite_color": g["invite_color"], "fen": g["fen"], "turn": turn, "ply": len(moves), "sans": sans,
                 "last": moves[-1] if moves else None, "result": g["result"], "reason": g["reason"],
                 "check": pos.in_check() and g["status"] == "active", "you": you, "draw_offer": g["draw_offer"], "invitee_id": g["invitee_id"], "room": g["room_id"],
                 "created": g["created"], "updated": g["updated"], "legal": {}}
            if g["status"] == "active" and you == turn:
                legal = {}
                for m in pos.legal_moves():
                    legal.setdefault(chess.sq_name(m[0]), [])
                    t = chess.sq_name(m[1])
                    if t not in legal[chess.sq_name(m[0])]:
                        legal[chess.sq_name(m[0])].append(t)
                v["legal"] = legal
            return v

        def _g_push(self, db, g, exclude=None):
            """Each player gets his own view (the one to move also gets the list of legal moves)."""
            for uid in {g["white_id"], g["black_id"], g["inviter_id"], g["invitee_id"]} | self._g_room_members(g):
                if uid:
                    self.push([uid], {"event": "game", "game": self._g_view(db, g, uid)}, exclude=exclude)

        def _g_refresh_card(self, db, g):
            if g["msg_id"]:
                msg = self._msg_by_id(db, g["msg_id"])
                if msg:
                    self.push(self._member_ids(db, g["chat_id"]), {"event": "message_updated", "message": msg})

        def _g_save(self, db, g, **upd):
            """Optimistic update: succeeds only if nobody changed the game since we read it."""
            cols = ", ".join(f"{k}=?" for k in upd)
            with db:
                n = db.execute(f"UPDATE games SET {cols}, seq=seq+1, updated=? WHERE id=? AND seq=?",
                               (*upd.values(), now(), g["id"], g["seq"])).rowcount
            if not n:
                raise Fail("بازی همین الان تغییر کرد؛ دوباره امتحان کن")
            return db.execute("SELECT * FROM games WHERE id=?", (g["id"],)).fetchone()

        def _g_limit(self, uid, bucket, limit, window):
            if not self._room_hits((bucket, uid), limit, window):
                raise Fail("خیلی سریع؛ یه لحظه صبر کن")

        # --------------------------------------------------------------------- ops
        def op_game_invite(self, conn, req):
            db = conn.db
            chat_id, _ = self._require_member(db, req.get("chat_id"), conn.uid)
            self._g_limit(conn.uid, "ginv", 10, 60)
            color = req.get("color")
            if color not in ("white", "black", "random"):
                color = "random"
            c = db.execute("SELECT kind, channel FROM chats WHERE id=?", (chat_id,)).fetchone()
            if not c or c["channel"]:
                raise Fail("تو کانال نمی‌شه بازی کرد")
            if c["kind"] == "private" and db.execute("SELECT COUNT(*) FROM members WHERE chat_id=?", (chat_id,)).fetchone()[0] < 2:
                raise Fail("برای بازی یه نفر دیگه لازمه")
            self._check_not_blocked_private(db, chat_id, conn.uid)
            if not self._can_post(db, chat_id, conn.uid):
                raise Fail("اینجا نمی‌تونی بازی بسازی")
            mine = db.execute("SELECT COUNT(*) FROM games WHERE inviter_id=? AND status='invite'", (conn.uid,)).fetchone()[0]
            if mine >= MAX_PENDING:
                raise Fail("چند دعوت بی‌جواب داری؛ اول یکی‌شون رو لغو کن")
            active = db.execute("SELECT COUNT(*) FROM games WHERE status='active' AND (white_id=? OR black_id=?)",
                                (conn.uid, conn.uid)).fetchone()[0]
            if active >= MAX_ACTIVE:
                raise Fail("چند بازی نیمه‌کاره داری؛ اول یکی‌شون رو تموم کن")
            with db:
                cur = db.execute("INSERT INTO games(chat_id, kind, inviter_id, invite_color, status, fen, moves, sans, reps, "
                                 "created, updated) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                 (chat_id, "chess", conn.uid, color, "invite", chess.START_FEN, "[]", "[]", "[]", now(), now()))
            gid = cur.lastrowid
            try:
                msg = self._store_message(db, conn.uid, chat_id, "♟ دعوت به بازی شطرنج", None, meta={"game": gid})
            except Exception:
                with db:
                    db.execute("DELETE FROM games WHERE id=?", (gid,))
                raise
            with db:
                db.execute("UPDATE games SET msg_id=? WHERE id=?", (msg["id"], gid))
            g = db.execute("SELECT * FROM games WHERE id=?", (gid,)).fetchone()
            msg = self._msg_by_id(db, msg["id"])
            self._announce(db, chat_id, msg, conn.uid, exclude=conn)
            return {"message": msg, "game": self._g_view(db, g, conn.uid)}

        def op_game_accept(self, conn, req):
            db = conn.db
            g = self._g_load(db, req.get("game_id"), conn.uid)
            self._g_limit(conn.uid, "gacc", 20, 60)
            if g["status"] != "invite":
                raise Fail("این دعوت دیگه معتبر نیست")
            if g["inviter_id"] == conn.uid:
                raise Fail("دعوت خودته؛ منتظر حریف بمون")
            if g["invitee_id"] and g["invitee_id"] != conn.uid:
                raise Fail("این دعوت برای کس دیگه‌ایه")
            if g["chat_id"] is not None:
                self._check_not_blocked_private(db, g["chat_id"], conn.uid)
            elif self._is_blocked(db, g["inviter_id"], conn.uid) or self._is_blocked(db, conn.uid, g["inviter_id"]):
                raise Fail("این دعوت دیگه معتبر نیست")
            active = db.execute("SELECT COUNT(*) FROM games WHERE status='active' AND (white_id=? OR black_id=?)",
                                (conn.uid, conn.uid)).fetchone()[0]
            if active >= MAX_ACTIVE:
                raise Fail("چند بازی نیمه‌کاره داری؛ اول یکی‌شون رو تموم کن")
            inviter = g["inviter_id"]
            color = g["invite_color"]
            if color == "random":
                color = "white" if self._rand_bit() else "black"
            white, black = (inviter, conn.uid) if color == "white" else (conn.uid, inviter)
            g = self._g_save(db, g, status="active", white_id=white, black_id=black)
            self._g_push(db, g)
            self._g_refresh_card(db, g)
            return {"game": self._g_view(db, g, conn.uid)}

        @staticmethod
        def _rand_bit():
            import secrets
            return secrets.randbelow(2)

        def op_game_cancel(self, conn, req):
            """Inviter withdraws, or the invited person declines (only while the game has not started)."""
            db = conn.db
            g = self._g_load(db, req.get("game_id"), conn.uid)
            if g["status"] != "invite":
                raise Fail("این دعوت دیگه معتبر نیست")
            if g["chat_id"] is not None:
                kind = db.execute("SELECT kind FROM chats WHERE id=?", (g["chat_id"],)).fetchone()["kind"]
            else:
                kind = "private" if g["invitee_id"] == conn.uid else "room"
            if g["inviter_id"] != conn.uid and kind != "private":
                raise Fail("فقط خودِ دعوت‌کننده می‌تونه دعوت رو لغو کنه")
            g = self._g_save(db, g, status="cancelled")
            self._g_push(db, g)
            self._g_refresh_card(db, g)
            return {"game": self._g_view(db, g, conn.uid)}

        def op_game_get(self, conn, req):
            g = self._g_load(conn.db, req.get("game_id"), conn.uid)
            return {"game": self._g_view(conn.db, g, conn.uid)}

        def op_game_list(self, conn, req):
            db = conn.db
            chat_id, _ = self._require_member(db, req.get("chat_id"), conn.uid)
            rows = db.execute("SELECT * FROM games WHERE chat_id=? AND status IN ('invite','active') ORDER BY id DESC LIMIT 30",
                              (chat_id,)).fetchall()
            return {"games": [self._g_view(db, g, conn.uid) for g in rows]}

        def op_game_mine(self, conn, req):
            """Everything unfinished that I play in (for the 'my games' list)."""
            db = conn.db
            rows = db.execute("SELECT * FROM games WHERE status='active' AND (white_id=? OR black_id=?) "
                              "ORDER BY updated DESC LIMIT 30", (conn.uid, conn.uid)).fetchall()
            return {"games": [self._g_view(db, g, conn.uid) for g in rows]}

        def _g_finish(self, db, g, result, reason, extra=None):
            upd = dict(status="finished", result=result, reason=reason, draw_offer=None)
            upd.update(extra or {})
            g = self._g_save(db, g, **upd)
            w, b = self._g_user(db, g["white_id"])["name"], self._g_user(db, g["black_id"])["name"]
            why = {"checkmate": "مات", "stalemate": "پات (بی‌حرکت)", "insufficient": "مهره‌ی کافی نیست", "fifty": "قانون ۵۰ حرکت",
                   "repetition": "تکرار سه‌باره", "resign": "تسلیم", "agreed": "توافق", "maxlen": "طولانی‌شدن بازی"}.get(reason, reason)
            score = {"1-0": "۱–۰", "0-1": "۰–۱", "1/2-1/2": "½–½"}.get(result, result)
            if g["chat_id"] is not None:
                self._system_message(db, g["chat_id"], f"♟ {w} در برابر {b}: {score} ({why})")
            self._g_push(db, g)
            self._g_refresh_card(db, g)
            return g

        def op_game_move(self, conn, req):
            db = conn.db
            g = self._g_load(db, req.get("game_id"), conn.uid)
            self._g_limit(conn.uid, "gmove", 120, 60)
            uci = req.get("move")
            if not isinstance(uci, str) or len(uci) > 5 or not UCI_RE.fullmatch(uci.lower()):
                raise Fail("حرکت نامعتبر")
            if g["status"] != "active":
                raise Fail("این بازی فعال نیست")
            moves = self._g_json(g["moves"], [])
            try:
                ply = int(req.get("ply"))
            except (TypeError, ValueError):
                raise Fail("حرکت نامعتبر")
            if ply != len(moves):
                raise Fail("نوبت یا وضعیت بازی عوض شده؛ صفحه رو تازه کن")
            pos = chess.Position.from_fen(g["fen"])
            mover = g["white_id"] if pos.turn else g["black_id"]
            if conn.uid != mover:
                raise Fail("نوبت تو نیست")
            m = pos.parse_uci(uci.lower())
            if m is None:
                raise Fail("این حرکت مجاز نیست")
            san = pos.san(m)
            new = pos.make(m)
            sans = self._g_json(g["sans"], [])
            reps = self._g_json(g["reps"], [])
            reps.append(_h(new))
            moves.append(chess.Position.uci(m))
            sans.append(san)
            out = chess.outcome(new, [new.key()] * reps.count(_h(new)))
            if out is None and len(moves) >= MAX_PLIES:
                out = ("1/2-1/2", "maxlen")
            g = self._g_save(db, g, fen=new.fen(), moves=json.dumps(moves), sans=json.dumps(sans, ensure_ascii=False),
                             reps=json.dumps(reps), draw_offer=None)
            if out:
                g = self._g_finish(db, g, out[0], out[1])
            else:
                self._g_push(db, g)
            return {"game": self._g_view(db, g, conn.uid)}

        def _g_player(self, g, uid):
            if uid not in (g["white_id"], g["black_id"]) or not uid:
                raise Fail("تو بازیکن این بازی نیستی")

        def op_game_resign(self, conn, req):
            db = conn.db
            g = self._g_load(db, req.get("game_id"), conn.uid)
            self._g_player(g, conn.uid)
            if g["status"] != "active":
                raise Fail("این بازی فعال نیست")
            g = self._g_finish(db, g, "0-1" if conn.uid == g["white_id"] else "1-0", "resign")
            return {"game": self._g_view(db, g, conn.uid)}

        def op_game_draw(self, conn, req):
            """action: offer | accept | decline"""
            db = conn.db
            g = self._g_load(db, req.get("game_id"), conn.uid)
            self._g_player(g, conn.uid)
            self._g_limit(conn.uid, "gdraw", 20, 60)
            if g["status"] != "active":
                raise Fail("این بازی فعال نیست")
            act = req.get("action")
            if act == "offer":
                if g["draw_offer"]:
                    raise Fail("پیشنهاد مساوی قبلاً داده شده")
                g = self._g_save(db, g, draw_offer=conn.uid)
                self._g_push(db, g)
            elif act in ("accept", "decline"):
                if not g["draw_offer"] or g["draw_offer"] == conn.uid:
                    raise Fail("پیشنهاد مساوی‌ای برای جواب دادن نیست")
                if act == "accept":
                    g = self._g_finish(db, g, "1/2-1/2", "agreed")
                else:
                    g = self._g_save(db, g, draw_offer=None)
                    self._g_push(db, g)
            else:
                raise Fail("درخواست نامعتبر")
            return {"game": self._g_view(db, g, conn.uid)}

        # ---- games inside a watch-room: two room members play, everybody else in the room watches
        def op_room_game_invite(self, conn, req):
            db = conn.db
            room = self._room_of(conn, req)
            self._g_limit(conn.uid, "rginv", 10, 60)
            try:
                opp = int(req.get("user_id"))
            except (TypeError, ValueError):
                raise Fail("حریف نامعتبر")
            if opp == conn.uid or opp not in room["members"]:
                raise Fail("حریف باید توی همین اتاق باشه")
            if self._is_blocked(db, opp, conn.uid) or self._is_blocked(db, conn.uid, opp):
                raise Fail("نمی‌تونی این کاربر رو دعوت کنی")
            color = req.get("color")
            if color not in ("white", "black", "random"):
                color = "random"
            if db.execute("SELECT COUNT(*) FROM games WHERE room_id=? AND status IN ('invite','active')", (room["id"],)).fetchone()[0] >= 3:
                raise Fail("توی این اتاق چند بازی در جریانه؛ بعد از تموم‌شدنشون ادامه بده")
            if db.execute("SELECT COUNT(*) FROM games WHERE inviter_id=? AND status='invite'", (conn.uid,)).fetchone()[0] >= MAX_PENDING:
                raise Fail("چند دعوت بی‌جواب داری؛ اول یکی‌شون رو لغو کن")
            if db.execute("SELECT COUNT(*) FROM games WHERE status='active' AND (white_id=? OR black_id=?)",
                          (conn.uid, conn.uid)).fetchone()[0] >= MAX_ACTIVE:
                raise Fail("چند بازی نیمه‌کاره داری؛ اول یکی‌شون رو تموم کن")
            with db:
                cur = db.execute("INSERT INTO games(chat_id, room_id, invitee_id, kind, inviter_id, invite_color, status, fen, moves, "
                                 "sans, reps, created, updated) VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?)",
                                 (room["id"], opp, "chess", conn.uid, color, "invite", chess.START_FEN, "[]", "[]", "[]", now(), now()))
            g = db.execute("SELECT * FROM games WHERE id=?", (cur.lastrowid,)).fetchone()
            self._g_push(db, g, exclude=conn)
            return {"game": self._g_view(db, g, conn.uid)}

        def op_room_games(self, conn, req):
            db = conn.db
            room = self._room_of(conn, req)
            rows = db.execute("SELECT * FROM games WHERE room_id=? AND status IN ('invite','active') ORDER BY id DESC LIMIT 10",
                              (room["id"],)).fetchall()
            return {"games": [self._g_view(db, g, conn.uid) for g in rows]}

        def _game_on_message_deleted(self, db, row):
            """If the sender deletes an invitation message, the still-unanswered invitation is withdrawn."""
            try:
                meta = json.loads(row["meta"]) if row["meta"] else {}
            except ValueError:
                return
            gid = meta.get("game") if isinstance(meta, dict) else None
            if isinstance(gid, int):
                g = db.execute("SELECT * FROM games WHERE id=? AND status='invite'", (gid,)).fetchone()
                if g:
                    g = self._g_save(db, g, status="cancelled")
                    self._g_push(db, g)

    return GamesMixin
