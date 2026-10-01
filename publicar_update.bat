@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ========================================
echo   Publicar actualizacion (payload)
echo ========================================
echo.
echo Tip: corre antes subir_a_github.bat para que el codigo fuente quede subido.
echo.

set /p VER=Version nueva (ej. 1.1.0): 
if "!VER!"=="" (
    echo Version vacia, cancelado.
    pause
    exit /b 1
)
set /p NOTES=Notas del cambio (se muestran en el boton Updates): 

python build_payload.py "!VER!" "!NOTES!"
if errorlevel 1 (
    echo [ERROR] No se pudo generar el payload.
    pause
    exit /b 1
)

where gh >nul 2>&1
if errorlevel 1 (
    echo.
    echo GitHub CLI ^(gh^) no esta instalado. Sube a mano en
    echo   https://github.com/azu42968-maker/acidmodloader/releases/new
    echo con tag v!VER! y estos dos archivos de la carpeta release\:
    echo   payload.zip  y  manifest.json
    pause
    exit /b 0
)

gh release create "v!VER!" release\payload.zip release\manifest.json --title "v!VER!" --notes "!NOTES!" --repo azu42968-maker/acidmodloader
if errorlevel 1 (
    echo [ERROR] Fallo la creacion del release. Revisa "gh auth status".
    pause
    exit /b 1
)

echo.
echo Listo: los usuarios veran el aviso en el boton Updates.
pause
