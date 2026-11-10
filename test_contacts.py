"""Delete a contact (hides the private chat's history for ONE user only). Run: python test_contacts.py"""
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
for t in ("salam", "khoobi?", "man alice am"): A.call("send", chat_id=cid, text=t)
B.call("send", chat_id=cid, text="mersi")
ids = lambda c: [x["id"] for x in c.call("chats")["chats"]]
ok("both have the chat", cid in ids(A) and cid in ids(B))
ok("bobby is alice's contact", S._is_contact(S_db := common.connect_db(tmp/"t.db"), A.uid, B.uid))
ok("outsider cannot delete", not M.call("delete_contact", chat_id=cid).get("ok"))
ok("bad id refused", not A.call("delete_contact", chat_id="x").get("ok"))
sv = A.call("open_private", username="alice")["chat"]["id"]
ok("saved messages cannot be deleted", not A.call("delete_contact", chat_id=sv).get("ok"))
grp = A.call("create_group", title="g", usernames=["bobby"])["chat"]["id"]
ok("a group is not a contact", not A.call("delete_contact", chat_id=grp).get("ok"))
ok("alice deletes bobby", A.call("delete_contact", chat_id=cid)["ok"])
ok("chat gone from alice's list", cid not in ids(A))
ok("chat still in bobby's list with all messages", cid in ids(B) and len(B.call("history", chat_id=cid)["messages"]) >= 4)
ok("alice's history is empty", A.call("history", chat_id=cid)["messages"] == [])
ok("alice's search finds nothing", A.call("search_messages", chat_id=cid, q="salam")["messages"] == [] and not any(r["chat_id"] == cid for r in A.call("search_all", q="salam")["results"]))
ok("bobby still finds it", len(B.call("search_messages", chat_id=cid, q="salam")["messages"]) == 1)
ok("no longer a contact for alice's privacy", not S._is_contact(S_db, A.uid, B.uid))
ok("alice is still a contact for bobby", S._is_contact(S_db, B.uid, A.uid))
r = A.call("open_private", username="bobby")["chat"]; ok("alice can re-open it: empty, no unread", r["last"] is None and r["unread"] == 0 and cid not in ids(A), r)
B.call("send", chat_id=cid, text="alice, are you there?")
ch = [x for x in A.call("chats")["chats"] if x["id"] == cid]
ok("a new message brings the chat back", len(ch) == 1 and ch[0]["unread"] == 1 and ch[0]["last"]["body"] == "alice, are you there?", ch)
h = A.call("history", chat_id=cid)["messages"]
ok("only the new message is visible", [m["body"] for m in h] == ["alice, are you there?"], h)
ok("alice can write again", A.call("send", chat_id=cid, text="here")["ok"])
print(f"contacts: {sum(res)} ok, {len(res) - sum(res)} failed")
sys.exit(0 if all(res) else 1)
