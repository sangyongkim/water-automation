"""
main.py  (v3 - stations 전용)
================================
HEC-1 임계지속기간 자동 산정 시스템

실행:
  python main.py              # 전체 실행
  python main.py --dry-run    # DAT 파일만 생성
  python main.py --parse-only # 기존 OUT 파일 파싱만

흐름:
  1. 관측소별 확률강우량 계산 (강우강도식)
  2. 유역별 Huff 분포 계산 (관측소별 군집 가중 평균)
  3. HEC-1 DAT 파일 생성
  4. HEC-1.exe 실행
  5. OUT 파일 파싱 → 첨두홍수량 추출
  6. 임계지속기간 및 기본홍수량 산정·출력
"""

import os
import sys
import shutil
import argparse

from config import (
    HEC1_EXE, WORK_DIR,
    RETURN_PERIODS, DURATIONS, DT_MIN,
    HUFF_QUARTILE,
    ARF_REGION,
    PROJECT,
)
import config as _cfg
STATIONS = getattr(_cfg, 'STATIONS', {})

from rainfall import (
    calc_rainfall,
    calc_weighted_huff_distribution,
)
from hec1_writer  import write_dat_file
from hec1_runner  import run_all
from hec1_parser  import parse_all_outputs
from reporter     import aggregate, print_critical_summary, save_csv, save_peak_flow_csv

# 결과 폴더: WORK_DIR / project_name / method
_proj_name         = PROJECT.get('name', 'Project').replace(' ', '_').replace('/', '_')
_method            = PROJECT.get('method', 'clark')
EFFECTIVE_WORK_DIR = os.path.join(WORK_DIR, _proj_name, _method)


# ============================================================
# 사전 검증
# ============================================================

def validate_config():
    """설정값 유효성 검사 — main() 호출 전에 실행."""
    errors = []

    # 지속기간이 DT_MIN 배수인지 확인
    bad_durs = [d for d in DURATIONS if d % DT_MIN != 0]
    if bad_durs:
        errors.append(
            f"DURATIONS 중 DT_MIN({DT_MIN}분)의 배수가 아닌 값: {bad_durs}\n"
            f"  → Huff 누가분포 시간간격이 어긋납니다."
        )

    # 유역 단위도 파라미터 검증
    _REQUIRED_PARAMS = {
        'clark':  ('tc', 'r'),
        'snyder': ('tp', 'cp'),
        'scs':    ('lag',),
    }
    for el in PROJECT['network']:
        if el['type'] not in ('basin', 'raw_basin'):
            continue
        method = el.get('method', 'clark').lower()
        params = el.get('params', {})
        required = _REQUIRED_PARAMS.get(method)
        if required is None:
            errors.append(
                f"유역 '{el['name']}': 알 수 없는 단위도 방법 '{method}'. "
                f"지원: clark | snyder | scs"
            )
        else:
            missing_p = [p for p in required if not params.get(p)]
            if missing_p:
                errors.append(
                    f"유역 '{el['name']}' ({method}): "
                    f"파라미터 {missing_p}가 없거나 0입니다."
                )

    # 외부수문곡선 ordinates 검증
    for el in PROJECT['network']:
        if el['type'] == 'hydrograph' and not el.get('ordinates'):
            errors.append(
                f"외부수문곡선 '{el['name']}': ordinates 배열이 비어있습니다.\n"
                f"  → config의 ordinates 또는 엑셀 '외부수문곡선' 시트를 확인하세요."
            )

    # 관측소별 huff_cluster 및 재현기간 계수 검증
    for stn_name, stn_cfg in STATIONS.items():
        if stn_cfg is None:
            continue
        if 'huff_cluster' not in stn_cfg:
            errors.append(
                f"STATIONS['{stn_name}']에 huff_cluster가 없습니다."
            )
        missing = [rp for rp in RETURN_PERIODS if rp not in stn_cfg]
        if missing:
            errors.append(
                f"STATIONS['{stn_name}']에 재현기간 {missing} 계수가 없습니다."
            )

    # 유역별 station_weights 검증
    for el in PROJECT['network']:
        if el['type'] not in ('basin', 'raw_basin'):
            continue
        sw = el.get('station_weights', [])
        if not sw:
            errors.append(
                f"유역 '{el['name']}'의 station_weights가 없습니다.\n"
                f"  → 모든 유역에 관측소별 가중치가 필요합니다."
            )
            continue
        total = sum(w for _, w in sw)
        if abs(total - 1.0) > 0.001:
            errors.append(
                f"유역 '{el['name']}' station_weights 합계 = {total:.4f} "
                f"(1.0 이어야 함)"
            )

    if errors:
        print("\n[오류] 설정 검증 실패:")
        for e in errors:
            print(f"  [!] {e}")
        sys.exit(1)


# ============================================================
# 경로 헬퍼
# ============================================================

def make_paths(work_dir, rp, duration):
    base = f"{rp:03d}-{duration:04d}"
    return (os.path.join(work_dir, f"{base}.DAT"),
            os.path.join(work_dir, f"{base}.OUT"))


# ============================================================
# Step 1+2: 확률강우량 + 유역별 Huff 분포 계산
# ============================================================

def step_rainfall_and_huff() -> dict:
    """
    빈도×지속기간별 관측소 강우량과 유역별 Huff 누가비를 계산합니다.

    Returns
    -------
    dict : {(rp, dur): {'station_rf': {관측소명: mm},
                        'basin_huff': {유역명: [누가비, ...]}}}
    """
    print("\n[Step 1-2] 확률강우량 + 유역별 Huff 분포 계산 (stations 모드)")
    print("-" * 60)
    print(f"  ARF 권역:  {ARF_REGION}")
    print(f"  Huff 분위: {HUFF_QUARTILE}분위  (관측소별 군집번호 사용)")
    print()

    # 유역 목록 (basin / raw_basin 만)
    basin_elements = [
        el for el in PROJECT['network']
        if el['type'] in ('basin', 'raw_basin')
    ]

    table = {}

    for rp in RETURN_PERIODS:
        print(f"  ▶ 재현기간 {rp}년")

        for dur in DURATIONS:
            # 관측소별 지점강우량
            stn_rf = {}
            for stn_name, stn_cfg in STATIONS.items():
                if stn_cfg is None:
                    stn_rf[stn_name] = 0.0
                    continue
                if rp not in stn_cfg:
                    raise KeyError(
                        f"STATIONS['{stn_name}']에 {rp}년 계수가 없습니다."
                    )
                fc = stn_cfg[rp]
                stn_rf[stn_name] = calc_rainfall(fc['formula'], fc['params'], dur)

            # 유역별 Huff 누가분포 (관측소별 군집 가중 평균)
            basin_huff = {}
            for el in basin_elements:
                sw = el.get('station_weights', [])
                basin_huff[el['name']] = calc_weighted_huff_distribution(
                    sw, STATIONS, dur, HUFF_QUARTILE, DT_MIN
                )

            table[(rp, dur)] = {
                'station_rf': stn_rf,
                'basin_huff': basin_huff,
            }

        # 대표 지속기간 샘플 출력
        sample_durs = [DURATIONS[0], DURATIONS[len(DURATIONS) // 2], DURATIONS[-1]]
        for d in sample_durs:
            r = table[(rp, d)]
            rf_strs = "  ".join(
                f"{n}={v:.1f}mm" for n, v in r['station_rf'].items()
                if n.upper() != 'DUMMY'
            )
            print(f"    {d:4d}분: {rf_strs}")

    return table


# ============================================================
# Step 3: DAT 파일 생성
# ============================================================

def step_write_dat(table: dict) -> list:
    print("\n[Step 3] HEC-1 입력파일 생성")
    print("-" * 60)
    os.makedirs(EFFECTIVE_WORK_DIR, exist_ok=True)
    jobs = []

    for rp in RETURN_PERIODS:
        for dur in DURATIONS:
            r        = table[(rp, dur)]
            dat, out = make_paths(EFFECTIVE_WORK_DIR, rp, dur)

            write_dat_file(
                project           = PROJECT,
                station_rainfalls = r['station_rf'],
                basin_huff        = r['basin_huff'],
                duration_min      = dur,
                output_path       = dat,
                dt_min            = DT_MIN,
                return_period     = rp,
            )
            jobs.append({
                'return_period': rp, 'duration': dur,
                'dat': dat, 'out': out,
            })

    print(f"  총 {len(jobs)}개 생성 → {EFFECTIVE_WORK_DIR}")
    return jobs


# ============================================================
# Step 4: HEC-1 실행
# ============================================================

def step_run_hec1(jobs):
    print("\n[Step 4] HEC-1 실행")
    return run_all(HEC1_EXE, jobs)


# ============================================================
# Step 5: 출력파일 파싱
# ============================================================

def step_parse(jobs):
    print("\n[Step 5] 출력파일 파싱")
    print("-" * 60)
    return parse_all_outputs(jobs)


# ============================================================
# Step 6: 결과 집계
# ============================================================

def step_report(records):
    print("\n[Step 6] 결과 집계")
    summary = aggregate(records)
    print_critical_summary(summary)
    csv_path = os.path.join(EFFECTIVE_WORK_DIR, "results.csv")
    save_csv(summary, csv_path, None)
    save_peak_flow_csv(summary, os.path.join(EFFECTIVE_WORK_DIR, 'peak_flow.csv'))
    return summary


def _copy_input_xlsx():
    """input.xlsx를 결과 폴더에 복사하고 파일명을 변경합니다."""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
    else:
        exe_dir = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(exe_dir, 'input.xlsx')
    if not os.path.isfile(src):
        return
    dst_name = f"input_{_proj_name}_{_method}.xlsx"
    dst      = os.path.join(EFFECTIVE_WORK_DIR, dst_name)
    shutil.copy2(src, dst)
    print(f"  input.xlsx 복사 완료: {dst}")


# ============================================================
# 메인
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="HEC-1 임계지속기간 자동 산정 v3")
    parser.add_argument('--dry-run',    action='store_true',
                        help="DAT 파일만 생성, HEC-1 실행 안 함")
    parser.add_argument('--parse-only', action='store_true',
                        help="기존 OUT 파일만 파싱")
    args = parser.parse_args()

    validate_config()

    print("=" * 60)
    print("  HEC-1 임계지속기간 자동 산정 시스템  v3")
    print("=" * 60)
    print(f"  결과폴더: {EFFECTIVE_WORK_DIR}")
    print(f"  빈도:     {RETURN_PERIODS}")
    print(f"  지속기간: {DURATIONS[0]}~{DURATIONS[-1]}분  ({len(DURATIONS)}개)")
    print(f"  계산간격: {DT_MIN}분")
    print(f"  ARF권역:  {ARF_REGION}")
    print(f"  Huff분위: {HUFF_QUARTILE}분위  (관측소별 군집)")

    # Step 1~2: 강우량 + Huff 계산
    table = step_rainfall_and_huff()

    if args.parse_only:
        jobs = []
        for rp in RETURN_PERIODS:
            for dur in DURATIONS:
                dat, out = make_paths(EFFECTIVE_WORK_DIR, rp, dur)
                jobs.append({
                    'return_period': rp, 'duration': dur,
                    'dat': dat, 'out': out,
                    'success': os.path.isfile(out),
                })
    else:
        # Step 3: DAT 생성
        jobs = step_write_dat(table)

        if args.dry_run:
            print("\n[--dry-run] DAT 생성 완료. HEC-1 실행 생략.")
            return

        # Step 4: HEC-1 실행
        jobs = step_run_hec1(jobs)

    # Step 5: 파싱
    records = step_parse(jobs)
    if not records:
        print("\n[오류] 파싱된 데이터가 없습니다.")
        sys.exit(1)

    # Step 6: 결과
    step_report(records)

    # 완료 후 input.xlsx를 결과 폴더로 복사
    _copy_input_xlsx()
    print("\n완료!")


if __name__ == '__main__':
    main()
