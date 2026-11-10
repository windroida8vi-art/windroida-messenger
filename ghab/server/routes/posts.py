"""پست‌ها: ساخت، حذف، لایک، ذخیره و نظر."""
import time

from flask import Blueprint, jsonify, request, session

from .. import jobs, storage
from ..db import q, q1, run
from ..notify import notify, notify_mentions, unnotify
from ..security import auth, cur_user, err
from .. import vis
from ..serializers import ser

bp = Blueprint('posts', __name__)


@bp.get('/api/saved')
@auth
def saved():
    inv = vis.invisible(session['uid'])
    rows = q('select p.* from posts p join saves s on s.post_id=p.id where s.user_id=? order by p.id desc', session['uid'])
    return jsonify([ser(p) for p in rows if p['user_id'] not in inv])


@bp.get('/api/post/<int:pid>')
@auth
def one_post(pid):
    p = q1('select * from posts where id=?', pid)
    if not p or p['user_id'] in vis.invisible(session['uid']):
        return err('پست پیدا نشد', 404)
    return jsonify(ser(p, True))


@bp.post('/api/posts')
@auth
def new_post():
    files = [f for f in request.files.getlist('file') if f and f.filename]
    if not files:
        return err('یک عکس یا ویدیو انتخاب کن')
    me_name = cur_user()['username']
    r = storage.save_file(files[0], me_name, 'posts')
    if not r:
        return err('فرمت فایل پشتیبانی نمی‌شود')
    extras = []
    if len(files) > 1 and r[1] == 'image':  # کاروسل: تا ۱۰ عکس
        for f in files[1:10]:
            e = storage.save_file(f, me_name, 'posts', kinds=('image',))
            if e:
                extras.append(e)
    poster = r[2] if r[1] == 'image' else storage.save_poster(request.files.get('poster'), me_name)
    kbps = jobs.probe_kbps(storage.abs_path(r[0])) if r[1] == 'video' else None
    sha = jobs.file_sha(storage.abs_path(r[0])) if r[1] == 'video' else None
    c = run('insert into posts(user_id,file,kind,caption,created,poster,mid,optimized,kbps,nmedia,sha) values(?,?,?,?,?,?,?,?,?,?,?)',
            session['uid'], r[0], r[1], (request.form.get('caption') or '')[:2200], time.time(), poster, r[3], int(r[1] == 'image'),
            kbps, 1 + len(extras), sha)
    for i, e in enumerate(extras, 1):
        run('insert into post_media(post_id,file,mid,poster,pos) values(?,?,?,?,?)', c.lastrowid, e[0], e[3], e[2], i)
    notify_mentions(request.form.get('caption') or '', session['uid'], c.lastrowid)
    if r[1] == 'video':
        jobs.enqueue('posts', c.lastrowid, r[0])
    return jsonify(id=c.lastrowid)


@bp.post('/api/impressions')
@auth
def impressions():
    """کلاینت فهرست پست‌هایی که واقعاً دیده شدند را می‌فرستد (برای «دسترسی» در آمار پست). هر کاربر یک‌بار حساب می‌شود."""
    ids = [i for i in ((request.get_json(silent=True) or {}).get('ids') or [])[:200] if isinstance(i, int)]
    for i in ids:
        run('insert or ignore into impressions(post_id,user_id,created) select id, ?, ? from posts where id=? and user_id!=?',
            session['uid'], time.time(), i, session['uid'])
    return jsonify(ok=True)


@bp.get('/api/post/<int:pid>/insights')
@auth
def insights(pid):
    """آمار پست فقط برای صاحبش."""
    p = q1('select * from posts where id=? and user_id=?', pid, session['uid'])
    if not p:
        return err('پست پیدا نشد', 404)
    n = lambda sql: q1(sql, pid)['c']
    viewers = {r['u'] for r in q('select user_id u from impressions where post_id=? union select user_id from watch where post_id=?', pid, pid)}
    fol = {r['follower'] for r in q('select follower from follows where followee=?', p['user_id'])}
    d = dict(kind=p['kind'], reach=len(viewers), likes=n('select count(*) c from likes where post_id=?'),
             comments=n('select count(*) c from comments where post_id=?'), saves=n('select count(*) c from saves where post_id=?'),
             non_followers=round(100 * len(viewers - fol) / len(viewers)) if viewers else 0)
    if p['kind'] == 'video':
        w = q('select secs, plays, dur from watch where post_id=? and dur>0', pid)
        d['plays'] = sum(1 for r in w if r['secs'] >= 1)
        d['avg_watch'] = round(100 * sum(min(r['secs'] / max(r['plays'], 1) / r['dur'], 1) for r in w) / len(w)) if w else 0
        d['watch_minutes'] = round(sum(r['secs'] for r in w) / 60, 1)
    return jsonify(d)


@bp.delete('/api/posts/<int:pid>')
@auth
def del_post(pid):
    p = q1('select * from posts where id=? and user_id=?', pid, session['uid'])
    if not p:
        return err('پست پیدا نشد', 404)
    extras = q('select * from post_media where post_id=?', pid)
    run('delete from posts where id=?', pid)
    for e in extras:
        for f in (e['file'], e['mid'], e['poster']):
            storage.rm_file(f)
    storage.rm_file(p['file'])
    storage.rm_file(p['poster'])
    storage.rm_file(p['mid'])
    storage.rm_file(p['low'])
    return jsonify(ok=True)


def toggle(table, pid):
    if not q1('select 1 from posts where id=?', pid):
        return err('پست پیدا نشد', 404)
    uid = session['uid']
    owner = q1('select user_id from posts where id=?', pid)['user_id']
    if owner in vis.invisible(session['uid']):
        return err('پست پیدا نشد', 404)
    if q1(f'select 1 from {table} where user_id=? and post_id=?', uid, pid):
        run(f'delete from {table} where user_id=? and post_id=?', uid, pid)
        if table == 'likes':
            unnotify(owner, uid, 'like', pid)
    else:
        run(f'insert into {table}(user_id,post_id) values(?,?)', uid, pid)
        if table == 'likes':
            notify(owner, uid, 'like', pid, unique=True)
    return jsonify(ser(q1('select * from posts where id=?', pid), True))


@bp.post('/api/posts/<int:pid>/like')
@auth
def like(pid): return toggle('likes', pid)


@bp.post('/api/posts/<int:pid>/save')
@auth
def save(pid): return toggle('saves', pid)


@bp.post('/api/posts/<int:pid>/comments')
@auth
def comment(pid):
    d = request.get_json(silent=True) or {}
    text = (d.get('text') or '').strip()[:500]
    if not text:
        return err('نظر خالی است')
    post = q1('select * from posts where id=?', pid)
    if not post or post['user_id'] in vis.invisible(session['uid']):
        return err('پست پیدا نشد', 404)
    me_ = session['uid']
    parent = None
    if d.get('parent_id'):
        parent = q1('select * from comments where id=? and post_id=?', d['parent_id'], pid)
        if not parent:
            return err('نظر اصلی پیدا نشد', 404)
        replied = parent
        if parent['parent_id']:  # پاسخ به پاسخ هم زیر همان نظر اصلی می‌رود (مثل اینستاگرام)
            parent = q1('select * from comments where id=?', parent['parent_id'])
    c = run('insert into comments(post_id,user_id,text,created,parent_id) values(?,?,?,?,?)',
            pid, me_, text, time.time(), parent['id'] if parent else None)
    cid = c.lastrowid
    skip = {me_}
    if parent:
        for target in {replied['user_id'], parent['user_id']}:  # هم کسی که جوابش را دادی، هم صاحب نظر اصلی
            if target not in skip:
                notify(target, me_, 'reply', pid, cid)
                skip.add(target)
    if post['user_id'] not in skip:
        notify(post['user_id'], me_, 'comment', pid, cid)
        skip.add(post['user_id'])
    notify_mentions(text, me_, pid, cid, skip)
    return jsonify(ok=True, id=cid)


@bp.post('/api/comments/<int:cid>/like')
@auth
def like_comment(cid):
    c = q1('select * from comments where id=?', cid)
    if not c:
        return err('نظر پیدا نشد', 404)
    me_ = session['uid']
    if q1('select 1 from comment_likes where comment_id=? and user_id=?', cid, me_):
        run('delete from comment_likes where comment_id=? and user_id=?', cid, me_)
        unnotify(c['user_id'], me_, 'comment_like', c['post_id'], cid)
    else:
        run('insert into comment_likes(comment_id,user_id) values(?,?)', cid, me_)
        notify(c['user_id'], me_, 'comment_like', c['post_id'], cid, unique=True)
    return jsonify(likes=q1('select count(*) n from comment_likes where comment_id=?', cid)['n'],
                   liked=bool(q1('select 1 from comment_likes where comment_id=? and user_id=?', cid, me_)))


@bp.delete('/api/comments/<int:cid>')
@auth
def delete_comment(cid):
    c = q1('select c.*, p.user_id as owner from comments c join posts p on p.id=c.post_id where c.id=?', cid)
    if not c:
        return err('نظر پیدا نشد', 404)
    if session['uid'] not in (c['user_id'], c['owner']):
        return err('فقط نویسنده نظر یا صاحب پست', 403)
    ids = [cid] + [r['id'] for r in q('select id from comments where parent_id=?', cid)]
    for i in ids:
        run('delete from notifications where comment_id=?', i)
        run('delete from comments where id=?', i)
    return jsonify(ok=True)


@bp.patch('/api/posts/<int:pid>')
@auth
def edit_post(pid):
    p = q1('select * from posts where id=? and user_id=?', pid, session['uid'])
    if not p:
        return err('پست پیدا نشد', 404)
    cap = ((request.get_json(silent=True) or {}).get('caption') or '').strip()[:2200]
    run('update posts set caption=? where id=?', cap, pid)
    notify_mentions(cap, session['uid'], pid)
    return jsonify(ser(q1('select * from posts where id=?', pid), True))
