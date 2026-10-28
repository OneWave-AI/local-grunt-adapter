#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python build_panel.py
.venv/bin/python adapter.py --doctor
.venv/bin/python install_clients.py "$@"
