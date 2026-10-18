#!/usr/bin/env bash
# Trabaja siempre en la carpeta donde esta este script
cd "$(dirname "$(readlink -f "$0")")" || exit 1
export PATH="$HOME/.local/bin:/home/linuxbrew/.linuxbrew/bin:$PATH"

echo "========================================"
echo "  Subir web a GitHub"
echo "  Carpeta: $PWD"
echo "========================================"
echo

# --- Comprobar que Git esta instalado ---
if ! command -v git >/dev/null 2>&1; then
  echo "[ERROR] Git no esta instalado."
  echo "En Bazzite/Fedora Atomic: usa 'brew install git' o corre este script dentro de distrobox."
  read -rp "Pulsa Enter para salir..." _
  exit 1
fi

# --- Nombre y correo de Git, solo si faltan ---
if [ -z "$(git config --global user.name)" ]; then
  read -rp "Tu nombre para los commits: " GIT_NAME
  git config --global user.name "$GIT_NAME"
fi
if [ -z "$(git config --global user.email)" ]; then
  read -rp "Tu correo de GitHub: " GIT_MAIL
  git config --global user.email "$GIT_MAIL"
fi

# --- Inicializar repositorio la primera vez ---
if [ ! -d .git ]; then
  echo "Primera vez: inicializando repositorio..."
  git init
  git branch -M main
fi

# --- Repositorio de destino ---
REPO_URL="https://github.com/azu42968-maker/acidmodloader.git"
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REPO_URL"
else
  git remote add origin "$REPO_URL"
fi

# --- Aviso si falta el .gitignore (sin el, se subiria todo) ---
if [ ! -f .gitignore ]; then
  echo "[AVISO] No hay .gitignore: se subiria todo, incluidos dist, .build-venv y el JRE."
  echo "        Copia el .gitignore del proyecto y vuelve a ejecutar."
  read -rp "Pulsa Enter para salir..." _
  exit 1
fi

# --- Sacar del repo lo que ya estaba subido pero ahora esta ignorado ---
# (no borra nada de tu disco, solo deja de rastrearlo en git)
echo "Limpiando archivos innecesarios del repositorio..."
git rm -r --cached -q --ignore-unmatch dist build .build-venv .build-python312 release \
  vendor/jre config.json AcidModLoader.spec __pycache__ payload/__pycache__ >/dev/null 2>&1

# --- Anadir cambios y hacer commit ---
git add -A
echo
echo "Resumen de lo que se va a subir:"
git diff --cached --shortstat
echo
if ! git diff --cached --quiet; then
  read -rp "Mensaje del commit, Enter para usar fecha y hora: " MSG
  [ -z "$MSG" ] && MSG="Actualizacion $(date '+%d/%m/%Y %H:%M:%S')"
  git commit -m "$MSG"
else
  echo "No hay cambios nuevos que commitear."
fi

ok() {
  echo
  echo "Listo, subido correctamente."
  read -rp "Pulsa Enter para salir..." _
  exit 0
}

fallo() {
  echo
  echo "[ERROR] No se pudo subir. Revisa tu login de GitHub y el mensaje de arriba."
  read -rp "Pulsa Enter para salir..." _
  exit 1
}

# --- Login a GitHub (abre Firefox) ---
abrir_navegador() {
  if command -v firefox >/dev/null 2>&1; then
    export GH_BROWSER="firefox"
  elif command -v flatpak >/dev/null 2>&1 && flatpak info org.mozilla.firefox >/dev/null 2>&1; then
    export GH_BROWSER="flatpak run org.mozilla.firefox"
  fi
}

instalar_gh() {
  echo "Descargando GitHub CLI (gh) a ~/.local/bin ..."
  mkdir -p "$HOME/.local/bin"
  local url tmp ver
  # La redireccion de /releases/latest trae la version (sin usar la API, que limita)
  ver=$(curl -fsSIL -o /dev/null -w '%{url_effective}' https://github.com/cli/cli/releases/latest | sed 's#.*/tag/v##')
  [ -z "$ver" ] && { echo "[ERROR] No pude obtener la version de gh."; return 1; }
  url="https://github.com/cli/cli/releases/download/v${ver}/gh_${ver}_linux_amd64.tar.gz"
  tmp=$(mktemp -d)
  curl -fsSL "$url" -o "$tmp/gh.tar.gz" || return 1
  tar xzf "$tmp/gh.tar.gz" -C "$tmp" || return 1
  cp "$tmp"/gh_*/bin/gh "$HOME/.local/bin/gh" && chmod +x "$HOME/.local/bin/gh"
  rm -rf "$tmp"
  command -v gh >/dev/null 2>&1
}

asegurar_login() {
  if ! command -v gh >/dev/null 2>&1; then
    if command -v brew >/dev/null 2>&1; then
      brew install gh || instalar_gh || return 1
    else
      instalar_gh || return 1
    fi
  fi
  if ! gh auth status >/dev/null 2>&1; then
    echo
    echo "Hay que iniciar sesion en GitHub. Se abrira Firefox:"
    echo "copia el codigo que aparece aqui, pegalo en la pagina y autoriza."
    abrir_navegador
    gh auth login --hostname github.com --git-protocol https --web || return 1
  fi
  gh auth setup-git >/dev/null 2>&1
  return 0
}

asegurar_login

# --- Subir ---
hacer_push() {
  PUSH_OUT=$(LC_ALL=C.UTF-8 git push -u origin main 2>&1)
  local rc=$?
  echo "$PUSH_OUT"
  return $rc
}

echo
echo "Subiendo a GitHub..."
hacer_push && ok

# Fallo de autenticacion: iniciar sesion y reintentar una vez
if echo "$PUSH_OUT" | grep -qiE "Authentication failed|Invalid username or token|could not read Username"; then
  echo
  echo "[!] Falta iniciar sesion en GitHub."
  gh auth logout --hostname github.com >/dev/null 2>&1
  asegurar_login || fallo
  hacer_push && ok
  echo "$PUSH_OUT" | grep -qiE "Authentication failed|Invalid username or token" && fallo
fi

echo
echo "[!] GitHub rechazo el push: el repo remoto tiene commits que no tienes aqui."
echo
echo "  [1] Unir y quedarme con MIS archivos   (seguro, no se pierde historial)"
echo "  [2] Reemplazar el remoto con lo mio    (borra el historial viejo de main)"
echo "  [N] Cancelar"
echo
read -rp "Elige 1, 2 o N: " OPT
case "${OPT,,}" in
  1)
    echo
    echo "Uniendo historiales..."
    git fetch origin || fallo
    git merge -s ours origin/main --allow-unrelated-histories \
      -m "Unir historial remoto (se conservan los archivos locales)" || fallo
    git push -u origin main || fallo
    ok
    ;;
  2)
    echo
    echo "Reemplazando el remoto con tu version..."
    git fetch origin || fallo
    git push -u origin main --force-with-lease || fallo
    ok
    ;;
  *)
    echo
    echo "Cancelado. No se subio nada."
    read -rp "Pulsa Enter para salir..." _
    exit 0
    ;;
esac
