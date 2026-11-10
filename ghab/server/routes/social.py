"""اعلان‌ها، فهرست دنبال‌کننده‌ها، هشتگ‌ها و گزارش."""
import re
import time

from flask import Blueprint, jsonify, request, session

from .. import vis
from ..db import q, q1, run
from ..notify import HASHTAG
from ..security import auth, err, too_many
from ..serializers import ser, uj

bp = Blueprint('social', __name__)


@bp.get('/api/activity')
@auth
def activity():
    me_ = session['uid']
    fol = {r['followee'] for r in q('select followee from follows where follower=?', me_)}
    rows = q('select n.*, a.username, a.avatar, a.name, p.file pfile, p.poster ppost, p.kind pkind, c.text ctext '
             'from notifications n join users a on a.id=n.actor left join posts p on p.id=n.post_id '
             'left join comments c on c.id=n.comment_id where n.user_id=? order by n.id desc limit 80', me_)
    blk = vis.blocked(me_)
    rows = [r for r in rows if r['actor'] not in blk]
    return jsonify([dict(
        id=r['id'], type=r['type'], created=r['created'], seen=bool(r['seen']),
        actor=dict(id=r['actor'], username=r['username'], name=r['name'], avatar=r['avatar']),
        post=dict(id=r['post_id'], file=r['pfile'], poster=r['ppost'], kind=r['pkind']) if r['post_id'] and r['pfile'] else None,
        text=(r['ctext'] or '')[:90], followed=r['actor'] in fol) for r in rows])


@bp.post('/api/activity/seen')
@auth
def activity_seen():
    run('update notifications set seen=1 where user_id=? and seen=0', session['uid'])
    return jsonify(ok=True)


def _people(sql, uid):
    me_ = session['uid']
    fol = {r['followee'] for r in q('select followee from follows where follower=?', me_)}
    blk = vis.blocked(me_)
    return jsonify([dict(uj(u), followed=u['id'] in fol, me=u['id'] == me_) for u in q(sql, uid) if u['id'] not in blk])


@bp.get('/api/user/<username>/followers')
@auth
def followers(username):
    u = q1('select id from users where username=?', username.lower())
    if not u:
        return err('کاربر پیدا نشد', 404)
    return _people('select u.* from follows f join users u on u.id=f.follower where f.followee=? order by f.rowid desc limit 300', u['id'])


@bp.get('/api/user/<username>/following')
@auth
def following_list(username):
    u = q1('select id from users where username=?', username.lower())
    if not u:
        return err('کاربر پیدا نشد', 404)
    return _people('select u.* from follows f join users u on u.id=f.followee where f.follower=? order by f.rowid desc limit 300', u['id'])


@bp.get('/api/tag/<tag>')
@auth
def tag_page(tag):
    tag = tag.lower().lstrip('#')
    if not re.fullmatch(r'[\w\u0600-\u06FF]{2,40}', tag):
        return err('هشتگ نامعتبر', 400)
    rx = re.compile(r'#' + re.escape(tag) + r'(?![\w\u0600-\u06FF])', re.I)
    inv = vis.invisible(session['uid'])
    rows = [p for p in q('select * from posts where caption like ? order by id desc limit 400', '%#' + tag + '%')
            if rx.search(p['caption'] or '') and p['user_id'] not in inv]
    return jsonify(tag=tag, count=len(rows), posts=[ser(p) for p in rows[:90]])


@bp.get('/api/search/tags')
@auth
def search_tags():
    s = (request.args.get('q') or '').strip().lower().lstrip('#')
    if len(s) < 1 or not re.fullmatch(r'[\w\u0600-\u06FF]{1,40}', s):
        return jsonify([])
    counts = {}
    for r in q('select caption from posts where caption like ? order by id desc limit 800', '%#' + s + '%'):
        for t in HASHTAG.findall((r['caption'] or '').lower()):
            if t.startswith(s):
                counts[t] = counts.get(t, 0) + 1
    return jsonify([dict(tag=t, count=c) for t, c in sorted(counts.items(), key=lambda x: -x[1])[:12]])


@bp.post('/api/report')
@auth
def report():
    d = request.get_json(silent=True) or {}
    me_ = session['uid']
    if too_many(('report', me_), 20, 3600):
        return err('تعداد گزارش‌ها زیاد است', 429)
    kind, ref = d.get('kind'), d.get('ref_id')
    table = {'post': 'posts', 'comment': 'comments', 'user': 'users'}.get(kind)
    if not table or not isinstance(ref, int) or not q1(f'select 1 from {table} where id=?', ref):
        return err('مورد گزارش‌شده پیدا نشد', 404)
    reason = (d.get('reason') or 'other')[:200]
    if not q1('select 1 from reports where reporter=? and kind=? and ref_id=?', me_, kind, ref):
        run('insert into reports(reporter,kind,ref_id,reason,created) values(?,?,?,?,?)', me_, kind, ref, reason, time.time())
    return jsonify(ok=True)
