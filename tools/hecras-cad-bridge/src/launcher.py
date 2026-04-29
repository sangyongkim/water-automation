"""HEC-RAS CAD Bridge — 통합 실행 메뉴"""
import sys
import os

# Windows 콘솔 UTF-8 출력 설정 (한글 깨짐 방지)
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ──────────────────────────────────────────────────────────
# PyInstaller 번들 실행 시: exe와 같은 폴더의 config.py를 우선 탐색
# ──────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    _exe_dir = os.path.dirname(sys.executable)
    # exe 디렉토리를 sys.path 맨 앞에 추가 (config.py 위치)
    if _exe_dir not in sys.path:
        sys.path.insert(0, _exe_dir)
    # config.py 존재 여부 확인
    if not os.path.exists(os.path.join(_exe_dir, 'config.py')):
        print("=" * 55)
        print("[오류] config.py 파일이 없습니다.")
        print()
        print(f"  exe 파일과 같은 폴더에 config.py를 복사하세요.")
        print(f"  위치: {_exe_dir}")
        print()
        print("  배포 패키지의 config.py를 복사하고")
        print("  실제 HEC-RAS 파일 경로를 수정한 뒤 다시 실행하세요.")
        print("=" * 55)
        input("\nEnter를 눌러 종료합니다...")
        sys.exit(1)

import step0_config
import step1_to_dxf
import step2_to_hecras
import step3_run_hecras
import step4_update_dxf
import check_env


def _run(fn):
    """각 step main() 실행 — SystemExit/예외 처리 포함"""
    try:
        fn()
    except SystemExit:
        pass
    except KeyboardInterrupt:
        print("\n[중단] 사용자가 취소했습니다.")
    except Exception as e:
        print(f"\n[오류] {type(e).__name__}: {e}")
    input("\n계속하려면 Enter를 누르세요...")


def _show_config_summary():
    """현재 config.py 설정 요약 출력"""
    try:
        import config
        print(f"\n  현재 설정 (config.py):")
        prj = config.HECRAS_PROJECT_FILE
        prj_short = prj if len(prj) <= 45 else "..." + prj[-42:]
        print(f"    HEC-RAS 프로젝트: {prj_short}")
        print(f"    DXF 파일        : {config.DXF_FILE}")
        profile_name = getattr(config, 'FLOOD_PROFILE_NAME', '').strip()
        if profile_name:
            print(f"    홍수위 프로파일 : \"{profile_name}\" (이름 지정)")
        else:
            print(f"    홍수위 프로파일 : {config.FLOOD_PROFILE_INDEX}번 (INDEX 지정)")
    except Exception:
        print("\n  [주의] config.py 읽기 실패 — 경로를 확인하세요.")


def main():
    while True:
        print("\n" + "=" * 55)
        print("   HEC-RAS CAD Bridge  v1.0")
        print("=" * 55)
        _show_config_summary()
        print()
        print("   0.  Step 0 — 프로젝트 설정 (경로·프로파일 변경)")
        print()
        print("   1.  Step 1 — HEC-RAS → DXF 생성")
        print("   2.  Step 2 — DXF → HEC-RAS geometry 업데이트")
        print("   3.  Step 3 — HEC-RAS 실행 및 홍수위 추출")
        print("   4.  Step 4 — 홍수위 → DXF 갱신")
        print()
        print("   5.  환경 점검 (패키지/COM/경로 확인)")
        print("   9.  종료")
        print("-" * 55)
        choice = input("   번호를 입력하세요: ").strip()

        if choice == '0':
            step0_config.main()
        elif choice == '1':
            _run(step1_to_dxf.main)
        elif choice == '2':
            _run(step2_to_hecras.main)
        elif choice == '3':
            _run(step3_run_hecras.main)
        elif choice == '4':
            _run(step4_update_dxf.main)
        elif choice == '5':
            _run(check_env.main)
        elif choice == '9':
            print("\n  종료합니다.")
            break
        elif choice == '':
            pass
        else:
            print("  잘못된 입력입니다. 0~5, 9 중에서 선택하세요.")


if __name__ == '__main__':
    main()
