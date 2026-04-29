"""
reporter.py
===========
파싱된 첨두홍수량 레코드를 집계하고
임계지속기간 및 기본홍수량을 산정하여 결과를 출력합니다.
"""

import csv
import os


def aggregate(records: list[dict]) -> dict:
    """
    전체 레코드를 (빈도, 지점)별로 집계하여
    임계지속기간 및 기본홍수량을 산정합니다.

    Returns
    -------
    dict
        key: (return_period, station)
        value: {
            'return_period': int,
            'station': str,
            'records': [{'duration', 'peak_flow', 'time_of_peak', ...}, ...],
            'critical': {'duration': int, 'peak_flow': float, ...},
        }
    """
    grouped = {}

    for rec in records:
        key = (rec['return_period'], rec['station'])
        if key not in grouped:
            grouped[key] = {
                'return_period': rec['return_period'],
                'station':       rec['station'],
                'records':       [],
            }
        grouped[key]['records'].append(rec)

    summary = {}
    for key, group in grouped.items():
        records_sorted = sorted(group['records'], key=lambda r: r['duration'])
        critical = max(group['records'], key=lambda r: r['peak_flow'])
        summary[key] = {
            'return_period': group['return_period'],
            'station':       group['station'],
            'records':       records_sorted,
            'critical':      critical,
        }

    return summary


def print_critical_summary(summary: dict):
    """임계지속기간 행만 추려 콘솔에 출력합니다."""
    if not summary:
        print("\n[결과 없음] 분석 가능한 데이터가 없습니다.")
        return

    sorted_keys = sorted(summary.keys(), key=lambda k: (k[0], k[1]))

    print("\n" + "=" * 72)
    print("  HEC-1 임계지속기간 및 기본홍수량 산정 결과")
    print("=" * 72)
    print(f"  {'빈도(년)':>8}  {'지점':<8}  {'임계지속기간(분)':>16}  "
          f"{'첨두홍수량(m³/s)':>16}  {'첨두발생(hr)':>12}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*16}  {'-'*16}  {'-'*12}")

    current_rp = None
    for key in sorted_keys:
        data  = summary[key]
        crit  = data['critical']
        rp    = data['return_period']
        tpeak = f"{crit['time_of_peak']:.2f}" if crit.get('time_of_peak') else "-"
        if rp != current_rp:
            if current_rp is not None:
                print(f"  {'':>8}  {'':8}")   # 빈도 구분 공백
            current_rp = rp
        print(f"  {rp:>8}  {data['station']:<8}  "
              f"{crit['duration']:>16}  {crit['peak_flow']:>16.2f}  {tpeak:>12}")

    print("=" * 72)


def print_summary(summary: dict, rainfall_table: dict = None):
    """
    집계 결과를 콘솔에 출력합니다.

    Parameters
    ----------
    summary        : aggregate() 반환값
    rainfall_table : {(return_period, duration): rainfall_mm} (선택)
                     확률강우량도 함께 출력하고 싶을 때 사용
    """
    if not summary:
        print("\n[결과 없음] 분석 가능한 데이터가 없습니다.")
        return

    sorted_keys = sorted(summary.keys(), key=lambda k: (k[0], k[1]))

    print("\n" + "=" * 80)
    print("  HEC-1 임계지속기간 및 기본홍수량 산정 결과")
    print("=" * 80)

    current_rp = None
    for key in sorted_keys:
        data     = summary[key]
        rp       = data['return_period']
        station  = data['station']
        records  = data['records']
        critical = data['critical']

        if rp != current_rp:
            print(f"\n▶ 빈도: {rp}년")
            print("-" * 80)
            current_rp = rp

        print(f"\n  ■ 지점: {station}")

        # 헤더
        has_rf = rainfall_table is not None
        if has_rf:
            print(f"  {'지속기간(분)':>12}  {'확률강우량(mm)':>14}  "
                  f"{'첨두홍수량(m³/s)':>16}  {'첨두발생(hr)':>12}  비고")
            print(f"  {'-'*12}  {'-'*14}  {'-'*16}  {'-'*12}  {'-'*8}")
        else:
            print(f"  {'지속기간(분)':>12}  {'첨두홍수량(m³/s)':>16}  "
                  f"{'첨두발생(hr)':>12}  비고")
            print(f"  {'-'*12}  {'-'*16}  {'-'*12}  {'-'*8}")

        for rec in records:
            is_crit = (rec['duration'] == critical['duration'])
            marker  = "◀ 임계" if is_crit else ""
            tpeak   = f"{rec['time_of_peak']:.2f}" if rec['time_of_peak'] else "-"

            if has_rf:
                rf = rainfall_table.get((rp, rec['duration']), 0.0)
                print(f"  {rec['duration']:>12}  {rf:>14.1f}  "
                      f"{rec['peak_flow']:>16.2f}  {tpeak:>12}  {marker}")
            else:
                print(f"  {rec['duration']:>12}  "
                      f"{rec['peak_flow']:>16.2f}  {tpeak:>12}  {marker}")

        print(f"\n  ★ 임계지속기간: {critical['duration']}분  |  "
              f"기본홍수량: {critical['peak_flow']:.2f} m³/s")

    print("\n" + "=" * 80)


def save_csv(
    summary: dict,
    output_path: str,
    rainfall_table: dict = None,
):
    """
    결과를 CSV 파일로 저장합니다.

    Parameters
    ----------
    summary        : aggregate() 반환값
    output_path    : 저장 경로
    rainfall_table : {(return_period, duration): rainfall_mm} (선택)
    """
    rows = []
    for key, data in summary.items():
        rp      = data['return_period']
        station = data['station']
        crit_dur = data['critical']['duration']

        for rec in data['records']:
            row = {
                '빈도(년)':          rp,
                '지점':             station,
                '지속기간(분)':      rec['duration'],
                '첨두홍수량(m³/s)':  rec['peak_flow'],
                '첨두발생시각(hr)':  rec.get('time_of_peak', ''),
                '임계지속기간':      'Y' if rec['duration'] == crit_dur else 'N',
            }
            if rainfall_table:
                row['확률강우량(mm)'] = rainfall_table.get((rp, rec['duration']), '')
            row['소스파일'] = rec.get('source_file', '')
            rows.append(row)

    if not rows:
        print("  [경고] 저장할 데이터가 없습니다.")
        return

    rows.sort(key=lambda r: (r['빈도(년)'], r['지점'], r['지속기간(분)']))

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n  CSV 저장 완료: {output_path}")


def save_peak_flow_csv(summary: dict, output_path: str):
    """
    각 지점별 임계지속기간 데이터만 추출하여 요약 CSV로 저장합니다.
    """
    rows = []
    # summary는 (빈도, 지점)을 키로 가집니다.
    for key, data in summary.items():
        crit = data['critical']
        rows.append({
            '빈도(년)': data['return_period'],
            '지점': data['station'],
            '임계지속기간(분)': crit['duration'],
            '첨두홍수량(m³/s)': crit['peak_flow'],
            '첨두발생시각(hr)': crit.get('time_of_peak', ''),
            '유역면적(km2)': crit.get('area_km2', '')
        })

    if not rows:
        return

    # 빈도순, 지점순 정렬
    rows.sort(key=lambda r: (r['빈도(년)'], r['지점']))

    headers = ['빈도(년)', '지점', '임계지속기간(분)', '첨두홍수량(m³/s)', '첨두발생시각(hr)', '유역면적(km2)']
    
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"  [완료] 요약 결과 저장됨: {os.path.basename(output_path)}")