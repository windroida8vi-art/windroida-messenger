"""Account of a friend deleted -> the chat stays; when I delete the chat it is erased from the server. Run: python test_deleted_account.py"""
import sys, tempfile, base64
from pathlib import Path
sys.path.insert(0, ".")
import common
tmp = Path(tempfile.mkdtemp()); common.DATA_DIR = tmp; common.UPLOADS_DIR = tmp/"u"; common.AVATARS_DIR = tmp/"a"; common.WALLPAPERS_DIR = tmp/"w"; common.ROOMAUDIO_DIR = tmp/"r"; common.FILES_DIR = tmp/"f"; (tmp/"f").mkdir()
import server as srv
import re, textwrap
from client_core import Client
S = srv.WindroidaServer("127.0.0.1", 0, db_path=tmp/"t.db", web_port=0); port = S.start()
S._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
PW = "Str0ng-pass1"; res = []
def ok(n, c, x=""): res.append(c); print(("  ok   " if c else "  FAIL ") + n, "" if c else x)
def cl(n):
    c = Client(); c.connect("127.0.0.1", port)
    r = c.call("register", username=n, password=PW, display_name=n, sec_question="سوال تستی؟", sec_answer="x1"); assert r["ok"], r
    c.uid = r["me"]["id"]; return c
A, B = cl("alice"), cl("bobby")
cid = A.call("open_private", username="bobby")["chat"]["id"]
A.call("send", chat_id=cid, text="salam")
B.call("send", chat_id=cid, text="hi")
r = B.call("send", chat_id=cid, text="file", file={"name": "a.txt", "data": base64.b64encode(b"hello").decode()})
fp = common.connect_db(tmp/"t.db").execute("SELECT file_path FROM messages WHERE file_path IS NOT NULL").fetchone()["file_path"]
ok("file stored", common.resolve_upload(fp) is not None)
# admin deletes bobby's account (same code as the datasheet window)
db = common.connect_db(tmp/"t.db")
# tkinter may be missing here: pull the two methods out of datasheet.py and run them on a plain class
src = open("datasheet.py", encoding="utf-8").read()
def meth(name):
    m = re.search(r"(    def %s\(.*?)(?=\n    def |\Z)" % name, src, re.S); return textwrap.dedent(m.group(1))
ns = {"remove_upload": common.remove_upload, "common": common}
exec(meth("_remove_files") + "\n" + meth("_delete_user"), ns)
class Fake: pass
f = Fake(); f.db = db
f._remove_files = lambda where, args=(): ns["_remove_files"](f, where, args)
with db:
    ns["_delete_user"](f, B.uid)
ch = [x for x in A.call("chats")["chats"] if x["id"] == cid]
ok("chat stays for alice", len(ch) == 1, ch)
ok("not shown as saved messages", ch and not ch[0]["saved"] and ch[0]["title"] == "حساب حذف‌شده", ch)
ok("alice still reads the history", len(A.call("history", chat_id=cid)["messages"]) >= 3)
ok("alice cannot write to a deleted account", not A.call("send", chat_id=cid, text="x").get("ok"))
ok("file still on server", common.resolve_upload(fp) is not None)
ok("alice deletes the chat", A.call("delete_contact", chat_id=cid)["ok"])
n = common.connect_db(tmp/"t.db").execute("SELECT COUNT(*) FROM messages").fetchone()[0]
ok("all messages erased from server", n == 0, n)
ok("chat erased", common.connect_db(tmp/"t.db").execute("SELECT COUNT(*) FROM chats WHERE id=?", (cid,)).fetchone()[0] == 0)
ok("file erased from server", common.resolve_upload(fp) is None)
ok("alice's own saved messages still work", A.call("send", chat_id=A.call("open_private", username="alice")["chat"]["id"], text="note")["ok"])
print(f"deleted-account: {sum(res)} ok, {len(res) - sum(res)} failed")
sys.exit(0 if all(res) else 1)
