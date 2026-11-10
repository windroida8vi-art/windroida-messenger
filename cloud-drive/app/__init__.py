"""Cloud Drive application factory."""
import logging
import os
import secrets
import threading
import time
from datetime import timedelta
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, request, send_from_directory

from . import db as dbm
from .config import load_config
from .errors import ApiError
from .fileops import cleanup_stale_uploads, purge_expired_files, purge_expired_trash
from .security import RateLimiter, client_ip
from .services import get_int, get_setting, log_event
from .storage import LocalStorage

__version__ = "1.0.0"


def _resolve_secret(app):
    key = app.config.get("SECRET_KEY")
    if key:
        return key
    f = app.config["DATA_DIR"] / "secret.key"  # generated once, random, never in the source tree
    if not f.exists():
        f.write_text(secrets.token_hex(32))
        try:
            os.chmod(f, 0o600)
        except OSError:
            pass
    return f.read_text().strip()


def run_housekeeping(app):
    """One maintenance pass: stale uploads, 20-day file retention, expired trash. Needs an app context for settings."""
    with app.app_context():
        c = dbm.connect(app.config["DB_PATH"])
        try:
            cleanup_stale_uploads(c, app.storage, get_int(c, "incomplete_upload_hours"))
            purge_expired_files(c, app.storage, get_int(c, "file_retention_days"))
            if get_setting(c, "trash_enabled") == "1":
                purge_expired_trash(c, app.storage, get_int(c, "trash_retention_days"))
        finally:
            c.close()


def _housekeeping(app):
    first = True
    while True:
        if not first:
            time.sleep(600)
        first = False
        try:
            run_housekeeping(app)
        except Exception:
            app.logger.exception("housekeeping failed")


def create_app(**overrides):
    cfg = load_config(**overrides)
    app = Flask(__name__, static_folder=str(os.path.join(os.path.dirname(__file__), "static")), static_url_path="/static")
    app.config.update(cfg)
    for k in ("DATA_DIR", "UPLOAD_DIR", "TMP_DIR", "LOG_DIR"):
        app.config[k].mkdir(parents=True, exist_ok=True)
    app.config.update(
        SECRET_KEY=_resolve_secret(app), SESSION_COOKIE_NAME="cd_session", SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=cfg["COOKIE_SECURE"],
        PERMANENT_SESSION_LIFETIME=timedelta(days=14), MAX_CONTENT_LENGTH=cfg["CHUNK_SIZE"] + 1024 * 1024,
        JSON_AS_ASCII=False, DEBUG=False)
    app.storage = LocalStorage(app.config["UPLOAD_DIR"], app.config["TMP_DIR"])
    app.limiter = RateLimiter()

    handler = RotatingFileHandler(app.config["LOG_DIR"] / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    dbm.migrate(app.config["DB_PATH"])
    app.teardown_appcontext(dbm.close_db)

    from . import routes_admin, routes_auth, routes_files, routes_share, routes_sso
    for m in (routes_auth, routes_files, routes_share, routes_admin, routes_sso):
        app.register_blueprint(m.bp)

    @app.before_request
    def _no_admin_when_folded():
        # folded into Windroida (CD_PASSWORD_AUTH=0): the datasheet is the only admin panel, so the web admin page and API do not exist at all
        if not app.config.get("PASSWORD_AUTH", True) and (request.path.rstrip("/") == "/admin" or request.path.startswith("/api/admin")):
            return jsonify(error="not_found", message="یافت نشد", message_en="Not found"), 404

    @app.before_request
    def _global_rate_limit():
        if request.path.startswith("/api/"):
            if request.mimetype == "application/json" and request.method in ("POST", "PUT", "PATCH", "DELETE"):
                body = request.get_json(silent=True)
                if body is not None and not isinstance(body, dict):  # arrays/strings/numbers are never valid here
                    return jsonify(error="bad_request", message="بدنه درخواست نامعتبر است", message_en="Invalid request body"), 400
            limit = get_int(dbm.get_db(), "rate_api_per_min")
            if limit > 0 and not app.limiter.hit("api:%s" % client_ip(), limit, 60):
                return jsonify(error="rate_limited", message="تعداد درخواست‌ها زیاد است", message_en="Too many requests"), 429

    @app.after_request
    def _headers(resp):
        if resp.status_code < 500:
            dbm.commit_db()
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        resp.headers.setdefault("Content-Security-Policy",
                                "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                                "frame-src 'self'; object-src 'self'; base-uri 'self'; form-action 'self'; "
                                "frame-ancestors 'self'")
        if app.config["COOKIE_SECURE"] and app.config.get("HSTS", True):
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        if request.path.startswith("/api/") and "Cache-Control" not in resp.headers:
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.errorhandler(ApiError)
    def _api_error(e):
        c = dbm.g.get("db")
        if c is not None and c.in_transaction:
            c.rollback()  # never keep a write lock after a rejected request
        body = dict(error=e.code, message=e.fa, message_en=e.en, **e.extra)
        return jsonify(body), e.status

    @app.errorhandler(404)
    def _404(e):
        if request.path.startswith("/api/"):
            return jsonify(error="not_found", message="پیدا نشد", message_en="Not found"), 404
        return "Not found", 404

    @app.errorhandler(405)
    def _405(e):
        return jsonify(error="method_not_allowed", message="روش درخواست مجاز نیست", message_en="Method not allowed"), 405

    @app.errorhandler(413)
    def _413(e):
        return jsonify(error="too_large", message="حجم درخواست زیاد است", message_en="Request too large"), 413

    @app.errorhandler(Exception)
    def _500(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e
        app.logger.exception("unhandled error on %s", request.path)
        try:
            c = dbm.connect(app.config["DB_PATH"])
            log_event(c, "error", "exception", "%s on %s" % (type(e).__name__, request.path), client_ip())
            c.commit()
            c.close()
        except Exception:
            pass
        return jsonify(error="server_error", message="خطای داخلی سرور", message_en="Internal server error"), 500

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html", max_age=0)

    @app.get("/admin")
    @app.get("/admin/")
    def admin_page():
        return send_from_directory(app.static_folder, "admin.html", max_age=0)

    @app.get("/api/health")
    def public_health():
        return jsonify(status="ok", version=__version__)

    if cfg["HOUSEKEEPING"] and not cfg["TESTING"]:
        threading.Thread(target=_housekeeping, args=(app,), daemon=True).start()
    return app
