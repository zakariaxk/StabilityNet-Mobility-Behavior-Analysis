#!/usr/bin/env bash
# One-shot local setup: virtualenv, dependencies, ffmpeg check, model weights.
#
# Deliberately not Docker: torch + ultralytics + opencv is a ~3 GB image, and
# for a local-first tool two documented commands are faster and clearer.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Python"
python3 --version

if [ ! -d .venv ]; then
  echo "==> Creating .venv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing backend (this pulls torch; expect a few minutes)"
python3 -m pip install --quiet --upgrade pip
python3 -m pip install -e ".[dev]"

echo "==> ffmpeg"
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -version | head -1
else
  echo "MISSING. Annotated video output returns HTTP 503 without it."
  case "$(uname -s)" in
    Darwin) echo "  brew install ffmpeg" ;;
    Linux)  echo "  sudo apt install ffmpeg" ;;
    *)      echo "  https://ffmpeg.org/download.html" ;;
  esac
fi

echo "==> Model weights (auto-downloads yolo26n.pt if absent)"
python3 smoke_test.py

echo
echo "Ready. Start the backend with:"
echo "  cd backend && source .venv/bin/activate && uvicorn app.main:app --port 8000"
echo "Then the frontend in another terminal:"
echo "  cd frontend && npm install && npm run dev"
