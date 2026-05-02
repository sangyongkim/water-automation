# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

# pandas / numpy 전체 수집 (숨겨진 의존성 포함)
datas,    binaries,    hiddenimports    = collect_all('pandas')
d2, b2, h2 = collect_all('numpy')
datas        += d2
binaries     += b2
hiddenimports += h2

a = Analysis(
    ['hecras_geo.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='hecras_geo',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='hecras_geo',
)
