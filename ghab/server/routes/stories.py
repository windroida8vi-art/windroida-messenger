"""استوری ۲۴ ساعته: ساخت (برای همه / دوستان نزدیک، با استیکر نظرسنجی)، دیدن، بازدیدکننده‌ها، رأی، پاسخ و حذف."""
import json
import time

from flask import Blueprint, jsonify, request, session

from .. import jobs, storage, vis
from ..db import q, q1, run
from ..ranking import invalidate
from ..security import auth, cur_user, err
from ..serializers import uj

bp = Blueprint('stories', __name__)
DAY = 86400
SELECT = ("select s.*, u.username, u.avatar, "
          "(select 1 from story_views v where v.story_id=s.id and v.viewer=?) as seen, "
          "(select count(*) from story_views v where v.story_id=s.id) as views, "
          "(select count(*) from story_votes v where v.story_id=s.id and v.choice=0) as v0, "
          "(select count(*) from story_votes v where v.story_id=s.id and v.choice=1) as v1, "
          "(select choice from story_votes v where v.story_id=s.id and v.user_id=?) as myv "
          "from stories s join users u on u.id=s.user_id ")
AUD = ("(s.audience='all' or s.audience is null or s.user_id=? or exists "
       "(select 1 from close_friends c where c.owner=s.user_id and c.friend=?))")


def _item(r, mine):
    st = json.loads(r['sticker']) if r['sticker'] else None
    if st:
        st['votes'] = [r['v0'], r['v1']] if (mine or r['myv'] is not None) else None
        st['mine'] = r['myv']
    return dict(id=r['id'], file=r['file'], kind=r['kind'], created=r['created'], seen=bool(r['seen']) or mine,
                views=r['views'] if mine else None, audience=r['audience'] or 'all', sticker=st)


def _groups(rows, me_):
    groups = {}
    for r in rows:
        mine = r['user_id'] == me_
        g = groups.setdefault(r['user_id'], dict(username=r['username'], avatar=r['avatar'], mine=mine, close=False, items=[]))
        g['items'].append(_item(r, mine))
        g['close'] = g['close'] or (r['audience'] == 'close')
    out = list(groups.values())
    for g in out:
        g['seen'] = all(i['seen'] for i in g['items'])
    out.sort(key=lambda g: (not g['mine'], g['seen']))
    return out


def user_story(uid, me_):
    """استوری فعال یک کاربر (برای حلقه دور آواتار در پروفایل)."""
    if uid in vis.invisible(me_):
        return None
    rows = q(SELECT + f'where s.user_id=? and s.created>? and {AUD} order by s.created', me_, me_, uid, time.time() - DAY, me_, me_)
    g = _groups(rows, me_)
    return g[0] if g else None


@bp.get('/api/stories')
@auth
def stories():
    me_ = session['uid']
    cl, pa = vis.not_in('s.user_id', vis.blocked(me_))
    rows = q(SELECT + f'where s.created>? and (s.user_id=? or s.user_id in (select followee from follows where follower=?)) '
             f'and {AUD} and {cl} order by s.created', me_, me_, time.time() - DAY, me_, me_, me_, me_, *pa)
    return jsonify(_groups(rows, me_))


@bp.post('/api/stories')
@auth
def add_story():
    f = request.files.get('file')
    r = storage.save_file(f, cur_user()['username'], 'stories', thumb=False, side=1080) if f and f.filename else None
    if not r:
        return err('فایل نامعتبر است')
    audience = 'close' if request.form.get('audience') == 'close' else 'all'
    sticker = None
    pq, pa_, pb = (request.form.get(k, '').strip()[:60] for k in ('poll_q', 'poll_a', 'poll_b'))
    if pq and pa_ and pb:
        sticker = json.dumps(dict(type='poll', q=pq, a=pa_[:24], b=pb[:24]), ensure_ascii=False)
    c = run('insert into stories(user_id,file,kind,created,audience,sticker) values(?,?,?,?,?,?)',
            session['uid'], r[0], r[1], time.time(), audience, sticker)
    if r[1] == 'video':
        jobs.enqueue('stories', c.lastrowid, r[0])
    return jsonify(ok=True)


def _story(sid):
    """استوریِ زنده‌ای که کاربر مجاز به دیدنش است (بلاک/دوستان نزدیک رعایت می‌شود)."""
    me_ = session['uid']
    s = q1('select * from stories where id=? and created>?', sid, time.time() - DAY)
    if not s or s['user_id'] in vis.blocked(me_):
        return None
    if s['user_id'] != me_ and s['audience'] == 'close' and not q1(
            'select 1 from close_friends where owner=? and friend=?', s['user_id'], me_):
        return None
    return s


@bp.post('/api/stories/<int:sid>/view')
@auth
def view_story(sid):
    s = _story(sid)
    if not s:
        return err('استوری پیدا نشد', 404)
    if s['user_id'] != session['uid']:
        run('insert or ignore into story_views(story_id,viewer,created) values(?,?,?)', sid, session['uid'], time.time())
    return jsonify(ok=True)


@bp.post('/api/stories/<int:sid>/vote')
@auth
def vote(sid):
    s = _story(sid)
    choice = (request.get_json(silent=True) or {}).get('choice')
    if not s or not s['sticker'] or choice not in (0, 1) or s['user_id'] == session['uid']:
        return err('رأی ممکن نیست', 400)
    run('insert or ignore into story_votes(story_id,user_id,choice) values(?,?,?)', sid, session['uid'], choice)
    r = q1('select (select count(*) from story_votes where story_id=? and choice=0) v0, '
           '(select count(*) from story_votes where story_id=? and choice=1) v1, '
           '(select choice from story_votes where story_id=? and user_id=?) my', sid, sid, sid, session['uid'])
    return jsonify(votes=[r['v0'], r['v1']], mine=r['my'])


@bp.get('/api/stories/<int:sid>/viewers')
@auth
def viewers(sid):
    s = _story(sid)
    if not s or s['user_id'] != session['uid']:
        return err('فقط صاحب استوری', 403)
    rows = q('select u.*, v.created as at from story_views v join users u on u.id=v.viewer where v.story_id=? '
             'order by v.created desc', sid)
    return jsonify([dict(uj(r), at=r['at']) for r in rows])


@bp.delete('/api/stories/<int:sid>')
@auth
def delete_story(sid):
    s = q1('select * from stories where id=? and user_id=?', sid, session['uid'])
    if not s:
        return err('استوری پیدا نشد', 404)
    run('delete from stories where id=?', sid)
    storage.rm_file(s['file'])
    return jsonify(ok=True)


@bp.post('/api/posts/<int:pid>/story')
@auth
def post_to_story(pid):
    p = q1('select * from posts where id=?', pid)
    if not p or p['user_id'] in vis.invisible(session['uid']):
        return err('پست پیدا نشد', 404)
    name = storage.copy_file(p['file'], cur_user()['username'], 'stories')
    run('insert into stories(user_id,file,kind,created) values(?,?,?,?)', session['uid'], name, p['kind'], time.time())
    return jsonify(ok=True)
