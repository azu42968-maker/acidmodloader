#!/usr/bin/env bash
SELF="$(readlink -f "$0")"
ROOT="$(dirname "$SELF")"
DISTROBOX_NAME="${DISTROBOX_NAME:-acid}"

# Si no estamos dentro de una caja, relanzar dentro de ella
if [ ! -f /run/.containerenv ] && [ -z "$CONTAINER_ID" ]; then
  echo "Abriendo dentro de la caja: $DISTROBOX_NAME"
  exec distrobox enter "$DISTROBOX_NAME" -- "$SELF" "$@"
fi

cd "$ROOT/payload" || exit 1

if [ -x "$HOME/.local/share/jdk21/bin/java" ]; then
  export JAVA_HOME="$HOME/.local/share/jdk21"
elif command -v java >/dev/null 2>&1; then
  export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v java)")")")"
fi
export PATH="$JAVA_HOME/bin:$PATH"
echo "JAVA_HOME=$JAVA_HOME"

# --- Backend Qt (Chromium) en vez de WebKitGTK ---
# Se pueden sobreescribir desde fuera, p. ej.:
#   QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox" ./run-linux.sh
export PYWEBVIEW_GUI="${PYWEBVIEW_GUI:-qt}"
export QT_API="${QT_API:-pyqt6}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
export QTWEBENGINE_CHROMIUM_FLAGS="${QTWEBENGINE_CHROMIUM_FLAGS:---no-sandbox --disable-gpu}"
export PYTHONUNBUFFERED=1

# Python del venv con ruta absoluta (evita el aviso de sys.prefix)
if [ -x "$ROOT/venv/bin/python" ]; then PY="$ROOT/venv/bin/python"; else PY=python3; fi

LOG="$ROOT/acid.log"
# PyQt6 aborta el proceso entero si un slot lanza una excepción sin manejar
# (p. ej. pywebview fallando al parsear una cookie de GameBanana/anuncios).
# Con un excepthook propio se imprime el error y la app sigue viva.
"$PY" - "$@" <<'PYEOF' 2>&1 | tee "$LOG"
import sys, runpy, traceback

def _hook(tp, val, tb):
    traceback.print_exception(tp, val, tb)

sys.excepthook = _hook
sys.argv = ["app_main.py"] + sys.argv[1:]
runpy.run_path("app_main.py", run_name="__main__")
PYEOF
CODE=${PIPESTATUS[0]}

if [ "$CODE" -ne 0 ]; then
  echo
  echo "AcidModLoader terminó con código $CODE (139 = segfault, 137 = sin RAM). Log: $LOG"
fi
exit "$CODE"
