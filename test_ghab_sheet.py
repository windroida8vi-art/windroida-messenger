"""Datasheet's Ghab tabs without a GUI: tkinter is replaced by a stub, so only the data/delete/ban/link logic runs. Run: python test_ghab_sheet.py"""
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import types
from pathlib import Path
from unittest import mock

here = Path(__file__).resolve().parent
# --- stub tkinter + ui_kit (no display here)
tk = types.ModuleType("tkinter")
tk.Tk = type("Tk", (), {})
tk.Toplevel = tk.Frame = tk.Label = tk.Text = tk.Menu = tk.StringVar = tk.BooleanVar = object
tkf, tkm, tkt = types.ModuleType("tkinter.filedialog"), types.ModuleType("tkinter.messagebox"), types.ModuleType("tkinter.ttk")
sys.modules.update({"tkinter": tk, "tkinter.filedialog": tkf, "tkinter.messagebox": tkm, "tkinter.ttk": tkt,
                    "tkinter.simpledialog": types.ModuleType("tkinter.simpledialog")})
tk.filedialog, tk.messagebox, tk.ttk = tkf, tkm, tkt
ui = types.ModuleType("ui_kit")
for n in ("T", "Dialog", "FlatButton", "font", "gregorian_to_jalali", "init_fonts", "make_entry", "set_theme"):
    setattr(ui, n, mock.MagicMock())
ui.fa = lambda x: str(x)
sys.modules["ui_kit"] = ui
sys.path.insert(0, str(here))
import datasheet  # noqa: E402

ok = bad = 0


def check(name, cond):
    global ok, bad
    if cond:
        ok += 1
    else:
        bad += 1
        print("FAIL", name)


root = Path(tempfile.mkdtemp())
data = root / "ghab" / "data"
(data / "users" / "ali" / "posts").mkdir(parents=True)
(data / "users" / "sara").mkdir(parents=True)
for f in ("ali/posts/a.jpg", "ali/posts/a_p.jpg", "sara/x.jpg"):
    (data / "users" / f).write_bytes(b"x" * 2048)
# build a Ghab database with the real migrations
sys.path.insert(0, str(here / "ghab"))
os.environ["GHAB_DATA"] = str(data)
from server.db import migrate  # noqa: E402
migrate()
con = sqlite3.connect(data / "ghab.db")
con.executescript("""
insert into users(id,username,pass,name,created,wd_name) values(1,'ali','x','Ali',1700000000,'Ali');
insert into users(id,username,pass,name,created) values(2,'sara','x','Sara',1700000100);
insert into posts(id,user_id,file,kind,caption,created,poster) values(1,1,'ali/posts/a.jpg','image','hello',1700000200,'ali/posts/a_p.jpg');
insert into comments(id,post_id,user_id,text,created) values(1,1,2,'nice',1700000300);
insert into likes(user_id,post_id) values(2,1);
insert into follows(follower,followee) values(2,1);
insert into messages(id,sender,receiver,text,created) values(1,2,1,'secret dm',1700000400);
insert into stories(id,user_id,file,kind,created) values(1,2,'sara/x.jpg','image',1700000500);
""")
con.commit()
con.close()

D = datasheet.Datasheet
sheet = object.__new__(D)
sheet._ghab_data_root = lambda: data
msgs = []
sheet.toast = lambda m, error=False: msgs.append((m, error))
sheet.confirm = lambda t: True
sheet.last_signature = None
sheet.refresh = lambda: None
wdb = sqlite3.connect(":memory:")
wdb.row_factory = sqlite3.Row
wdb.execute("create table users(username text)")
wdb.execute("insert into users values('Sara_W')")
sheet.db = wdb


def load(tab):
    rows = D.load_ghab_table(sheet, tab)
    sheet.rows = rows
    return rows


def select(tab, idx):
    rows = load(tab)
    sheet.tree = types.SimpleNamespace(selection=lambda: [rows[idx]["iid"]])
    sheet.tab = tab
    return rows


for tab in datasheet.GHAB_TABS:
    r = load(tab)
    check(f"{tab} loads", len(r) >= 1 or tab == "ghabreports")
    for row in r:
        check(f"{tab} columns match", len(row["display"]) == len(datasheet.COLUMNS[tab]) == len(row["export"]) == len(row["sort"]))
users = load("ghab")
check("users: 2 rows, linked/old", [u["display"][2] for u in users] == ["Ali", "— (حساب قدیمی)"])
check("posts size shown", load("ghabposts")[0]["display"][4] != "—")
check("dm readable", "secret dm" in load("ghabdm")[0]["display"][3])
check("follows/likes iid unique", len({r["iid"] for r in load("ghabfollows")}) == 1)

# ban / unban
select("ghab", 1)
D.act_ghab_ban(sheet)
check("banned", sqlite3.connect(data / "ghab.db").execute("select banned from users where id=2").fetchone()[0] == 1)
select("ghab", 1)
D.act_ghab_ban(sheet)
check("unbanned", sqlite3.connect(data / "ghab.db").execute("select banned from users where id=2").fetchone()[0] == 0)

# link old account to a Windroida user (must exist there)
select("ghab", 1)
with mock.patch.dict(sys.modules, {"tkinter.simpledialog": types.SimpleNamespace(askstring=lambda *a, **k: "nobody")}):
    D.act_ghab_link(sheet)
check("link unknown windroida user refused", sqlite3.connect(data / "ghab.db").execute("select wd_name from users where id=2").fetchone()[0] is None)
select("ghab", 1)
with mock.patch.dict(sys.modules, {"tkinter.simpledialog": types.SimpleNamespace(askstring=lambda *a, **k: "sara_w")}):
    D.act_ghab_link(sheet)
check("linked (exact windroida name)", sqlite3.connect(data / "ghab.db").execute("select wd_name from users where id=2").fetchone()[0] == "Sara_W")
select("ghab", 0)   # already linked
n0 = len(msgs)
D.act_ghab_link(sheet)
check("already linked refused", msgs[-1][1] is True)

# reports tab: shows size/owner, "delete reported content" removes post + files + its reports; "delete report" keeps content
(data / "users/ali/posts/b.mp4").write_bytes(b"v" * 5000)
rc = sqlite3.connect(data / "ghab.db")
rc.execute("insert into posts(id,user_id,file,kind,caption,created) values(9,1,'ali/posts/b.mp4','video','bad video',1700000900)")
rc.execute("insert into reports(id,reporter,kind,ref_id,reason,created) values(1,2,'post',9,'spam',1700001000)")
rc.execute("insert into reports(id,reporter,kind,ref_id,reason,created) values(2,2,'post',9,'abuse',1700001001)")
rc.execute("insert into reports(id,reporter,kind,ref_id,reason,created) values(3,2,'comment',1,'rude',1700001002)")
rc.commit(); rc.close()
rr = load("ghabreports")
check("reports columns match", all(len(r["display"]) == len(datasheet.COLUMNS["ghabreports"]) for r in rr))
vid = [r for r in rr if r["ghab"]["ref"] == 9][0]
check("report shows size + owner", "KB" in vid["display"][5] or "B" in vid["display"][5] and vid["display"][4] == "ali")
sheet.tab = "ghabreports"
sheet.tree = types.SimpleNamespace(selection=lambda: [rr[[r["iid"] for r in rr].index(vid["iid"])]["iid"]])
D.act_ghab_delete(sheet)   # only the report row
rc = sqlite3.connect(data / "ghab.db")
check("delete report keeps the video", rc.execute("select count(*) from posts where id=9").fetchone()[0] == 1 and (data / "users/ali/posts/b.mp4").exists())
rr = load("ghabreports")
vid = [r for r in rr if r["ghab"]["ref"] == 9][0]
sheet.tree = types.SimpleNamespace(selection=lambda: [vid["iid"]])
D.act_ghab_delete_reported(sheet)
rc = sqlite3.connect(data / "ghab.db")
check("delete reported: post + file gone", rc.execute("select count(*) from posts where id=9").fetchone()[0] == 0 and not (data / "users/ali/posts/b.mp4").exists())
check("delete reported: its reports gone, others kept", rc.execute("select count(*) from reports where ref_id=9 and kind='post'").fetchone()[0] == 0 and rc.execute("select count(*) from reports where kind='comment'").fetchone()[0] == 1)
rc.execute("delete from reports"); rc.commit(); rc.close()

# delete a post: row + both files go
select("ghabposts", 0)
sheet.tab = "ghabposts"
D.act_ghab_delete(sheet)
con = sqlite3.connect(data / "ghab.db")
check("post row gone", con.execute("select count(*) from posts").fetchone()[0] == 0)
check("comment/like cascaded", con.execute("select count(*) from comments").fetchone()[0] == 0 and con.execute("select count(*) from likes").fetchone()[0] == 0)
check("post files gone", not (data / "users/ali/posts/a.jpg").exists() and not (data / "users/ali/posts/a_p.jpg").exists())
check("other user's files kept", (data / "users/sara/x.jpg").exists())

# path traversal in a stored file name never escapes the users folder
secret = root / "outside.txt"
secret.write_text("keep me")
con.execute("insert into posts(id,user_id,file,kind,created) values(9,1,'../../../outside.txt','image',1)")
con.commit()
con.close()
select("ghabposts", 0)
sheet.tab = "ghabposts"
D.act_ghab_delete(sheet)
check("traversal path not deleted", secret.exists())
check("traversal open refused", D._ghab_file(sheet, "../../../outside.txt") is None)

# delete a user: whole folder goes, nobody else's
select("ghab", 1)
sheet.tab = "ghab"
D.act_ghab_delete(sheet)
check("user folder removed", not (data / "users/sara").exists())
check("other folder kept", (data / "users/ali").exists())

# unsupported
sheet.tab = "ghablikes"
D.act_ghab_delete(sheet)
check("likes not deletable", msgs[-1][1] is True)

# ---- Cloud Drive: wipe a user's files / delete an account (DB rows + files on disk)
import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location("cd_db", here / "cloud-drive" / "app" / "db.py")
cdd = importlib.util.module_from_spec(spec); spec.loader.exec_module(cdd)
droot = root / "cd"
(droot / "uploads").mkdir(parents=True); (droot / "tmp").mkdir()
cdd.migrate(droot / "cloud_drive.db")
cc = cdd.connect(droot / "cloud_drive.db")
now_ = "2026-01-01T00:00:00"
cc.executescript(f"""
insert into users(id,username,password_hash,role,quota_bytes,created_at) values(1,'ali','x','user',1000000,'{now_}');
insert into users(id,username,password_hash,role,quota_bytes,created_at) values(2,'sara','x','user',1000000,'{now_}');
insert into users(id,username,password_hash,role,quota_bytes,created_at) values(3,'boss','x','admin',1000000,'{now_}');
insert into folders(id,owner_id,name,created_at) values(1,1,'f','{now_}');
""")
names = {}
for i, uid in enumerate((1, 1, 2)):
    nm = ("%02x" % (i + 10)) * 16
    names[i] = nm
    (droot / "uploads" / nm[:2]).mkdir(exist_ok=True)
    (droot / "uploads" / nm[:2] / nm).write_bytes(b"x" * 1000)
    cc.execute("insert into files(owner_id,folder_id,name,stored_name,size,mime,created_at) values(?,?,?,?,?,?,?)", (uid, 1 if uid == 1 else None, f"n{i}", nm, 1000, "text/plain", now_))
up = "ab" * 16
cc.execute("insert into uploads(id,owner_id,name,size,chunk_size,total_chunks,created_at,updated_at) values(?,?,?,?,?,?,?,?)", (up, 1, "big", 5, 5, 1, now_, now_))
(droot / "tmp" / up).mkdir(); (droot / "tmp" / up / "0").write_bytes(b"y")
cc.execute("insert into shares(token,file_id,owner_id,created_at) values('t',1,1,?)", (now_,))
cc.commit(); cc.close()
sheet._drive_data_root = lambda: droot
sheet._drive_db_path = lambda: droot / "cloud_drive.db"
sheet._drive_conn_write = lambda: D._drive_conn_write(sheet)
def drv_rows(*ids):
    sheet.rows = [dict(iid=f"drv{i}", display=(i, u, "مدیر" if u == "boss" else "کاربر"), export=(i,)) for i, u in ((1, "ali"), (2, "sara"), (3, "boss")) if i in ids]
    sheet.tree = types.SimpleNamespace(selection=lambda: tuple(r["iid"] for r in sheet.rows))
drv_rows(1)
D.act_drive_wipe_files(sheet)
q_ = sqlite3.connect(droot / "cloud_drive.db")
check("drive wipe: user files gone, account kept", q_.execute("select count(*) from files where owner_id=1").fetchone()[0] == 0 and q_.execute("select count(*) from users where id=1").fetchone()[0] == 1)
check("drive wipe: folders/uploads/shares gone", q_.execute("select count(*) from folders").fetchone()[0] == 0 and q_.execute("select count(*) from uploads").fetchone()[0] == 0 and q_.execute("select count(*) from shares").fetchone()[0] == 0)
check("drive wipe: disk files gone, tmp gone", not (droot / "uploads" / names[0][:2] / names[0]).exists() and not (droot / "uploads" / names[1][:2] / names[1]).exists() and not (droot / "tmp" / up).exists())
check("drive wipe: other user's file kept", (droot / "uploads" / names[2][:2] / names[2]).exists() and q_.execute("select count(*) from files where owner_id=2").fetchone()[0] == 1)
drv_rows(3)
D.act_drive_delete_user(sheet)
check("drive: admin account not deleted", msgs[-1][1] is True and q_.execute("select count(*) from users where id=3").fetchone()[0] == 1)
drv_rows(2)
D.act_drive_delete_user(sheet)
check("drive delete account: row + file gone", q_.execute("select count(*) from users where id=2").fetchone()[0] == 0 and not (droot / "uploads" / names[2][:2] / names[2]).exists())
check("drive delete: other accounts intact", q_.execute("select count(*) from users").fetchone()[0] == 2)
q_.close()

shutil.rmtree(root, ignore_errors=True)
print(f"ghab sheet: {ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
