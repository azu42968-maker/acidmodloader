#!/usr/bin/env bash
SELF="$(readlink -f "$0")"
DISTROBOX_NAME="${DISTROBOX_NAME:-acid}"

# Si no estamos dentro de una caja, relanzar dentro de ella
if [ ! -f /run/.containerenv ] && [ -z "$CONTAINER_ID" ]; then
  echo "Abriendo dentro de la caja: $DISTROBOX_NAME"
  exec distrobox enter "$DISTROBOX_NAME" -- "$SELF" "$@"
fi

cd "$(dirname "$SELF")/payload" || exit 1

if [ -x "$HOME/.local/share/jdk21/bin/java" ]; then
  export JAVA_HOME="$HOME/.local/share/jdk21"
elif command -v java >/dev/null 2>&1; then
  export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v java)")")")"
fi
export PATH="$JAVA_HOME/bin:$PATH"
echo "JAVA_HOME=$JAVA_HOME"

if [ -x ../venv/bin/python ]; then PY=../venv/bin/python; else PY=python3; fi
exec "$PY" app_main.py "$@"
