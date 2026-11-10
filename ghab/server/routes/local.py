"""درگاه محلیِ دیتاشیت ویندروید: فقط برای کارهایی که باید داخل همین پروسه انجام شوند (فشرده‌سازی صف ویدیوها).

دو قفل: درخواست باید از 127.0.0.1 بیاید و هدر X-Local-Key باید با فایل data/local_admin.key (تصادفی، فقط خودِ دیتاشیت
روی همین کامپیوتر می‌خواندش) برابر باشد. از اینترنت/شبکه قابل‌استفاده نیست. هیچ داده‌ای از کاربرها اینجا نمی‌آید.
"""
import hmac
import os
import secrets

from flask import Blueprint, jsonify, request

from .. import config, jobs
from ..security import err

bp = Blueprint('local', __name__, url_prefix='/_local')
_KEY_PATH = os.path.join(config.DATA_DIR, 'local_admin.key')


def _key():
    try:
        with open(_KEY_PATH, encoding='utf-8') as f:
            k = f.read().strip()
        if len(k) >= 32:
            return k
    except OSError:
        pass
    k = secrets.token_hex(32)
    with open(_KEY_PATH, 'w', encoding='utf-8') as f:
        f.write(k)
    try:
        os.chmod(_KEY_PATH, 0o600)
    except OSError:
        pass
    return k


KEY = _key()


@bp.before_request
def _guard():
    if request.remote_addr not in ('127.0.0.1', '::1') or request.headers.get('X-Forwarded-For') \
            or not hmac.compare_digest(request.headers.get('X-Local-Key', ''), KEY):
        return err('یافت نشد', 404)


@bp.get('/status')
def status():
    return jsonify(jobs.status())


@bp.post('/compress')
def compress_all():
    n = jobs.enqueue_all()
    return jsonify(queued=n, **jobs.status())
