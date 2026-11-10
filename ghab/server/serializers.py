"""تبدیل ردیف‌های دیتابیس به JSON برای کلاینت."""
from flask import g, session

from . import vis
from .db import q, q1


def uj(u):
    return dict(id=u['id'], username=u['username'], name=u['name'], bio=u['bio'], avatar=u['avatar'])


def me_json(u):
    """اطلاعات خودِ کاربر: همان uj به‌اضافه اینکه سوال امنیتی ثبت کرده یا نه."""
    d = uj(u)
    from . import config
    d['sso_only'] = not config.PASSWORD_AUTH
    d['has_sec'] = bool(u['sec_q']) or not config.PASSWORD_AUTH
    d['private'] = bool(u['private'])
    return d


def _user(uid):
    cache = g.setdefault('_users', {})
    if uid not in cache:
        cache[uid] = q1('select * from users where id=?', uid)
    return cache[uid]


def _my_sets():
    """لایک‌ها و ذخیره‌های من، یک‌بار در هر درخواست (نه یک کوئری برای هر پست)."""
    if '_sets' not in g:
        me = session.get('uid')
        g._sets = ({r['post_id'] for r in q('select post_id from likes where user_id=?', me)},
                   {r['post_id'] for r in q('select post_id from saves where user_id=?', me)})
    return g._sets


def comments_of(pid):
    me = session.get('uid')
    cl, pa = vis.not_in('c.user_id', vis.blocked(me))
    return [dict(id=c['id'], parent_id=c['parent_id'], text=c['text'], created=c['created'], username=c['username'],
                 avatar=c['avatar'], likes=c['lk'], liked=bool(c['liked']), mine=c['user_id'] == me) for c in q(
        'select c.id, c.parent_id, c.text, c.created, c.user_id, u.username, u.avatar, '
        '(select count(*) from comment_likes l where l.comment_id=c.id) lk, '
        '(select 1 from comment_likes l where l.comment_id=c.id and l.user_id=?) liked '
        f'from comments c join users u on u.id=c.user_id where c.post_id=? and {cl} order by c.id', me, pid, *pa)]


def ser(p, full=False):
    me = session.get('uid')
    pre = 'lk' in p.keys()  # اگر شمارش‌ها از قبل در کوئری آمده باشند دوباره نمی‌شماریم
    liked, saved = _my_sets()
    d = dict(
        id=p['id'], user=uj(_user(p['user_id'])), file=p['file'], poster=p['poster'], nmedia=p['nmedia'] or 1, mid=p['mid'] or None, low=p['low'] or None, kbps=p['kbps'], lkbps=p['lkbps'], kind=p['kind'], caption=p['caption'], created=p['created'],
        likes=p['lk'] if pre else q1('select count(*) c from likes where post_id=?', p['id'])['c'],
        liked=p['id'] in liked, saved=p['id'] in saved,
        ncomments=p['cm'] if pre else q1('select count(*) c from comments where post_id=?', p['id'])['c'],
        mine=p['user_id'] == me)
    if p['nmedia'] and p['nmedia'] > 1:  # کاروسل: چند عکس در یک پست
        d['media'] = [dict(file=p['file'], mid=p['mid'], poster=p['poster'])] + [
            dict(file=r['file'], mid=r['mid'], poster=r['poster']) for r in q('select * from post_media where post_id=? order by pos', p['id'])]
    if p['kind'] == 'video':
        d['views'] = q1('select count(*) c from watch where post_id=? and secs>=1', p['id'])['c']
    if full:
        d['comments'] = comments_of(p['id'])
    return d


def msg_ser(m):
    d = dict(id=m['id'], mine=m['sender'] == session['uid'], text=m['text'], created=m['created'], seen=bool(m['seen']),
             kind=m['kind'] or 'text', media=m['media'])
    if m['deleted']:
        d['text'], d['deleted'] = '', True
    elif m['post_id']:
        p = q1('select * from posts where id=?', m['post_id'])
        if p:
            u = q1('select username from users where id=?', p['user_id'])
            d['post'] = dict(id=p['id'], file=p['file'], poster=p['poster'], kind=p['kind'], user=u['username'], caption=(p['caption'] or '')[:80])
    elif not m['text'] and not m['media']:
        d['gone'] = True
    return d
