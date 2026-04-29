"""
hec1_parser.py
==============
HEC-1 아웃풋 파일(.OUT)에서 RUNOFF SUMMARY 섹션을 파싱하여
지점별 첨두홍수량, 첨두발생시각, 유역면적을 추출합니다.

RUNOFF SUMMARY 칼럼 구조 (고정폭):
  '+' 다음 데이터 라인:
    지점명 뒤 첫 번째 숫자  → PEAK FLOW (m³/s)
    두 번째 숫자            → TIME OF PEAK (hr)
    마지막 숫자             → BASIN AREA (km²)

주의:
  - 저수지(ROUTED TO) 지점은 다음 줄에 STAGE/TIME 정보가 추가로 붙음
    → 반드시 지점명이 있는 첫 번째 '+' 라인만 파싱
  - 잔류유역은 지점명 앞에 'X'가 붙음 (예: XBS000) → 그대로 사용
"""

import os
import re


def parse_peak_flows(filepath: str) -> list[dict]:
    """
    RUNOFF SUMMARY 섹션에서 지점별 [첨두홍수량, 첨두발생시각, 유역면적]을 추출합니다.

    Returns
    -------
    list[dict]
        [{'station': 'BS040', 'peak_flow': 134.99,
          'time_of_peak': 6.83, 'area_km2': 18.40}, ...]
    """
    results = []

    try:
        with open(filepath, 'r', encoding='euc-kr', errors='replace') as f:
            lines = f.readlines()
    except OSError:
        return results

    # RUNOFF SUMMARY 섹션 찾기
    summary_start = -1
    for i, line in enumerate(lines):
        if 'RUNOFF SUMMARY' in line:
            summary_start = i
            break

    if summary_start < 0:
        return results

    # 섹션 내에서 파싱
    # 작업 유형 패턴: HYDROGRAPH AT / ROUTED TO / COMBINED AT 등
    op_pattern = re.compile(
        r'(HYDROGRAPH AT|ROUTED TO|COMBINED AT|PUMPED TO|DIVERTED TO)'
    )
    # 숫자 패턴
    num_pattern = re.compile(r'-?\d+\.\d+')

    i = summary_start
    while i < len(lines):
        line = lines[i]

        # 섹션 종료
        if '1TABLE' in line or 'NORMAL END OF HEC-1' in line:
            break

        # 작업 유형 행 감지
        if op_pattern.search(line):
            # 바로 다음 줄이 '+' 로 시작하는 데이터 행이어야 함
            j = i + 1
            # 빈 줄 건너뜀
            while j < len(lines) and lines[j].strip() == '':
                j += 1

            if j < len(lines) and lines[j].startswith('+'):
                data_line = lines[j]
                # '+' 이후 지점명과 숫자 추출
                after_plus = data_line[1:]
                parts = after_plus.split()

                if not parts:
                    i = j + 1
                    continue

                station = parts[0]
                nums = num_pattern.findall(after_plus)

                # 숫자가 최소 2개 이상이어야 유효
                # 순서: PEAK_FLOW, TIME_OF_PEAK, [6HR, 24HR, 72HR,] BASIN_AREA
                if len(nums) >= 2:
                    peak_flow    = float(nums[0])
                    time_of_peak = float(nums[1])
                    # BASIN_AREA는 마지막 숫자
                    # 단, 저수지처럼 AREA가 없을 수도 있으니 6개 이상일 때만 신뢰
                    area_km2 = float(nums[-1]) if len(nums) >= 6 else None

                    results.append({
                        'station':      station,
                        'peak_flow':    peak_flow,
                        'time_of_peak': time_of_peak,
                        'area_km2':     area_km2,
                    })

                i = j + 1
                continue

        i += 1

    return results


def parse_out_file(filepath: str, return_period: int, duration: int) -> list[dict]:
    """
    단일 OUT 파일을 파싱하고 빈도·지속기간 정보를 함께 반환합니다.
    """
    fname = os.path.basename(filepath)
    peaks = parse_peak_flows(filepath)
    return [
        {**p, 'return_period': return_period,
         'duration': duration, 'source_file': fname}
        for p in peaks
    ]


def parse_all_outputs(jobs: list[dict]) -> list[dict]:
    """
    실행 완료된 전체 작업의 OUT 파일을 파싱합니다.
    """
    all_records = []
    for job in jobs:
        out = job.get('out', '')
        if not os.path.isfile(out):
            continue
        records = parse_out_file(out, job['return_period'], job['duration'])
        all_records.extend(records)
    return all_records