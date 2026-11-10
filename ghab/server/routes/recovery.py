"""بازیابی و تغییر رمز: «فراموش کردم» با سوال امنیتی، تغییر رمز و ثبت سوال برای حساب‌های قدیمی."""
import time

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import q1, run
from ..recovery import QUESTIONS, check_answer, hash_answer
from ..security import auth, err, sso_only_block, too_many

bp = Blueprint('recovery', __name__)


@bp.get('/api/security/questions')
def questions():
    return jsonify(QUESTIONS)


@bp.get('/api/reset/question')
def reset_question():
    if sso_only_block():
        return sso_only_block()
    if too_many(('rq', request.remote_addr), 30, 900):
        return err('تلاش زیاد است؛ کمی بعد دوباره امتحان کن', 429)
    u = q1('select sec_q from users where username=?', (request.args.get('username') or '').strip().lower())
    if not u or not u['sec_q']:  # پیام یکسان تا معلوم نشود کاربر وجود دارد یا نه
        return err('برای این حساب بازیابی فعال نیست؛ از ادمین بخواه رمز را ریست کند', 404)
    return jsonify(question=u['sec_q'])


@bp.post('/api/reset')
def reset():
    if sso_only_block():
        return sso_only_block()
    d = request.get_json(silent=True) or {}
    name = (d.get('username') or '').strip().lower()
    if too_many(('rs', request.remote_addr, name), 6, 900) or too_many(('rsi', request.remote_addr), 30, 900):
        return err('تلاش زیاد است؛ ۱۵ دقیقه بعد دوباره امتحان کن', 429)
    pw = d.get('password') or ''
    if len(pw) < 6:
        return err('رمز جدید حداقل ۶ کاراکتر باشد')
    u = q1('select * from users where username=?', name)
    if not u or not check_answer(u['sec_a'], d.get('answer')):
        time.sleep(0.5)
        return err('جواب درست نیست', 401)
    run('update users set pass=? where id=?', generate_password_hash(pw), u['id'])
    return jsonify(ok=True)


def _me_checked(password):
    u = q1('select * from users where id=?', session['uid'])
    return u if check_password_hash(u['pass'], password or '') else None


@bp.post('/api/me/password')
@auth
def change_password():
    if sso_only_block():
        return sso_only_block()
    d = request.get_json(silent=True) or {}
    if too_many(('cp', session['uid']), 10, 900):
        return err('تلاش زیاد است', 429)
    u = _me_checked(d.get('current'))
    if not u:
        return err('رمز فعلی درست نیست', 401)
    if len(d.get('password') or '') < 6:
        return err('رمز جدید حداقل ۶ کاراکتر باشد')
    run('update users set pass=? where id=?', generate_password_hash(d['password']), u['id'])
    return jsonify(ok=True)


@bp.post('/api/me/security')
@auth
def set_security():
    if sso_only_block():
        return sso_only_block()
    d = request.get_json(silent=True) or {}
    if too_many(('ss', session['uid']), 10, 900):
        return err('تلاش زیاد است', 429)
    u = _me_checked(d.get('current'))
    if not u:
        return err('رمز فعلی درست نیست', 401)
    try:
        question = QUESTIONS[int(d.get('sec_q'))]
    except (TypeError, ValueError, IndexError):
        return err('یک سوال انتخاب کن')
    ans = (d.get('sec_a') or '').strip()
    if len(ans) < 2:
        return err('جواب را بنویس')
    run('update users set sec_q=?, sec_a=? where id=?', question, hash_answer(ans), u['id'])
    return jsonify(ok=True)
