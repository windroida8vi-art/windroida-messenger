"""فید، کاوش و ریلز (همه با رتبه‌بندی و رعایت بلاک/حساب خصوصی/میوت). فید و ریلز صفحه‌به‌صفحه‌اند: limit و exclude."""
import logging
import time

from flask import Blueprint, jsonify, request, session

from .. import reco, vis
from ..db import q, q1, run
from ..ranking import CAND, affinity, following, marks, rank, rank_reels, seen_ids, unseen_first
from ..security import auth, err
from ..serializers import ser

bp = Blueprint('feed', __name__)
log = logging.getLogger('ghab.reco')


def _cut(ranked):
    """حذف پست‌هایی که کلاینت قبلاً گرفته و برش به اندازه limit."""
    ex = {int(x) for x in request.args.get('exclude', '').split(',') if x.isdigit()}
    limit = min(request.args.get('limit', type=int, default=12), 30)
    return [p for p in ranked if p['id'] not in ex][:limit]


@bp.get('/api/feed')
@auth
def feed():
    me_ = session['uid']
    inv, mut = vis.invisible(me_), vis.muted(me_)
    fol = (following(me_) - vis.blocked(me_) - mut) | {me_}
    # همه‌ی پست‌ها می‌آیند، ولی دیده‌نشده‌ها اول و دیده‌شده‌ها (هر زمان) ته فید؛ داخل هر دسته همان رتبه‌بندی قبلی
    S = 'p.id in (select post_id from impressions where user_id=?)'
    cl, pa = vis.not_in('p.user_id', inv | mut | fol)
    rows = []
    for neg, n_fol, n_oth in (('not ', 5000, 5000), ('', 5000, 5000)):
        rows += q(CAND + f'where p.user_id in ({marks(len(fol))}) and {neg}{S} order by p.id desc limit {n_fol}', *fol, me_)
        rows += q(CAND + f'where {cl} and {neg}{S} order by p.id desc limit {n_oth}', *pa, me_)
    return jsonify([ser(p) for p in _cut(unseen_first(rank(rows, me_, affinity(me_), 36, fol), seen_ids(me_)))])


@bp.get('/api/explore')
@auth
def explore():
    """کاوش شخصی‌سازی‌شده: علاوه بر محبوبیت و تازگی، شباهت کپشن به سلیقه‌ی کاربر (همان مدل پیشنهاد ویدیو) اثر دارد."""
    me_ = session['uid']
    cl, pa = vis.not_in('p.user_id', vis.invisible(me_))
    rows = q(CAND + f'where {cl} order by p.id desc', *pa)
    have = {r['id'] for r in rows}
    # پست‌های پرتعاملِ ۱۰ روز اخیر هم نامزد می‌شوند (قبلاً فقط ۲۰۰ پستِ آخر دیده می‌شد و پست خوبِ قدیمی‌تر هیچ‌وقت نمی‌آمد)
    for r in q(CAND + f'where {cl} and p.created>? order by lk*2+cm*3+sv*3 desc', *pa, 0):
        if r['id'] not in have:
            rows.append(r)
    try:
        extra = reco.personalize(rows, me_)
    except Exception:
        log.exception('کاوش شخصی')
        extra = None
    return jsonify([ser(p) for p in unseen_first(rank(rows, me_, affinity(me_), 96, extra=extra), seen_ids(me_))])


@bp.get('/api/reels')
@auth
def reels():
    me_ = session['uid']
    fol = following(me_) - vis.blocked(me_)
    cl, pa = vis.not_in('p.user_id', vis.invisible(me_))
    if request.args.get('tab') == 'following':
        ids = fol | {me_}
        rows = q(CAND + f"where p.kind='video' and p.user_id in ({marks(len(ids))}) order by p.id desc", *ids)
    else:
        rows = q(CAND + f"where p.kind='video' and {cl} order by p.id desc", *pa)
    out = []
    for p in _cut(rank_reels(rows, me_, affinity(me_), fol)):
        d = ser(p)
        d['followed'] = p['user_id'] in fol
        out.append(d)
    return jsonify(out)


@bp.post('/api/reels/watch')
@auth
def reel_watch():
    """کلاینت وقتی از یک ریل خارج می‌شود می‌فرستد چند ثانیه از چند ثانیه را دیده؛ الگوریتم از همین یاد می‌گیرد."""
    d = request.get_json(silent=True) or {}
    try:
        pid, secs, dur = int(d['post_id']), float(d['secs']), float(d['dur'])
    except (KeyError, TypeError, ValueError):
        return err('نامعتبر')
    if not (0 < dur <= 3600) or secs < 0.1 or not q1('select 1 from posts where id=?', pid):
        return jsonify(ok=True)
    run('insert into watch(user_id,post_id,secs,dur,plays,created) values(?,?,?,?,1,?) '
        'on conflict(user_id,post_id) do update set secs=secs+excluded.secs, dur=excluded.dur, plays=plays+1, created=excluded.created',
        session['uid'], pid, min(secs, dur * 3), dur, time.time())
    try:
        reco.train_event(session['uid'], pid)  # مدل با هر تماشا یاد می‌گیرد
    except Exception:
        log.exception('آموزش مدل پیشنهاد')
    return jsonify(ok=True)
