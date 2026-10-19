#!/usr/bin/env bash
export PATH="$HOME/.local/bin:/home/linuxbrew/.linuxbrew/bin:$PATH"
cd "$(dirname "$(readlink -f "$0")")" || exit 1

echo "========================================"
echo "  Publicar actualizacion (payload)"
echo "========================================"
echo
echo "Tip: corre antes ./subir_a_github.sh para que el codigo fuente quede subido."
echo

read -rp "Version nueva (ej. 1.1.0): " VER
if [ -z "$VER" ]; then
  echo "Version vacia, cancelado."
  exit 1
fi
read -rp "Notas del cambio (se muestran en el boton Updates): " NOTES

if ! python3 build_payload.py "$VER" "$NOTES"; then
  echo "[ERROR] No se pudo generar el payload."
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo
  echo "GitHub CLI (gh) no esta instalado. Sube a mano en"
  echo "  https://github.com/azu42968-maker/acidmodloader/releases/new"
  echo "con tag v$VER y estos dos archivos de la carpeta release/:"
  echo "  payload.zip  y  manifest.json"
  exit 0
fi

if ! gh release create "v$VER" release/payload.zip release/manifest.json \
     --title "v$VER" --notes "$NOTES" --repo azu42968-maker/acidmodloader; then
  echo "[ERROR] Fallo la creacion del release. Revisa 'gh auth status'."
  exit 1
fi

echo
echo "Listo: los usuarios veran el aviso en el boton Updates."
