"""اعلان‌ها (activity) و @منشن‌ها."""
import re
import time

from .db import q1, run

MENTION = re.compile(r'(?<![\w@])@([a-z0-9_][a-z0-9_.]{1,30}[a-z0-9_])', re.I)
HASHTAG = re.compile(r'#([\w\u0600-\u06FF]{2,40})')


def notify(user_id, actor, typ, post_id=None, comment_id=None, unique=False):
    if user_id == actor:
        return
    if unique and q1('select 1 from notifications where user_id=? and actor=? and type=? and post_id is ? and comment_id is ?',
                     user_id, actor, typ, post_id, comment_id):
        return
    run('insert into notifications(user_id,actor,type,post_id,comment_id,created) values(?,?,?,?,?,?)',
        user_id, actor, typ, post_id, comment_id, time.time())


def unnotify(user_id, actor, typ, post_id=None, comment_id=None):
    run('delete from notifications where user_id=? and actor=? and type=? and post_id is ? and comment_id is ?',
        user_id, actor, typ, post_id, comment_id)


def notify_mentions(text, actor, post_id, comment_id=None, skip=()):
    for name in {m.lower() for m in MENTION.findall(text or '')}:
        u = q1('select id from users where username=?', name)
        if u and u['id'] not in skip:
            notify(u['id'], actor, 'mention', post_id, comment_id, unique=True)
