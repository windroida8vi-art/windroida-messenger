#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Python 3.12+ is required"; exit 1; }
[ -d venv ] || python3 -m venv venv
. venv/bin/activate
if [ -d wheels ]; then pip install --no-index --find-links wheels -r requirements.txt
else pip install -r requirements.txt; fi
if ! python manage.py has-admin; then
  echo "No admin exists yet - create the first admin / اولین مدیر را بسازید:"
  python manage.py create-admin
fi
exec python wsgi.py
