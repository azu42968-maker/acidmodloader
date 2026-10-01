@echo off
setlocal EnableDelayedExpansion

REM Trabaja siempre en la carpeta donde esta este .bat
cd /d "%~dp0"

echo ========================================
echo   Subir web a GitHub
echo   Carpeta: %cd%
echo ========================================
echo.

REM --- Comprobar que Git esta instalado ---
where git >nul 2>&1
if not errorlevel 1 goto git_ok
if exist "%ProgramFiles%\Git\cmd\git.exe" set "PATH=%PATH%;%ProgramFiles%\Git\cmd"
where git >nul 2>&1
if not errorlevel 1 goto git_ok
echo [ERROR] Git no esta instalado o Windows no lo encuentra.
echo Descargalo en https://git-scm.com/download/win
echo Despues de instalarlo, cierra esta ventana y vuelve a ejecutar el script.
pause
exit /b 1
:git_ok

REM --- Nombre y correo de Git, solo si faltan ---
set "GIT_NAME="
for /f "delims=" %%A in ('git config --global user.name 2^>nul') do set "GIT_NAME=%%A"
if not defined GIT_NAME (
    set /p GIT_NAME=Tu nombre para los commits: 
    git config --global user.name "!GIT_NAME!"
)
set "GIT_MAIL="
for /f "delims=" %%A in ('git config --global user.email 2^>nul') do set "GIT_MAIL=%%A"
if not defined GIT_MAIL (
    set /p GIT_MAIL=Tu correo de GitHub: 
    git config --global user.email "!GIT_MAIL!"
)

REM --- Inicializar repositorio la primera vez ---
if not exist ".git" (
    echo Primera vez: inicializando repositorio...
    git init
    git branch -M main
)

REM --- Repositorio de destino ---
set "REPO_URL=https://github.com/azu42968-maker/acidmodloader.git"
git remote get-url origin >nul 2>&1
if errorlevel 1 (
    git remote add origin "%REPO_URL%"
) else (
    git remote set-url origin "%REPO_URL%"
)

REM --- Aviso si falta el .gitignore (sin el, se subiria todo) ---
if not exist ".gitignore" (
    echo [AVISO] No hay .gitignore: se subiria todo, incluidos dist, .build-venv y el JRE.
    echo         Copia el .gitignore del proyecto y vuelve a ejecutar.
    pause
    exit /b 1
)

REM --- Sacar del repo lo que ya estaba subido pero ahora esta ignorado ---
REM     (no borra nada de tu disco, solo deja de rastrearlo en git)
echo Limpiando archivos innecesarios del repositorio...
git rm -r --cached -q --ignore-unmatch dist build .build-venv .build-python312 release vendor/jre config.json AcidModLoader.spec __pycache__ payload/__pycache__ >nul 2>&1

REM --- Anadir cambios y hacer commit ---
git add -A
echo.
echo Resumen de lo que se va a subir:
git diff --cached --shortstat
echo.
git diff --cached --quiet
if errorlevel 1 (
    set "MSG="
    set /p MSG=Mensaje del commit, Enter para usar fecha y hora: 
    if "!MSG!"=="" set "MSG=Actualizacion %date% %time%"
    git commit -m "!MSG!"
) else (
    echo No hay cambios nuevos que commitear.
)

REM --- Subir ---
echo.
echo Subiendo a GitHub...
git push -u origin main
if not errorlevel 1 goto ok

echo.
echo [!] GitHub rechazo el push: el repo remoto tiene commits que no tienes aqui.
echo.
echo   [1] Unir y quedarme con MIS archivos   (seguro, no se pierde historial)
echo   [2] Reemplazar el remoto con lo mio    (borra el historial viejo de main)
echo   [N] Cancelar
echo.
choice /c 12N /n /m "Elige 1, 2 o N: "
if errorlevel 3 goto cancelado
if errorlevel 2 goto forzar

echo.
echo Uniendo historiales...
git fetch origin
git merge -s ours origin/main --allow-unrelated-histories -m "Unir historial remoto (se conservan los archivos locales)"
if errorlevel 1 goto fallo
git push -u origin main
if errorlevel 1 goto fallo
goto ok

:forzar
echo.
echo Reemplazando el remoto con tu version...
git fetch origin
git push -u origin main --force-with-lease
if errorlevel 1 goto fallo
goto ok

:cancelado
echo.
echo Cancelado. No se subio nada.
pause
exit /b 0

:fallo
echo.
echo [ERROR] No se pudo subir. Revisa tu login de GitHub y el mensaje de arriba.
pause
exit /b 1

:ok
echo.
echo Listo, subido correctamente.
pause
