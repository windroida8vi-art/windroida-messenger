"""اندازه‌گیری سرعت: مرورگر یک بسته کوچک بی‌فشار می‌گیرد و از زمانش کیفیت ویدیو/عکس را انتخاب می‌کند."""
import os

from flask import Blueprint, Response, request

from ..security import err, too_many

bp = Blueprint('net', __name__)


@bp.get('/api/speed')
def speed():
    if too_many(('speed', request.remote_addr), 300, 60):
        return err('تلاش زیاد است', 429)
    n = max(1000, min(request.args.get('n', type=int, default=300000), 600000))
    return Response(os.urandom(n), mimetype='application/octet-stream', headers={'Cache-Control': 'no-store'})
