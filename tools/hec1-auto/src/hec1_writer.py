"""
hec1_writer.py  (v4 - 관측소별 PG + 유역별 Huff 패턴)
=======================================================
stations 모드 전용.  각 유역이 자신의 Huff 패턴(PG/PC)을 가집니다.

출력 구조:
  PG  STA   xx.xx   ← 관측소별 지점강우량
  PG  STB   xx.xx
  PG DUMMY    0.00
  PG BS050    0.00  ← 유역 BS050의 Huff 패턴 정의
  PC  0.00   ...   (cluster 9 × 0.6 + cluster 17 × 0.4 가중 평균)
  PG BS040    0.00  ← 유역 BS040의 Huff 패턴 정의
  PC  0.00   ...

  KK  BS050
  BA  9.10
  PR BS050          ← 유역별 패턴 참조
  PW  1.000         ← ARF
  PT   STA   STB  DUMMY
  PW 0.600 0.400 0.000
  LS         81.8
  UC  0.47   0.78
"""

import os
from rainfall import calc_arf as _calc_arf


# ──────────────────────────────────────────────────────────────
# 공용 포맷 헬퍼
# ──────────────────────────────────────────────────────────────

def _fmt(card_id: str, *fields) -> str:
    """1~2열: ID, 3~8열: F1(6칸), 이후 8칸씩"""
    line = f"{card_id[:2]:<2}"
    for i, f in enumerate(fields):
        width = 6 if i == 0 else 8
        if isinstance(f, float):
            val = f"{f:{width}.2f}"
        elif isinstance(f, int):
            val = f"{f:{width}d}"
        elif f is None or f == "":
            val = " " * width
        else:
            val = f"{str(f):>{width}}"
        line += val[:width]
    return line[:80].rstrip()


def _calc_nq(duration_min: int, dt_min: int) -> int:
    """총 시간간격 수: 지속기간의 3배, 최소 300."""
    return max(300, (duration_min // dt_min) * 3)


# ──────────────────────────────────────────────────────────────
# PG / PC 블록
# ──────────────────────────────────────────────────────────────

def _make_pc_pct_lines(ratios: list) -> list:
    """누가강우비(0~1) → PC 카드 (백분율 0~100, 소수점 2자리, 10개/줄)"""
    lines = []
    for i in range(0, len(ratios), 10):
        chunk = ratios[i:i + 10]
        line  = "PC"
        for j, v in enumerate(chunk):
            pct = v * 100.0
            line += f"{pct:6.2f}" if j == 0 else f"{pct:8.2f}"
        lines.append(line)
    return lines


def _make_pg_pc_block(station_rainfalls: dict, basin_huff: dict) -> list:
    """
    전역 PG 블록 생성.

    station_rainfalls : {관측소명: mm}
    basin_huff        : {유역명: [누가강우비, ...]}
                        — 유역마다 고유한 Huff 패턴을 정의합니다.
    """
    lines = []
    # 관측소 강우량
    for name, rf in station_rainfalls.items():
        if name.upper() == 'DUMMY':
            continue
        lines.append(_fmt("PG", name, round(rf, 2)))
    lines.append(_fmt("PG", "DUMMY", 0))
    # 유역별 Huff 패턴 정의
    for basin_name, ratios in basin_huff.items():
        lines.append(_fmt("PG", basin_name, 0))
        lines.extend(_make_pc_pct_lines(ratios))
    return lines


# ──────────────────────────────────────────────────────────────
# 유역 블록
# ──────────────────────────────────────────────────────────────

def _basin_body_stations(basin: dict, arf: float) -> list:
    """
    stations 모드 유역 카드 블록.
    패턴명 = 유역명 (PG 블록에서 동일 이름으로 정의됨).

    BA → PR(유역명) → PW(ARF) → PT/PW(가중치) → LS → UC/US/UH
    """
    lines   = []
    cn      = basin['cn']
    method  = basin['method'].lower()
    params  = basin['params']
    sw      = basin.get('station_weights', [])
    pattern = basin['name']          # 유역명 = Huff 패턴명

    lines.append(_fmt("BA", round(basin['area_km2'], 2)))
    lines.append(f"PR{pattern:>6}")
    lines.append(f"PW{arf:6.3f}")

    # PT / PW 쌍
    names   = [s[0] for s in sw]
    weights = [s[1] for s in sw]
    for start in range(0, len(names), 10):
        ns = names[start:start + 10]
        ws = weights[start:start + 10]
        pt = "PT" + "".join(f"{n:>6}" if i == 0 else f"{n:>8}" for i, n in enumerate(ns))
        pw = "PW" + "".join(f"{w:6.3f}" if i == 0 else f"{w:8.3f}" for i, w in enumerate(ws))
        lines.append(pt)
        lines.append(pw)

    lines.append(_fmt("LS", "", cn))
    if method == 'clark':
        lines.append(_fmt("UC", params['tc'], params['r']))
    elif method == 'snyder':
        lines.append(_fmt("US", params['tp'], params['cp']))
    elif method == 'scs':
        lines.append(_fmt("UH", params['lag']))
    return lines


# ──────────────────────────────────────────────────────────────
# 기타 네트워크 요소
# ──────────────────────────────────────────────────────────────

def _make_reservoir(res: dict) -> list:
    lines = []
    lines.append(f"KK {res['name']}")
    lines.append(_fmt("RS", 1, "STOR"))

    for sv_chunk in [res['storage'][i:i+10] for i in range(0, len(res['storage']), 10)]:
        line = "SV"
        for j, v in enumerate(sv_chunk):
            line += f"{v:6.2f}" if j == 0 else f"{v:8.2f}"
        lines.append(line)

    for se_chunk in [res['elevation'][i:i+10] for i in range(0, len(res['elevation']), 10)]:
        line = "SE"
        for j, v in enumerate(se_chunk):
            line += f"{v:6.2f}" if j == 0 else f"{v:8.2f}"
        lines.append(line)

    if res.get('stage_discharge'):
        # 옵션 2: SQ 카드 — 수위-방류량 테이블 직접 입력 (5쌍/줄)
        flat = [x for pair in res['stage_discharge'] for x in pair]
        for i in range(0, len(flat), 10):
            chunk = flat[i:i + 10]
            line  = "SQ"
            for j, v in enumerate(chunk):
                line += f"{float(v):6.2f}" if j == 0 else f"{float(v):8.2f}"
            lines.append(line)
    else:
        # 옵션 1: SS 카드 — 방류공식 Q = C × L × (WSE − E₀)^n
        ss   = res['spillway']
        line = "SS"
        for j, v in enumerate(ss):
            line += f"{v:6.2f}" if j == 0 else f"{v:8.2f}"
        lines.append(line)

    lines.append(_fmt("KO", res['outflow_kk']))
    return lines


def _make_routing(rt: dict, start_date: str, start_time: str, dt_min: int) -> list:
    lines = []
    lines.append(f"KK {rt['name']}")
    lines.append(_fmt("IN", dt_min, start_date, start_time))
    lines.append(_fmt("RM", rt.get('n_reaches', 1), rt['k'], rt['x']))
    return lines


def _make_combine(el: dict) -> list:
    lines = [f"KK {el['name']}"]
    lines.append(_fmt("HC", el['n_inputs']))
    return lines


def _make_hydrograph(el: dict, dt_min: int, start_date: str, start_time: str) -> list:
    """외부 수문곡선 직접 입력 (QI 카드)."""
    lines = []
    lines.append(f"KK {el['name']}")
    lines.append(_fmt("IN", dt_min, start_date, start_time))
    ords = el.get('ordinates', [])
    for i in range(0, len(ords), 10):
        chunk = ords[i:i + 10]
        line  = "QI"
        for j, v in enumerate(chunk):
            line += f"{float(v):6.2f}" if j == 0 else f"{float(v):8.2f}"
        lines.append(line)
    return lines


# ──────────────────────────────────────────────────────────────
# 메인 함수
# ──────────────────────────────────────────────────────────────

def write_dat_file(
    project:           dict,
    station_rainfalls: dict,        # {관측소명: mm}
    basin_huff:        dict,        # {유역명: [누가강우비, ...]}
    duration_min:      int,
    output_path:       str,
    dt_min:            int = 10,
    return_period:     int = 0,
) -> str:
    """HEC-1 DAT 파일 생성 (stations 모드 전용)."""
    arf_region  = project.get('arf_region', '한강')
    start_date  = "17NOV25"
    start_time  = "1800"
    nq          = _calc_nq(duration_min, dt_min)
    name        = project.get('name', 'Project')

    lines = []

    # ── 헤더 ──────────────────────────────────────────────────
    lines.append(f"ID {name} - {return_period}yr {duration_min}min")
    lines.append("*DIAGRAM")
    lines.append("IM")
    lines.append(_fmt("IO", 5, 2))
    lines.append(_fmt("IT", dt_min, start_date, start_time, nq))

    for st in project.get('output_stations', []):
        lines.append(_fmt("VS", st['name']))
        lines.append(_fmt("VV", st['var_code']))

    # ── 전역 PG / PC 블록 ─────────────────────────────────────
    lines.append("*")
    lines.extend(_make_pg_pc_block(station_rainfalls, basin_huff))

    # ── 네트워크 요소 ─────────────────────────────────────────
    for element in project['network']:
        etype   = element['type']
        comment = element.get('comment', '')
        lines.append("*")
        if comment:
            lines.append(f"* {comment}")
        lines.append("*")

        if etype in ('basin', 'raw_basin'):
            if etype == 'raw_basin':
                lines.append(element.get('kk_line', f"KK {element['name']}"))
            else:
                lines.append(f"KK {element['name']}")
            arf = _calc_arf(element['area_km2'], duration_min,
                            return_period, arf_region)
            lines.extend(_basin_body_stations(element, arf))

        elif etype == 'reservoir':
            lines.extend(_make_reservoir(element))

        elif etype == 'routing':
            lines.extend(_make_routing(element, start_date, start_time, dt_min))

        elif etype == 'combine':
            lines.extend(_make_combine(element))

        elif etype == 'hydrograph':
            lines.extend(_make_hydrograph(element, dt_min, start_date, start_time))

    lines.append("*")
    lines.append("ZZ")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='ascii', errors='replace') as f:
        f.write('\n'.join(lines) + '\n')
    return output_path
