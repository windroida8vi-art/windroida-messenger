"""One-click launcher (double-click start.bat).

Starts everything: server + web UI (https), the admin datasheet, Cloud Drive (فضای ابری), and opens the web UI
in your browser. Friends on your Wi-Fi/LAN just open the "Friends" address printed below in Chrome.
Missing Python libraries (Pillow, cryptography, and Cloud Drive's Flask/waitress) are installed automatically.

Options:  --local        only this PC (don't open to the network)
          --http         plain http instead of https (voice recording/calls then only work on this PC)
          --no-datasheet / --no-install / --no-drive / --no-ghab
          --browser      also open the web UI in the browser (off by default)
"""
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

here = Path(__file__).resolve().parent
os.environ["WINDROIDA_LAUNCHER"] = "1"
sys.path.insert(0, str(here))
from server import lan_ip  # noqa: E402

PORT, WEB_PORT, DRIVE_PORT = 8765, 8081, int(os.environ.get("WINDROIDA_DRIVE_PORT") or 8082)
GHAB_PORT = int(os.environ.get("WINDROIDA_GHAB_PORT") or 8084)
flags = set(a for a in sys.argv[1:] if a.startswith("--"))


LOGDIR = here / "data" / "logs"


def _logfile(name):
    """Child processes write here instead of the console, so the window stays clean (open the file if something looks wrong)."""
    try:
        LOGDIR.mkdir(parents=True, exist_ok=True)
        p = LOGDIR / (name + ".log")
        if p.exists() and p.stat().st_size > 2_000_000:           # keep one old copy, start a fresh file
            try:
                p.replace(LOGDIR / (name + ".old.log"))
            except OSError:
                pass
        return open(p, "ab")
    except OSError:
        return subprocess.DEVNULL


def _quiet_kw(name):
    kw = {"stdout": _logfile(name), "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000                            # CREATE_NO_WINDOW
    return kw


def spawn(script, *args):
    name = Path(script).stem
    kw = {} if name == "datasheet" else _quiet_kw(name)
    return subprocess.Popen([sys.executable, str(here / script), *args], cwd=str(here), **kw)


def port_open(port):
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
        return True
    except OSError:
        return False


REQUIREMENTS = [("PIL", "Pillow", "profile photos"), ("cryptography", "cryptography", "https certificate")]


def ensure_libs():
    """Try to import each library; if missing pip-install it (several fallbacks). Never fatal."""
    import importlib
    missing = []
    for mod, pkg, why in REQUIREMENTS:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append((mod, pkg, why))
    if not missing:
        return
    print("  Installing needed libraries: " + ", ".join(p for _, p, _ in missing) + " ...", flush=True)
    for mod, pkg, why in missing:
        done = False
        wheels = here / "wheels"        # offline cache made by download_wheels.bat: works without any internet
        srcs = ([["--no-index", "--find-links", str(wheels)]] if wheels.is_dir() else []) + [[]]
        for src, extra in [(a, b) for a in srcs for b in ([], ["--user"], ["--break-system-packages"], ["--user", "--break-system-packages"])]:
            r = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q", pkg, *src, *extra],
                               capture_output=True, text=True, timeout=180)
            if r.returncode == 0:
                done = True
                break
        try:
            importlib.invalidate_caches()
            importlib.import_module(mod)
        except ImportError:
            done = False
        print(f"    {'OK  ' if done else 'FAIL'} {pkg}" + ("" if done else f"  (no {why}; run: pip install {pkg})"), flush=True)
    print()


DRIVE_REQUIREMENTS = [("flask", "Flask", "فضای ابری - لازم"), ("waitress", "waitress", "فضای ابری - سرور تولید"),
                      ("argon2", "argon2-cffi", "فضای ابری - هش رمز قوی‌تر")]


def ensure_drive_libs():
    """Same idea as ensure_libs() but for Cloud Drive's own requirements, installed into this SAME Python (no venv,
    so one `start.bat` run gets everything). Flask is required; waitress/argon2-cffi are optional (Cloud Drive
    falls back on its own if they're missing). Returns True iff Cloud Drive can actually be started."""
    import importlib
    missing = []
    for mod, pkg, why in DRIVE_REQUIREMENTS:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append((mod, pkg, why))
    if missing:
        print("  Installing Cloud Drive libraries: " + ", ".join(p for _, p, _ in missing) + " ...", flush=True)
        for mod, pkg, why in missing:
            done = False
            wheels = here / "wheels"
            srcs = ([["--no-index", "--find-links", str(wheels)]] if wheels.is_dir() else []) + [[]]
            for src, extra in [(a, b) for a in srcs for b in ([], ["--user"], ["--break-system-packages"], ["--user", "--break-system-packages"])]:
                r = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q", pkg, *src, *extra],
                                   capture_output=True, text=True, timeout=180)
                if r.returncode == 0:
                    done = True
                    break
            try:
                importlib.invalidate_caches()
                importlib.import_module(mod)
            except ImportError:
                done = False
            print(f"    {'OK  ' if done else 'FAIL'} {pkg}" + ("" if done else f"  (no {why})"), flush=True)
        print()
    try:
        importlib.import_module("flask")
        return True
    except ImportError:
        return False


def spawn_drive(drive_secret, local):
    """Launch cloud-drive/wsgi.py as another subprocess of this same Python (its own venv/run.bat/run.sh are for
    running it standalone; start.bat instead folds it in, same as the datasheet). Never fatal: if anything about
    Cloud Drive fails, the messenger itself still starts normally."""
    env = dict(os.environ)
    env["CD_PORT"] = str(DRIVE_PORT)
    env["CD_HOST"] = "127.0.0.1" if local else "0.0.0.0"
    env["CD_SSO_SECRET"] = drive_secret
    env["CD_HSTS"] = "0"
    env["CD_PASSWORD_AUTH"] = "0"      # folded into Windroida: only the SSO link gets anyone in, no separate
                                        # username/password (and so no separate admin login either - see datasheet)
    crt, key = here / "data" / "server.crt", here / "data" / "server.key"
    if crt.is_file() and key.is_file():          # reuse Windroida's own certificate: same browser warning, real TLS
        env["CD_SSL_CERT"], env["CD_SSL_KEY"], env["CD_COOKIE_SECURE"] = str(crt), str(key), "1"
    return subprocess.Popen([sys.executable, str(here / "cloud-drive" / "wsgi.py")], cwd=str(here / "cloud-drive"), env=env, **_quiet_kw("cloud-drive"))


def _drive_bg(result, do_install, local):
    """Runs on its own thread: install (optional), read the shared secret server.py already wrote, spawn. Writes
    into `result` (a plain dict the main thread already holds a reference to) so the main thread can find and stop
    the process later, but never waits on this thread itself."""
    try:
        ok = ensure_drive_libs() if do_install else _have_flask()
        if not ok:
            result["status"] = "no-flask"
            return
        secret = (here / "data" / "drive_sso.key").read_text(encoding="utf-8").strip()
        if not secret:
            result["status"] = "no-secret"
            return
        result["proc"] = spawn_drive(secret, local)
        result["respawn"] = lambda: spawn_drive(secret, local)
        result["status"] = "started"
    except Exception:
        result["status"] = "error"


GHAB_REQUIREMENTS = [("flask", "Flask", "قاب - لازم"), ("imageio_ffmpeg", "imageio-ffmpeg", "قاب - فشرده‌سازی ویدیو (اختیاری)")]


def _pip_install(mod, pkg, why):
    import importlib
    try:
        importlib.import_module(mod)
        return True
    except ImportError:
        pass
    wheels = here / "wheels"
    srcs = ([["--no-index", "--find-links", str(wheels)]] if wheels.is_dir() else []) + [[]]
    for src, extra in [(a, b) for a in srcs for b in ([], ["--user"], ["--break-system-packages"], ["--user", "--break-system-packages"])]:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q", pkg, *src, *extra],
                           capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            break
    try:
        importlib.invalidate_caches()
        importlib.import_module(mod)
        return True
    except ImportError:
        return False


def spawn_ghab(secret, local):
    """Ghab (قاب) as another subprocess of this same Python, exactly like Cloud Drive: no signup/login/admin page of its
    own (GHAB_PASSWORD_AUTH=0), entered only through the Windroida menu link, same https certificate. Never fatal."""
    env = dict(os.environ)
    env["GHAB_PORT"] = str(GHAB_PORT)
    env["GHAB_SSO_SECRET"] = secret
    env["GHAB_PASSWORD_AUTH"] = "0"
    env["WD_WEB_PORT"] = str(WEB_PORT)   # so a "message" tap in Ghab can open the real chat on the messenger
    env["PYTHONIOENCODING"] = "utf-8"
    crt, key = here / "data" / "server.crt", here / "data" / "server.key"
    if crt.is_file() and key.is_file():
        env["GHAB_CERT"], env["GHAB_KEY"] = str(crt), str(key)
    return subprocess.Popen([sys.executable, str(here / "ghab" / "app.py")], cwd=str(here / "ghab"), env=env, **_quiet_kw("ghab"))


def _ghab_bg(result, do_install, local):
    try:
        ok = _pip_install("flask", "Flask", "قاب") if do_install else _have_flask()
        if not ok:
            result["status"] = "no-flask"
            return
        if do_install:
            _pip_install("imageio_ffmpeg", "imageio-ffmpeg", "فشرده‌سازی ویدیو")   # optional: Ghab works without it
        secret = (here / "data" / "ghab_sso.key").read_text(encoding="utf-8").strip()
        if not secret:
            result["status"] = "no-secret"
            return
        result["proc"] = spawn_ghab(secret, local)
        result["respawn"] = lambda: spawn_ghab(secret, local)
        result["status"] = "started"
    except Exception:
        result["status"] = "error"


_stopping = threading.Event()


def _why(name, code):
    """Write why a service stopped (exit code + the last lines of its own log) to data/logs/supervisor.log: next time the cause is known."""
    try:
        LOGDIR.mkdir(parents=True, exist_ok=True)
        tail = ""
        base = name.split(" (")[0]
        lf = LOGDIR / (("server" if base == "Windroida" else base.lower().replace(" ", "-")) + ".log")
        if lf.is_file():
            data = lf.read_bytes()[-3000:].decode("utf-8", "replace").splitlines()[-15:]
            tail = "\n".join("    | " + x for x in data)
        with open(LOGDIR / "supervisor.log", "a", encoding="utf-8") as f:
            f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {name} stopped, exit code {code}\n{tail}\n")
    except Exception:
        pass


def _supervise(named_results):
    """Cloud Drive and Ghab run as their own processes. If one dies (a crash, ffmpeg going wild, the process being killed) it is started
    again after a few seconds - at most 8 times in 10 minutes, so a service that can never start doesn't loop forever."""
    crashes = {name: [] for name, _ in named_results}
    pause = {}                                   # name -> time before which it is not started again (it never gives up for good)
    while not _stopping.wait(3):
        for name, res in named_results:
            again = res.get("respawn")
            if again is None:
                continue
            p = res.get("proc")
            if p is not None and p.poll() is None:
                continue
            t = time.time()
            if p is not None:                                # it has just died
                _why(name, p.returncode)
                crashes[name] = [x for x in crashes[name] if x > t - 600] + [t]
                n = len(crashes[name])
                res["proc"] = None
                if n > 6:                                    # crash loop: rest for 2 minutes, then try again (forever)
                    pause[name] = t + 120
                    print(f"\n  {name} keeps crashing; resting 2 minutes, then trying again (the messenger is unaffected). Details: data/logs/\n", flush=True)
                    continue
                pause[name] = t + min(30, 2 * n)             # short, growing pause so a busy port can be released
            if t < pause.get(name, 0):
                continue
            print(f"\n  {name}: starting it again ...\n", flush=True)
            try:
                res["proc"] = again()
            except Exception:
                res["proc"] = None
                pause[name] = t + 30


def _have_flask():
    try:
        import flask  # noqa: F401
        return True
    except ImportError:
        return False


def save_wheels_in_background():
    """With internet: quietly copy the libraries into ./wheels (exactly for THIS Python), so the whole folder can be moved to
    another PC/server and start.bat installs them from there without any internet. Skipped if wheels/ already has files."""
    try:
        wheels = here / "wheels"
        if wheels.is_dir() and any(wheels.glob("*.whl")):
            return
        wheels.mkdir(exist_ok=True)
        kw = {"creationflags": 0x08000000} if os.name == "nt" else {}      # no black window on Windows
        subprocess.Popen([sys.executable, "-m", "pip", "download", "--disable-pip-version-check", "-q", "-r",
                          str(here / "requirements-all.txt"), "-d", str(wheels)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, **kw)
    except Exception:
        pass


def real_scheme(wanted):
    """The server falls back to http if it could not make a certificate; ask it which one it really speaks."""
    if wanted == "http":
        return "http"
    import ssl
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection(("127.0.0.1", WEB_PORT), timeout=2) as raw:
            ctx.wrap_socket(raw).close()
        return "https"
    except OSError:
        return "http"


def have_tk():
    try:
        import tkinter  # noqa: F401
        return True
    except ImportError:
        return False


def keep_awake_and_unfreeze():
    """Windows only. (1) A click inside a cmd window turns on "selection" and FREEZES the program until a key is pressed: that is
    the classic reason a server "falls asleep". QuickEdit is switched off. (2) The PC is told not to sleep while the server runs."""
    if os.name != "nt":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-10)                                     # STD_INPUT_HANDLE
        mode = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(mode)):
            k.SetConsoleMode(h, (mode.value & ~0x0040) | 0x0080)    # clear ENABLE_QUICK_EDIT_MODE, set ENABLE_EXTENDED_FLAGS
        k.SetThreadExecutionState(0x80000000 | 0x00000001)          # ES_CONTINUOUS | ES_SYSTEM_REQUIRED (the thread must stay alive: it is the main one)
    except Exception:
        pass


def alive(port, tls_first=True, timeout=None):
    """True only if something on the port really ANSWERS an http request (a hung process that merely owns the port fails)."""
    import ssl
    timeout = timeout or float(os.environ.get("WINDROIDA_WD_TIMEOUT") or 20.0)
    for tls in ((True, False) if tls_first else (False, True)):
        try:
            raw = socket.create_connection(("127.0.0.1", port), timeout=timeout)
            raw.settimeout(timeout)
            if tls:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                raw = ctx.wrap_socket(raw)
            raw.sendall(b"GET /__ping HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n")
            data = raw.recv(16)
            raw.close()
            if data.startswith(b"HTTP/"):
                return True
        except (OSError, ssl.SSLError):
            continue
    return False


def _watchdog(targets):
    """Guard dog. Every 20 s it knocks on each service's port. A process that is still "running" but no longer answers
    (frozen / deadlocked) 4 times in a row (about 80 s) is killed, and the normal supervisors then start it again.
    A freshly started process gets 3 minutes to come up before it is judged."""
    state = {}
    every, grace = float(os.environ.get("WINDROIDA_WD_EVERY") or 20), float(os.environ.get("WINDROIDA_WD_GRACE") or 180)
    while not _stopping.wait(every):
        for name, port, get_proc in targets:
            p = get_proc()
            if p is None or p.poll() is not None:
                state.pop(name, None)
                continue
            st = state.get(name)
            if st is None or st["pid"] != p.pid:
                st = state[name] = {"pid": p.pid, "t0": time.time(), "bad": 0}
            if alive(port):
                st["bad"] = 0
                continue
            if time.time() - st["t0"] < grace:
                continue
            st["bad"] += 1
            if st["bad"] >= 6:
                _why(name + " (hung)", "no answer for ~%d s" % int(every * 6))
                print(f"\n  {name} stopped answering - restarting it ...\n", flush=True)
                try:
                    p.kill()
                except OSError:
                    pass
                state.pop(name, None)


_JOB = None


def kill_children_with_me():
    """Windows: put this process into a "job" that kills every process in it when this one ends. Closing the black window
    kills start.py without running any cleanup, and the servers (started without a window) used to stay alive and keep
    their ports busy until Windows was restarted. Now they all die together with the window."""
    global _JOB
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateJobObjectW.restype = wintypes.HANDLE
        k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k.GetCurrentProcess.restype = wintypes.HANDLE
        k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]

        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

        class IOC(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                       "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class EXT(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IOC), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]
        job = k.CreateJobObjectW(None, None)
        if not job:
            return
        info = EXT()
        info.BasicLimitInformation.LimitFlags = 0x2000              # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)) and \
                k.AssignProcessToJobObject(job, k.GetCurrentProcess()):
            _JOB = job                                             # keep the handle open for as long as we live
    except Exception:
        pass


def kill_leftovers():
    """Servers left over from an older run whose window was closed (they hold the ports): stop them. Only python processes that run
    files from THIS folder (never start.py itself)."""
    if os.name != "nt":
        return
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\\.exe$' -and $_.CommandLine -and "
          "$_.CommandLine.Contains($env:WD_DIR) -and -not $_.CommandLine.Contains('start.py') -and $_.ProcessId -ne [int]$env:WD_PID } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    try:
        env = dict(os.environ, WD_DIR=str(here), WD_PID=str(os.getpid()))
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], env=env, timeout=40,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, creationflags=0x08000000)
    except Exception:
        pass


def main():
    kill_children_with_me()
    keep_awake_and_unfreeze()
    if "--no-install" not in flags:
        ensure_libs()
        save_wheels_in_background()
    if port_open(WEB_PORT) or port_open(PORT):
        kill_leftovers()                                   # an old run whose window was closed may still hold the ports
        for _ in range(20):
            if not (port_open(WEB_PORT) or port_open(PORT)):
                break
            time.sleep(0.4)
    if port_open(WEB_PORT) or port_open(PORT):
        print("\n  Windroida seems to be running already (port %d/%d is busy)." % (PORT, WEB_PORT))
        print("  Close the other Windroida window first, then try again.\n")
        return 1
    want_drive = "--no-drive" not in flags
    drive_already_running = want_drive and port_open(DRIVE_PORT)
    server_args = ["--web", "--web-port", str(WEB_PORT), "--port", str(PORT)]
    if "--local" not in flags:
        server_args += ["--host", "0.0.0.0"]
    scheme = "http" if "--http" in flags else "https"
    if scheme == "http":
        server_args.append("--http")
    procs = [spawn("server.py", *server_args)]
    time.sleep(0.3)
    for _ in range(60):                                   # wait until the server answers
        if procs[0].poll() is not None:
            print("\n  The server could not start (see the message above).\n")
            return 1
        if port_open(WEB_PORT):
            break
        time.sleep(0.2)

    # Cloud Drive is optional and its (rare) pip install can be slow on a bad connection, so it's set up in the
    # background: the messenger itself must never wait on it. drive_result gets filled in once that's done.
    drive_result = {"proc": None, "status": "running-separately" if drive_already_running else None}
    if want_drive and not drive_already_running:
        threading.Thread(target=_drive_bg, args=(drive_result, "--no-install" not in flags, "--local" in flags), daemon=True).start()

    want_ghab = "--no-ghab" not in flags and (here / "ghab" / "app.py").is_file()
    ghab_already_running = want_ghab and port_open(GHAB_PORT)
    ghab_result = {"proc": None, "status": "running-separately" if ghab_already_running else None}
    if want_ghab and not ghab_already_running:
        threading.Thread(target=_ghab_bg, args=(ghab_result, "--no-install" not in flags, "--local" in flags), daemon=True).start()

    threading.Thread(target=_supervise, args=([("Cloud Drive", drive_result), ("Ghab", ghab_result)],), daemon=True).start()
    threading.Thread(target=_watchdog, args=([("Windroida", WEB_PORT, lambda: procs[0]), ("Cloud Drive", DRIVE_PORT, lambda: drive_result.get("proc")),
                                              ("Ghab", GHAB_PORT, lambda: ghab_result.get("proc"))],), daemon=True).start()

    scheme = real_scheme(scheme)
    print("\n" + "=" * 58)
    print("  Windroida is running")
    print(f"    Web UI (this PC):  {scheme}://127.0.0.1:{WEB_PORT}")
    if "--local" not in flags:
        print(f"    Friends (Wi-Fi):   {scheme}://{lan_ip()}:{WEB_PORT}")
    if scheme == "https":
        print("  First visit: the browser warns about the self-signed certificate -> Advanced -> Continue.")
        print("  (https is what lets browsers use the microphone for voice messages and calls.)")
    elif "--http" not in flags:
        print("  https is OFF (certificate could not be created: pip install cryptography). Voice only works on this PC.")
    try:                                              # fingerprint of the server certificate: the Android app asks you to confirm it once
        import hashlib, ssl as _ssl
        _pem = (here / "data" / "server.crt")
        if _pem.exists():
            _fp = hashlib.sha256(_ssl.PEM_cert_to_DER_cert(_pem.read_text())).hexdigest().upper()
            print("  Android app certificate fingerprint (SHA-256):")
            print("    " + ":".join(_fp[i:i + 2] for i in range(0, len(_fp), 2)))
    except Exception:
        pass
    if drive_already_running:
        print(f"    Cloud Drive (فضای ابری):  http://127.0.0.1:{DRIVE_PORT}  (از قبل جدا روشن بود)")
    elif want_drive:
        print(f"    Cloud Drive (فضای ابری):  داره تو پس‌زمینه آماده می‌شه... (از منوی ویندروید → ☁ فضای ابری)")
    elif want_drive:
        print("    Cloud Drive (فضای ابری): راه نیفتاد (Flask نصب نشد یا پوشهٔ cloud-drive پیدا نشد)")
    if ghab_already_running:
        print(f"    Ghab (قاب):  port {GHAB_PORT} از قبل جدا روشن بود")
    elif want_ghab:
        print("    Ghab (قاب):  داره تو پس‌زمینه آماده می‌شه...  (از منوی ویندروید)")
    print("  The window stays quiet on purpose; details are in data/logs/ and data/windroida.log.")
    print("  Close this window to stop everything (a click inside it no longer freezes anything).")
    print("=" * 58 + "\n", flush=True)

    if have_tk():
        if "--no-datasheet" not in flags:
            procs.append(spawn("datasheet.py"))
    else:
        print("  (tkinter is not installed, so the desktop windows are skipped; the web UI works.)\n")
    if "--browser" in flags:
        webbrowser.open(f"{scheme}://127.0.0.1:{WEB_PORT}")

    try:
        crashes = []                                       # supervisor: if the server process dies, start it again (max 8 times in 10 minutes)
        while True:
            while procs[0].poll() is None:
                time.sleep(0.5)
            code = procs[0].returncode
            t = time.time()
            crashes = [x for x in crashes if x > t - 600] + [t]
            if code in (0, None) or len(crashes) > 8:
                break
            _why("Windroida", code)
            print(f"\n  The server stopped unexpectedly (code {code}); restarting in 3 s ... (details: data/windroida.log)\n", flush=True)
            time.sleep(3)
            procs[0] = spawn("server.py", *server_args)
    finally:
        _stopping.set()
        for p in procs:
            if p.poll() is None:
                p.terminate()
        gp = ghab_result.get("proc")
        if gp is not None and gp.poll() is None:
            gp.terminate()
        dp = drive_result.get("proc")                  # may have been started just now by the background thread
        if dp is not None and dp.poll() is None:
            dp.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
