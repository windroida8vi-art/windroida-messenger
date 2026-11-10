"""Web gateway: serves web/index.html and bridges WebSocket clients to the Windroida server.

Pure standard library (minimal RFC 6455 implementation). Every WebSocket connection is a
normal Windroida session, so the browser UI uses exactly the same operations/security as the desktop app.
"""
import base64
import hashlib
import json
import re
import socket
import ssl
import struct
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import common
from common import (avatar_folder_for_chat, avatar_folder_for_user, BASE_DIR, MAX_AVATAR, MAX_FRAME, MAX_UPLOAD, connect_db, media_info, resolve_avatar,
                    resolve_upload, small_avatar_rel)
from server import Conn, Fail, log

MAX_CONN_PER_IP = 150        # generous: mobile operators put many users behind one IP
MAX_CONN_TOTAL = 1500        # combined with the raw-TCP listener's own cap, keeps total server threads (~1 MB stack each on Windows)
                              # in a safe range even under a many-IP flood, instead of letting both listeners fill up independently
HEADER_TIMEOUT = 20          # slowloris: a client must finish its TLS handshake + request line/headers in 20 s
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
WEB_DIR = BASE_DIR / "web"
SECURITY_HEADERS = (
    "Content-Security-Policy: default-src 'self'; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; connect-src 'self' ws: wss:; img-src 'self' data: blob:; "
    "media-src 'self' blob:; manifest-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'\r\n"
    "X-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\n"
    "Permissions-Policy: camera=(self), microphone=(self), geolocation=(), payment=(), usb=(), display-capture=(self)\r\n"
    "Cross-Origin-Opener-Policy: same-origin\r\nX-Permitted-Cross-Domain-Policies: none\r\n"
    "Cache-Control: no-store\r\n"
)


def _recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("closed")
        buf.extend(chunk)
    return bytes(buf)


def ws_frame(payload: bytes, opcode=1) -> bytes:
    head = bytes([0x80 | opcode])
    n = len(payload)
    if n < 126:
        head += bytes([n])
    elif n < 65536:
        head += bytes([126]) + struct.pack(">H", n)
    else:
        head += bytes([127]) + struct.pack(">Q", n)
    return head + payload


def ws_read(sock, send_raw):
    """Read one complete (possibly fragmented) data message; answers ping/close control frames."""
    message, kind = bytearray(), None
    while True:
        b1, b2 = _recv_exact(sock, 2)
        fin, op, masked, n = b1 & 0x80, b1 & 0x0F, b2 & 0x80, b2 & 0x7F
        if n == 126:
            n = struct.unpack(">H", _recv_exact(sock, 2))[0]
        elif n == 127:
            n = struct.unpack(">Q", _recv_exact(sock, 8))[0]
        if n > MAX_FRAME or not masked:          # clients must mask; refuse oversized
            raise ConnectionError("bad frame")
        mask = _recv_exact(sock, 4)
        payload = _recv_exact(sock, n)
        if n:
            key = (mask * (n // 4 + 1))[:n]
            payload = (int.from_bytes(payload, "big") ^ int.from_bytes(key, "big")).to_bytes(n, "big")
        if op == 8:
            send_raw(ws_frame(b"", 8))
            raise ConnectionError("close")
        if op == 9:
            send_raw(ws_frame(payload, 10))
            continue
        if op == 10:
            continue
        if op in (1, 2):
            kind = op
        message.extend(payload)
        if len(message) > MAX_FRAME:
            raise ConnectionError("too large")
        if fin:
            return bytes(message)


class WSConn(Conn):
    def send(self, obj):
        if not self.alive:
            return
        try:
            data = ws_frame(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            with self.send_lock:
                self.sock.sendall(data)
        except Exception:
            self.alive = False

    def send_raw(self, data):
        try:
            with self.send_lock:
                self.sock.sendall(data)
        except Exception:
            self.alive = False


class WebGateway:
    def __init__(self, server, host, port):
        self.server, self.host, self.port = server, host, port
        self.listener = None
        self._stop = False

    def start(self):
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind((self.host, self.port))
        self.listener.listen(64)
        self.port = self.listener.getsockname()[1]
        self._conns, self._conn_lock = {}, threading.Lock()
        threading.Thread(target=self._accept, daemon=True).start()
        threading.Thread(target=self._fetch_lottie, daemon=True).start()
        scheme = "https" if self.server.ssl_ctx else "http"
        log(f"web UI on {scheme}://{self.host}:{self.port}")
        return self.port

    def stop(self):
        self._stop = True
        try:
            self.listener.close()
        except Exception:
            pass

    def _accept(self):
        while not self._stop:
            try:
                sock, addr = self.listener.accept()
            except OSError:
                break
            ip = addr[0]
            with self._conn_lock:
                if self._conns.get(ip, 0) >= MAX_CONN_PER_IP or sum(self._conns.values()) >= MAX_CONN_TOTAL:
                    try:
                        sock.close()
                    except OSError:
                        pass
                    continue
                self._conns[ip] = self._conns.get(ip, 0) + 1
            threading.Thread(target=self._handle_counted, args=(sock, addr), daemon=True).start()

    def _handle_counted(self, sock, addr):
        try:
            self._handle(sock, addr)
        finally:
            with self._conn_lock:
                n = self._conns.get(addr[0], 1) - 1
                if n <= 0:
                    self._conns.pop(addr[0], None)
                else:
                    self._conns[addr[0]] = n

    # ---------------------------------------------------------------- http
    @staticmethod
    def _reply(sock, status, body=b"", ctype="text/plain; charset=utf-8", extra=""):
        head = (f"HTTP/1.1 {status}\r\nContent-Type: {ctype}\r\nContent-Length: {len(body)}\r\n"
                f"Connection: close\r\n{SECURITY_HEADERS}{extra}\r\n").encode()
        try:
            sock.sendall(head + body)
        except OSError:
            pass

    def _handle(self, sock, addr):
        try:
            sock.settimeout(HEADER_TIMEOUT)
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)    # no Nagle delay for small audio frames
            except OSError:
                pass
            if self.server.ssl_ctx:
                try:                                    # someone typed http:// on the https port -> redirect them
                    first = sock.recv(1, socket.MSG_PEEK)
                except OSError:
                    return sock.close()
                if first and first != b"\x16":
                    return self._redirect_to_https(sock)
                sock = self.server.ssl_ctx.wrap_socket(sock, server_side=True)
            raw = b""
            while b"\r\n\r\n" not in raw:
                chunk = sock.recv(4096)
                if not chunk or len(raw) > 16384:
                    return sock.close()
                raw += chunk
            head, _, rest = raw.partition(b"\r\n\r\n")
            lines = head.decode("latin-1").split("\r\n")
            method, path, _ = lines[0].split(" ", 2)
            headers = {}
            for ln in lines[1:]:
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
            path, _, query = path.partition("?")
            qs = parse_qs(query)
            sock.settimeout(120)          # headers are in: normal (upload) timeout from here
            hh = headers.get("host", "").rsplit(":", 1)[0] if self.server.ssl_ctx else ""
            if hh and hh[0].isdigit():
                self.server.learn_host(hh, addr[0])
            if path == "/ws" and headers.get("upgrade", "").lower() == "websocket":
                return self._websocket(sock, addr, headers)
            if method in ("GET", "HEAD") and path.startswith("/media/"):
                return self._media(sock, method, path, qs, headers)
            if method == "POST" and path == "/upload":
                return self._upload(sock, qs, headers, rest)
            if method == "GET" and path == "/upload-status":
                return self._upload_status(sock, qs)
            if method == "POST" and path == "/notify":
                return self._notify(sock, addr, headers, rest)
            if method == "POST" and path == "/ghab-share":
                return self._ghab_share(sock, addr, headers, rest)
            if method == "POST" and path == "/avatar":
                return self._avatar_post(sock, qs, headers, rest)
            if method == "POST" and path == "/userwall":
                return self._userwall_post(sock, qs, headers, rest)
            if method in ("GET", "HEAD") and path == "/userwall":
                return self._userwall_get(sock, method, qs)
            if method == "GET" and path == "/rules.txt":                 # your own rules: put them in data/rules.txt (else the page shows the default text)
                try:
                    f = common.DATA_DIR / "rules.txt"
                    body = f.read_bytes()[:20000] if f.is_file() else b""
                except OSError:
                    body = b""
                if not body:
                    return self._reply(sock, "404 Not Found", b"") or sock.close()
                return self._reply(sock, "200 OK", body, extra="Cache-Control: no-store\r\n") or sock.close()
            if method == "GET" and path == "/windroida.crt":
                return self._cert_download(sock)
            if method == "POST" and path == "/thumb":
                return self._thumb_post(sock, qs, headers, rest)
            if method in ("GET", "HEAD") and path.startswith("/thumb/"):
                return self._thumb_get(sock, method, path, qs)
            if method == "GET" and path == "/sw.js":
                return self._static(sock, "sw.js", extra="Service-Worker-Allowed: /\r\n")
            if method in ("GET", "HEAD") and path.startswith("/roomaudio/"):
                return self._roomaudio_get(sock, method, path, qs, headers)
            if method == "POST" and path == "/roomupload":
                return self._roomupload(sock, qs, headers, rest)
            if method in ("GET", "HEAD") and path.startswith("/wall/"):
                return self._wall_get(sock, method, path, qs)
            if method in ("GET", "HEAD") and path.startswith("/avatar/"):
                return self._avatar_get(sock, method, path, qs)
            if method == "GET" and path.startswith("/emoji/"):
                return self._emoji_get(sock, path[7:])
            if method == "GET" and path.startswith("/static/"):
                return self._static(sock, path[8:])
            if method == "GET" and path == "/manifest.webmanifest":
                return self._static(sock, "manifest.webmanifest")
            if method == "GET" and path in ("/", "/index.html"):
                return self._static(sock, "index.html")
            self._reply(sock, "404 Not Found", b"not found")
            sock.close()
        except Exception:
            try:
                sock.close()
            except Exception:
                pass

    def _redirect_to_https(self, sock):
        try:
            sock.settimeout(5)
            raw = sock.recv(4096).decode("latin-1")
            host = ""
            for ln in raw.split("\r\n"):
                if ln.lower().startswith("host:"):
                    host = ln.split(":", 1)[1].strip()
            if not re.fullmatch(r"[A-Za-z0-9.\-\[\]:]{1,100}", host or ""):
                host = f"localhost:{self.port}"
            m = re.match(r"[A-Z]+ (\S+)", raw)
            target = m.group(1) if m and m.group(1).startswith("/") and not m.group(1).startswith("//") else "/"
            if target.split("?")[0] == "/windroida.crt":
                return self._cert_download(sock)          # plain http: no certificate warning, so Android can download it
            self._reply(sock, "301 Moved Permanently", b"https required", extra=f"Location: https://{host}{target}\r\n")
        except OSError:
            pass
        finally:
            sock.close()

    STATIC_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                    ".js": "application/javascript; charset=utf-8", ".svg": "image/svg+xml",
                    ".png": "image/png", ".webmanifest": "application/manifest+json", ".ico": "image/x-icon",
                    ".woff2": "font/woff2", ".woff": "font/woff"}

    def _cert_download(self, sock):
        """The public certificate (no secrets) so a phone can trust it: Settings -> Security -> Install a certificate -> CA."""
        try:
            der = ssl.PEM_cert_to_DER_cert(Path(self.server._crt_path).read_text())
        except Exception:
            return self._reply(sock, "404 Not Found", b"no certificate") or sock.close()
        head = (f"HTTP/1.1 200 OK\r\nContent-Type: application/x-x509-ca-cert\r\nContent-Length: {len(der)}\r\n"
                'Content-Disposition: attachment; filename="windroida.crt"\r\nAccept-Ranges: none\r\n'
                "Cache-Control: public, max-age=3600\r\nX-Content-Type-Options: nosniff\r\nConnection: close\r\n\r\n").encode()
        try:
            sock.sendall(head + der)       # public certificate only; no Cache-Control: no-store (Android's download manager stalls on it)
        except OSError:
            pass
        sock.close()

    def _thumb_post(self, sock, qs, headers, rest):
        """POST /thumb?k=<key>&message_id=<id>[&w=&h=]  body = small JPEG made by the sender's browser."""
        origin = headers.get("origin")
        uid = self.server.check_media_key((qs.get("k") or [""])[0])
        if (origin and urlparse(origin).netloc != headers.get("host")) or uid is None:
            self._discard(sock, headers, rest)
            return self._json(sock, "403 Forbidden", {"ok": False, "error": "forbidden"})
        try:
            raw = self._read_body(sock, headers, rest, 400 * 1024)
            mid = int((qs.get("message_id") or ["0"])[0])
            w = int((qs.get("w") or ["0"])[0] or 0)
            h = int((qs.get("h") or ["0"])[0] or 0)
        except ValueError:
            self._discard(sock, headers, rest)
            return self._json(sock, "400 Bad Request", {"ok": False, "error": "bad request"})
        except (ConnectionError, OSError, ssl.SSLError):
            return sock.close()
        db = connect_db(self.server.db_path)
        try:
            self.server.set_thumb(db, uid, mid, raw, w, h)
            self._json(sock, "200 OK", {"ok": True})
        except Fail as e:
            self._json(sock, "400 Bad Request", {"ok": False, "error": str(e)})
        finally:
            db.close()

    def _thumb_get(self, sock, method, path, qs):
        uid = self.server.check_media_key((qs.get("k") or [""])[0])
        try:
            mid = int(path.rsplit("/", 1)[1])
        except ValueError:
            mid = 0
        fpath = None
        if uid is not None:
            db = connect_db(self.server.db_path)
            try:
                row = db.execute("SELECT m.file_path, m.file_name, m.deleted FROM messages m JOIN members mm ON mm.chat_id=m.chat_id "
                                 "AND mm.user_id=? WHERE m.id=?", (uid, mid)).fetchone()
            finally:
                db.close()
            if row and not row["deleted"]:
                fpath = resolve_upload(common.thumb_rel(row["file_path"]))
                if fpath is None and row["file_path"] and media_info(row["file_name"])[1] == "image":
                    db = connect_db(self.server.db_path)
                    try:
                        full = db.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
                        fpath = self.server.image_thumb(db, full)
                    finally:
                        db.close()
        if fpath is None:
            return self._reply(sock, "404 Not Found", b"none") or sock.close()
        data = fpath.read_bytes()
        head = (f"HTTP/1.1 200 OK\r\nContent-Type: image/jpeg\r\nContent-Length: {len(data)}\r\n"
                "Cache-Control: private, max-age=31536000, immutable\r\nX-Content-Type-Options: nosniff\r\n"
                "Cross-Origin-Resource-Policy: same-origin\r\nConnection: close\r\n\r\n").encode()
        try:
            sock.sendall(head + (b"" if method == "HEAD" else data))
        except OSError:
            pass
        sock.close()

    def _emoji_get(self, sock, name):
        """Telegram's animated emoji (web/emoji/<code>.tgs + map.json): public, cached by the browser for a week"""
        if not re.fullmatch(r"(?:[0-9a-f]{2,6}(?:-[0-9a-f]{2,6})*\.tgs|map\.json)", name):
            return self._reply(sock, "404 Not Found", b"not found") or sock.close()
        f = WEB_DIR / "emoji" / name
        if not f.is_file():
            return self._reply(sock, "404 Not Found", b"not found") or sock.close()
        body = f.read_bytes()
        ctype = "application/json; charset=utf-8" if name.endswith(".json") else "application/octet-stream"
        head = (f"HTTP/1.1 200 OK\r\nContent-Type: {ctype}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n"
                + SECURITY_HEADERS.replace("Cache-Control: no-store\r\n", "") + "Cache-Control: public, max-age=604800\r\n\r\n").encode()
        try:
            sock.sendall(head + body)
        except OSError:
            pass
        sock.close()

    @staticmethod
    def _fetch_lottie():
        """The animated emoji need the small 'lottie-web' player. Download it once into web/ (the page's security policy only
        allows scripts from this server). If there is no internet, put lottie_light.js into the web folder by hand."""
        dest = WEB_DIR / "lottie_light.js"
        if dest.is_file() and dest.stat().st_size > 100_000:
            return
        import urllib.request
        for url in ("https://cdn.jsdelivr.net/npm/lottie-web@5.12.2/build/player/lottie_light.min.js",
                    "https://cdnjs.cloudflare.com/ajax/libs/lottie-web/5.12.2/lottie_light.min.js",
                    "https://unpkg.com/lottie-web@5.12.2/build/player/lottie_light.min.js"):
            try:
                data = urllib.request.urlopen(url, timeout=20).read()
                if len(data) > 100_000 and b"lottie" in data[:4000].lower() + data[-4000:].lower():
                    dest.write_bytes(data)
                    log("animated emoji: lottie player downloaded")
                    return
            except Exception:
                continue
        log("animated emoji: could not download lottie_light.js (no internet?) - emoji stay plain until it is in the web folder")

    def _static(self, sock, name, extra=""):
        ext = Path(name).suffix.lower()
        if not re.fullmatch(r"[A-Za-z0-9_\-]+(\.[A-Za-z0-9_\-]+)?", name) or ext not in self.STATIC_TYPES:
            return self._reply(sock, "404 Not Found", b"not found") or sock.close()
        f = WEB_DIR / name
        if not f.is_file():
            return self._reply(sock, "404 Not Found", b"not found") or sock.close()
        self._reply(sock, "200 OK", f.read_bytes(), self.STATIC_TYPES[ext], extra)
        sock.close()

    # ------------------------------------------------------------- avatars
    def _roomaudio_get(self, sock, method, path, qs, headers):
        """GET /roomaudio/<playlist>/<song>?k=<key>  (Range supported). Library songs: any signed-in user.
        Private uploads (_uploads/<user>/..): the owner, or someone sitting in a room that has the song queued."""
        from urllib.parse import unquote
        uid = self.server.check_media_key((qs.get("k") or [""])[0])
        rel = unquote(path[11:])
        p = common.resolve_roomaudio(rel) if uid is not None else None
        if uid is None:
            return self._reply(sock, "403 Forbidden", b"forbidden") or sock.close()
        db = connect_db(self.server.db_path)
        try:
            u = db.execute("SELECT username, banned FROM users WHERE id=?", (uid,)).fetchone()
        finally:
            db.close()
        if p is None or not u or u["banned"] or not self.server._roomaudio_allowed(uid, u["username"], rel):
            return self._reply(sock, "404 Not Found", b"none") or sock.close()
        mime = media_info(p.name)[0]
        return self._send_file(sock, method, headers, p, mime if media_info(p.name)[2] else ("video/mp4" if common.is_video_name(p.name) else "audio/mpeg"), p.name)

    def _roomupload(self, sock, qs, headers, rest):
        """POST /roomupload?k=<key>&name=<file name>  body = the song. Kept forever in roomaudio/_uploads/<user>/."""
        origin = headers.get("origin")
        if origin and urlparse(origin).netloc != headers.get("host"):
            self._discard(sock, headers, rest)
            return self._json(sock, "403 Forbidden", {"ok": False, "error": "bad origin"})
        uid = self.server.check_media_key((qs.get("k") or [""])[0])
        if uid is None:
            self._discard(sock, headers, rest)
            return self._json(sock, "403 Forbidden", {"ok": False, "error": "نشست معتبر نیست؛ صفحه رو رفرش کن"})
        if not common.disk_ok():
            self._discard(sock, headers, rest)
            return self._json(sock, "507 Insufficient Storage", {"ok": False, "error": "فضای دیسک سرور تقریباً پره؛ به مدیر بگو"})
        name = re.sub(r"[\x00-\x1f\x7f\u2028\u2029]", "", (qs.get("name") or ["song.mp3"])[0]).strip() or "song.mp3"
        if common.is_video_name(name):
            return self._roomupload_video(sock, uid, name, headers, rest)
        if not self.server._room_hits(("songup", uid), 20, 3600):
            self._discard(sock, headers, rest)
            return self._json(sock, "429 Too Many Requests", {"ok": False, "error": "تا یه ساعت دیگه نمی‌تونی آهنگ بیشتری آپلود کنی"})
        db = connect_db(self.server.db_path)
        try:
            u = db.execute("SELECT username, banned FROM users WHERE id=?", (uid,)).fetchone()
        finally:
            db.close()
        if not u or u["banned"]:
            self._discard(sock, headers, rest)
            return self._json(sock, "403 Forbidden", {"ok": False, "error": "دسترسی نداری"})
        try:
            raw = self._read_body(sock, headers, rest, common.SONG_MAX)
        except ValueError:
            return self._json(sock, "413 Payload Too Large", {"ok": False, "error": "حجم آهنگ حداکثر ۸۰ مگابایت"})
        except (ConnectionError, OSError):
            return sock.close()
        try:
            rel = common.store_roomaudio(u["username"], (qs.get("name") or ["song.mp3"])[0], raw)
        except ValueError as e:
            return self._json(sock, "400 Bad Request", {"ok": False, "error": str(e)})
        p = common.resolve_roomaudio(rel)
        return self._json(sock, "200 OK", {"ok": True, "rel": rel, "size": p.stat().st_size if p else len(raw)})

    def _roomupload_video(self, sock, uid, name, headers, rest):
        """A movie for a watch-room: streamed straight into the user's private folder (never held in memory), checked
        before reading (extension, size, quota) and after (container signature). Half-finished uploads are cleaned up."""
        if not common.disk_ok():
            self._discard(sock, headers, rest)
            return self._json(sock, "507 Insufficient Storage", {"ok": False, "error": "فضای دیسک سرور تقریباً پره؛ به مدیر بگو"})
        if not self.server._room_hits(("videoup", uid), 8, 3600):
            self._discard(sock, headers, rest)
            return self._json(sock, "429 Too Many Requests", {"ok": False, "error": "تا یه ساعت دیگه نمی‌تونی فیلم بیشتری آپلود کنی"})
        db = connect_db(self.server.db_path)
        try:
            u = db.execute("SELECT username, banned FROM users WHERE id=?", (uid,)).fetchone()
        finally:
            db.close()
        if not u or u["banned"]:
            self._discard(sock, headers, rest)
            return self._json(sock, "403 Forbidden", {"ok": False, "error": "دسترسی نداری"})
        try:
            length = int(headers.get("content-length", ""))
        except ValueError:
            length = 0
        try:
            tmp, dest = common.begin_roomvideo(u["username"], name, length)
        except ValueError as e:
            self._discard(sock, headers, rest)
            return self._json(sock, "400 Bad Request", {"ok": False, "error": str(e)})
        sock.settimeout(120)
        got = 0
        try:
            with open(tmp, "wb") as f:
                part = rest[:length]
                f.write(part)
                got = len(part)
                while got < length:
                    chunk = sock.recv(min(262144, length - got))
                    if not chunk:
                        raise ConnectionError("interrupted")
                    f.write(chunk)
                    got += len(chunk)
        except (ConnectionError, OSError, ssl.SSLError):
            try:
                tmp.unlink()
            except OSError:
                pass
            return sock.close()
        try:
            rel = common.finish_roomvideo(tmp, dest)
        except ValueError as e:
            return self._json(sock, "400 Bad Request", {"ok": False, "error": str(e)})
        return self._json(sock, "200 OK", {"ok": True, "rel": rel, "size": got})

    def _wall_get(self, sock, method, path, qs):
        """GET /wall/<file name>?k=<key>[&s=1 preview]  - chat backgrounds from data/wallpapers/"""
        from urllib.parse import unquote
        if self.server.check_media_key((qs.get("k") or [""])[0]) is None:
            return self._reply(sock, "403 Forbidden", b"forbidden") or sock.close()
        p = common.resolve_wallpaper(unquote(path[6:]), small="s" in qs)
        if p is None:
            return self._reply(sock, "404 Not Found", b"none") or sock.close()
        data = p.read_bytes()
        head = (f"HTTP/1.1 200 OK\r\nContent-Type: {media_info(p.name)[0]}\r\nContent-Length: {len(data)}\r\n"
                "Cache-Control: private, max-age=3600\r\nX-Content-Type-Options: nosniff\r\n"
                "Cross-Origin-Resource-Policy: same-origin\r\nConnection: close\r\n\r\n").encode()
        try:
            sock.sendall(head + (b"" if method == "HEAD" else data))
        except OSError:
            pass
        sock.close()

    def _userwall_post(self, sock, qs, headers, rest):
        """POST /userwall?k=<key>  body = the image; saved in this user's own folder (data/userwalls/<user>/)."""
        origin = headers.get("origin")
        if origin and urlparse(origin).netloc != headers.get("host"):
            self._discard(sock, headers, rest)
            return self._json(sock, "403 Forbidden", {"ok": False, "error": "bad origin"})
        uid = self.server.check_media_key((qs.get("k") or [""])[0])
        if uid is None:
            self._discard(sock, headers, rest)
            return self._json(sock, "403 Forbidden", {"ok": False, "error": "نشست معتبر نیست؛ صفحه رو رفرش کن"})
        try:
            raw = self._read_body(sock, headers, rest, MAX_AVATAR)
        except ValueError:
            self._discard(sock, headers, rest)
            return self._json(sock, "400 Bad Request", {"ok": False, "error": "حجم عکس نامعتبره"})
        except (ConnectionError, OSError, ssl.SSLError):
            return sock.close()
        db = connect_db(self.server.db_path)
        try:
            self._json(sock, "200 OK", {"ok": True, "v": self.server.set_user_wall(db, uid, raw)})
        except Fail as e:
            self._json(sock, "400 Bad Request", {"ok": False, "error": str(e)})
        finally:
            db.close()

    def _userwall_get(self, sock, method, qs):
        """GET /userwall?k=<key>&v=<version>  - the caller's OWN background only."""
        uid = self.server.check_media_key((qs.get("k") or [""])[0])
        if uid is None:
            return self._reply(sock, "403 Forbidden", b"forbidden") or sock.close()
        db = connect_db(self.server.db_path)
        try:
            row = db.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
        finally:
            db.close()
        try:
            want = int((qs.get("v") or ["0"])[0])
        except ValueError:
            want = 0
        p, _v = common.current_user_wall(row["username"], want) if row else (None, 0)
        if p is None:
            return self._reply(sock, "404 Not Found", b"none") or sock.close()
        data = p.read_bytes()
        if (qs.get("s") or [""])[0] == "1" and common.HAVE_PIL:          # small preview for the settings list
            try:
                import io
                im = common.Image.open(io.BytesIO(data))
                im.thumbnail((180, 180))
                buf = io.BytesIO()
                im.convert("RGB").save(buf, "JPEG", quality=70)
                data = buf.getvalue()
            except Exception:
                pass
        ctype = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
        head = (f"HTTP/1.1 200 OK\r\nContent-Type: {ctype}\r\nContent-Length: {len(data)}\r\n"
                "Cache-Control: private, max-age=3600\r\nX-Content-Type-Options: nosniff\r\n"
                "Cross-Origin-Resource-Policy: same-origin\r\nConnection: close\r\n\r\n").encode()
        try:
            sock.sendall(head + (b"" if method == "HEAD" else data))
        except OSError:
            pass
        sock.close()

    def _avatar_get(self, sock, method, path, qs):
        """GET /avatar/u<user id> | /avatar/c<chat id>?k=<key>&v=<version>[&s=1 small]"""
        uid = self.server.check_media_key((qs.get("k") or [""])[0])
        m = re.fullmatch(r"/avatar/([uc])(\d+)", path)
        if uid is None or not m:
            return self._reply(sock, "403 Forbidden", b"forbidden") or sock.close()
        db = connect_db(self.server.db_path)
        try:
            if m.group(1) == "u":
                row = db.execute("SELECT avatar, username FROM users WHERE id=? AND banned=0", (int(m.group(2)),)).fetchone()
                folder = avatar_folder_for_user(row["username"]) if row else None
            else:
                row = db.execute("SELECT c.avatar, c.title, c.id FROM chats c JOIN members mm ON mm.chat_id=c.id "
                                 "WHERE c.id=? AND mm.user_id=?", (int(m.group(2)), uid)).fetchone()
                folder = avatar_folder_for_chat(row["id"], row["title"] or "") if row else None
        finally:
            db.close()
        pic = (qs.get("pic") or [""])[0]
        if pic:                                                  # one specific kept photo (gallery)
            rel = f"{folder}/{pic}" if folder and common.valid_pic_name(pic) else None
        else:
            rel = row["avatar"] if row else None
        orig = rel
        if rel and "s" in qs:
            rel = small_avatar_rel(rel)
        fpath = resolve_avatar(rel) or (resolve_avatar(orig) if orig else None)
        if fpath is None:
            return self._reply(sock, "404 Not Found", b"none") or sock.close()
        data = fpath.read_bytes()
        mime = media_info(fpath.name)[0]
        head = (f"HTTP/1.1 200 OK\r\nContent-Type: {mime}\r\nContent-Length: {len(data)}\r\n"
                "Cache-Control: private, max-age=31536000, immutable\r\nX-Content-Type-Options: nosniff\r\n"
                "Cross-Origin-Resource-Policy: same-origin\r\nConnection: close\r\n\r\n").encode()
        try:
            sock.sendall(head + (b"" if method == "HEAD" else data))
        except OSError:
            pass
        sock.close()

    def _read_body(self, sock, headers, rest, limit, dest=None):
        length = int(headers.get("content-length", ""))
        if length <= 0 or length > limit:
            raise ValueError("size")
        sock.settimeout(120)
        buf = bytearray(rest[:length])
        while len(buf) < length:
            chunk = sock.recv(min(65536, length - len(buf)))
            if not chunk:
                raise ConnectionError("interrupted")
            buf.extend(chunk)
        return bytes(buf)

    def _avatar_post(self, sock, qs, headers, rest):
        """POST /avatar?k=<key>&target=me   or   &target=chat&chat_id=<id>   body = the image."""
        origin = headers.get("origin")
        if origin and urlparse(origin).netloc != headers.get("host"):
            self._discard(sock, headers, rest)
            return self._json(sock, "403 Forbidden", {"ok": False, "error": "bad origin"})
        uid = self.server.check_media_key((qs.get("k") or [""])[0])
        if uid is None:
            self._discard(sock, headers, rest)
            return self._json(sock, "403 Forbidden", {"ok": False, "error": "نشست معتبر نیست؛ صفحه رو رفرش کن"})
        try:
            raw = self._read_body(sock, headers, rest, MAX_AVATAR)
        except ValueError:
            self._discard(sock, headers, rest)
            return self._json(sock, "400 Bad Request", {"ok": False, "error": "حجم عکس نامعتبره"})
        except (ConnectionError, OSError, ssl.SSLError):
            return sock.close()
        db = connect_db(self.server.db_path)
        try:
            if (qs.get("target") or ["me"])[0] == "chat":
                at = self.server.set_chat_avatar(db, uid, int((qs.get("chat_id") or ["0"])[0]), raw)
            else:
                at = self.server.set_user_avatar(db, uid, raw)
            self._json(sock, "200 OK", {"ok": True, "at": at})
        except Fail as e:
            self._json(sock, "400 Bad Request", {"ok": False, "error": str(e)})
        except ValueError:
            self._json(sock, "400 Bad Request", {"ok": False, "error": "درخواست نامعتبر"})
        finally:
            db.close()

    # ------------------------------------------------------- media streaming
    def _media(self, sock, method, path, qs, headers):
        """GET /media/<message id>?k=<key>  - supports Range requests, so audio/video can play and seek."""
        try:
            mid = int(path.rsplit("/", 1)[1])
        except ValueError:
            return self._reply(sock, "404 Not Found", b"not found") or sock.close()
        uid = self.server.check_media_key((qs.get("k") or [""])[0])
        if uid is None:
            return self._reply(sock, "403 Forbidden", b"forbidden") or sock.close()
        db = connect_db(self.server.db_path)
        try:
            row = db.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
            user = db.execute("SELECT banned FROM users WHERE id=?", (uid,)).fetchone()
            allowed = bool(row and not row["deleted"] and row["kind"] == "file" and user and not user["banned"]
                           and db.execute("SELECT 1 FROM members WHERE chat_id=? AND user_id=?",
                                          (row["chat_id"], uid)).fetchone())
        finally:
            db.close()
        fpath = resolve_upload(row["file_path"]) if allowed else None
        if fpath is None:
            return self._reply(sock, "404 Not Found", b"not found") or sock.close()
        mime, _, inline = media_info(row["file_name"])
        return self._send_file(sock, method, headers, fpath, mime, row["file_name"], "dl" in qs or not inline)

    def _send_file(self, sock, method, headers, fpath, mime, file_name, as_download=False):
        size = fpath.stat().st_size
        start, end, status = 0, size - 1, "200 OK"
        rng = headers.get("range", "")
        if rng.startswith("bytes=") and "," not in rng and size:
            a, _, b = rng[6:].strip().partition("-")
            try:
                if a == "":                                  # suffix range: last N bytes
                    start = max(0, size - int(b))
                else:
                    start = int(a)
                    end = min(int(b), size - 1) if b else size - 1
            except ValueError:
                start = size
            if start >= size or start > end:
                head = (f"HTTP/1.1 416 Range Not Satisfiable\r\nContent-Range: bytes */{size}\r\n"
                        "Content-Length: 0\r\nConnection: close\r\n\r\n").encode()
                try:
                    sock.sendall(head)
                except OSError:
                    pass
                return sock.close()
            status = "206 Partial Content"
        length = max(0, end - start + 1)
        ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", file_name) or "file"
        disp = (f"{'attachment' if as_download else 'inline'}; filename=\"{ascii_name}\"; "
                f"filename*=UTF-8''{quote(file_name)}")
        head = (f"HTTP/1.1 {status}\r\nContent-Type: {mime}\r\nContent-Length: {length}\r\nAccept-Ranges: bytes\r\n"
                + (f"Content-Range: bytes {start}-{end}/{size}\r\n" if status.startswith("206") else "")
                + f"Content-Disposition: {disp}\r\nX-Content-Type-Options: nosniff\r\n"
                "Content-Security-Policy: sandbox\r\nCross-Origin-Resource-Policy: same-origin\r\n"
                "Cache-Control: private, max-age=3600\r\nConnection: close\r\n\r\n").encode()
        try:
            sock.settimeout(300)
            sock.sendall(head)
            if method != "HEAD" and length:
                with open(fpath, "rb") as f:
                    f.seek(start)
                    left = length
                    while left > 0:
                        chunk = f.read(min(65536, left))
                        if not chunk:
                            break
                        sock.sendall(chunk)
                        left -= len(chunk)
        except (OSError, ssl.SSLError):                      # player closed the connection (seek/pause): normal
            pass
        finally:
            sock.close()

    # --------------------------------------------------------------- upload
    @staticmethod
    def _discard(sock, headers, rest, cap=8 * 1024 * 1024):
        """Read and drop an unread request body so the browser gets our error reply instead of a TCP reset."""
        try:
            left = int(headers.get("content-length", "0")) - len(rest)
            if left > cap:
                return
            sock.settimeout(10)
            while left > 0:
                chunk = sock.recv(min(65536, left))
                if not chunk:
                    break
                left -= len(chunk)
        except (ValueError, OSError, ssl.SSLError):
            pass

    def _notify(self, sock, addr, headers, rest):
        """POST /notify  {"token": session token, "since": n}  -> long-poll used by the Android app's background service"""
        try:
            length = int(headers.get("content-length", "0"))
            if not 0 < length <= 2048:
                raise ValueError
            body = bytes(rest)
            sock.settimeout(10)
            while len(body) < length:
                chunk = sock.recv(length - len(body))
                if not chunk:
                    raise ValueError
                body += chunk
            req = json.loads(body[:length].decode())
            sock.settimeout(60)
            status, obj = self.server.notify_poll(req.get("token"), req.get("since", -1), addr[0])
        except (ValueError, OSError, ssl.SSLError):
            return self._json(sock, "400 Bad Request", {"ok": False})
        return self._json(sock, {200: "200 OK", 403: "403 Forbidden", 429: "429 Too Many Requests"}.get(status, "400 Bad Request"), obj)

    def _ghab_share(self, sock, addr, headers, rest):
        """POST /ghab-share (Ghab's server -> here, same machine only): drop a shared-post link into a friend's chat.
        The body is signed (see server.ghab_share), so even on loopback only Ghab, which holds the key, can use it."""
        if addr[0] not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            return self._json(sock, "403 Forbidden", {"ok": False})
        try:
            length = int(headers.get("content-length", "0"))
            if not 0 < length <= 4096:
                raise ValueError
            body = bytes(rest)
            sock.settimeout(10)
            while len(body) < length:
                chunk = sock.recv(length - len(body))
                if not chunk:
                    raise ValueError
                body += chunk
            req = json.loads(body[:length].decode())
            if not isinstance(req, dict):
                raise ValueError
        except (ValueError, OSError, ssl.SSLError):
            return self._json(sock, "400 Bad Request", {"ok": False})
        try:
            status, obj = self.server.ghab_share(req)
        except Exception as e:
            log("ghab_share error:", repr(e))
            status, obj = 500, {"ok": False}
        return self._json(sock, {200: "200 OK", 400: "400 Bad Request", 403: "403 Forbidden", 404: "404 Not Found",
                                 409: "409 Conflict", 429: "429 Too Many Requests"}.get(status, "500 Internal Server Error"), obj)

    def _json(self, sock, status, obj):
        self._reply(sock, status, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")
        sock.close()

    RESUME_KEEP = 1800          # a half-finished resumable upload is kept this many seconds
    RESUME_MAX = 3              # ... and one user may have at most this many at the same time (the oldest goes)

    @staticmethod
    def _resume_tmp(uid, rid):
        rid = re.sub(r"[^0-9a-zA-Z]", "", str(rid or ""))[:40]
        if len(rid) < 8:
            return None
        d = common.UPLOADS_DIR / ".tmp"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"r_{uid}_{rid}"

    def _upload_status(self, sock, qs):
        """GET /upload-status?k=<key>&rid=<id>  -> {"ok":true,"have":<bytes already stored>} (so the app can continue after a cut)"""
        uid = self.server.check_media_key((qs.get("k") or [""])[0])
        if uid is None:
            return self._json(sock, "403 Forbidden", {"ok": False})
        t = self._resume_tmp(uid, (qs.get("rid") or [""])[0])
        have = 0
        try:
            if t is not None and t.is_file() and time.time() - t.stat().st_mtime < self.RESUME_KEEP:
                have = t.stat().st_size
        except OSError:
            have = 0
        return self._json(sock, "200 OK", {"ok": True, "have": have})

    def _upload(self, sock, qs, headers, rest):
        """POST /upload?k=<key>&chat_id=..&name=..[&text=..][&reply_to=..]  with the raw file as the body.
        Resumable: add &rid=<random id>&offset=<bytes already sent>&total=<full size>; the body is then only the rest of the file.
        Streams straight to disk, so big videos don't need to fit in memory (limit: MAX_UPLOAD)."""
        origin = headers.get("origin")
        if origin and urlparse(origin).netloc != headers.get("host"):
            self._discard(sock, headers, rest)
            return self._json(sock, "403 Forbidden", {"ok": False, "error": "bad origin"})
        uid = self.server.check_media_key((qs.get("k") or [""])[0])
        if uid is None:
            self._discard(sock, headers, rest)
            return self._json(sock, "403 Forbidden", {"ok": False, "error": "نشست معتبر نیست؛ صفحه رو رفرش کن"})
        if not common.disk_ok():
            self._discard(sock, headers, rest)
            return self._json(sock, "507 Insufficient Storage", {"ok": False, "error": "فضای دیسک سرور تقریباً پره؛ به مدیر بگو"})
        # a per-user cap BEFORE the body is read: many parallel uploads must not all pass disk_ok() and stream to disk together
        if not self.server._room_hits(("upload", uid), 20, 60):
            self._discard(sock, headers, rest)
            return self._json(sock, "429 Too Many Requests", {"ok": False, "error": "یه لحظه صبر کن، خیلی سریع آپلود می‌کنی"})
        try:
            chat_id = int(qs["chat_id"][0])
            reply_to = int(qs["reply_to"][0]) if qs.get("reply_to") else None
            length = int(headers.get("content-length", ""))
        except (KeyError, ValueError, IndexError):
            self._discard(sock, headers, rest)
            return self._json(sock, "400 Bad Request", {"ok": False, "error": "درخواست نامعتبر"})
        name = re.sub(r"[\x00-\x1f\x7f\u2028\u2029]", "", (qs.get("name") or ["file"])[0]).strip() or "file"
        text = (qs.get("text") or [""])[0]
        voice = None
        if qs.get("voice"):
            voice = {"dur": (qs.get("dur") or ["0"])[0], "wave": (qs.get("wave") or [""])[0]}
        if length <= 0:
            return self._json(sock, "400 Bad Request", {"ok": False, "error": "فایل خالیه"})
        if length > MAX_UPLOAD:
            self._discard(sock, headers, rest, cap=64 * 1024 * 1024)
            return self._json(sock, "413 Payload Too Large",
                              {"ok": False, "error": f"حجم فایل بیشتر از {MAX_UPLOAD // (1024 * 1024)} مگابایته"})
        # bytes-in-flight accounting: concurrent uploads must not all pass disk_ok() before any of them finishes writing
        if not common.disk_ok(extra=length + self.server._upload_bytes_inflight()):
            self._discard(sock, headers, rest)
            return self._json(sock, "507 Insufficient Storage", {"ok": False, "error": "فضای دیسک سرور تقریباً پره؛ به مدیر بگو"})
        tmpdir = common.UPLOADS_DIR / ".tmp"
        tmpdir.mkdir(parents=True, exist_ok=True)
        rtmp = self._resume_tmp(uid, (qs.get("rid") or [""])[0])
        offset = 0
        keep = False
        if rtmp is not None:
            try:
                offset = int((qs.get("offset") or ["0"])[0])
                total = int((qs.get("total") or [str(length)])[0])
            except ValueError:
                self._discard(sock, headers, rest)
                return self._json(sock, "400 Bad Request", {"ok": False, "error": "درخواست نامعتبر"})
            have = rtmp.stat().st_size if rtmp.is_file() else 0
            if not rtmp.is_file():                  # a NEW partial upload: keep only the newest RESUME_MAX per user
                try:
                    mine = sorted(rtmp.parent.glob(f"r_{uid}_*"), key=lambda f: f.stat().st_mtime)
                    for old_ in mine[:max(0, len(mine) - self.RESUME_MAX + 1)]:
                        old_.unlink()
                except OSError:
                    pass
            if offset != have or offset + length != total or total > MAX_UPLOAD:
                self._discard(sock, headers, rest)
                return self._json(sock, "409 Conflict", {"ok": False, "error": "resume mismatch", "have": have})
            tmp = rtmp
            keep = True
        else:
            tmp = tmpdir / uuid.uuid4().hex
        db = None
        self.server._upload_begin(length)
        try:
            sock.settimeout(120)
            with open(tmp, "ab" if keep else "wb") as f:
                body = rest[:length]
                f.write(body)
                left = length - len(body)
                while left > 0:
                    chunk = sock.recv(min(65536, left))
                    if not chunk:
                        raise ConnectionError("upload interrupted")
                    f.write(chunk)
                    left -= len(chunk)
            db = connect_db(self.server.db_path)
            try:
                msg = self.server.create_file_message(db, uid, chat_id, text, reply_to, name, tmp, voice=voice)
            except Fail as e:
                return self._json(sock, "400 Bad Request", {"ok": False, "error": str(e)})
            self._json(sock, "200 OK", {"ok": True, "message": msg})
        except (ConnectionError, OSError, ssl.SSLError):
            sock.close()
        except Exception as e:
            log("upload error:", repr(e))
            self._json(sock, "500 Internal Server Error", {"ok": False, "error": "خطای داخلی سرور"})
        finally:
            self.server._upload_end(length)
            if db is not None:
                db.close()
            done = db is not None       # file fully received: the temp file is moved/unneeded
            if not (keep and not done):  # interrupted resumable upload: keep the part for the app to continue
                try:
                    tmp.unlink()            # already moved on success
                except OSError:
                    pass
            self._sweep_resume()

    def _sweep_resume(self):
        """delete half-finished resumable uploads older than RESUME_KEEP"""
        try:
            now_ = time.time()
            for f in (common.UPLOADS_DIR / ".tmp").glob("r_*"):
                if now_ - f.stat().st_mtime > self.RESUME_KEEP:
                    f.unlink()
        except OSError:
            pass

    # ----------------------------------------------------------- websocket
    def _websocket(self, sock, addr, headers):
        origin = headers.get("origin")
        if origin and urlparse(origin).netloc != headers.get("host"):     # block cross-site hijacking
            self._reply(sock, "403 Forbidden", b"bad origin")
            return sock.close()
        key = headers.get("sec-websocket-key")
        if not key:
            self._reply(sock, "400 Bad Request", b"no key")
            return sock.close()
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        sock.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode())
        sock.settimeout(900)            # mobile clients may go quiet for a while (screen off); they ping when awake
        conn = WSConn(self.server, sock, addr)
        conn.db = connect_db(self.server.db_path)
        try:
            while conn.alive:
                data = ws_read(sock, conn.send_raw)
                try:
                    req = json.loads(data.decode("utf-8"))
                except ValueError:
                    continue
                self.server._dispatch(conn, req)
        except (ConnectionError, OSError, ssl.SSLError, ValueError):
            pass
        except Exception as e:
            log("web client error:", repr(e))
        finally:
            self.server._drop(conn)
