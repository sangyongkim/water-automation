# -*- mode: python ; coding: utf-8 -*-
# HEC-RAS CAD Bridge — PyInstaller 빌드 설정
# PyInstaller 6.x 기준

import sys
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

# pywin32 DLL 경로
_pywin32_dll_dir = os.path.join(sys.prefix, 'lib', 'site-packages', 'pywin32_system32')

# ─── ezdxf 전체 수집 ───────────────────────────────────────
ezdxf_datas, ezdxf_binaries, ezdxf_hiddenimports = collect_all('ezdxf')

# ─── h5py 전체 수집 ────────────────────────────────────────
h5py_datas, h5py_binaries, h5py_hiddenimports = collect_all('h5py')

# ─── pywin32 DLL 수동 추가 ─────────────────────────────────
_win32_dlls = []
if os.path.isdir(_pywin32_dll_dir):
    for dll in os.listdir(_pywin32_dll_dir):
        if dll.endswith('.dll'):
            _win32_dlls.append(
                (os.path.join(_pywin32_dll_dir, dll), '.')
            )

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=ezdxf_binaries + h5py_binaries + _win32_dlls,
    datas=ezdxf_datas + h5py_datas,
    hiddenimports=(
        ezdxf_hiddenimports
        + h5py_hiddenimports
        + [
            'win32com',
            'win32com.client',
            'win32com.client.gencache',
            'win32api',
            'win32con',
            'win32process',
            'pywintypes',
            'pythoncom',
        ]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # config.py 는 exe 옆에 별도 파일로 두어 사용자가 편집할 수 있도록 제외
    excludes=['config'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='hecras_launcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,      # UPX 압축 비활성화 (win32com DLL 호환성)
    console=True,   # 콘솔 창 (input/print 사용)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='hecras_launcher',
)
