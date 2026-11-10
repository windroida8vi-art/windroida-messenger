"""هایلایت، کالکشن و پیشنهاد «افرادی که شاید بشناسی» (الگوریتم گراف دنبال‌کردن + علاقه‌های مشترک)."""
import math
import time

from flask import Blueprint, jsonify, request, session

from .. import vis
from ..db import q, q1, run
from ..notify import HASHTAG
from ..ranking import following
from ..security import auth, err
from ..serializers import ser, uj

bp = Blueprint('extras', __name__)


# ---------- هایلایت ----------
def _hl_group(h, me_):
    rows = q('select s.*, u.username, u.avatar from highlight_items hi join stories s on s.id=hi.story_id '
             'join users u on u.id=s.user_id where hi.highlight_id=? order by hi.pos', h['id'])
    if not rows:
        return None
    return dict(username=rows[0]['username'], avatar=rows[0]['avatar'], mine=h['user_id'] == me_, close=False, seen=True,
                hid=h['id'], title=h['title'],
                items=[dict(id=r['id'], file=r['file'], kind=r['kind'], created=r['created'], seen=True, views=None,
                            audience='all', sticker=None, old=True) for r in rows])


@bp.get('/api/highlights/mine')
@auth
def my_highlights():
    return jsonify([dict(id=h['id'], title=h['title']) for h in q('select * from highlights where user_id=? order by id', session['uid'])])


@bp.get('/api/highlights/<int:hid>')
@auth
def highlight(hid):
    h = q1('select * from highlights where id=?', hid)
    if not h or h['user_id'] in vis.invisible(session['uid']):
        return err('هایلایت پیدا نشد', 404)
    g = _hl_group(h, session['uid'])
    return jsonify(g) if g else err('هایلایت خالی است', 404)


@bp.post('/api/highlights')
@auth
def create_highlight():
    d = request.get_json(silent=True) or {}
    title = (d.get('title') or '').strip()[:30] or 'هایلایت'
    s = q1('select * from stories where id=? and user_id=?', d.get('story_id'), session['uid'])
    if not s:
        return err('استوری پیدا نشد', 404)
    if q1('select count(*) c from highlights where user_id=?', session['uid'])['c'] >= 20:
        return err('حداکثر ۲۰ هایلایت')
    h = run('insert into highlights(user_id,title,created) values(?,?,?)', session['uid'], title, time.time())
    run('insert into highlight_items values(?,?,0)', h.lastrowid, s['id'])
    return jsonify(id=h.lastrowid)


@bp.post('/api/highlights/<int:hid>/add')
@auth
def add_to_highlight(hid):
    h = q1('select * from highlights where id=? and user_id=?', hid, session['uid'])
    s = q1('select * from stories where id=? and user_id=?', (request.get_json(silent=True) or {}).get('story_id'), session['uid'])
    if not h or not s:
        return err('پیدا نشد', 404)
    pos = q1('select coalesce(max(pos),-1)+1 p from highlight_items where highlight_id=?', hid)['p']
    run('insert or ignore into highlight_items values(?,?,?)', hid, s['id'], pos)
    return jsonify(ok=True)


@bp.delete('/api/highlights/<int:hid>')
@auth
def delete_highlight(hid):
    n = run('delete from highlights where id=? and user_id=?', hid, session['uid']).rowcount
    return jsonify(ok=True) if n else err('پیدا نشد', 404)


# ---------- کالکشن ----------
@bp.get('/api/collections')
@auth
def collections():
    me_, pid = session['uid'], request.args.get('post_id', type=int)
    out = []
    for c in q('select * from collections where user_id=? order by id', me_):
        cover = q1('select p.file, p.poster, p.kind from collection_items ci join posts p on p.id=ci.post_id '
                   'where ci.collection_id=? order by ci.created desc limit 1', c['id'])
        d = dict(id=c['id'], name=c['name'], count=q1('select count(*) n from collection_items where collection_id=?', c['id'])['n'],
                 cover=dict(file=cover['file'], poster=cover['poster'], kind=cover['kind']) if cover else None)
        if pid:
            d['has'] = bool(q1('select 1 from collection_items where collection_id=? and post_id=?', c['id'], pid))
        out.append(d)
    return jsonify(out)


@bp.post('/api/collections')
@auth
def new_collection():
    name = ((request.get_json(silent=True) or {}).get('name') or '').strip()[:40]
    if not name:
        return err('نام کالکشن را بنویس')
    if q1('select count(*) c from collections where user_id=?', session['uid'])['c'] >= 30:
        return err('حداکثر ۳۰ کالکشن')
    return jsonify(id=run('insert into collections(user_id,name,created) values(?,?,?)', session['uid'], name, time.time()).lastrowid)


@bp.post('/api/collections/<int:cid>/items')
@auth
def toggle_item(cid):
    pid = (request.get_json(silent=True) or {}).get('post_id')
    if not q1('select 1 from collections where id=? and user_id=?', cid, session['uid']):
        return err('کالکشن پیدا نشد', 404)
    p = q1('select user_id from posts where id=?', pid)
    if not p or p['user_id'] in vis.invisible(session['uid']):
        return err('پست پیدا نشد', 404)
    if q1('select 1 from collection_items where collection_id=? and post_id=?', cid, pid):
        run('delete from collection_items where collection_id=? and post_id=?', cid, pid)
        return jsonify(has=False)
    run('insert into collection_items values(?,?,?)', cid, pid, time.time())
    run('insert or ignore into saves(user_id,post_id) values(?,?)', session['uid'], pid)  # قرار گرفتن در کالکشن = ذخیره
    return jsonify(has=True)


@bp.get('/api/collections/<int:cid>')
@auth
def collection(cid):
    c = q1('select * from collections where id=? and user_id=?', cid, session['uid'])
    if not c:
        return err('کالکشن پیدا نشد', 404)
    inv = vis.invisible(session['uid'])
    rows = q('select p.* from collection_items ci join posts p on p.id=ci.post_id where ci.collection_id=? order by ci.created desc', cid)
    return jsonify(id=cid, name=c['name'], posts=[ser(p) for p in rows if p['user_id'] not in inv])


@bp.delete('/api/collections/<int:cid>')
@auth
def delete_collection(cid):
    n = run('delete from collections where id=? and user_id=?', cid, session['uid']).rowcount
    return jsonify(ok=True) if n else err('پیدا نشد', 404)


# ---------- افرادی که شاید بشناسی ----------
@bp.get('/api/suggestions')
@auth
def suggestions():
    """امتیاز = ۲×دنبال‌کننده‌ی مشترک + ۱٫۵×(تو را دنبال می‌کند) + ۳×شباهت هشتگ‌ها + محبوبیت (لگاریتمی). فوری و بدون مدل سنگین."""
    me_ = session['uid']
    fol = following(me_)
    skip = fol | vis.blocked(me_) | {me_} | {r['target'] for r in q('select target from follow_requests where requester=?', me_)}
    cand = {}

    def slot(u):
        return cand.setdefault(u, dict(mutual=0, back=0, tags=0.0))
    for r in q('select f2.followee u, count(*) c from follows f1 join follows f2 on f2.follower=f1.followee '
               'where f1.follower=? group by f2.followee', me_):
        if r['u'] not in skip:
            slot(r['u'])['mutual'] = r['c']
    for r in q('select follower u from follows where followee=?', me_):
        if r['u'] not in skip:
            slot(r['u'])['back'] = 1
    mine = set()
    for r in q('select p.caption from posts p where p.user_id=? union all select p.caption from likes l join posts p on p.id=l.post_id '
               'where l.user_id=? order by 1 limit 80', me_, me_):
        mine |= {t.lower() for t in HASHTAG.findall(r['caption'] or '')}
    if mine:
        top = sorted(mine)[:8]
        for r in q(f'select user_id u, caption from posts where ' + ' or '.join(['caption like ?'] * len(top)) + ' order by id desc limit 300',
                   *['%#' + t + '%' for t in top]):
            if r['u'] not in skip:
                theirs = {t.lower() for t in HASHTAG.findall(r['caption'] or '')}
                s_ = slot(r['u'])
                s_['tags'] = max(s_['tags'], len(mine & theirs) / len(mine | theirs))
    fc = {r['u']: r['c'] for r in q('select followee u, count(*) c from follows group by followee')}
    for u in sorted(fc, key=lambda k: -fc[k])[:15]:  # اگر کم بود، محبوب‌ترها
        if u not in skip:
            slot(u)
    scored = sorted(cand.items(), key=lambda kv: -(2 * kv[1]['mutual'] + 1.5 * kv[1]['back'] + 3 * kv[1]['tags'] + 0.3 * math.log1p(fc.get(kv[0], 0))))[:12]
    out = []
    for uid, s_ in scored:
        u = q1('select * from users where id=?', uid)
        if not u:
            continue
        reason = (f"{s_['mutual']} دنبال‌کننده مشترک" if s_['mutual'] else 'تو را دنبال می‌کند' if s_['back']
                  else 'علاقه‌های مشابه' if s_['tags'] else 'محبوب در قاب')
        out.append(dict(uj(u), reason=reason, private=bool(u['private'])))
    return jsonify(out)
