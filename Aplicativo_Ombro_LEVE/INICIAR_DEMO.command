#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt
DEMO_MODE=true .venv/bin/streamlit run app.py --server.address=127.0.0.1
