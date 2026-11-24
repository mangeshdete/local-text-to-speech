#!/usr/bin/env bash
cd "$(dirname "$(readlink -f "$0")")"
if [[ ! -x .venv/bin/python ]]; then
  echo "The voice tool is not set up yet. See README.md."
  exit 1
fi
mkdir -p output
URL="http://127.0.0.1:8765/"
PIDFILE="output/gui.pid"
alive=0
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  alive=1
fi
if [[ "$alive" -eq 0 ]]; then
  .venv/bin/python gui_server.py >> output/gui.log 2>&1 &
  echo $! > "$PIDFILE"
fi
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if .venv/bin/python -c "import urllib.request; urllib.request.urlopen('$URL', timeout=0.5)" >/dev/null 2>&1; then
    break
  fi
  sleep 0.3
done
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" >/dev/null 2>&1 || true
fi
echo "Open $URL in a browser. The command line still works with ./run.sh."
