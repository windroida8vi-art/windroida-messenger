"""پیشنهاد گیرنده برای «ارسال» پست به یک دوست؛ خودِ گفتگو دیگر اینجا نیست — «پیام» همیشه چت واقعی رو تو ویندروید باز
می‌کنه (همون حساب، با SSO)، تا پیام‌ها یک‌جا باشن و قاب دوباره یک پیام‌رسان دیگه نشه."""
import hashlib
import hmac
import json
import secrets
import ssl
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request, session

from .. import config, vis
from ..db import q, q1
from ..ranking import affinity
from ..security import auth, err, too_many
from ..serializers import uj

bp = Blueprint('messages', __name__)


@bp.get('/api/share/suggest')
@auth
def share_suggest():
    me_ = session['uid']
    s = (request.args.get('q') or '').strip().lower()
    aff = affinity(me_)
    # فقط کسانی که من فالوشان کرده‌ام
    ids = [r['followee'] for r in q('select followee from follows where follower=?', me_)]
    us = [u for u in (q1('select * from users where id=?', i) for i in ids) if u and u['id'] != me_]
    if s:
        us = [u for u in us if s in (u['username'] or '').lower() or s in (u['name'] or '').lower()]
    us = sorted([u for u in us if u['id'] not in vis.blocked(me_)], key=lambda u: -aff.get(u['id'], 0))
    return jsonify([uj(u) for u in us])


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_wd_scheme = ['http']   # آخرین پروتکلی که جواب داد؛ ویندروید با TLS روی http فقط ریدایرکت می‌دهد (فوری)، پس هیچ‌وقت منتظر timeout نمی‌مانیم


def _wd_post(payload):
    """POST به سرور ویندروید روی همین ماشین (loopback). گواهی خودامضاست، پس تأییدش خاموش است؛ امنیت با امضای HMAC است.
    اول http: اگر ویندروید TLS داشته باشد فوراً ریدایرکت می‌دهد و می‌رویم سراغ https. برمی‌گرداند (status, dict)
    یا (None, None) اگر وصل نشد."""
    body = json.dumps(payload).encode()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=ctx))
    for scheme in dict.fromkeys([_wd_scheme[0], 'http', 'https']):
        rq = urllib.request.Request(f'{scheme}://127.0.0.1:{config.WD_PORT}/ghab-share', data=body, method='POST',
                                    headers={'Content-Type': 'application/json'})
        try:
            with opener.open(rq, timeout=8) as r:
                _wd_scheme[0] = scheme
                return r.status, json.loads(r.read().decode() or '{}')
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 307, 308):     # «https لازم است»
                continue
            _wd_scheme[0] = scheme
            try:
                return e.code, json.loads(e.read().decode() or '{}')
            except ValueError:
                return e.code, {}
        except Exception:
            continue
    return None, None


@bp.post('/api/share/send')
@auth
def share_send():
    """«ارسال» پست/ریل به یک دوست: لینک مستقیم به‌عنوان پیام واقعی توی چت ویندروید همان دوست می‌نشیند.
    اگر این مسیر ممکن نبود، پاسخ fb=true می‌دهد تا مرورگر مثل قبل چت ویندروید را با لینکِ آماده باز کند."""
    me_ = session['uid']
    if too_many(('share_send', me_), 30, 60):
        return err('خیلی سریع می‌فرستی؛ کمی صبر کن', 429)
    d = request.get_json(silent=True) or {}
    try:
        pid, to = int(d.get('post_id')), int(d.get('to'))
    except (TypeError, ValueError):
        return err('درخواست نامعتبر است', 400)
    post = q1('select id, user_id from posts where id=?', pid)
    if not post or post['user_id'] in vis.invisible(me_):
        return err('پست پیدا نشد', 404)
    if to == me_ or to in vis.blocked(me_) or not q1('select 1 from follows where follower=? and followee=?', me_, to):
        return err('این کاربر در دسترس نیست', 400)
    sender, target = q1('select wd_name from users where id=?', me_), q1('select wd_name, banned from users where id=?', to)
    if not config.SSO_SECRET or not sender or not sender['wd_name'] or not target or not target['wd_name'] or target['banned']:
        return jsonify(error='ارسال مستقیم برای این کاربر ممکن نیست', fb=True), 409
    # آدرس لینک: همان origin که کاربر باز کرده؛ فقط اگر با Host درخواست یکی باشد (وگرنه از خود درخواست ساخته می‌شود)
    o = urlparse(str(d.get('origin') or ''))
    origin = f'{o.scheme}://{o.netloc}' if o.scheme in ('http', 'https') and o.netloc == request.host else request.host_url.rstrip('/')
    text = f'{origin}/p/{pid}'
    exp, nonce = int(time.time()) + 60, secrets.token_hex(8)
    msg = f"share:{sender['wd_name']}:{target['wd_name']}:{exp}:{nonce}:{hashlib.sha256(text.encode()).hexdigest()}"
    sig = hmac.new(config.SSO_SECRET.encode(), msg.encode(), 'sha256').hexdigest()
    st, res = _wd_post(dict({'from': sender['wd_name'], 'to': target['wd_name'], 'text': text, 'exp': exp, 'nonce': nonce, 'sig': sig}))
    if st == 200 and res.get('ok'):
        return jsonify(ok=True)
    if st == 409 and res.get('error'):      # مثلاً بلاک بودن در ویندروید؛ پیام خودش را نشان بده، fallback نه
        return err(res['error'], 409)
    return jsonify(error='ارسال مستقیم الان ممکن نشد', fb=True), 502


@bp.get('/api/unread')
@auth
def unread():
    return jsonify(activity=q1('select count(*) c from notifications where user_id=? and seen=0', session['uid'])['c'])
