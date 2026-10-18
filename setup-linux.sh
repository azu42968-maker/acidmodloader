#!/usr/bin/env bash
# Prepara AcidModLoader en Linux (probado en la idea de Bazzite/Fedora + Distrobox).
# En Bazzite correlo DENTRO de un distrobox de Fedora:
#   distrobox create -n acid -i fedora:latest && distrobox enter acid
#   ./setup-linux.sh
set -euo pipefail
cd "$(dirname "$0")"
DIR="$(pwd)"

if command -v dnf >/dev/null; then
  sudo dnf install -y git python3 python3-pip python3-devel gcc \
    python3-gobject gtk3 webkit2gtk4.1 java-latest-openjdk-headless 7zip
elif command -v apt-get >/dev/null; then
  sudo apt-get update
  sudo apt-get install -y git python3 python3-pip python3-venv python3-dev gcc \
    python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 default-jre-headless p7zip-full
else
  echo "Instala a mano: python3, PyGObject, GTK3, WebKit2GTK, Java 17+ y 7zip." >&2
fi

# --system-site-packages para que el venv vea PyGObject (gi) del sistema
python3 -m venv --system-site-packages venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements-linux.txt

# Lanzador en el menú de aplicaciones
mkdir -p "$HOME/.local/share/applications"
if [ -n "${CONTAINER_ID:-}" ]; then
  EXEC="distrobox enter ${CONTAINER_ID} -- $DIR/run-linux.sh"
else
  EXEC="$DIR/run-linux.sh"
fi
cat > "$HOME/.local/share/applications/acidmodloader.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Acid Mod Loader
Exec=$EXEC
Icon=$DIR/payload/icon.png
Terminal=false
Categories=Game;Utility;
DESK
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo
echo "Listo. Ejecuta: ./run-linux.sh"
echo "Si Brawlhalla está en otra ruta de Steam, elígela con el botón flotante de la app."
