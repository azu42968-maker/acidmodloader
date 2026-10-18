#!/usr/bin/env bash
cd "$(dirname "$(readlink -f "$0")")/payload" || exit 1
export JAVA_HOME="$HOME/.local/share/jdk21"
echo "JAVA_HOME=$JAVA_HOME"
if [ -x ../venv/bin/python ]; then PY=../venv/bin/python; else PY=python3; fi
exec "$PY" app_main.py "$@"
