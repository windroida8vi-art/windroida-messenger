"""Personal bookmarks with categories + search filters. Run: python test_marks.py"""
import sys, tempfile, time
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
    c.uid = r["me"]["id"]; return c
A, B, M = cl("alice"), cl("bobby"), cl("mallory")
cid = A.call("open_private", username="bobby")["chat"]["id"]
m1 = A.call("send", chat_id=cid, text="رمز وای‌فای: 1234")["message"]["id"]
m2 = B.call("send", chat_id=cid, text="سلام چطوری")["message"]["id"]
m3 = B.call("send", chat_id=cid, text="آدرس: خیابان آزادی")["message"]["id"]
print("== bookmarks")
ok("empty at first", A.call("marks")["marks"] == [])
r = A.call("mark_set", message_id=m1, tag="مهم", note="یادم نره"); ok("mark with tag+note", r["ok"] and r["mark"]["tag"] == "مهم", r)
ok("mark a message of the other person", A.call("mark_set", message_id=m3, tag="آدرس")["ok"])
ok("outsider cannot mark", not M.call("mark_set", message_id=m1).get("ok"))
ok("bad id refused", not A.call("mark_set", message_id="x").get("ok") and not A.call("mark_set", message_id=999999).get("ok"))
ok("overlong tag refused", not A.call("mark_set", message_id=m2, tag="x" * 50).get("ok"))
mk = A.call("marks")["marks"]
ok("list has both, newest first", [x["id"] for x in mk] == [m3, m1] and mk[1]["note"] == "یادم نره" and mk[1]["text"].startswith("رمز"), mk)
ok("bobby's marks are separate", B.call("marks")["marks"] == [])
ok("re-mark updates", A.call("mark_set", message_id=m1, tag="کار", note="")["ok"] and [x for x in A.call("marks")["marks"] if x["id"] == m1][0]["tag"] == "کار")
ok("no duplicate", len(A.call("marks")["marks"]) == 2)
B.call("delete", message_id=m3)
ok("deleted message disappears from marks", [x["id"] for x in A.call("marks")["marks"]] == [m1])
ok("remove", A.call("mark_remove", message_id=m1)["ok"] and A.call("marks")["marks"] == [])
A.call("mark_set", message_id=m1, tag="t")
A.call("delete_contact", chat_id=cid)
ok("deleting the contact hides its marks", A.call("marks")["marks"] == [])
print("== search filters")
now = int(time.time())
ok("sender filter in chat", [x["id"] for x in B.call("search_messages", chat_id=cid, sender_id=A.uid)["messages"]] == [m1])
ok("sender + text", B.call("search_messages", chat_id=cid, q="سلام", sender_id=A.uid)["messages"] == [])
ok("date range in chat", len(B.call("search_messages", chat_id=cid, from_ts=now - 60, to_ts=now + 60)["messages"]) >= 1)
ok("past range is empty", B.call("search_messages", chat_id=cid, from_ts=1000, to_ts=2000)["messages"] == [])
ok("garbage dates ignored", B.call("search_messages", chat_id=cid, from_ts="x", to_ts=-5)["messages"] == [])
ok("global by sender name", any(r["chat_id"] == cid for r in B.call("search_all", sender="alice")["results"]))
ok("global sender + text", B.call("search_all", q="سلام", sender="alice")["results"] == [])
ok("global wildcard is literal", B.call("search_all", sender="%")["results"] == [])
ok("global by date", len(B.call("search_all", from_ts=now - 60, to_ts=now + 60)["results"]) >= 1)
ok("outsider sees nothing", M.call("search_all", sender="alice")["results"] == [] and not M.call("search_messages", chat_id=cid, q="سلام").get("ok"))
print(f"marks: {sum(res)} ok, {len(res) - sum(res)} failed")
sys.exit(0 if all(res) else 1)
