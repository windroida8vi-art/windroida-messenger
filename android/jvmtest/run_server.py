"""Starts a throw-away Windroida server for the Kotlin JVM tests and prints its web port. Stops when stdin closes."""
import os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import common
tmp = Path(tempfile.mkdtemp()); common.DATA_DIR = tmp; common.UPLOADS_DIR = tmp/"u"; common.AVATARS_DIR = tmp/"a"; common.WALLPAPERS_DIR = tmp/"w"; common.ROOMAUDIO_DIR = tmp/"r"; common.FILES_DIR = tmp/"f"; (tmp/"f").mkdir()
import server as srv
S = srv.WindroidaServer("127.0.0.1", 0, tls=bool(os.environ.get("TLS")), db_path=tmp/"t.db", web_port=0); S.start()
print("PORT", S.web_port, "TLS" if S.tls else "PLAIN", flush=True)
sys.stdin.read()
os._exit(0)
