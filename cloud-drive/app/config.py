"""Configuration. Everything comes from environment variables (or a .env file next to the project)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env_file():
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return int(default)


def load_config(**overrides):
    _load_env_file()
    data = Path(os.environ.get("CD_DATA_DIR") or ROOT / "data").resolve()
    cfg = dict(
        HOST=os.environ.get("CD_HOST", "0.0.0.0"),
        PORT=_env_int("CD_PORT", 8082),
        DATA_DIR=data,
        UPLOAD_DIR=data / "uploads",
        TMP_DIR=data / "tmp",
        LOG_DIR=data / "logs",
        DB_PATH=data / "cloud_drive.db",
        SECRET_KEY=os.environ.get("CD_SECRET_KEY", ""),
        SSO_SECRET=os.environ.get("CD_SSO_SECRET", ""),  # single sign-on from Windroida; empty = SSO disabled
        # Off when run folded into Windroida (start.py sets CD_PASSWORD_AUTH=0): the only way in is then the SSO
        # link, so there is no username/password to guess, reset or admin-login with at all. On by default so
        # Cloud Drive still works normally as its own standalone app (run.bat/run.sh never set this).
        HSTS=os.environ.get("CD_HSTS", "1") == "1",   # start.py sets 0: with a self-signed certificate HSTS would remove the browser's "continue anyway" for the whole host
        PASSWORD_AUTH=os.environ.get("CD_PASSWORD_AUTH", "1") == "1",
        COOKIE_SECURE=os.environ.get("CD_COOKIE_SECURE", "0") == "1",
        TRUSTED_PROXY=os.environ.get("CD_TRUSTED_PROXY", "0") == "1",
        MAX_UPLOAD_MB=_env_int("CD_MAX_UPLOAD_MB", 0),  # 0 = no per-file limit (quota and free disk still apply)
        DEFAULT_QUOTA_MB=_env_int("CD_DEFAULT_QUOTA_MB", 7168),  # 7 GB per user
        CHUNK_SIZE=_env_int("CD_CHUNK_SIZE_MB", 4) * 1024 * 1024,
        SCAN_COMMAND=os.environ.get("CD_SCAN_COMMAND", ""),
        SCRYPT_N=2 ** 15,
        TESTING=False,
        HOUSEKEEPING=True,
    )
    cfg.update(overrides)
    for k in ("UPLOAD_DIR", "TMP_DIR", "LOG_DIR", "DB_PATH"):
        if k not in overrides:
            base = Path(cfg["DATA_DIR"]).resolve()
            cfg[k] = base / {"UPLOAD_DIR": "uploads", "TMP_DIR": "tmp", "LOG_DIR": "logs", "DB_PATH": "cloud_drive.db"}[k]
    cfg["DATA_DIR"] = Path(cfg["DATA_DIR"]).resolve()
    return cfg
