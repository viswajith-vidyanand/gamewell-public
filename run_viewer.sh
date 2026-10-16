#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ -f ".venv/bin/activate" ]; then
  . .venv/bin/activate
fi
python -m streamlit run viewer/app.py
