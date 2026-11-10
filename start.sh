#!/usr/bin/env bash
# Windroida launcher for Linux / macOS  (the same job as start.bat on Windows)
#   ./start.sh                run everything
#   ./start.sh --local        only this machine
#   ./start.sh --http         plain http instead of https
#   ./start.sh --no-ghab --no-drive --no-datasheet   (see the top of start.py for all options)
# First run: makes a private ".venv" folder and installs the libraries into it
# (from the "wheels" folder first = no internet; if that does not work, from pypi.org).
# Next runs start at once. Delete the ".venv" folder to redo the setup.
# اولین اجرا: ساخت پوشه .venv و نصب کتابخونه‌ها؛ دفعه‌های بعد مستقیم اجرا می‌شه.

cd "$(dirname "$0")" || exit 1

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo
  echo "  Python 3.9+ is not installed.  /  پایتون ۳ نصب نیست."
  echo "  Debian/Ubuntu:  sudo apt install python3 python3-venv python3-pip"
  echo "  Fedora:         sudo dnf install python3"
  echo "  macOS:          brew install python"
  echo
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo
  echo "  First run: preparing .venv ...  /  اولین اجرا: ساخت پوشه .venv"
  if ! "$PY" -m venv .venv; then
    rm -rf .venv
    echo "  Could not create .venv (on Debian/Ubuntu: sudo apt install python3-venv)."
    echo "  Using the normal Python instead.  /  با پایتون معمولی ادامه می‌دم"
    exec "$PY" start.py "$@"
  fi
fi
VPY=".venv/bin/python"

if [ ! -f ".venv/deps.ok" ]; then
  echo "  Installing libraries (offline from \"wheels\" first) ...  /  نصب کتابخونه‌ها"
  ok=0
  if ls wheels/*.whl >/dev/null 2>&1 && "$VPY" -m pip install --disable-pip-version-check -q --no-index --find-links wheels -r requirements-all.txt; then ok=1; fi
  if [ "$ok" = 0 ]; then
    echo "  wheels folder missing or for another system - trying the internet ...  /  تلاش از اینترنت"
    if "$VPY" -m pip install --disable-pip-version-check -q -r requirements-all.txt; then ok=1; fi
  fi
  if [ "$ok" = 1 ]; then
    echo ok > .venv/deps.ok
  else
    echo
    echo "  Could not install all libraries. The messenger still starts (some features limited)."
    echo "  (the wheels folder holds Windows files; on Linux the libraries come from pypi.org)"
  fi
fi

exec "$VPY" start.py "$@"
