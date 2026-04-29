"""
Step 3: HEC-RAS 실행 및 홍수위 추출
=====================================
HEC-RAS COM 컨트롤러로 현재 계획(plan)을 실행하고
각 횡단면의 홍수위(WSE)를 wse_results.json에 저장합니다.

실행: python step3_run_hecras.py

요구사항:
  - HEC-RAS 5.x가 설치되어 있어야 합니다.
  - pywin32 패키지가 필요합니다.
  - COM 서버가 등록되어 있어야 합니다 (HEC-RAS 설치 시 자동 등록).
"""

import json
import os
import sys

import config
import utils


_KNOWN_COM_IDS = [
    "RAS66.HECRASController",
    "RAS506.HECRASController",
    "RAS507.HECRASController",
    "RAS5.HECRASController",
]


def _dispatch_hecras():
    """config.HECRAS_COM_ID 우선, 실패 시 알려진 COM ID 순서로 자동 시도."""
    import win32com.client
    candidates = [config.HECRAS_COM_ID] + [
        c for c in _KNOWN_COM_IDS if c != config.HECRAS_COM_ID
    ]
    last_err = None
    for com_id in candidates:
        try:
            rc = win32com.client.Dispatch(com_id)
            print(f"  COM 연결 성공: {com_id}")
            return rc
        except Exception as e:
            last_err = e
    raise RuntimeError(
        f"사용 가능한 HEC-RAS COM ID를 찾지 못했습니다.\n"
        f"마지막 오류: {last_err}\n"
        f"시도한 ID: {candidates}"
    )


def _list_profiles_com(rc) -> list:
    """COM에서 프로파일 이름 목록 반환. COM 실패 시 HDF5 파일에서 재시도."""
    try:
        result = rc.Output_GetProfiles(0)
        n = result[0]
        if n > 0:
            return [str(result[1][i]) for i in range(n)]
    except Exception:
        pass

    # COM에서 못 읽었으면 HDF5 파일에서 읽기 (계산 완료 후 업데이트됨)
    try:
        if os.path.exists(config.HECRAS_HDF_FILE):
            names = utils.read_profile_names_from_hdf(config.HECRAS_HDF_FILE)
            if names:
                print("  (프로파일 목록: HDF5 파일에서 읽음)")
                return names
    except Exception:
        pass

    return []


def _resolve_profile(names: list) -> tuple:
    """
    config 설정에 따라 사용할 프로파일 (1-based 인덱스, 이름) 반환.
    names: COM 또는 HDF5에서 가져온 프로파일 이름 목록 (없으면 빈 리스트)
    """
    if names:
        print(f"  사용 가능한 프로파일 ({len(names)}개):")
        for i, n in enumerate(names, 1):
            print(f"    {i}. {n}")

    name_cfg = getattr(config, 'FLOOD_PROFILE_NAME', '').strip()
    if name_cfg and names:
        norm = name_cfg.replace(' ', '').lower()
        # 완전 일치 우선
        for i, name in enumerate(names, 1):
            if name.strip().replace(' ', '').lower() == norm:
                print(f"  선택된 프로파일: [{i}] {name}")
                return i, name
        # 부분 일치 차선
        for i, name in enumerate(names, 1):
            if norm in name.strip().replace(' ', '').lower():
                print(f"  선택된 프로파일 (부분 일치): [{i}] {name}")
                return i, name
        print(f"  [경고] 프로파일 '{name_cfg}'을 찾을 수 없음 — "
              f"INDEX {config.FLOOD_PROFILE_INDEX} 사용")

    idx = config.FLOOD_PROFILE_INDEX
    name = names[idx - 1] if names and 1 <= idx <= len(names) else f"Profile {idx}"
    print(f"  선택된 프로파일: [{idx}] {name}")
    return idx, name


class _ComComputedError(Exception):
    """COM으로 계산은 완료됐으나 WSE 추출에 실패한 경우."""
    pass


def run_via_com(project_file: str) -> tuple:
    """HEC-RAS RASController COM으로 실행 후 (wse_dict, profile_name) 반환."""
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        raise ImportError("pywin32 패키지를 설치하세요: pip install pywin32")

    print(f"  HEC-RAS COM 초기화 ({config.HECRAS_COM_ID})...")
    rc = _dispatch_hecras()

    print(f"  프로젝트 열기: {project_file}")
    rc.Project_Open(project_file)

    computed = False
    try:
        print("  계획 실행 중... (HEC-RAS 창이 열릴 수 있습니다)")
        rc.Compute_CurrentPlan(None, None, True)
        computed = True
        print("  실행 완료")

        # 프로파일 선택
        print("\n  프로파일 조회 중...")
        profile_names = _list_profiles_com(rc)
        profile_idx, profile_name = _resolve_profile(profile_names)

        # 홍수위 추출
        # Output_NodeOutput은 문자열 이름이 아닌 1-based 정수 인덱스를 요구함:
        #   Function Output_NodeOutput(nRiver As Long, nReach As Long, nNode As Long, ...)
        # Output_GetReaches / Output_GetNodes는 문자열 이름을 받으므로 둘 다 추적
        wse_dict = {}
        rivers_result = rc.Output_GetRivers(0)
        n_rivers = rivers_result[0]
        river_names = list(rivers_result[1]) if n_rivers > 0 else []

        for ri, river in enumerate(river_names, 1):          # ri: 1-based 인덱스
            reaches_result = rc.Output_GetReaches(river, 0)
            n_reaches = reaches_result[0]
            reach_names = list(reaches_result[1]) if n_reaches > 0 else []

            for rci, reach in enumerate(reach_names, 1):     # rci: 1-based 인덱스
                nodes_result = rc.Output_GetNodes(river, reach, 0)
                n_nodes = nodes_result[0]
                node_ids = list(nodes_result[1]) if n_nodes > 0 else []

                for ni, node_id in enumerate(node_ids, 1):   # ni: 1-based 인덱스
                    try:
                        val = rc.Output_NodeOutput(
                            ri,           # river 정수 인덱스 (1-based)
                            rci,          # reach 정수 인덱스 (1-based)
                            ni,           # node  정수 인덱스 (1-based)
                            True,         # bIsXS=True (횡단면)
                            profile_idx,  # 1-based 프로파일 번호
                            0             # 0 = WSE
                        )
                        wse = float(val[0]) if isinstance(val, (list, tuple)) else float(val)
                        key = f"{river.strip()}|{reach.strip()}|{node_id.strip()}"
                        wse_dict[key] = wse
                    except Exception as e:
                        print(f"    [주의] WSE 읽기 실패 {river}/{reach}/{node_id}: {e}")

        return wse_dict, profile_name

    except Exception as exc:
        if computed:
            raise _ComComputedError(str(exc)) from exc
        raise
    finally:
        try:
            rc.Project_Close()
        except Exception:
            pass


def run_via_hdf(project_file: str, skip_run: bool = False) -> tuple:
    """HEC-RAS 실행 후 HDF5에서 홍수위 읽기 (COM 대안). (wse_dict, profile_name) 반환."""
    import subprocess

    if skip_run:
        print("  [대안 모드] COM 계산 완료 — HDF5에서 직접 읽습니다.")
    else:
        print("  [대안 모드] HEC-RAS를 직접 실행합니다...")
        print(f"  프로젝트: {project_file}")

        try:
            # HEC-RAS 커맨드라인 파서는 프로젝트 경로가 반드시 따옴표로 감싸져야 함
            # subprocess 리스트 방식은 공백 없는 경로에 따옴표를 붙이지 않아 오류 발생
            # 문자열로 직접 전달하면 CreateProcessW가 따옴표를 그대로 유지함
            cmdline = '"{}" "{}"'.format(config.HECRAS_EXE, project_file)
            subprocess.Popen(cmdline)
            print("  HEC-RAS가 열렸습니다. 계산을 실행한 후 이 창으로 돌아오세요.")
            input("  HEC-RAS 계산이 완료되면 Enter를 누르세요...")
        except FileNotFoundError:
            print(f"  [경고] HEC-RAS 실행 파일 없음: {config.HECRAS_EXE}")
            print("  HEC-RAS를 수동으로 실행하고 계산을 완료한 후 Enter를 누르세요.")
            input("  Enter를 누르세요...")

    if not os.path.exists(config.HECRAS_HDF_FILE):
        raise FileNotFoundError(
            f"HDF5 결과 파일 없음: {config.HECRAS_HDF_FILE}\n"
            "HEC-RAS 계산 완료 후 다시 실행하세요."
        )

    # 프로파일 선택
    print(f"\n  프로파일 조회 중: {config.HECRAS_HDF_FILE}")
    profile_names = utils.read_profile_names_from_hdf(config.HECRAS_HDF_FILE)
    profile_idx_1, profile_name = _resolve_profile(profile_names)

    print(f"  HDF5 결과 읽는 중: {config.HECRAS_HDF_FILE}")
    xs_list = utils.parse_geometry(config.HECRAS_GEOMETRY_FILE)
    wse_dict = utils.read_wse_from_hdf(
        config.HECRAS_HDF_FILE,
        profile_idx_1 - 1,   # 0-based
        xs_list
    )
    return wse_dict, profile_name


def main():
    print("=" * 50)
    print("Step 3: HEC-RAS 실행 및 홍수위 추출")
    print("=" * 50)

    if not os.path.exists(config.HECRAS_PROJECT_FILE):
        print(f"[오류] 프로젝트 파일 없음: {config.HECRAS_PROJECT_FILE}")
        sys.exit(1)

    # COM 방식 시도, 실패하면 HDF5 방식으로 전환
    print("\nCOM 방식으로 실행 시도...")
    try:
        wse_dict, profile_name = run_via_com(config.HECRAS_PROJECT_FILE)
        print(f"  {len(wse_dict)}개 단면 홍수위 추출 완료 (COM)")
    except ImportError as e:
        print(f"  COM 실패: {e}")
        print("  → HDF5 방식으로 전환합니다.")
        wse_dict, profile_name = run_via_hdf(config.HECRAS_PROJECT_FILE)
    except _ComComputedError as e:
        print(f"  COM WSE 추출 실패: {e}")
        print("  → HEC-RAS는 이미 실행됨 — HDF5에서 직접 읽습니다.")
        wse_dict, profile_name = run_via_hdf(config.HECRAS_PROJECT_FILE, skip_run=True)
    except Exception as e:
        print(f"  COM 실패: {e}")
        print("  → HDF5 방식으로 전환합니다.")
        wse_dict, profile_name = run_via_hdf(config.HECRAS_PROJECT_FILE)

    if not wse_dict:
        print("[오류] 홍수위를 추출하지 못했습니다.")
        sys.exit(1)

    # WSE 결과 저장 (메타데이터 포함)
    output = {
        '_profile': profile_name,
        '_profile_index': config.FLOOD_PROFILE_INDEX,
    }
    output.update(wse_dict)
    with open(config.WSE_JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n홍수위 결과  (프로파일: {profile_name}):")
    for key, wse in wse_dict.items():
        print(f"  {key}: EL.{wse:.3f}")

    print(f"\n[완료] WSE 저장: {config.WSE_JSON_FILE}")
    print("  Step 4 (DXF 홍수위 업데이트)를 실행하세요.")


if __name__ == '__main__':
    main()
