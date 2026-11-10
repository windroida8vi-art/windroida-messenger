"""چه کسی چه چیزی را می‌بیند: بلاک (دوطرفه)، حساب خصوصی (فقط دنبال‌کننده‌ها) و میوت. هر درخواست یک‌بار محاسبه می‌شود."""
from flask import g

from .db import q


def blocked(me):
    if '_blk' not in g:
        s = set()
        for r in q('select blocker, blocked from blocks where blocker=? or blocked=?', me, me):
            s.add(r['blocked'] if r['blocker'] == me else r['blocker'])
        g._blk = s
    return g._blk


def private_hidden(me):
    if '_prv' not in g:
        g._prv = {r['id'] for r in q('select u.id from users u where u.private=1 and u.id!=? and not exists '
                                     '(select 1 from follows f where f.follower=? and f.followee=u.id)', me, me)}
    return g._prv


def invisible(me):
    return blocked(me) | private_hidden(me)


def muted(me):
    if '_mut' not in g:
        g._mut = {r['muted'] for r in q('select muted from mutes where user_id=?', me)}
    return g._mut


def not_in(col, ids):
    ids = list(ids)
    return (f'{col} not in ({",".join("?" * len(ids))})', ids) if ids else ('1=1', [])
