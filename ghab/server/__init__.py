import logging
import os
import shutil
from logging.handlers import RotatingFileHandler

from flask import Flask
from werkzeug.exceptions import HTTPException

from . import config
from .db import close_db, migrate
from .security import err


def _setup_logging():
    os.makedirs(config.LOG_DIR, exist_ok=True)
    h = RotatingFileHandler(os.path.join(config.LOG_DIR, 'ghab.log'), maxBytes=2_000_000, backupCount=3, encoding='utf-8')
    h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    root = logging.getLogger('ghab')
    if not root.handlers:
        root.setLevel(logging.INFO)
        root.addHandler(h)
    return root


def create_app():
    config.ensure_dirs()
    log = _setup_logging()
    migrate()
    from . import storage
    storage.cleanup_tmp()  # فایل‌های نیمه‌کاره فشرده‌سازی (.part) بعد از خاموشی ناگهانی
    app = Flask(__name__, static_folder=config.STATIC_DIR, static_url_path='/static')
    app.config.update(
        MAX_CONTENT_LENGTH=config.MAX_UPLOAD_MB * 1024 * 1024,
        SESSION_COOKIE_NAME='ghab_session', SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax', SEND_FILE_MAX_AGE_DEFAULT=31536000, PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 90)
    app.secret_key = config.secret_key()
    app.json.sort_keys = False  # ترتیب فیلدها همان که نوشته شده می‌ماند
    if config.BEHIND_PROXY:  # پشت Cloudflare/Caddy: IP واقعی کاربر از هدر خوانده شود
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    app.teardown_appcontext(close_db)
    app.register_error_handler(413, lambda _e: err(f'فایل خیلی بزرگ است (سقف {config.MAX_UPLOAD_MB} مگابایت)', 413))

    @app.errorhandler(Exception)
    def _boom(e):  # هیچ خطایی نباید سرور را بیندازد یا صفحه سفید بدهد
        if isinstance(e, HTTPException):
            return e
        if isinstance(e, OverflowError):  # شناسهٔ غیرعادی بزرگ (بیش از ۶۴ بیت) = چنین موردی وجود ندارد
            return err('پیدا نشد', 404)
        log.exception('خطای پردازش درخواست')
        return err('خطای داخلی سرور؛ دوباره امتحان کن', 500)

    @app.before_request
    def _guards():
        from urllib.parse import urlparse
        from flask import request, session
        from .security import too_many
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and not request.path.startswith('/_local/'):
            # 1) درخواست‌های تغییردهنده فقط از خود همین سایت: پورت‌های دیگر همین سرور (فضای ابری، ویندروید) «هم‌سایت» حساب می‌شن و
            #    SameSite جلوشون رو نمی‌گیره؛ پس هدر Origin باید دقیقاً همین آدرس باشد (اگر فرستاده شده باشد).
            org = request.headers.get('Origin')
            if org and not config.BEHIND_PROXY and urlparse(org).netloc != request.host:
                return err('درخواست از منبع نامعتبر', 403)
            # 2) سقف تعداد کارِ نوشتنی در دقیقه برای هر کاربر (جلوگیری از اسپم و فشار روی سرور)
            if request.path not in ('/api/reels/watch', '/api/impressions'):
                if too_many(('w', session.get('uid') or request.remote_addr), 400, 60):
                    return err('درخواست‌ها زیاد است؛ کمی صبر کن', 429)
            # 3) دیسک تقریباً پر است: آپلود جدید رد می‌شود تا سرور و ویندوز نیفتند
            if (request.content_length or 0) > 256 * 1024:
                try:
                    free = shutil.disk_usage(config.DATA_DIR).free
                except OSError:
                    free = None
                if free is not None and free < max(config.MIN_FREE_MB * 1048576, 2 * request.content_length):
                    return err('فضای دیسک سرور کم است؛ به ادمین بگو', 507)

    @app.after_request
    def headers(r):
        r.headers.setdefault('X-Content-Type-Options', 'nosniff')
        r.headers.setdefault('X-Frame-Options', 'DENY')
        r.headers.setdefault('Referrer-Policy', 'same-origin')
        r.headers.setdefault('Permissions-Policy', 'camera=(self), microphone=(self), geolocation=()')
        r.headers.setdefault('Content-Security-Policy',
                             "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                             "img-src 'self' data: blob:; media-src 'self' blob: data:; connect-src 'self'; worker-src 'self'; "
                             "manifest-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        if r.mimetype == 'application/json':
            r.headers['Cache-Control'] = 'no-store'
        return r

    from . import compress
    compress.init(app)
    import threading
    from . import jobs
    threading.Thread(target=jobs.backfill_sha, daemon=True).start()  # فقط ستون sha پر می‌شود؛ فایل‌ها دست‌نخورده
    from .routes import register_all
    register_all(app)
    return app
