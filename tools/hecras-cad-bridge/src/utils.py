# ==================================================
# HEC-RAS ↔ AutoCAD 연동 공용 유틸리티
#
# 대상 geometry 파일 형식 (HEC-RAS 5.x 실제 포맷):
#   - BEGIN/END CROSS-SECTION 없음
#   - "Type RM Length L Ch R = 1 ,STATION,..." 으로 단면 시작
#   - #Sta/Elev 데이터: 한 줄에 5쌍(10개 숫자) packed
#   - River/Reach 는 파일 상단 "River Reach=..." 에 한 번만 정의
# ==================================================

import json
import math
import os
import re
import shutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import ezdxf


# --------------------------------------------------
# 데이터 구조
# --------------------------------------------------

@dataclass
class CrossSection:
    river: str
    reach: str
    station: str                          # geometry 파일 원본 문자열 (예: "3.307")
    sta_elev: List[Tuple[float, float]] = field(default_factory=list)
    bank_sta: Tuple[float, float] = (0.0, 0.0)
    mannings_n: List[Tuple[float, float]] = field(default_factory=list)
    reach_lengths: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def key(self) -> str:
        return f"{self.river}|{self.reach}|{self.station}"


# --------------------------------------------------
# HEC-RAS Geometry 파싱
# --------------------------------------------------
# 실제 파일 구조:
#   River Reach=RIVER-1         ,Reach-1
#   Type RM Length L Ch R = 1 ,3.307   ,7,7,7
#   #Sta/Elev= 16
#          0    22.2    8.25   22.29   ...   (5쌍 = 10숫자/줄)
#   Bank Sta=43.23,56.57
#   ...
#   Type RM Length L Ch R = 1 ,3.300   ,100,100,100  ← 다음 단면

_XS_TYPE1_RE   = re.compile(r'Type RM Length L Ch R\s*=\s*1\s*,([^,]+)')
_XS_OTHERS_RE  = re.compile(r'Type RM Length L Ch R\s*=\s*[^1\s]')
_RIVER_REACH_RE = re.compile(r'River Reach\s*=\s*([^,]+),\s*(.*)')
_LEVEE_RE       = re.compile(r'^Levee=(-?\d+),([0-9.]+),([0-9.]+),(-?\d+),([0-9.]+),([0-9.]+)(,.*)$')


def parse_geometry(filepath: str) -> List[CrossSection]:
    """HEC-RAS .g0x 파일에서 횡단면(Type=1) 데이터를 읽어 반환합니다."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    xs_list: List[CrossSection] = []
    current_river = ''
    current_reach = ''
    current: Optional[CrossSection] = None

    # sta/elev packed 읽기 상태
    remaining_pairs = 0
    num_buffer: List[str] = []

    for line in lines:
        s = line.strip()

        # ── River/Reach 정의 ─────────────────────────────────
        m = _RIVER_REACH_RE.match(s)
        if m:
            current_river = m.group(1).strip()
            current_reach = m.group(2).strip()
            continue

        # ── 새 횡단면 시작 (Type = 1) ─────────────────────────
        m = _XS_TYPE1_RE.match(s)
        if m:
            _save_current(current, xs_list)
            station_str = m.group(1).strip()
            current = CrossSection(
                river=current_river,
                reach=current_reach,
                station=station_str,
            )
            remaining_pairs = 0
            num_buffer = []
            continue

        # ── 비-횡단면 노드 (교량=3, 위어=5 등) ────────────────
        if _XS_OTHERS_RE.match(s):
            _save_current(current, xs_list)
            current = None
            remaining_pairs = 0
            continue

        if current is None:
            continue

        # ── #Sta/Elev 헤더 ────────────────────────────────────
        if s.startswith('#Sta/Elev='):
            count_str = s.split('=', 1)[1].strip().split()[0]
            remaining_pairs = int(count_str)
            num_buffer = []
            current.sta_elev = []
            continue

        # ── #Sta/Elev 데이터 (packed: 5쌍/줄) ─────────────────
        if remaining_pairs > 0:
            num_buffer.extend(s.split())
            while len(num_buffer) >= 2 and remaining_pairs > 0:
                try:
                    sta  = float(num_buffer.pop(0))
                    elev = float(num_buffer.pop(0))
                    current.sta_elev.append((sta, elev))
                    remaining_pairs -= 1
                except ValueError:
                    remaining_pairs = 0
                    num_buffer = []
            continue

        # ── Bank Sta ─────────────────────────────────────────
        if s.startswith('Bank Sta='):
            parts = s[len('Bank Sta='):].split(',')
            if len(parts) >= 2:
                try:
                    current.bank_sta = (float(parts[0]), float(parts[1]))
                except ValueError:
                    pass
            continue

        # ── Downstream Reach Lengths ──────────────────────────
        if s.startswith('Downstream Reach Lengths='):
            parts = s.split('=', 1)[1].split(',')
            if len(parts) >= 3:
                try:
                    current.reach_lengths = (float(parts[0]), float(parts[1]), float(parts[2]))
                except ValueError:
                    pass
            continue

    # 마지막 단면 저장
    _save_current(current, xs_list)

    return xs_list


def _save_current(current: Optional[CrossSection],
                  xs_list: List[CrossSection]) -> None:
    if current is not None and current.sta_elev:
        xs_list.append(current)


# --------------------------------------------------
# HEC-RAS Geometry 수정 (#Sta/Elev 블록 교체)
# --------------------------------------------------

def update_geometry_xs(filepath: str,
                        updates: List[Tuple[str, str, str, List[Tuple[float, float]]]],
                        backup: bool = True) -> None:
    """
    HEC-RAS geometry 파일에서 지정 횡단면의 #Sta/Elev 데이터를 교체합니다.

    updates: [(river, reach, station_str, [(sta, elev), ...]), ...]
    """
    if backup:
        shutil.copy2(filepath, filepath + '.bak')
        print(f"  백업 생성: {filepath}.bak")

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    # ── 모든 Type RM 줄의 위치와 station 수집 ─────────────────
    type_entries: List[Tuple[int, bool, str]] = []  # (line_idx, is_xs, station)
    for i, line in enumerate(lines):
        s = line.strip()
        m1 = _XS_TYPE1_RE.match(s)
        if m1:
            type_entries.append((i, True, m1.group(1).strip()))
            continue
        if _XS_OTHERS_RE.match(s) or re.match(r'Type RM Length L Ch R\s*=\s*\d', s):
            type_entries.append((i, False, ''))

    # ── 각 XS 단면의 (시작줄, 끝줄, station) ─────────────────
    xs_sections: List[Tuple[int, int, str]] = []
    for k, (idx, is_xs, sta) in enumerate(type_entries):
        if not is_xs:
            continue
        next_idx = type_entries[k + 1][0] if k + 1 < len(type_entries) else len(lines)
        xs_sections.append((idx, next_idx - 1, sta))

    # ── 업데이트 대상 줄 수집 (라인 번호 내림차순으로 처리) ────
    pending: List[Tuple[int, int, int, List]] = []  # (header_line, old_count, data_lines, new_pts)

    for _, _, upd_sta, new_points in updates:
        section = next((s for s in xs_sections if s[2] == upd_sta), None)
        if section is None:
            print(f"  [경고] 단면 없음 (station={upd_sta}) — 건너뜀")
            continue

        start_i, end_i, _ = section
        for j in range(start_i, end_i + 1):
            if lines[j].strip().startswith('#Sta/Elev='):
                old_count = int(lines[j].strip().split('=', 1)[1].strip().split()[0])
                old_data_lines = math.ceil(old_count / 5)
                pending.append((j, old_count, old_data_lines, new_points))
                break

    # ── 뒤에서부터 교체 (라인 번호 유지) ──────────────────────
    pending.sort(key=lambda x: x[0], reverse=True)
    result = list(lines)

    for header_j, old_count, old_data_lines, new_points in pending:
        new_lines = _format_sta_elev(new_points)
        result[header_j: header_j + old_data_lines + 1] = new_lines
        # station 이름을 역추적해서 로그 출력
        sta_name = next(
            (s[2] for s in xs_sections
             if s[0] <= header_j <= s[1]), '?'
        )
        print(f"  업데이트: station={sta_name}  {old_count}점 → {len(new_points)}점")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(result)


def _format_sta_elev(points: List[Tuple[float, float]]) -> List[str]:
    """(sta, elev) 목록을 HEC-RAS packed 포맷 줄 목록으로 변환합니다 (5쌍/줄)."""
    out = [f"#Sta/Elev= {len(points)} \n"]
    for i in range(0, len(points), 5):
        batch = points[i: i + 5]
        row = ''.join(f'{v:8.2f}' for pair in batch for v in pair)
        out.append(row + '\n')
    return out


# --------------------------------------------------
# DXF 생성 (Step1: HEC-RAS → DXF)
# --------------------------------------------------

def create_xs_dxf(xs_list: List[CrossSection],
                   wse_dict: Optional[Dict[str, float]],
                   dxf_file: str,
                   panel_meta_file: str,
                   cfg) -> None:
    """
    횡단면 목록으로 DXF 도면을 생성합니다.
    각 횡단면은 가로로 나열된 패널에 그려집니다.

    wse_dict: {xs.key: 홍수위 표고} — None이면 홍수위선 생략
    """
    os.makedirs(os.path.dirname(dxf_file) or '.', exist_ok=True)

    doc = ezdxf.new('R2010')
    msp = doc.modelspace()

    _make_layer(doc, cfg.LAYER_EXISTING, cfg.COLOR_EXISTING)
    _make_layer(doc, cfg.LAYER_PLANNED,  cfg.COLOR_PLANNED)
    _make_layer(doc, cfg.LAYER_FLOOD,    cfg.COLOR_FLOOD)
    _make_layer(doc, cfg.LAYER_LEVEE,    cfg.COLOR_LEVEE)
    _make_layer(doc, cfg.LAYER_TEXT,     cfg.COLOR_TEXT)

    # 패널 높이 = 전체 단면 중 최대 표고 범위 + 간격
    elev_ranges = [
        max(e for _, e in xs.sta_elev) - min(e for _, e in xs.sta_elev)
        for xs in xs_list if len(xs.sta_elev) >= 2
    ]
    panel_height = max(elev_ranges, default=10.0) + cfg.PANEL_SPACING

    panels_meta = []

    # 하류→상류 순서 (station 오름차순 = idx 0이 최하류 = 도면 맨 아래)
    sorted_xs = sorted(xs_list, key=lambda x: float(x.station))

    for idx, xs in enumerate(sorted_xs):
        if len(xs.sta_elev) < 2:
            continue

        sta_min  = xs.sta_elev[0][0]
        y_offset = idx * panel_height   # 세로 적층: idx=0이 아래

        # 현황단면 폴리라인 (x = 상대 거리, y = 표고 + offset)
        pts = [(sta - sta_min, elev + y_offset) for sta, elev in xs.sta_elev]
        msp.add_lwpolyline(pts, dxfattribs={'layer': cfg.LAYER_EXISTING})

        # 제방 마커
        for bank_sta in xs.bank_sta:
            bx   = bank_sta - sta_min
            belv = _interp_elev(xs.sta_elev, bank_sta)
            msp.add_line((bx, belv + y_offset - 0.5), (bx, belv + y_offset + 2.0),
                         dxfattribs={'layer': cfg.LAYER_LEVEE})

        # 홍수위선 + 중앙 텍스트
        if wse_dict and xs.key in wse_dict:
            wse     = wse_dict[xs.key]
            x_right = xs.sta_elev[-1][0] - sta_min
            x_center = x_right / 2
            actual_y = wse + y_offset
            msp.add_line((0, actual_y), (x_right, actual_y),
                         dxfattribs={'layer': cfg.LAYER_FLOOD})
            msp.add_text(
                f"EL.{wse:.3f}",
                dxfattribs={
                    'layer':  cfg.LAYER_FLOOD,
                    'height': cfg.TEXT_HEIGHT,
                    'insert': (x_center, actual_y + cfg.TEXT_HEIGHT * 0.3),
                }
            )

        # 단면 제목 텍스트
        top_elev = max(e for _, e in xs.sta_elev)
        msp.add_text(
            f"STA {xs.station}  ({xs.river} / {xs.reach})",
            dxfattribs={
                'layer':  cfg.LAYER_TEXT,
                'height': cfg.TEXT_HEIGHT,
                'insert': (0, top_elev + y_offset + cfg.TEXT_HEIGHT * 2),
            }
        )

        x_end    = xs.sta_elev[-1][0] - sta_min
        min_elev = min(e for _, e in xs.sta_elev)
        max_elev = max(e for _, e in xs.sta_elev)
        # y_lo/y_hi를 실제 표고 기반으로 설정:
        # y_offset만 기준으로 하면 절대표고가 panel_height보다 클 때 패널을 못 찾음
        margin   = cfg.PANEL_SPACING / 4
        panels_meta.append({
            'panel_index': idx,
            'river':       xs.river,
            'reach':       xs.reach,
            'station':     xs.station,
            'x_origin':    0,
            'x_end':       x_end,
            'sta_min':     sta_min,
            'y_offset':    y_offset,
            'y_lo':        min_elev + y_offset - margin,
            'y_hi':        max_elev + y_offset + margin,
        })

    doc.saveas(dxf_file)
    print(f"DXF 저장: {dxf_file}  ({len(panels_meta)}개 단면)")

    with open(panel_meta_file, 'w', encoding='utf-8') as f:
        json.dump({'layout': 'vertical', 'panels': panels_meta}, f, ensure_ascii=False, indent=2)
    print(f"패널 메타데이터: {panel_meta_file}")


# --------------------------------------------------
# DXF 읽기 (Step2: 계획단면 폴리라인 → HEC-RAS 좌표)
# --------------------------------------------------

def read_planned_sections(dxf_file: str,
                           panel_meta_file: str,
                           planned_layer: str) -> Dict[str, List[Tuple[float, float]]]:
    """
    DXF에서 계획단면 레이어의 폴리라인을 읽어
    {xs.key: [(sta, elev), ...]} 형태로 반환합니다.
    """
    with open(panel_meta_file, 'r', encoding='utf-8') as f:
        meta = json.load(f)
    panels = meta['panels']

    doc = ezdxf.readfile(dxf_file)
    msp = doc.modelspace()

    result: Dict[str, List[Tuple[float, float]]] = {}

    for entity in msp.query(f'LWPOLYLINE[layer=="{planned_layer}"]'):
        pts = list(entity.get_points('xy'))
        if not pts:
            continue

        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        panel = _find_panel(panels, cx, cy)
        if panel is None:
            print(f"  [경고] 패널 매칭 실패 (중심X={cx:.1f}, Y={cy:.1f}) — 건너뜀")
            continue

        x_origin = panel['x_origin']
        y_offset = panel.get('y_offset', 0)
        sta_min  = panel['sta_min']
        xs_key   = f"{panel['river']}|{panel['reach']}|{panel['station']}"

        sta_elev = sorted(
            [(x - x_origin + sta_min, y - y_offset) for x, y in pts],
            key=lambda p: p[0]
        )
        result[xs_key] = sta_elev
        print(f"  읽기: {xs_key}  {len(sta_elev)}점 "
              f"(거리 {sta_elev[0][0]:.2f}~{sta_elev[-1][0]:.2f}m)")

    return result


# --------------------------------------------------
# DXF 읽기 (Step2: 제방 마커 위치 → Bank Sta)
# --------------------------------------------------

def read_bank_stations(dxf_file: str,
                        panel_meta_file: str,
                        levee_layer: str) -> Dict[str, Tuple[float, float]]:
    """
    DXF '제방' 레이어의 수직선 X 좌표를 읽어
    {xs.key: (left_bank_sta, right_bank_sta)} 로 반환합니다.
    사용자가 제방 마커를 이동하면 Bank Sta 값이 달라집니다.
    """
    with open(panel_meta_file, 'r', encoding='utf-8') as f:
        meta = json.load(f)
    panels = meta['panels']

    doc = ezdxf.readfile(dxf_file)
    msp = doc.modelspace()

    panel_xs: Dict[int, List[float]] = {}

    for entity in msp.query(f'LINE[layer=="{levee_layer}"]'):
        sx, sy = entity.dxf.start[0], entity.dxf.start[1]
        ex, ey = entity.dxf.end[0],   entity.dxf.end[1]
        cx = (sx + ex) / 2.0
        cy = (sy + ey) / 2.0
        panel = _find_panel(panels, cx, cy)
        if panel is None:
            continue
        pidx = panel['panel_index']
        sta  = cx - panel['x_origin'] + panel['sta_min']
        panel_xs.setdefault(pidx, []).append(sta)

    result: Dict[str, Tuple[float, float]] = {}
    for panel in panels:
        stas = sorted(panel_xs.get(panel['panel_index'], []))
        if len(stas) < 2:
            continue
        xs_key = f"{panel['river']}|{panel['reach']}|{panel['station']}"
        result[xs_key] = (stas[0], stas[-1])

    return result


# --------------------------------------------------
# HEC-RAS Geometry Bank Sta 수정 (Step2)
# --------------------------------------------------

def update_geometry_bank_sta(filepath: str,
                              bank_updates: Dict[str, Tuple[float, float]],
                              backup: bool = False) -> int:
    """
    HEC-RAS geometry 파일의 'Bank Sta=' 값을 교체합니다.
    변경된 단면 수를 반환합니다.
    bank_updates: {xs.key: (left_bank_sta, right_bank_sta)}
    """
    if backup:
        shutil.copy2(filepath, filepath + '.bak')
        print(f"  백업 생성: {filepath}.bak")

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    # XS 섹션 경계 수집
    type_entries: List[Tuple[int, bool, str]] = []
    for i, line in enumerate(lines):
        s = line.strip()
        m1 = _XS_TYPE1_RE.match(s)
        if m1:
            type_entries.append((i, True, m1.group(1).strip()))
            continue
        if _XS_OTHERS_RE.match(s) or re.match(r'Type RM Length L Ch R\s*=\s*\d', s):
            type_entries.append((i, False, ''))

    xs_sections: List[Tuple[int, int, str]] = []
    for k, (idx, is_xs, sta) in enumerate(type_entries):
        if not is_xs:
            continue
        next_idx = type_entries[k + 1][0] if k + 1 < len(type_entries) else len(lines)
        xs_sections.append((idx, next_idx - 1, sta))

    # xs.key → station 문자열 매핑
    sta_to_update: Dict[str, Tuple[float, float]] = {}
    for xs_key, (left, right) in bank_updates.items():
        parts = xs_key.split('|')
        if len(parts) == 3:
            sta_to_update[parts[2]] = (left, right)

    pending: List[Tuple[int, str, str]] = []
    for start_i, end_i, sta in xs_sections:
        if sta not in sta_to_update:
            continue
        left, right = sta_to_update[sta]
        for j in range(start_i, end_i + 1):
            if lines[j].strip().startswith('Bank Sta='):
                old = lines[j].strip()
                new_line = f"Bank Sta={left:.2f},{right:.2f}\n"
                pending.append((j, new_line,
                                f"station={sta}  {old} → Bank Sta={left:.2f},{right:.2f}"))
                break

    pending.sort(key=lambda x: x[0], reverse=True)
    result = list(lines)
    for line_j, new_line, label in pending:
        result[line_j] = new_line
        print(f"  Bank Sta 업데이트: {label}")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(result)

    return len(pending)


def sync_levee_to_bank_sta(filepath: str, backup: bool = False) -> int:
    """
    geometry 파일 내에서 Bank Sta= 와 Levee= 스테이션이 다른 모든 단면을
    찾아 Levee= 스테이션을 Bank Sta= 값으로 자동 동기화합니다.
    표고(3번째·6번째 필드)는 변경하지 않습니다.
    변경된 단면 수를 반환합니다.

    이 함수는 changed_banks 에 의존하지 않으므로 이전 실행에서
    Bank Sta 만 바뀌고 Levee 가 그대로인 경우도 모두 수정합니다.
    """
    if backup:
        shutil.copy2(filepath, filepath + '.bak')
        print(f"  백업 생성: {filepath}.bak")

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    type_entries: List[Tuple[int, bool, str]] = []
    for i, line in enumerate(lines):
        s = line.strip()
        m1 = _XS_TYPE1_RE.match(s)
        if m1:
            type_entries.append((i, True, m1.group(1).strip()))
            continue
        if _XS_OTHERS_RE.match(s) or re.match(r'Type RM Length L Ch R\s*=\s*\d', s):
            type_entries.append((i, False, ''))

    xs_sections: List[Tuple[int, int, str]] = []
    for k, (idx, is_xs, sta) in enumerate(type_entries):
        if not is_xs:
            continue
        next_idx = type_entries[k + 1][0] if k + 1 < len(type_entries) else len(lines)
        xs_sections.append((idx, next_idx - 1, sta))

    THRESHOLD = 0.005  # 0.5cm 이내는 동일로 취급
    pending: List[Tuple[int, str, str]] = []

    for start_i, end_i, sta in xs_sections:
        bank_line_j = levee_line_j = -1
        bank_left = bank_right = None
        levee_raw = None

        for j in range(start_i, end_i + 1):
            s = lines[j].strip()
            if s.startswith('Bank Sta=') and bank_line_j == -1:
                parts = s[len('Bank Sta='):].split(',')
                if len(parts) >= 2:
                    try:
                        bank_left  = float(parts[0])
                        bank_right = float(parts[1])
                        bank_line_j = j
                    except ValueError:
                        pass
            elif s.startswith('Levee=') and levee_line_j == -1:
                levee_line_j = j
                levee_raw = s

        if bank_line_j == -1 or levee_line_j == -1:
            continue  # Bank Sta 또는 Levee 없는 단면은 건너뜀

        m = _LEVEE_RE.match(levee_raw)
        if not m:
            print(f"  [경고] Levee= 파싱 실패 (station={sta}): {levee_raw}")
            continue

        lev_left  = float(m.group(2))
        lev_right = float(m.group(5))

        if (abs(lev_left  - bank_left)  <= THRESHOLD and
                abs(lev_right - bank_right) <= THRESHOLD):
            continue  # 이미 일치 → 건너뜀

        node_l, elev_l = m.group(1), m.group(3)
        node_r, elev_r = m.group(4), m.group(6)
        tail = m.group(7)
        new_line = (f"Levee={node_l},{bank_left:.2f},{elev_l},"
                    f"{node_r},{bank_right:.2f},{elev_r}{tail}\n")
        pending.append((levee_line_j, new_line,
                        f"station={sta}  Levee({lev_left:.2f},{lev_right:.2f})"
                        f" → ({bank_left:.2f},{bank_right:.2f})"))

    pending.sort(key=lambda x: x[0], reverse=True)
    result = list(lines)
    for line_j, new_line, label in pending:
        result[line_j] = new_line
        print(f"  Levee 동기화: {label}")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(result)

    return len(pending)


_MANN_HDR_RE = re.compile(r'^#Mann=\s*(\d+)\s*,')


def sync_mann_to_bank_sta(filepath: str, backup: bool = False) -> int:
    """
    geometry 파일 내에서 Bank Sta= 와 #Mann= 구역 경계가 다른 모든 단면을
    찾아 Manning's n 구역 경계 스테이션을 Bank Sta= 값으로 자동 동기화합니다.
    n값(조도계수) 자체는 변경하지 않습니다.
    변경된 단면 수를 반환합니다.
    """
    if backup:
        shutil.copy2(filepath, filepath + '.bak')
        print(f"  백업 생성: {filepath}.bak")

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    type_entries: List[Tuple[int, bool, str]] = []
    for i, line in enumerate(lines):
        s = line.strip()
        m1 = _XS_TYPE1_RE.match(s)
        if m1:
            type_entries.append((i, True, m1.group(1).strip()))
            continue
        if _XS_OTHERS_RE.match(s) or re.match(r'Type RM Length L Ch R\s*=\s*\d', s):
            type_entries.append((i, False, ''))

    xs_sections: List[Tuple[int, int, str]] = []
    for k, (idx, is_xs, sta) in enumerate(type_entries):
        if not is_xs:
            continue
        next_idx = type_entries[k + 1][0] if k + 1 < len(type_entries) else len(lines)
        xs_sections.append((idx, next_idx - 1, sta))

    THRESHOLD = 0.005
    pending: List[Tuple[int, str, str]] = []

    for start_i, end_i, sta in xs_sections:
        bank_left = bank_right = None
        mann_hdr_j = -1
        mann_count = 0

        for j in range(start_i, end_i + 1):
            s = lines[j].strip()
            if s.startswith('Bank Sta=') and bank_left is None:
                parts = s[len('Bank Sta='):].split(',')
                try:
                    bank_left  = float(parts[0])
                    bank_right = float(parts[1])
                except (ValueError, IndexError):
                    pass
            mh = _MANN_HDR_RE.match(s)
            if mh and mann_hdr_j == -1:
                mann_hdr_j = j
                mann_count = int(mh.group(1))

        if bank_left is None or mann_hdr_j == -1 or mann_count < 2:
            continue

        # Collect data tokens across lines following the #Mann= header
        needed = mann_count * 3
        raw_toks: List[str] = []
        data_line_indices: List[int] = []
        j = mann_hdr_j + 1
        while len(raw_toks) < needed and j <= end_i:
            s = lines[j].strip()
            toks = s.split()
            if not toks:
                break
            # Stop if we hit another keyword line
            if toks[0].startswith('#') or not toks[0].replace('.', '').replace('-', '').replace('e', '').replace('E', '').replace('+', '').lstrip('-').isdigit():
                break
            raw_toks.extend(toks)
            data_line_indices.append(j)
            j += 1

        if len(raw_toks) < needed or not data_line_indices:
            continue

        try:
            vals = [float(x) for x in raw_toks[:needed]]
        except ValueError:
            continue

        # Zone 2 station (index 3) = bank_left boundary
        # Zone N (last) station (index 3*(n-1)) = bank_right boundary
        zone2_sta = vals[3]
        zoneN_sta = vals[3 * (mann_count - 1)]

        if (abs(zone2_sta - bank_left) <= THRESHOLD and
                abs(zoneN_sta - bank_right) <= THRESHOLD):
            continue

        old_z2, old_zN = zone2_sta, zoneN_sta
        new_toks = list(raw_toks[:needed])
        new_toks[3]                    = f'{bank_left:.2f}'
        new_toks[3 * (mann_count - 1)] = f'{bank_right:.2f}'

        # Rebuild data lines preserving original token count per line
        tok_idx = 0
        for dl_j in data_line_indices:
            orig_count = len(lines[dl_j].strip().split())
            chunk = new_toks[tok_idx: tok_idx + orig_count]
            tok_idx += orig_count
            row = ''.join(f'{t:>8}' for t in chunk)
            pending.append((dl_j, row + '\n',
                            f"station={sta}  #Mann({old_z2:.2f},{old_zN:.2f})"
                            f"→({bank_left:.2f},{bank_right:.2f})"))

    pending.sort(key=lambda x: x[0], reverse=True)
    result = list(lines)
    updated_stations: set = set()
    for line_j, new_line, label in pending:
        result[line_j] = new_line
        sta_label = label.split()[0]  # "station=X.XXX"
        if sta_label not in updated_stations:
            print(f"  Manning's n 구역 동기화: {label}")
            updated_stations.add(sta_label)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(result)

    return len(updated_stations)


# --------------------------------------------------
# DXF 홍수위 업데이트 (Step4)
# --------------------------------------------------

def update_dxf_wse(dxf_file: str,
                    panel_meta_file: str,
                    wse_dict: Dict[str, float],
                    flood_layer: str,
                    text_layer: str,
                    text_height: float) -> None:
    """DXF의 홍수위 레이어를 새 WSE 값으로 교체합니다."""
    with open(panel_meta_file, 'r', encoding='utf-8') as f:
        meta = json.load(f)

    doc = ezdxf.readfile(dxf_file)
    msp = doc.modelspace()

    # 기존 홍수위 엔티티 삭제
    for e in list(msp.query(f'LINE[layer=="{flood_layer}"]')):
        msp.delete_entity(e)
    for e in list(msp.query(f'TEXT[layer=="{flood_layer}"]')):
        msp.delete_entity(e)

    updated = 0
    for panel in meta['panels']:
        xs_key = f"{panel['river']}|{panel['reach']}|{panel['station']}"
        if xs_key not in wse_dict:
            continue

        wse      = wse_dict[xs_key]
        x_origin = panel['x_origin']
        x_end    = panel['x_end']
        y_offset = panel.get('y_offset', 0)
        x_center = (x_origin + x_end) / 2
        actual_y = wse + y_offset

        msp.add_line((x_origin, actual_y), (x_end, actual_y),
                     dxfattribs={'layer': flood_layer})
        msp.add_text(
            f"EL.{wse:.3f}",
            dxfattribs={
                'layer':  flood_layer,
                'height': text_height,
                'insert': (x_center, actual_y + text_height * 0.3),
            }
        )
        updated += 1

    doc.saveas(dxf_file)
    print(f"홍수위 업데이트: {updated}개 단면  →  {dxf_file}")


# --------------------------------------------------
# HEC-RAS HDF5 결과 읽기
# --------------------------------------------------

def read_profile_names_from_hdf(hdf_file: str) -> List[str]:
    """HEC-RAS HDF5 결과 파일에서 프로파일 이름 목록을 반환합니다. 실패 시 빈 리스트."""
    try:
        import h5py
    except ImportError:
        return []

    PROFILE_PATHS = [
        '/Plan Data/Plan Information/Profile Names',
        '/Results/Steady/Output/Output Blocks/Base Output/Steady Profiles/Profile Names',
    ]
    try:
        with h5py.File(hdf_file, 'r') as f:
            for path in PROFILE_PATHS:
                if path in f:
                    return [_decode(v) for v in f[path][:]]
    except Exception:
        pass
    return []


def read_wse_from_hdf(hdf_file: str,
                       profile_index: int,
                       xs_list: List[CrossSection]) -> Dict[str, float]:
    """
    HEC-RAS 계산 결과 HDF5에서 홍수위(WSE)를 읽어
    {xs.key: wse} 형태로 반환합니다.

    profile_index: 0-based 인덱스
    """
    try:
        import h5py
    except ImportError:
        raise ImportError("pip install h5py 를 실행하세요.")

    result: Dict[str, float] = {}
    WSE_PATH = (
        '/Results/Steady/Output/Output Blocks/'
        'Base Output/Steady Profiles/Cross Sections/Water Surface'
    )
    ATTR_PATH = '/Geometry/Cross Sections/Attributes'

    with h5py.File(hdf_file, 'r') as f:
        if WSE_PATH not in f:
            raise KeyError(
                f"HDF5 경로 없음: {WSE_PATH}\n"
                "HEC-RAS 계획 파일(.p0x.hdf)이 맞는지, 계산이 완료됐는지 확인하세요."
            )
        wse_array = f[WSE_PATH][:]

        if ATTR_PATH in f:
            attrs = f[ATTR_PATH][:]
            for i, attr in enumerate(attrs):
                river = _decode(attr['River'])
                reach = _decode(attr['Reach'])
                rs    = _decode(attr['RS'])
                key   = f"{river}|{reach}|{rs}"
                wse   = float(wse_array[profile_index, i]
                              if wse_array.ndim == 2 else wse_array[i])
                result[key] = wse
        else:
            # Attributes 없으면 geometry 파싱 순서로 매핑
            print("  [주의] HDF5 Attributes 없음 — geometry 순서로 매핑합니다.")
            for i, xs in enumerate(xs_list):
                if i >= (wse_array.shape[1] if wse_array.ndim == 2 else len(wse_array)):
                    break
                wse = float(wse_array[profile_index, i]
                            if wse_array.ndim == 2 else wse_array[i])
                result[xs.key] = wse

    return result


def _decode(v) -> str:
    if isinstance(v, bytes):
        return v.decode('utf-8', errors='replace').strip()
    return str(v).strip()


# --------------------------------------------------
# 내부 헬퍼 함수
# --------------------------------------------------

def _make_layer(doc, name: str, color: int) -> None:
    if name not in doc.layers:
        doc.layers.new(name, dxfattribs={'color': color})


def _interp_elev(sta_elev: List[Tuple[float, float]], target_sta: float) -> float:
    """선형 보간으로 특정 거리의 표고를 반환합니다."""
    for i in range(len(sta_elev) - 1):
        s0, e0 = sta_elev[i]
        s1, e1 = sta_elev[i + 1]
        if s0 <= target_sta <= s1:
            t = (target_sta - s0) / (s1 - s0) if s1 != s0 else 0
            return e0 + t * (e1 - e0)
    return sta_elev[-1][1]


def _find_panel(panels: list, cx: float, cy: float = None) -> Optional[dict]:
    """패널 식별: 세로 배치(y_lo/y_hi 있음)이면 cy로, 가로 배치이면 cx로 검색."""
    vertical = bool(panels and 'y_lo' in panels[0])

    if vertical and cy is not None:
        for p in panels:
            if p['y_lo'] <= cy <= p['y_hi']:
                return p
        if panels:
            nearest = min(panels, key=lambda p: abs((p['y_lo'] + p['y_hi']) / 2 - cy))
            print(f"  [경고] 폴리라인(중심Y={cy:.1f})이 패널 경계 밖 "
                  f"— STA {nearest['station']} 패널(Y={nearest['y_lo']:.1f}"
                  f"~{nearest['y_hi']:.1f})로 강제 매핑됩니다. 위치를 확인하세요.")
            return nearest
    else:
        for p in panels:
            if p['x_origin'] <= cx <= p['x_end']:
                return p
        if panels:
            nearest = min(panels, key=lambda p: abs((p['x_origin'] + p['x_end']) / 2 - cx))
            print(f"  [경고] 폴리라인(중심X={cx:.1f})이 패널 경계 밖 "
                  f"— STA {nearest['station']} 패널(X={nearest['x_origin']:.1f}"
                  f"~{nearest['x_end']:.1f})로 강제 매핑됩니다. 위치를 확인하세요.")
            return nearest
    return None
