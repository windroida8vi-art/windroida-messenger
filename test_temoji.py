"""Animated Telegram emoji: files are served and the map is complete. Run: python test_temoji.py"""
import sys, tempfile, json, gzip, urllib.request, urllib.error
from pathlib import Path
sys.path.insert(0, ".")
import common
tmp = Path(tempfile.mkdtemp()); common.DATA_DIR = tmp; common.UPLOADS_DIR = tmp/"u"; common.AVATARS_DIR = tmp/"a"; common.WALLPAPERS_DIR = tmp/"w"; common.ROOMAUDIO_DIR = tmp/"r"; common.FILES_DIR = tmp/"f"; (tmp/"f").mkdir()
import server as srv, webgw
webgw.WebGateway._fetch_lottie = staticmethod(lambda: None) if hasattr(webgw, "WebGateway") else None
S = srv.WindroidaServer("127.0.0.1", 0, db_path=tmp/"t.db", web_port=0); S.start()
S._may_add_directly = lambda db, adder, target: True     # these tests build groups by adding people directly (the real rule: test_group_invite.py)
port = S.web_port
res = []
def ok(n, c, x=""): res.append(bool(c)); print(("  ok   " if c else "  FAIL ") + n, "" if c else x)
def get(p):
    try:
        r = urllib.request.urlopen(f"http://127.0.0.1:{port}{p}", timeout=5); return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e: return e.code, b"", e.headers
st, body, hd = get("/emoji/map.json"); mp = json.loads(body) if st == 200 else {}
ok("map served", st == 200 and len(mp) > 500, st)
ok("😂 and ❤ are in the map", "😂" in mp and "❤" in mp)
st, body, hd = get(f"/emoji/{mp['😂']}.tgs")
d = json.loads(gzip.decompress(body)) if st == 200 else {}
ok("😂 file is a real lottie animation", st == 200 and d.get("w") == 512 and d.get("layers"), st)
ok("cached by the browser", "max-age" in (hd.get("Cache-Control") or "") and "no-store" not in (hd.get("Cache-Control") or ""))
ok("path tricks refused", get("/emoji/../server.py")[0] == 404 and get("/emoji/x.tgs")[0] == 404 and get("/emoji/..%2fserver.py")[0] == 404)
missing = [n for n in set(mp.values()) if not (Path("web/emoji")/f"{n}.tgs").is_file() or not (Path("android/app/src/main/assets/emoji")/f"{n}.tgs").is_file()]
ok("every mapped file exists for web and Android", not missing, missing[:3])
print(f"temoji: {sum(res)} ok, {len(res) - sum(res)} failed"); sys.exit(0 if all(res) else 1)
