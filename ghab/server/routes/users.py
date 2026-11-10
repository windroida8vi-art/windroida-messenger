"""پروفایل، دنبال کردن (با حساب خصوصی/بلاک) و جستجوی هوشمند کاربر."""
import difflib
import time

from flask import Blueprint, jsonify, request, session

from .. import vis
from ..db import q, q1, run
from ..notify import notify, unnotify
from ..recovery import norm
from ..security import auth, err
from ..serializers import ser, uj
from .stories import user_story

bp = Blueprint('users', __name__)


def highlights_of(uid):
    return [dict(id=h['id'], title=h['title'], cover=dict(file=h['file'], kind=h['kind']) if h['file'] else None)
            for h in q('select h.id, h.title, (select s.file from highlight_items hi join stories s on s.id=hi.story_id '
                       'where hi.highlight_id=h.id order by hi.pos limit 1) as file, (select s.kind from highlight_items hi '
                       'join stories s on s.id=hi.story_id where hi.highlight_id=h.id order by hi.pos limit 1) as kind '
                       'from highlights h where h.user_id=? order by h.id', uid)]


@bp.get('/api/user/<username>')
@auth
def user(username):
    u = q1('select * from users where username=?', username.lower())
    me_ = session['uid']
    if not u or q1('select 1 from blocks where blocker=? and blocked=?', u['id'], me_):
        return err('کاربر پیدا نشد', 404)
    followed = bool(q1('select 1 from follows where follower=? and followee=?', me_, u['id']))
    mine = u['id'] == me_
    i_blocked = bool(q1('select 1 from blocks where blocker=? and blocked=?', me_, u['id']))
    locked = bool(u['private']) and not mine and not followed
    show = not (locked or i_blocked)
    d = uj(u)
    d.update(
        posts=[ser(p) for p in q('select * from posts where user_id=? order by id desc', u['id'])] if show else [],
        followers=q1('select count(*) c from follows where followee=?', u['id'])['c'],
        following=q1('select count(*) c from follows where follower=?', u['id'])['c'],
        is_me=mine, followed=followed, private=bool(u['private']), locked=locked, blocked_by_me=i_blocked,
        muted=bool(q1('select 1 from mutes where user_id=? and muted=?', me_, u['id'])),
        requested=bool(q1('select 1 from follow_requests where requester=? and target=?', me_, u['id'])),
        close=bool(q1('select 1 from close_friends where owner=? and friend=?', me_, u['id'])))
    d['story'] = user_story(u['id'], me_) if show else None
    d['highlights'] = highlights_of(u['id']) if show else []
    return jsonify(d)


@bp.post('/api/user/<username>/follow')
@auth
def follow(username):
    u = q1('select * from users where username=?', username.lower())
    me_ = session['uid']
    if not u or u['id'] == me_ or u['id'] in vis.blocked(me_):
        return err('امکان‌پذیر نیست')
    if q1('select 1 from follows where follower=? and followee=?', me_, u['id']):
        run('delete from follows where follower=? and followee=?', me_, u['id'])
        run('delete from close_friends where owner=? and friend=?', u['id'], me_)
        unnotify(u['id'], me_, 'follow')
        return jsonify(ok=True, followed=False)
    if u['private']:  # حساب خصوصی: درخواست (دوباره زدن = لغو درخواست)
        if q1('select 1 from follow_requests where requester=? and target=?', me_, u['id']):
            run('delete from follow_requests where requester=? and target=?', me_, u['id'])
            unnotify(u['id'], me_, 'follow_request')
            return jsonify(ok=True, requested=False)
        run('insert into follow_requests values(?,?,?)', me_, u['id'], time.time())
        notify(u['id'], me_, 'follow_request', unique=True)
        return jsonify(ok=True, requested=True)
    run('insert into follows values(?,?)', me_, u['id'])
    notify(u['id'], me_, 'follow', unique=True)
    return jsonify(ok=True, followed=True)


def _typo_score(qn, name):
    if not name:
        return 0
    if name == qn:
        return 100
    if name.startswith(qn):
        return 90
    if qn in name:
        return 75
    r = difflib.SequenceMatcher(None, qn, name[:len(qn) + 2]).ratio()  # غلط املایی کوچک (ی/ي، جا‌افتادگی...)
    return 60 * r if r >= 0.78 else 0


@bp.get('/api/search')
@auth
def search():
    """جستجوی هوشمند: نرمال‌سازی فارسی (ی/ي، ک/ك، نیم‌فاصله، ارقام) + تحمل غلط املایی + اولویت با محبوب‌تر."""
    qn = norm(request.args.get('q') or '')
    me_ = session['uid']
    if not qn:
        return jsonify([])
    blk = vis.blocked(me_)
    fc = {r['u']: r['c'] for r in q('select followee u, count(*) c from follows group by followee')}
    scored = []
    for u in q('select * from users where id!=? limit 5000', me_):
        if u['id'] in blk:
            continue
        s = max(_typo_score(qn, norm(u['username'])), _typo_score(qn, norm(u['name'] or '')))
        if s:
            scored.append((s + min(fc.get(u['id'], 0), 50) / 50, u))
    scored.sort(key=lambda x: -x[0])
    return jsonify([uj(u) for _, u in scored[:25]])
