# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/josef/Videos/Proyects/AcidModinstaller/main.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/josef/Videos/Proyects/AcidModinstaller/vendor', 'vendor'), ('C:/Users/josef/Videos/Proyects/AcidModinstaller/modloader_inject.js', '.'), ('C:/Users/josef/Videos/Proyects/AcidModinstaller/gamebanana_inject.js', '.'), ('C:/Users/josef/Videos/Proyects/AcidModinstaller/modmanager_inject.js', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AcidModLoader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:/Users/josef/Videos/Proyects/AcidModinstaller/icon.ico'],
)
