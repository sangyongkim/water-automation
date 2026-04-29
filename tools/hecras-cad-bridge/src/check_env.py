"""
환경 점검 스크립트
==================
Step 1~4를 실행하기 전에 이 스크립트를 먼저 실행하여
필수 패키지 및 HEC-RAS COM 등록 여부를 확인합니다.

실행: python check_env.py
"""

import sys
import os
import platform


def _ok(msg):  print(f"  [OK]  {msg}")
def _warn(msg): print(f"  [!]   {msg}")
def _fail(msg): print(f"  [실패] {msg}")


def check_python():
    print("\n[1] Python 버전")
    v = sys.version_info
    ver_str = f"{v.major}.{v.minor}.{v.micro}"
    if v.major == 3 and v.minor >= 9:
        _ok(f"Python {ver_str}")
    else:
        _fail(f"Python {ver_str} — 3.9 이상 필요")


def check_packages():
    print("\n[2] 필수 패키지")
    packages = {
        "ezdxf":   "DXF 읽기/쓰기",
        "h5py":    "HEC-RAS HDF5 결과 읽기",
        "win32com": "HEC-RAS COM 자동화 (pywin32)",
    }
    for pkg, desc in packages.items():
        try:
            if pkg == "win32com":
                import win32com.client  # noqa
            else:
                __import__(pkg)
            _ok(f"{pkg}  ({desc})")
        except ImportError:
            if pkg == "h5py":
                _warn(f"{pkg} 없음 ({desc}) — HDF5 대안 모드 사용 불가 (COM 모드는 영향 없음)")
            else:
                _fail(f"{pkg} 없음 ({desc}) — pip install -r requirements.txt 실행 필요")


def check_hecras_com():
    print("\n[3] HEC-RAS COM 등록 확인")
    try:
        import winreg
    except ImportError:
        _warn("winreg 없음 — Windows 전용 확인 항목 건너뜀")
        return

    known_ids = [
        "RAS506.HECRASController",
        "RAS507.HECRASController",
        "RAS66.HECRASController",
        "RAS5.HECRASController",
    ]
    found = []
    for com_id in known_ids:
        try:
            winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           f"SOFTWARE\\Classes\\{com_id}")
            found.append(com_id)
            _ok(f"등록됨: {com_id}")
        except FileNotFoundError:
            pass

    if not found:
        _fail("HEC-RAS COM이 등록되어 있지 않습니다.")
        print("       HEC-RAS 5.x 또는 6.x 를 설치하세요.")
        print("       설치 후 Step 3는 COM 모드 대신 HDF5 대안 모드로도 동작합니다.")
    else:
        print(f"  → config.py 의 HECRAS_COM_ID 를 위 값 중 하나로 설정하세요.")


def check_config():
    print("\n[4] config.py 경로 확인")
    try:
        import config
    except ImportError:
        _fail("config.py 를 읽을 수 없습니다. 같은 폴더에 있는지 확인하세요.")
        return

    paths = [
        ("HECRAS_PROJECT_FILE",  config.HECRAS_PROJECT_FILE),
        ("HECRAS_GEOMETRY_FILE", config.HECRAS_GEOMETRY_FILE),
        ("HECRAS_HDF_FILE",      config.HECRAS_HDF_FILE),
        ("HECRAS_EXE",           config.HECRAS_EXE),
    ]
    placeholder_parts = ["프로젝트", "프로젝트명", r"C:\프로젝트"]

    for name, path in paths:
        if any(p in path for p in placeholder_parts):
            _warn(f"{name} = {path!r}  ← 아직 기본값입니다. config.py를 수정하세요.")
        elif name == "HECRAS_HDF_FILE":
            # HDF 파일은 계산 전에 없을 수 있음
            if os.path.exists(path):
                _ok(f"{name} 존재: {path}")
            else:
                _warn(f"{name} 아직 없음 (HEC-RAS 계산 전 정상): {path}")
        else:
            if os.path.exists(path):
                _ok(f"{name} 존재: {path}")
            else:
                _fail(f"{name} 없음: {path}")

    # DXF/dwg 폴더
    dxf_dir = os.path.dirname(config.DXF_FILE)
    if os.path.isdir(dxf_dir):
        _ok(f"DXF 폴더 존재: {dxf_dir}")
    else:
        _warn(f"DXF 폴더 없음: {dxf_dir}  (Step 1 실행 시 자동 생성됩니다)")


def main():
    print("=" * 55)
    print("  HEC-RAS CAD Bridge — 환경 점검")
    print("=" * 55)
    print(f"  OS      : {platform.system()} {platform.release()}")
    print(f"  Python  : {sys.executable}")

    check_python()
    check_packages()
    check_hecras_com()
    check_config()

    print("\n" + "=" * 55)
    print("  점검 완료. [실패] 항목을 모두 해결한 뒤 실행하세요.")
    print("=" * 55)


if __name__ == "__main__":
    main()
