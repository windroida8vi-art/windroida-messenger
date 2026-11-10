"""همه Blueprintها اینجا ثبت می‌شوند. ماژول تازه ساختی؟ فقط اسمش را به لیست اضافه کن."""
from . import auth, extras, feed, messages, net, pages, local, posts, privacy, recovery, social, sso, stories, users

ALL = (pages, net, sso, auth, recovery, users, privacy, extras, social, posts, feed, stories, messages, local)


def register_all(app):
    for m in ALL:
        app.register_blueprint(m.bp)
