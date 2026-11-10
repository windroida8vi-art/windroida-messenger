"""ورود یکپارچه: کاربری که در ویندروید واردشده بدون رمز دوم وارد قاب می‌شود.

سرور ویندروید برای کاربرِ واردشده یک توکن کوتاه‌عمر و امضاشده می‌سازد (HMAC-SHA256 با یک رمز مشترک تصادفی: GHAB_SSO_SECRET
اینجا، data/drive_sso.key آنجا) و همین آدرس را با آن باز می‌کند. اینجا فقط امضا بررسی می‌شود؛ بدون رمز مشترک هیچ‌کس نمی‌تواند
توکن معتبر بسازد، پس نمی‌شود به‌جای کسی دیگر وارد شد. هر توکن یک‌بار مصرف و ۶۰ ثانیه‌ای است.
اکانت قاب با ستون wd_name (نام دقیق ویندروید) پیدا می‌شود، نه با نام کاربری قاب؛ پس «Ali» و «ali» یا اکانت‌های قدیمی هرگز قاطی نمی‌شوند.
"""
import hmac
import re
import secrets
import threading
import time

from flask import Blueprint, redirect, request, session
from werkzeug.security import generate_password_hash

from .. import config
from ..db import q1, run
from ..security import err, too_many

bp = Blueprint('sso', __name__)

RESERVED = {'admin', 'api', 'static', 'media', 'con', 'prn', 'aux', 'nul',
            *(f'com{i}' for i in range(1, 10)), *(f'lpt{i}' for i in range(1, 10))}
WD_NAME = re.compile(r'^(?=.*[A-Za-z0-9])[A-Za-z0-9_]{3,32}$')
_used, _lock = {}, threading.Lock()


def _fresh(sig, keep_until):
    t = time.time()
    with _lock:
        for k in [k for k, v in _used.items() if v < t]:
            del _used[k]
        if sig in _used:
            return False
        _used[sig] = keep_until
        return True


def _pick_username(wd):
    """نام قاب = نام ویندروید با حروف کوچک (اسم پوشه هم هست). رزرو/تکراری باشد پسوند می‌گیرد."""
    base = wd.lower()
    if base in RESERVED:
        base = 'u_' + base
    base = base[:32]
    name, n = base, 1
    while q1('select 1 from users where username=?', name):
        n += 1
        suf = f'_{n}'
        name = base[:32 - len(suf)] + suf
    return name


@bp.get('/sso')
def sso():
    if too_many(('sso', request.remote_addr), 20, 60):
        return err('تلاش زیاد است؛ کمی بعد دوباره امتحان کن', 429)
    if not config.SSO_SECRET:
        return err('ورود یکپارچه از ویندروید روی این سرور فعال نیست', 403)
    parts = (request.args.get('t') or '').split('.')
    if len(parts) != 4:
        return err('لینک نامعتبر است', 400)
    wd, exp_s, nonce, sig = parts
    if not WD_NAME.match(wd) or not exp_s.isdigit() or not (1 <= len(nonce) <= 40) or len(sig) != 64:
        return err('لینک نامعتبر است', 400)
    exp = int(exp_s)
    good = hmac.new(config.SSO_SECRET.encode(), f'{wd}:{exp}:{nonce}'.encode(), 'sha256').hexdigest()
    if not hmac.compare_digest(good, sig):
        return err('لینک نامعتبر است', 400)
    if time.time() > exp:
        return err('این لینک منقضی شده؛ دوباره از ویندروید باز کن', 400)
    if not _fresh(sig, exp + 5):
        return err('این لینک قبلاً استفاده شده', 400)
    u = q1('select * from users where wd_name=?', wd)
    if not u:
        c = run('insert into users(username,pass,name,created,wd_name) values(?,?,?,?,?)',
                _pick_username(wd), generate_password_hash(secrets.token_urlsafe(32)), wd, time.time(), wd)
        u = q1('select * from users where id=?', c.lastrowid)
    if u['banned']:
        return err('این حساب مسدود شده است', 403)
    session.clear()
    session['uid'] = u['id']
    session.permanent = True
    nxt = request.args.get('next') or ''
    # optional landing page inside Ghab (a shared post / profile): only a plain same-site path like /p/12 or /u/name
    if re.fullmatch(r'/(?:p/\d{1,12}|u/[A-Za-z0-9_.\-]{1,40})', nxt):
        return redirect(nxt)
    return redirect('/')
