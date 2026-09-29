@echo off
setlocal

rem --- Microsoft Visual C++ Runtime - needed for python312.dll itself to load ---
reg query "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64" /v Installed >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing a required system component (1/2), please wait...
    set "VC_EXE=%TEMP%\vc_redist.x64.exe"
    powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile '%VC_EXE%' -UseBasicParsing } catch { exit 1 }"
    if exist "%VC_EXE%" (
        "%VC_EXE%" /install /quiet /norestart
        del "%VC_EXE%"
    ) else (
        echo Could not download the required component automatically.
        echo Please install it manually from: https://aka.ms/vs/17/release/vc_redist.x64.exe
        pause
    )
)

rem --- Microsoft Edge WebView2 Runtime - needed for the app's window to open ---
set "WV2_KEY=HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
reg query "%WV2_KEY%" /v pv >nul 2>&1
if %errorlevel% neq 0 (
    reg query "HKCU\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv >nul 2>&1
)
if %errorlevel% neq 0 (
    echo Installing a required system component (2/2), please wait...
    set "WV2_EXE=%TEMP%\MicrosoftEdgeWebview2Setup.exe"
    powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile '%WV2_EXE%' -UseBasicParsing } catch { exit 1 }"
    if exist "%WV2_EXE%" (
        "%WV2_EXE%" /silent /install
        del "%WV2_EXE%"
    ) else (
        echo Could not download the required component automatically.
        echo Please install it manually from: https://developer.microsoft.com/microsoft-edge/webview2/
        pause
    )
)

start "" "%~dp0AcidModLoader.exe"
endlocal
