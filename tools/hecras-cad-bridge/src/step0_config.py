"""Step 0: 프로젝트 설정 — 자주 바뀌는 경로와 프로파일을 대화형으로 수정"""
import importlib
import os
import re
import sys


# ──────────────────────────────────────────────────────
# config.py 파일 경로 결정
# ──────────────────────────────────────────────────────

def _cfg_path() -> str:
    """exe 번들이면 exe 폴더, 아니면 현재 스크립트 폴더의 config.py"""
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), 'config.py')
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.py')


# ──────────────────────────────────────────────────────
# config.py 텍스트 조작 헬퍼
# ──────────────────────────────────────────────────────

def _read(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _write(path: str, text: str) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def _set_str(text: str, var: str, value: str) -> str:
    """VAR = r"..." 또는 VAR = "..." 줄을 새 값으로 교체. 후행 주석은 보존."""
    pattern = r'^(' + re.escape(var) + r'\s*=\s*)r?"[^"]*"'
    if value:
        repl = lambda m: m.group(1) + 'r"' + value + '"'
    else:
        repl = lambda m: m.group(1) + '""'
    return re.sub(pattern, repl, text, flags=re.MULTILINE)


def _set_int(text: str, var: str, value: int) -> str:
    """VAR = 숫자 줄을 새 값으로 교체."""
    pattern = r'^(' + re.escape(var) + r'\s*=\s*)\d+'
    return re.sub(pattern, lambda m: m.group(1) + str(value), text, flags=re.MULTILINE)


def _reload():
    """config 모듈을 디스크에서 다시 읽어 반환."""
    import config
    importlib.reload(config)
    return config


# ──────────────────────────────────────────────────────
# 경로 자동 제안
# ──────────────────────────────────────────────────────

def _suggest_geo(prj: str) -> str:
    """프로젝트 파일(.prj) 기준으로 geometry 파일(.g0x) 자동 탐색."""
    base = os.path.splitext(prj)[0]
    for ext in ('.g01', '.g02', '.g03', '.g04', '.g05'):
        if os.path.exists(base + ext):
            return base + ext
    return base + '.g01'


def _suggest_hdf(prj: str) -> str:
    """프로젝트 파일(.prj) 기준으로 HDF 결과 파일(.p0x.hdf) 자동 탐색."""
    base = os.path.splitext(prj)[0]
    for ext in ('.p01.hdf', '.p02.hdf', '.p03.hdf', '.p04.hdf', '.p05.hdf'):
        if os.path.exists(base + ext):
            return base + ext
    return base + '.p01.hdf'


# ──────────────────────────────────────────────────────
# UI 헬퍼
# ──────────────────────────────────────────────────────

def _ask(label: str, current: str) -> str:
    """값 입력. 빈 줄이면 현재값 유지. 앞뒤 따옴표 자동 제거."""
    disp = ('...' + current[-47:]) if len(current) > 50 else current
    print(f"  {label}")
    print(f"    현재값: {disp}")
    raw = input("    새 값  (Enter=유지): ").strip().strip('"\'')
    return raw or current


def _show(cfg) -> None:
    profile_name = getattr(cfg, 'FLOOD_PROFILE_NAME', '').strip()
    prj = cfg.HECRAS_PROJECT_FILE
    dxf = cfg.DXF_FILE
    prj_s = ('...' + prj[-42:]) if len(prj) > 45 else prj
    dxf_s = ('...' + dxf[-42:]) if len(dxf) > 45 else dxf

    print(f"\n  현재 설정:")
    print(f"  ① HEC-RAS  : {prj_s}")
    print(f"  ② DXF 파일 : {dxf_s}")
    if profile_name:
        print(f'  ③ 프로파일 : "{profile_name}" (이름 지정)')
    else:
        print(f"  ③ 프로파일 : {cfg.FLOOD_PROFILE_INDEX}번 (INDEX 지정)")


# ──────────────────────────────────────────────────────
# 각 항목 편집
# ──────────────────────────────────────────────────────

def _edit_hecras(cfg_path: str) -> None:
    cfg = _reload()
    print("\n  ── HEC-RAS 파일 설정 ──\n")

    prj = _ask("[1/3] HEC-RAS 프로젝트 파일 (.prj)", cfg.HECRAS_PROJECT_FILE)

    if prj != cfg.HECRAS_PROJECT_FILE:
        # 프로젝트가 바뀌면 geometry / HDF 자동 탐색
        geo_default = _suggest_geo(prj)
        hdf_default = _suggest_hdf(prj)
        found_geo = os.path.basename(geo_default) if os.path.exists(geo_default) else '파일 없음 — 직접 입력'
        found_hdf = os.path.basename(hdf_default) if os.path.exists(hdf_default) else '파일 없음 — 직접 입력'
        print(f"\n  → 자동 탐색 결과: geometry={found_geo} / HDF={found_hdf}")
    else:
        geo_default = cfg.HECRAS_GEOMETRY_FILE
        hdf_default = cfg.HECRAS_HDF_FILE

    print()
    geo = _ask("[2/3] Geometry 파일 (.g0x)", geo_default)
    print()
    hdf = _ask("[3/3] HDF 결과 파일 (.p0x.hdf)", hdf_default)

    text = _read(cfg_path)
    text = _set_str(text, 'HECRAS_PROJECT_FILE', prj)
    text = _set_str(text, 'HECRAS_GEOMETRY_FILE', geo)
    text = _set_str(text, 'HECRAS_HDF_FILE', hdf)
    _write(cfg_path, text)
    _reload()
    print("\n  [저장 완료]")


def _edit_dxf(cfg_path: str) -> None:
    cfg = _reload()
    print("\n  ── DXF 파일 설정 ──\n")

    dxf = _ask("DXF 파일 경로 (.dxf)", cfg.DXF_FILE)

    base   = os.path.splitext(dxf)[0]
    folder = os.path.dirname(dxf) or '.'
    panel  = base + '_panels.json'
    wse    = os.path.join(folder, 'wse_results.json')

    text = _read(cfg_path)
    text = _set_str(text, 'DXF_FILE', dxf)
    text = _set_str(text, 'PANEL_META', panel)
    text = _set_str(text, 'WSE_JSON_FILE', wse)
    _write(cfg_path, text)
    _reload()
    print(f"\n  [저장 완료]")
    print(f"    PANEL_META    → {os.path.basename(panel)}  (DXF와 같은 폴더)")
    print(f"    WSE_JSON_FILE → {os.path.basename(wse)}  (DXF와 같은 폴더)")


def _edit_profile(cfg_path: str) -> None:
    cfg = _reload()
    profile_name = getattr(cfg, 'FLOOD_PROFILE_NAME', '').strip()

    print("\n  ── 홍수위 프로파일 설정 ──\n")
    if profile_name:
        print(f'  현재: 이름 "{profile_name}" 지정')
    else:
        print(f"  현재: {cfg.FLOOD_PROFILE_INDEX}번 INDEX 지정")

    print()
    print("  이름 입력  → 해당 이름의 프로파일 사용  (예: 200yr, 100년빈도, PF 1)")
    print("  숫자 입력  → 해당 번호의 프로파일 사용  (1부터 시작)")
    print("  Enter     → 현재 설정 유지")
    print()
    print("  ※ 프로파일 이름 확인 방법:")
    print("    · HEC-RAS → Edit → Steady Flow Data → 상단 Profile Names 목록")
    print("    · 또는 Step 3 실행 시 '사용 가능한 프로파일' 목록에서 확인")

    val = input("\n  프로파일 이름 또는 번호: ").strip()
    if not val:
        return

    text = _read(cfg_path)
    if val.isdigit():
        text = _set_str(text, 'FLOOD_PROFILE_NAME', '')
        text = _set_int(text, 'FLOOD_PROFILE_INDEX', int(val))
        print(f"  → {val}번 INDEX 설정")
    else:
        text = _set_str(text, 'FLOOD_PROFILE_NAME', val)
        print(f'  → 이름 "{val}" 설정')
    _write(cfg_path, text)
    _reload()
    print("  [저장 완료]")


# ──────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────

def main() -> None:
    cfg_path = _cfg_path()
    if not os.path.exists(cfg_path):
        print(f"[오류] config.py 파일 없음: {cfg_path}")
        return

    while True:
        cfg = _reload()

        print("\n" + "=" * 50)
        print("Step 0: 프로젝트 설정")
        print("=" * 50)
        _show(cfg)
        print()
        print("  1.  HEC-RAS 파일 경로 변경")
        print("  2.  DXF 파일 경로 변경")
        print("  3.  홍수위 프로파일 변경")
        print("  0.  메인 메뉴로 돌아가기")
        print("-" * 50)
        choice = input("  번호를 입력하세요: ").strip()

        if choice == '0' or choice == '':
            break
        elif choice == '1':
            _edit_hecras(cfg_path)
        elif choice == '2':
            _edit_dxf(cfg_path)
        elif choice == '3':
            _edit_profile(cfg_path)
        else:
            print("  잘못된 입력입니다.")


if __name__ == '__main__':
    main()
