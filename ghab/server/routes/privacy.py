"""حریم خصوصی: بلاک، میوت، حساب خصوصی، درخواست دنبال کردن و دوستان نزدیک."""
import time

from flask import Blueprint, jsonify, request, session

from ..db import q, q1, run
from ..notify import notify, unnotify
from ..security import auth, err
from ..serializers import uj

bp = Blueprint('privacy', __name__)


def _user(username):
    return q1('select * from users where username=?', username.lower())


@bp.post('/api/user/<username>/block')
@auth
def block(username):
    u, me_ = _user(username), session['uid']
    if not u or u['id'] == me_:
        return err('امکان‌پذیر نیست')
    if q1('select 1 from blocks where blocker=? and blocked=?', me_, u['id']):
        run('delete from blocks where blocker=? and blocked=?', me_, u['id'])
        return jsonify(blocked=False)
    run('insert into blocks values(?,?)', me_, u['id'])
    for a, b in ((me_, u['id']), (u['id'], me_)):  # دنبال کردن، درخواست و دوست نزدیک در هر دو جهت قطع می‌شود
        run('delete from follows where follower=? and followee=?', a, b)
        run('delete from follow_requests where requester=? and target=?', a, b)
        run('delete from close_friends where owner=? and friend=?', a, b)
    return jsonify(blocked=True)


@bp.post('/api/user/<username>/mute')
@auth
def mute(username):
    u, me_ = _user(username), session['uid']
    if not u or u['id'] == me_:
        return err('امکان‌پذیر نیست')
    if q1('select 1 from mutes where user_id=? and muted=?', me_, u['id']):
        run('delete from mutes where user_id=? and muted=?', me_, u['id'])
        return jsonify(muted=False)
    run('insert into mutes values(?,?)', me_, u['id'])
    return jsonify(muted=True)


@bp.get('/api/blocked')
@auth
def blocked_list():
    me_ = session['uid']
    return jsonify(
        blocked=[uj(u) for u in q('select u.* from blocks b join users u on u.id=b.blocked where b.blocker=?', me_)],
        muted=[uj(u) for u in q('select u.* from mutes m join users u on u.id=m.muted where m.user_id=?', me_)])


@bp.post('/api/me/privacy')
@auth
def set_private():
    me_ = session['uid']
    on = bool((request.get_json(silent=True) or {}).get('private'))
    run('update users set private=? where id=?', int(on), me_)
    if not on:  # عمومی شد: همه درخواست‌های منتظر پذیرفته می‌شوند (مثل اینستاگرام)
        for r in q('select requester from follow_requests where target=?', me_):
            run('insert or ignore into follows values(?,?)', r['requester'], me_)
            notify(me_, r['requester'], 'follow', unique=True)
        run('delete from follow_requests where target=?', me_)
    return jsonify(private=on)


@bp.get('/api/requests')
@auth
def requests_list():
    return jsonify([uj(u) for u in q('select u.* from follow_requests r join users u on u.id=r.requester '
                                     'where r.target=? order by r.created desc', session['uid'])])


@bp.post('/api/requests/<username>/<action>')
@auth
def request_answer(username, action):
    u, me_ = _user(username), session['uid']
    if not u or action not in ('accept', 'decline') or not q1(
            'select 1 from follow_requests where requester=? and target=?', u['id'], me_):
        return err('درخواست پیدا نشد', 404)
    run('delete from follow_requests where requester=? and target=?', u['id'], me_)
    unnotify(me_, u['id'], 'follow_request')
    if action == 'accept':
        run('insert or ignore into follows values(?,?)', u['id'], me_)
        notify(me_, u['id'], 'follow', unique=True)
        notify(u['id'], me_, 'follow_accept', unique=True)
    return jsonify(ok=True)


@bp.get('/api/close-friends')
@auth
def close_get():
    me_ = session['uid']
    cl = {r['friend'] for r in q('select friend from close_friends where owner=?', me_)}
    people = q('select u.* from follows f join users u on u.id=f.followee where f.follower=? '
               'union select u.* from follows f join users u on u.id=f.follower where f.followee=?', me_, me_)
    return jsonify([dict(uj(u), close=u['id'] in cl) for u in people])


@bp.post('/api/close-friends')
@auth
def close_set():
    me_ = session['uid']
    ids = {i for i in ((request.get_json(silent=True) or {}).get('ids') or []) if isinstance(i, int) and i != me_}
    run('delete from close_friends where owner=?', me_)
    for i in ids:
        if q1('select 1 from users where id=?', i):
            run('insert or ignore into close_friends values(?,?)', me_, i)
    return jsonify(count=len(ids))
