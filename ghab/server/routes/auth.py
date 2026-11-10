"""ثبت‌نام، ورود و پروفایل خود کاربر."""
import re
import time

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from .. import storage
from ..db import q1, run
from ..security import auth, cur_user, err, sso_only_block, too_many
from ..recovery import QUESTIONS, hash_answer
from ..serializers import me_json

bp = Blueprint('auth', __name__)


USERNAME_RE = r'[a-z0-9][a-z0-9_.]{1,18}[a-z0-9]'  # چون نام کاربری اسم پوشه‌اش هم هست
RESERVED = {'admin', 'api', 'static', 'media', 'con', 'prn', 'aux', 'nul',
            *(f'com{i}' for i in range(1, 10)), *(f'lpt{i}' for i in range(1, 10))}


@bp.post('/api/register')
def register():
    if sso_only_block():
        return sso_only_block()
    if too_many(('reg', request.remote_addr), 10, 3600):
        return err('تلاش زیاد است؛ کمی بعد دوباره امتحان کن', 429)
    d = request.get_json(silent=True) or {}
    u = (d.get('username') or '').strip().lower()
    p = d.get('password') or ''
    if not re.fullmatch(USERNAME_RE, u) or u in RESERVED:
        return err('نام کاربری ۳ تا ۲۰ کاراکتر (حرف انگلیسی، عدد، _ یا .) باشد، با حرف یا عدد شروع و تمام شود و رزرو نباشد')
    if len(p) < 6:
        return err('رمز عبور حداقل ۶ کاراکتر باشد')
    try:
        question = QUESTIONS[int(d.get('sec_q'))]
    except (TypeError, ValueError, IndexError):
        return err('یک سوال امنیتی انتخاب کن (برای بازیابی رمز)')
    answer = (d.get('sec_a') or '').strip()
    if len(answer) < 2:
        return err('جواب سوال امنیتی را بنویس')
    if q1('select 1 from users where username=?', u):
        return err('این نام کاربری قبلاً گرفته شده', 409)
    c = run('insert into users(username,pass,name,created,sec_q,sec_a) values(?,?,?,?,?,?)',
            u, generate_password_hash(p), (d.get('name') or '').strip()[:40], time.time(), question, hash_answer(answer))
    session.clear()
    session['uid'] = c.lastrowid
    session.permanent = True
    return jsonify(me_json(q1('select * from users where id=?', c.lastrowid)))


@bp.post('/api/login')
def login():
    if sso_only_block():
        return sso_only_block()
    if too_many(('login', request.remote_addr), 15, 300):
        return err('تلاش زیاد است؛ چند دقیقه بعد دوباره امتحان کن', 429)
    d = request.get_json(silent=True) or {}
    u = q1('select * from users where username=?', (d.get('username') or '').strip().lower())
    if not u or not check_password_hash(u['pass'], d.get('password') or ''):
        return err('نام کاربری یا رمز عبور اشتباه است', 401)
    if u['banned']:
        return err('این حساب مسدود شده است', 403)
    session.clear()
    session['uid'] = u['id']
    session.permanent = True
    return jsonify(me_json(u))


@bp.get('/api/auth_mode')
def auth_mode():
    from .. import config
    return jsonify(password_auth=config.PASSWORD_AUTH)


@bp.post('/api/logout')
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.get('/api/me')
@auth
def me():
    return jsonify(me_json(q1('select * from users where id=?', session['uid'])))


@bp.post('/api/me/update')
@auth
def me_update():
    uid = session['uid']
    run('update users set name=?, bio=? where id=?',
        (request.form.get('name') or '').strip()[:40], (request.form.get('bio') or '').strip()[:300], uid)
    f = request.files.get('avatar')
    if f and f.filename:
        r = storage.save_file(f, cur_user()['username'], 'avatar', kinds=('image',), side=320, thumb=False)
        if not r:
            return err('آواتار باید عکس باشد')
        old = q1('select avatar from users where id=?', uid)['avatar']
        run('update users set avatar=? where id=?', r[0], uid)
        if old:
            storage.rm_file(old)
    return jsonify(me_json(q1('select * from users where id=?', uid)))


