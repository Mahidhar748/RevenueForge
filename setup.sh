#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt
(cd frontend && npm install)
echo "Setup complete. Run ./start.sh"
