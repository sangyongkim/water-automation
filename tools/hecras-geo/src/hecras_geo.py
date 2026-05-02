#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
HEC-RAS 횡단면 지형데이터 생성 자동화
측량 횡단 야장(CSV) → HEC-RAS Geometry 파일(.g01)

사용 예)
  # 거리형 측점 (기본)
  python hecras_geo.py fieldbook.csv --river 테스트하천 --reach Reach1

  # No형 측점 (정측점 간격 50m)
  python hecras_geo.py fieldbook.csv --river 테스트하천 --reach Reach1 --type no --spacing 50

* .prj (프로젝트 파일)은 HEC-RAS에서 직접 생성하세요:
  File > New Project → Geom File 로 생성된 .g01 추가
"""

import math
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Windows 콘솔 한글 출력 보정
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


MANNINGS_N   = 0.032   # 전체 횡단면 고정
LEVEE_MARGIN = 5.0     # 제방 여유고(m)


# ─────────────────────────────────────────────────────────
# 1. 입력 처리 모듈
# ─────────────────────────────────────────────────────────

def parse_fieldbook(csv_path: str) -> pd.DataFrame:
    """
    횡단 야장 CSV 파싱.
    - 측점 컬럼 forward-fill (첫 행에만 측점 기재된 형식 처리)
    - 수치 변환 및 필수 결측 제거
    """
    for enc in ('utf-8-sig', 'cp949', 'utf-8'):
        try:
            df = pd.read_csv(csv_path, header=0, dtype=str, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"파일 인코딩을 인식할 수 없습니다: {csv_path}")

    if df.shape[1] < 4:
        raise ValueError("CSV 컬럼 수 부족 (최소 4열 필요: 측점, 거리, 표고, 제방)")

    if df.shape[1] >= 5:
        df.columns = ['station', 'offset', 'elevation', 'bank', 'structure']
    else:
        df.columns = ['station', 'offset', 'elevation', 'bank']
        df['structure'] = ''

    df['station'] = (
        df['station']
        .replace(r'^\s*$', np.nan, regex=True)
        .ffill()
    )

    for col in ('station', 'offset', 'elevation'):
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['bank'] = pd.to_numeric(df['bank'], errors='coerce')
    df['structure'] = df['structure'].fillna('').str.strip()

    df = df.dropna(subset=['station', 'offset', 'elevation']).reset_index(drop=True)

    if df.empty:
        raise ValueError("유효한 데이터가 없습니다.")

    return df


# ─────────────────────────────────────────────────────────
# 2. 횡단면 생성 모듈
# ─────────────────────────────────────────────────────────

def _no_type_position(station: float, spacing: float) -> float:
    """
    No형 측점을 절대 거리(m)로 변환.
    정수부 × 정측점간격 + 소수부 × 1000
    예) No.2+40 → 2.04, spacing=50  →  2×50 + 0.04×1000 = 140m
    """
    n = math.floor(station)
    return n * spacing + (station - n) * 1000.0


def _calc_reach_length(prev: float, curr: float,
                        mode: str, spacing: float) -> float:
    """두 인접 측점 사이의 Reach Length(m) 계산."""
    if mode == 'distance':
        return (curr - prev) * 1000.0
    return _no_type_position(curr, spacing) - _no_type_position(prev, spacing)


def build_cross_sections(df: pd.DataFrame,
                          station_type: str = 'distance',
                          spacing: float = 0.0) -> list:
    """
    DataFrame → CrossSection 딕셔너리 목록.
    정렬: 측점 오름차순(하류 → 상류).
    """
    result = []
    for stn in sorted(df['station'].unique()):
        grp = df[df['station'] == stn]

        if len(grp) < 2:
            print(f"  [SKIP] 측점 {stn}: 포인트 수 부족 ({len(grp)}개)")
            continue

        lb_rows = grp[grp['bank'] == 1]
        rb_rows = grp[grp['bank'] == 2]
        if lb_rows.empty or rb_rows.empty:
            print(f"  [SKIP] 측점 {stn}: 좌안(1) 또는 우안(2) Bank Station 누락")
            continue

        lb_off  = float(lb_rows.iloc[0]['offset'])
        rb_off  = float(rb_rows.iloc[0]['offset'])
        lb_elev = float(lb_rows.iloc[0]['elevation'])
        rb_elev = float(rb_rows.iloc[0]['elevation'])

        if lb_off >= rb_off:
            print(f"  [WARN] 측점 {stn}: 좌안({lb_off}) ≥ 우안({rb_off}) — 확인 필요")

        sv = grp[grp['structure'] != '']['structure']
        structure = sv.iloc[0] if not sv.empty else ''

        pts = grp[['offset', 'elevation']].sort_values('offset')
        points = list(zip(pts['offset'], pts['elevation']))

        result.append({
            'station':      stn,
            'points':       points,
            'left_bank':    lb_off,
            'right_bank':   rb_off,
            'left_elev':    lb_elev,
            'right_elev':   rb_elev,
            'structure':    structure,
            'reach_length': 0.0,
        })

    if not result:
        raise ValueError("유효한 횡단면이 없습니다.")

    for i in range(1, len(result)):
        result[i]['reach_length'] = _calc_reach_length(
            result[i - 1]['station'],
            result[i]['station'],
            station_type, spacing
        )

    return result


# ─────────────────────────────────────────────────────────
# 3. HEC-RAS 출력 모듈
# ─────────────────────────────────────────────────────────

def _sta_elev_lines(points: list) -> list:
    """Station-Elevation 데이터를 HEC-RAS 포맷으로 변환 (5쌍/줄, 8자리 필드)."""
    flat = [v for pair in points for v in pair]
    rows = []
    for i in range(0, len(flat), 10):
        rows.append(''.join(f'{v:8.2f}' for v in flat[i:i + 10]))
    return rows


def _mann_line(lb: float, rb: float, n: float) -> str:
    """#Mann= 3존 포맷 (LOB, Channel, ROB) 한 줄 생성."""
    return f'{0:8.2f}{n:8.3f}{0:8.0f}{lb:8.2f}{n:8.3f}{0:8.0f}{rb:8.2f}{n:8.3f}{0:8.0f}'


def write_geometry(cross_sections: list,
                   river: str,
                   reach: str,
                   output_path: str,
                   title: str = 'HEC-RAS Geometry') -> None:
    """
    HEC-RAS 5.x Geometry 파일(.g01) 생성.
    - 구조물명이 있는 횡단면은 Type RM 줄 바로 다음에 BEGIN/END DESCRIPTION 블록 추가
    - 크로스섹션은 상류(큰 측점) → 하류(작은 측점) 순서로 출력
    """
    river_padded = f'{river:<16s}'
    reach_padded = f'{reach:<16s}'

    lines = [
        f'Geom Title={title}',
        'Program Version=5.06',
        'Viewing Rectangle= 0 , 1 , 1 , 0 ',
        '',
        f'River Reach={river_padded},{reach_padded}',
        'Reach XY= 2 ',
        '             0.5            0.95             0.5            0.05',
        'Rch Text X Y=0.5,0.5',
        'Reverse River Text= 0 ',
        '',
    ]

    for xs in sorted(cross_sections, key=lambda x: x['station'], reverse=True):
        rs    = xs['station']
        rl    = int(round(xs['reach_length']))
        lb    = xs['left_bank']
        rb    = xs['right_bank']
        lev_l = round(xs['left_elev']  + LEVEE_MARGIN, 2)
        lev_r = round(xs['right_elev'] + LEVEE_MARGIN, 2)

        lines.append(f"Type RM Length L Ch R = 1 ,{rs}   ,{rl},{rl},{rl}")

        # 구조물명 → Description 블록 (구조물 없는 횡단면은 블록 생략)
        if xs['structure']:
            lines.append('BEGIN DESCRIPTION:')
            lines.append(xs['structure'])
            lines.append('END DESCRIPTION:')

        lines.append(f"#Sta/Elev= {len(xs['points'])} ")
        lines.extend(_sta_elev_lines(xs['points']))
        lines.append(f"#Mann= 3 , 0 , 0 ")
        lines.append(_mann_line(lb, rb, MANNINGS_N))
        lines.append(f"Levee=-1,{lb},{lev_l},-1,{rb},{lev_r},,")
        lines.append(f"Bank Sta={lb},{rb}")
        lines.append("XS Rating Curve= 0 ,0")
        lines.append("Exp/Cntr=0.3,0.1")
        lines.append("")

    Path(output_path).write_text('\n'.join(lines), encoding='cp949', errors='replace')


# ─────────────────────────────────────────────────────────
# 4. HEC-RAS 프로젝트 파일 생성
# ─────────────────────────────────────────────────────────

def write_project(river: str, geom_path: str, output_path: str) -> None:
    """
    HEC-RAS Project 파일(.prj) 생성.
    - .prj 와 .g01 은 반드시 같은 폴더, 같은 기본명이어야 함
    - Geom File=g01  ← HEC-RAS가 연결 파일을 찾는 핵심 키
    """
    geom_suffix = Path(geom_path).suffix.lstrip('.')  # "g01"
    lines = [
        f'Proj Title={river}',
        'Default Exp/Contr=0.3,0.1',
        'SI Units',
        f'Geom File={geom_suffix}',
        'Y Axis Title=Elevation',
        'X Axis Title(PF)=Main Channel Distance',
        'X Axis Title(XS)=Station',
        'BEGIN DESCRIPTION:',
        '',
        'END DESCRIPTION:',
    ]
    Path(output_path).write_text('\n'.join(lines), encoding='cp949', errors='replace')


# ─────────────────────────────────────────────────────────
# 메인 진입점
# ─────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description='횡단 야장 CSV → HEC-RAS Geometry(.g01)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument('csv',                          help='입력 CSV 파일')
    ap.add_argument('--river',   default='하천명',   help='하천명 (기본: 하천명)')
    ap.add_argument('--reach',   default='Reach1',  help='Reach명 (기본: Reach1)')
    ap.add_argument('--output',  default=None,       help='출력 .g01 파일 경로')
    ap.add_argument('--type',    choices=['distance', 'no'], default='distance',
                    help='측점 형식: distance(거리형, 기본) | no(No형)')
    ap.add_argument('--spacing', type=float, default=None,
                    help='No형 전용: 정측점 간 거리(m). --type no 시 필수')
    ap.add_argument('--title',   default='HEC-RAS Geometry', help='Geometry 제목')
    args = ap.parse_args()

    if args.type == 'no' and not args.spacing:
        ap.error('--type no 사용 시 --spacing 값이 필요합니다.')

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f'[오류] 파일 없음: {csv_path}')
        return 1

    out_path = Path(args.output) if args.output else csv_path.with_suffix('.g01')
    prj_path = out_path.with_suffix('.prj')

    print('=' * 55)
    print('  HEC-RAS 횡단면 지형데이터 생성')
    print('=' * 55)
    print(f'  입력 CSV   : {csv_path}')
    print(f'  하천명/Reach: {args.river} / {args.reach}')
    print(f'  측점 형식  : {args.type}' +
          (f' (정측점 간격 {args.spacing}m)' if args.type == 'no' else ''))
    print(f'  출력 Geom  : {out_path}')
    print(f'  출력 Proj  : {prj_path}')
    print()

    df = parse_fieldbook(str(csv_path))
    print(f'  파싱 완료  : {len(df)}행 / 측점 {sorted(df["station"].unique())}')

    xs_list = build_cross_sections(df, args.type, args.spacing or 0.0)

    print(f'\n  횡단면 수  : {len(xs_list)}')
    print(f'  {"측점(km)":>8}  {"pts":>4}  {"Reach(m)":>10}  '
          f'{"좌안":>8}  {"우안":>8}  구조물')
    print(f'  {"-"*8}  {"-"*4}  {"-"*10}  {"-"*8}  {"-"*8}  {"-"*10}')
    for xs in xs_list:
        print(f'  {xs["station"]:>8}  '
              f'{len(xs["points"]):>4}  {xs["reach_length"]:>10.1f}  '
              f'{xs["left_bank"]:>8.3f}  {xs["right_bank"]:>8.3f}  '
              f'{xs["structure"] or ""}')

    write_geometry(xs_list, args.river, args.reach, str(out_path), args.title)
    print(f'  [완료] {out_path}')

    write_project(args.river, str(out_path), str(prj_path))
    print(f'  [완료] {prj_path}')

    print()
    print(f'  ── HEC-RAS에서 여는 방법 ──────────────────────────────')
    print(f'  1. File > Open Project → [{prj_path.name}] 선택')
    print(f'  2. Edit > Geometric Data → 자동으로 .g01 로드됨')
    print(f'  ──────────────────────────────────────────────────────')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
