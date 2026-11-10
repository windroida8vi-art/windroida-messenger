"""Group moderation: silence a member (for a while / for good), slow mode, ban (and unban).

Rules (all enforced here, on the server; the UI only shows the buttons):
* Only the owner and admins moderate; only in real groups (not channels, not private chats).
* Owner and admins are never restricted (mute / slow mode do not apply to them) and cannot be silenced; an admin can only
  moderate normal members, the owner can also ban an admin (and must demote him first to silence him).
* Silence and the slow-mode clock live in `group_limits`, which is keyed by (chat, user) and NOT by membership: leaving and
  rejoining does not reset them. Bans live in `group_bans`: a banned user cannot rejoin by link / @id or be added.
* Slow mode is checked and the clock advanced in the same transaction that stores the message (atomic upsert), so two
  parallel sends can never both pass.
"""
SLOW_CHOICES = (0, 10, 30, 60, 300, 900, 3600)
MUTE_CHOICES = (0, 3600, 86400, 604800, -1)          # 0 = lift, -1 = for good
FOREVER = 4102444800                                   # year 2100


def make_groupadmin(Fail, common):
    now = common.now

    def _label(secs):
        if secs == -1:
            return "برای همیشه"
        if secs % 86400 == 0:
            return f"{secs // 86400} روز"
        if secs % 3600 == 0:
            return f"{secs // 3600} ساعت"
        if secs % 60 == 0:
            return f"{secs // 60} دقیقه"
        return f"{secs} ثانیه"

    class GroupAdminMixin:
        # ------------------------------------------------------------------ helpers used by the rest of the server
        def _ga_muted_until(self, db, chat_id, uid):
            r = db.execute("SELECT muted_until FROM group_limits WHERE chat_id=? AND user_id=?", (chat_id, uid)).fetchone()
            t = r["muted_until"] if r else 0
            return t if t > now() else 0

        def _ga_gate(self, db, chat_id, uid):
            """Called before a user's message is stored. Raises if he is silenced; returns the slow-mode seconds that apply
            to him (0 = none) so the caller can advance the clock inside its own transaction."""
            c = db.execute("SELECT kind, channel, slow_secs FROM chats WHERE id=?", (chat_id,)).fetchone()
            if not c or c["kind"] != "group" or c["channel"]:
                return 0
            m = db.execute("SELECT role FROM members WHERE chat_id=? AND user_id=?", (chat_id, uid)).fetchone()
            if not m or m["role"] in ("owner", "admin"):
                return 0
            until = self._ga_muted_until(db, chat_id, uid)
            if until:
                if until >= FOREVER - 10:
                    raise Fail("ادمین گروه تو رو ساکت کرده؛ نمی‌تونی پیام بذاری")
                left = until - now()
                raise Fail("ادمین گروه تو رو ساکت کرده؛ " + (f"{(left + 59) // 60} دقیقه‌ی دیگه" if left < 3600 else f"{(left + 3599) // 3600} ساعت دیگه") + " می‌تونی پیام بذاری")
            return c["slow_secs"] or 0

        def _ga_slow_hit(self, db, chat_id, uid, slow):
            """Advance the member's slow-mode clock (call INSIDE the transaction that inserts the message)."""
            t = now()
            n = db.execute("INSERT INTO group_limits(chat_id, user_id, last_post) VALUES (?,?,?) "
                           "ON CONFLICT(chat_id, user_id) DO UPDATE SET last_post=excluded.last_post "
                           "WHERE group_limits.last_post <= ?", (chat_id, uid, t, t - slow)).rowcount
            if not n:
                r = db.execute("SELECT last_post FROM group_limits WHERE chat_id=? AND user_id=?", (chat_id, uid)).fetchone()
                left = max(1, slow - (t - (r["last_post"] if r else 0)))
                raise Fail(f"حالت آهسته روشنه؛ {left} ثانیه‌ی دیگه می‌تونی پیام بذاری")

        def _ga_banned(self, db, chat_id, uid):
            return db.execute("SELECT 1 FROM group_bans WHERE chat_id=? AND user_id=?", (chat_id, uid)).fetchone() is not None

        # ------------------------------------------------------------------ permission helper for the ops below
        def _ga_manager(self, conn, req):
            self._room_guard(conn.uid, "gadmin", 80, 60, "خیلی سریع؛ یه لحظه صبر کن")
            chat_id, me = self._require_member(conn.db, req.get("chat_id"), conn.uid)
            chat = conn.db.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()
            if chat["kind"] != "group" or chat["channel"]:
                raise Fail("این کار فقط تو گروه ممکنه")
            if me["role"] not in ("owner", "admin"):
                raise Fail("فقط سازنده یا ادمین گروه می‌تونه این کار رو بکنه")
            return chat_id, me, chat

        @staticmethod
        def _ga_uid(req):
            v = req.get("user_id")
            if isinstance(v, bool) or not isinstance(v, int) or v <= 0 or v > 2 ** 62:
                raise Fail("کاربر نامعتبر")
            return v

        def _ga_name(self, db, uid):
            r = db.execute("SELECT display_name FROM users WHERE id=?", (uid,)).fetchone()
            return r["display_name"] if r else "کاربر"

        def _ga_refresh(self, db, chat_id, uid=None):
            """tell everybody the member list changed and the affected user (or everybody) that the chat's state changed"""
            ids = self._member_ids(db, chat_id)
            self.push(ids, {"event": "members_changed", "chat_id": chat_id})
            for m in ids if uid is None else [uid]:
                v = self._chat_view(db, chat_id, m)
                if v:
                    self.push([m], {"event": "chat_updated", "chat": v})

        # ------------------------------------------------------------------ ops
        def op_set_slow(self, conn, req):
            chat_id, me, chat = self._ga_manager(conn, req)
            secs = req.get("secs")
            if isinstance(secs, bool) or secs not in SLOW_CHOICES:
                raise Fail("این مقدار برای حالت آهسته مجاز نیست")
            if secs != (chat["slow_secs"] or 0):
                with conn.db:
                    conn.db.execute("UPDATE chats SET slow_secs=? WHERE id=?", (secs, chat_id))
                name = self._ga_name(conn.db, conn.uid)
                self._system_message(conn.db, chat_id, f"{name} حالت آهسته رو " + (f"روشن کرد ({_label(secs)})" if secs else "خاموش کرد"))
                self._ga_refresh(conn.db, chat_id)
            return {"slow": secs}

        def op_mute_member(self, conn, req):
            chat_id, me, chat = self._ga_manager(conn, req)
            uid = self._ga_uid(req)
            secs = req.get("secs")
            if isinstance(secs, bool) or secs not in MUTE_CHOICES:
                raise Fail("مدت نامعتبر")
            if uid == conn.uid:
                raise Fail("نمی‌تونی خودت رو ساکت کنی")
            t = conn.db.execute("SELECT role FROM members WHERE chat_id=? AND user_id=?", (chat_id, uid)).fetchone()
            if not t:
                raise Fail("این کاربر عضو گروه نیست")
            if t["role"] in ("owner", "admin"):
                raise Fail("ادمین یا سازنده رو نمی‌شه ساکت کرد")
            until = 0 if secs == 0 else FOREVER if secs == -1 else now() + secs
            with conn.db:
                conn.db.execute("INSERT INTO group_limits(chat_id, user_id, muted_until) VALUES (?,?,?) "
                                "ON CONFLICT(chat_id, user_id) DO UPDATE SET muted_until=excluded.muted_until", (chat_id, uid, until))
            name = self._ga_name(conn.db, uid)
            self._system_message(conn.db, chat_id, f"{name} ساکت شد ({_label(secs)})" if secs else f"{name} دوباره می‌تونه پیام بذاره")
            self._ga_refresh(conn.db, chat_id, uid)
            return {"muted_until": until}

        def op_ban_member(self, conn, req):
            chat_id, me, chat = self._ga_manager(conn, req)
            uid = self._ga_uid(req)
            if uid == conn.uid:
                raise Fail("نمی‌تونی خودت رو مسدود کنی")
            t = conn.db.execute("SELECT role FROM members WHERE chat_id=? AND user_id=?", (chat_id, uid)).fetchone()
            if t is None:
                if not conn.db.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
                    raise Fail("کاربر نامعتبر")
            elif t["role"] == "owner" or (t["role"] == "admin" and me["role"] != "owner"):
                raise Fail("ادمین‌ها رو فقط سازنده گروه می‌تونه مسدود کنه")
            if self._ga_banned(conn.db, chat_id, uid):
                raise Fail("این کاربر قبلاً مسدود شده")
            name = self._ga_name(conn.db, uid)
            with conn.db:
                conn.db.execute("INSERT INTO group_bans(chat_id, user_id, by_id, at) VALUES (?,?,?,?)", (chat_id, uid, conn.uid, now()))
                conn.db.execute("DELETE FROM members WHERE chat_id=? AND user_id=?", (chat_id, uid))
            if t is not None:
                self.push([uid], {"event": "chat_removed", "chat_id": chat_id})
                self._system_message(conn.db, chat_id, f"{name} از گروه مسدود شد")
                self.push(self._member_ids(conn.db, chat_id), {"event": "members_changed", "chat_id": chat_id})
            return {}

        def op_unban_member(self, conn, req):
            chat_id, me, chat = self._ga_manager(conn, req)
            uid = self._ga_uid(req)
            with conn.db:
                n = conn.db.execute("DELETE FROM group_bans WHERE chat_id=? AND user_id=?", (chat_id, uid)).rowcount
            if not n:
                raise Fail("این کاربر مسدود نیست")
            return {}

        def op_bans(self, conn, req):
            chat_id, me, chat = self._ga_manager(conn, req)
            rows = conn.db.execute("SELECT u.id, u.username, u.display_name, b.at FROM group_bans b JOIN users u ON u.id=b.user_id "
                                   "WHERE b.chat_id=? ORDER BY b.at DESC LIMIT 200", (chat_id,)).fetchall()
            return {"bans": [dict(id=r["id"], username=r["username"], display_name=r["display_name"], at=r["at"]) for r in rows]}

    return GroupAdminMixin
