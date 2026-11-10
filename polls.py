"""Polls (نظرسنجی) in chats: a poll is an ordinary message ("📊 question") whose meta carries {"poll": id}.

Rules (enforced here): only members of the chat see / vote / close it; 2-10 options; single or multiple choice; anonymous or
public voters; a vote can be changed or withdrawn until the poll is closed; only the creator or a group owner/admin closes it;
a closed or deleted poll takes no more votes; creating a poll is a normal message for silence / slow mode / channel rules.
Counts are public to the chat (they travel inside the message); WHO voted is shown only for non-anonymous polls."""
import json
import re

_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f‎‏‪-‮⁦-⁩]")
MAX_OPTIONS = 10
MAX_Q = 200
MAX_OPT = 100


def make_polls(Fail, common):
    now = common.now

    def _clean(t, n, what):
        if not isinstance(t, str):
            raise Fail(f"{what} نامعتبره")
        t = " ".join(_CTRL.sub("", t).split())
        if not t:
            raise Fail(f"{what} نمی‌تونه خالی باشه")
        if len(t) > n:
            raise Fail(f"{what} خیلی طولانیه (حداکثر {n} کاراکتر)")
        return t

    def _flag(v):
        if v in (None, False, 0):
            return 0
        if v is True or v == 1:
            return 1
        raise Fail("درخواست نامعتبر")

    class PollsMixin:
        def _poll_card(self, db, pid):
            p = db.execute("SELECT * FROM polls WHERE id=?", (pid,)).fetchone()
            if not p:
                return None
            opts = json.loads(p["options"])
            counts = [0] * len(opts)
            for r in db.execute("SELECT opt, COUNT(*) AS n FROM poll_votes WHERE poll_id=? GROUP BY opt", (pid,)):
                if 0 <= r["opt"] < len(counts):
                    counts[r["opt"]] = r["n"]
            voters = db.execute("SELECT COUNT(DISTINCT user_id) FROM poll_votes WHERE poll_id=?", (pid,)).fetchone()[0]
            return {"id": pid, "q": p["question"], "opts": opts, "counts": counts, "voters": voters, "multi": bool(p["multi"]),
                    "anon": bool(p["anon"]), "closed": bool(p["closed"]), "creator": p["creator_id"]}

        def _poll_load(self, conn, req):
            """the poll + my membership, only if the poll's message is alive and I am in its chat (one generic error otherwise)"""
            pid = req.get("poll_id")
            if isinstance(pid, bool) or not isinstance(pid, int) or not 0 < pid < 2 ** 62:
                raise Fail("نظرسنجی پیدا نشد")
            p = conn.db.execute("SELECT p.*, m.deleted AS mdel FROM polls p LEFT JOIN messages m ON m.id=p.msg_id WHERE p.id=?", (pid,)).fetchone()
            mem = conn.db.execute("SELECT role FROM members WHERE chat_id=? AND user_id=?", (p["chat_id"], conn.uid)).fetchone() if p else None
            if not p or not mem or p["msg_id"] is None or p["mdel"]:
                raise Fail("نظرسنجی پیدا نشد")
            return p, mem

        def _poll_push(self, db, p, exclude=None):
            msg = self._msg_by_id(db, p["msg_id"])
            self.push(self._member_ids(db, p["chat_id"]), {"event": "message_updated", "message": msg}, exclude=exclude)
            return msg

        # ------------------------------------------------------------------ ops
        def op_poll_create(self, conn, req):
            db = conn.db
            chat_id, _ = self._require_member(db, req.get("chat_id"), conn.uid)
            kind = db.execute("SELECT kind FROM chats WHERE id=?", (chat_id,)).fetchone()
            if not kind or kind["kind"] != "group":          # polls only exist in groups (and channels), not in private chats
                raise Fail("نظرسنجی فقط تو گروه‌ها ممکنه")
            self._room_guard(conn.uid, "pollc", 10, 60, "خیلی سریع؛ یه لحظه صبر کن")
            q = _clean(req.get("question"), MAX_Q, "سؤال")
            raw = req.get("options")
            if not isinstance(raw, list) or not 2 <= len(raw) <= MAX_OPTIONS:
                raise Fail(f"بین ۲ تا {MAX_OPTIONS} گزینه لازمه")
            opts = [_clean(o, MAX_OPT, "گزینه") for o in raw]
            if len({o.lower() for o in opts}) != len(opts):
                raise Fail("گزینه‌ها نباید تکراری باشن")
            multi, anon = _flag(req.get("multi")), _flag(req.get("anon"))
            if not self._can_post(db, chat_id, conn.uid):
                raise Fail("فقط مدیر می‌تونه تو این کانال پیام بذاره")
            with db:
                cur = db.execute("INSERT INTO polls(chat_id, creator_id, question, options, multi, anon, created) VALUES (?,?,?,?,?,?,?)",
                                 (chat_id, conn.uid, q, json.dumps(opts, ensure_ascii=False), multi, anon, now()))
            pid = cur.lastrowid
            try:
                msg = self._store_message(db, conn.uid, chat_id, "📊 " + q, None, meta={"poll": pid})
            except Exception:
                with db:
                    db.execute("DELETE FROM polls WHERE id=?", (pid,))
                raise
            with db:
                db.execute("UPDATE polls SET msg_id=? WHERE id=?", (msg["id"], pid))
            msg = self._msg_by_id(db, msg["id"])
            self._announce(db, chat_id, msg, conn.uid, exclude=conn)
            return {"message": msg}

        def op_poll_get(self, conn, req):
            p, mem = self._poll_load(conn, req)
            db = conn.db
            mine = [r["opt"] for r in db.execute("SELECT opt FROM poll_votes WHERE poll_id=? AND user_id=? ORDER BY opt", (p["id"], conn.uid))]
            out = {"poll": self._poll_card(db, p["id"]), "mine": mine}
            if req.get("voters") and not p["anon"]:
                names = {}
                for r in db.execute("SELECT v.opt, u.display_name FROM poll_votes v JOIN users u ON u.id=v.user_id "
                                    "WHERE v.poll_id=? ORDER BY v.opt, u.display_name LIMIT 500", (p["id"],)):
                    names.setdefault(r["opt"], []).append(r["display_name"])
                out["voters"] = {str(k): v for k, v in names.items()}
            return out

        def op_poll_vote(self, conn, req):
            p, mem = self._poll_load(conn, req)
            self._room_guard(conn.uid, "pollv", 60, 60, "خیلی سریع؛ یه لحظه صبر کن")
            db = conn.db
            n = len(json.loads(p["options"]))
            ch = req.get("options")
            if not isinstance(ch, list) or len(ch) > n or any(isinstance(x, bool) or not isinstance(x, int) or not 0 <= x < n for x in ch) \
                    or len(set(ch)) != len(ch):
                raise Fail("انتخاب نامعتبر")
            if len(ch) > 1 and not p["multi"]:
                raise Fail("این نظرسنجی فقط یک انتخاب داره")
            if p["closed"]:
                raise Fail("این نظرسنجی بسته شده")
            with db:
                db.execute("DELETE FROM poll_votes WHERE poll_id=? AND user_id=? AND EXISTS(SELECT 1 FROM polls WHERE id=? AND closed=0)",
                           (p["id"], conn.uid, p["id"]))
                for o in ch:
                    db.execute("INSERT INTO poll_votes(poll_id, user_id, opt) SELECT ?,?,? WHERE EXISTS(SELECT 1 FROM polls WHERE id=? AND closed=0)",
                               (p["id"], conn.uid, o, p["id"]))
            if db.execute("SELECT closed FROM polls WHERE id=?", (p["id"],)).fetchone()["closed"]:
                raise Fail("این نظرسنجی بسته شده")
            msg = self._poll_push(db, p, exclude=conn)
            return {"message": msg, "mine": sorted(ch)}

        def op_poll_close(self, conn, req):
            p, mem = self._poll_load(conn, req)
            self._room_guard(conn.uid, "pollx", 30, 60, "خیلی سریع؛ یه لحظه صبر کن")
            db = conn.db
            ch = db.execute("SELECT kind, channel FROM chats WHERE id=?", (p["chat_id"],)).fetchone()
            mgr = ch["kind"] == "group" and mem["role"] in ("owner", "admin")
            if p["creator_id"] != conn.uid and not mgr:
                raise Fail("فقط سازنده‌ی نظرسنجی یا ادمین گروه می‌تونه ببندتش")
            if p["closed"]:
                raise Fail("این نظرسنجی قبلاً بسته شده")
            with db:
                db.execute("UPDATE polls SET closed=1 WHERE id=?", (p["id"],))
            return {"message": self._poll_push(db, p, exclude=conn)}

    return PollsMixin
