#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 9000 --reload
