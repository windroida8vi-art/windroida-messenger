"""صفحه‌ها (index) و فایل‌های رسانه."""
import os

from urllib.parse import quote

from flask import Blueprint, Response, redirect, send_file, send_from_directory

from .. import config
from ..security import err, user_ok

bp = Blueprint('pages', __name__)


def _asset_version():
    """با هر تغییر در فایل‌های static عوض می‌شود، پس کش مرورگر خودکار تازه می‌شود."""
    t = max((os.path.getmtime(os.path.join(config.STATIC_DIR, f)) for f in os.listdir(config.STATIC_DIR)), default=0)
    return f'{config.VERSION}-{int(t)}'


def _html(name):
    with open(os.path.join(config.WEB_DIR, name), encoding='utf-8') as f:
        return Response(f.read().replace('{{v}}', _asset_version()).replace('{{wdport}}', str(config.WD_PORT)), mimetype='text/html')


@bp.get('/')
def index():
    return _html('index.html')


@bp.get('/ca.crt')
def ca_cert():
    """گواهی مرجع محلی؛ هر دستگاه یک‌بار نصب کند، هشدار امنیتی مرورگر برای همیشه از بین می‌رود."""
    from ..tls import CA_CERT
    if not os.path.exists(CA_CERT):
        return Response('CA موجود نیست (گواهی دلخواه استفاده می‌شود).', status=404)
    return send_file(CA_CERT, mimetype='application/x-x509-ca-cert', as_attachment=True, download_name='ghab-ca.crt')


@bp.get('/trust')
def trust():
    return _html('trust.html')


@bp.get('/media/<path:name>')
def media(name):
    """عکس و ویدیو فقط برای کاربر واردشده. قبلاً هر کسی با لینک مستقیم فایل را بدون ورود می‌دید."""
    if not user_ok():
        return err('برای دیدن این فایل باید وارد حساب شوی', 401)
    r = send_from_directory(config.USERS_DIR, name, conditional=True)
    r.headers['Cache-Control'] = 'private, max-age=31536000, immutable'
    r.headers['Content-Security-Policy'] = "sandbox; default-src 'none'; img-src 'self'; media-src 'self'"   # فایل کاربر هیچ‌وقت اسکریپت اجرا نکند
    r.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    return r


@bp.get('/p/<int:pid>')
def post_link(pid):
    """لینک کوتاه پست: https://سایت/p/12 ← پست را در برنامه باز می‌کند (اگر وارد نشده باشی اول ورود)."""
    return redirect(f'/#/p/{pid}')


@bp.get('/u/<username>')
def user_link(username):
    return redirect('/#/u/' + quote(username, safe=''))


@bp.get('/manifest.webmanifest')
def manifest():
    import json
    m = dict(name='قاب', short_name='قاب', start_url='/', scope='/', display='standalone', background_color='#07090d',
             theme_color='#07090d', lang='fa', dir='rtl',
             icons=[dict(src='/static/icon-192.png', sizes='192x192', type='image/png'),
                    dict(src='/static/icon-512.png', sizes='512x512', type='image/png', purpose='any maskable')])
    return Response(json.dumps(m, ensure_ascii=False), mimetype='application/manifest+json')


@bp.get('/sw.js')
def service_worker():
    """Service Worker: فایل‌های static را کش می‌کند تا برنامه فوراً باز شود؛ API و فایل‌های رسانه هرگز کش نمی‌شوند."""
    with open(os.path.join(config.WEB_DIR, 'sw.js'), encoding='utf-8') as f:
        r = Response(f.read(), mimetype='text/javascript')
    r.headers['Cache-Control'] = 'no-cache'
    return r


@bp.get('/offline')
def offline():
    return Response('<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">'
                    '<body style="background:#07090d;color:#f2f4f8;font:16px Tahoma;display:grid;place-content:center;height:100vh;text-align:center">'
                    '<div><h2>اینترنت قطع است</h2><p>وقتی وصل شدی دوباره امتحان کن.</p><a href="/" '
                    'style="padding:10px 22px;border-radius:12px;background:#7c5cff;color:#fff;text-decoration:none">تلاش دوباره</a></div>', mimetype='text/html')
