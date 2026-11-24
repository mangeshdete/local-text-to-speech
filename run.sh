#!/usr/bin/env bash
cd "$(dirname "$(readlink -f "$0")")"
if [[ ! -x .venv/bin/python ]]; then
  echo "The voice tool is not set up yet. See README.md."
  exit 1
fi
exec .venv/bin/python app.py "$@"
