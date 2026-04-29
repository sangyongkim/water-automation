"""
Step 2: AutoCAD DXF → HEC-RAS geometry 업데이트
================================================
AutoCAD에서 수정한 두 가지를 HEC-RAS geometry 파일에 반영합니다:
  - '계획단면' 레이어 폴리라인 → #Sta/Elev 데이터 교체
  - '제방'     레이어 마커 이동 → Bank Sta= 값 교체  (1cm 이상 변화 시)

실행: python step2_to_hecras.py
"""

import os
import sys

import config
import utils


def main():
    print("=" * 50)
    print("Step 2: DXF → HEC-RAS Geometry 업데이트")
    print("=" * 50)

    # 파일 존재 확인
    for path, label in [
        (config.DXF_FILE,              "DXF"),
        (config.PANEL_META,            "패널 메타"),
        (config.HECRAS_GEOMETRY_FILE,  "Geometry"),
    ]:
        if not os.path.exists(path):
            print(f"[오류] {label} 파일 없음: {path}")
            sys.exit(1)

    # ── 1. 계획단면 폴리라인 읽기 ─────────────────────────────
    print(f"\n[1] 계획단면 읽는 중...")
    planned = utils.read_planned_sections(
        dxf_file=config.DXF_FILE,
        panel_meta_file=config.PANEL_META,
        planned_layer=config.LAYER_PLANNED,
    )
    if planned:
        print(f"  {len(planned)}개 계획단면 감지:")
        for key, pts in planned.items():
            elev_min = min(e for _, e in pts)
            elev_max = max(e for _, e in pts)
            print(f"    - {key}: {len(pts)}점 "
                  f"(거리 {pts[0][0]:.1f}~{pts[-1][0]:.1f}m, "
                  f"표고 {elev_min:.2f}~{elev_max:.2f})")
    else:
        print("  '계획단면' 레이어에 폴리라인 없음")

    # ── 2. 제방 마커 위치 읽기 + geometry 현재값 비교 ─────────
    print(f"\n[2] 제방 위치 읽는 중...")
    dxf_banks = utils.read_bank_stations(
        dxf_file=config.DXF_FILE,
        panel_meta_file=config.PANEL_META,
        levee_layer=config.LAYER_LEVEE,
    )

    xs_list  = utils.parse_geometry(config.HECRAS_GEOMETRY_FILE)
    xs_by_key = {xs.key: xs for xs in xs_list}

    THRESHOLD = 0.01  # 1cm 미만 변화는 노이즈로 무시
    changed_banks = {}
    for xs_key, (new_left, new_right) in dxf_banks.items():
        xs = xs_by_key.get(xs_key)
        if xs is None:
            continue
        old_left, old_right = xs.bank_sta
        if (abs(new_left  - old_left)  > THRESHOLD or
                abs(new_right - old_right) > THRESHOLD):
            changed_banks[xs_key] = (new_left, new_right)
            print(f"  변경 감지: {xs_key}")
            print(f"    좌안: {old_left:.2f} → {new_left:.2f} m  |  "
                  f"우안: {old_right:.2f} → {new_right:.2f} m")

    if not changed_banks:
        print("  제방 위치 변경 없음 (1cm 미만 차이는 무시)")

    # ── 3. 변경 사항 없으면 중단 ──────────────────────────────
    if not planned and not changed_banks:
        print("\n[중단] 변경 사항이 없습니다.")
        sys.exit(0)

    # ── 4. 사용자 확인 ────────────────────────────────────────
    summary_parts = []
    if planned:
        summary_parts.append(f"계획단면 {len(planned)}개 (#Sta/Elev 교체)")
    if changed_banks:
        summary_parts.append(f"제방 위치 {len(changed_banks)}개 (Bank Sta 교체)")
    print(f"\n업데이트 예정: {', '.join(summary_parts)}")

    ans = input("HEC-RAS geometry 파일을 업데이트하시겠습니까? (y/n): ").strip().lower()
    if ans != 'y':
        print("취소되었습니다.")
        sys.exit(0)

    # ── 5. geometry 파일 업데이트 ─────────────────────────────
    print(f"\nGeometry 파일 업데이트 중: {config.HECRAS_GEOMETRY_FILE}")
    made_backup = False

    if planned:
        updates = []
        for xs_key, sta_elev in planned.items():
            parts = xs_key.split('|')
            if len(parts) == 3:
                updates.append((parts[0], parts[1], parts[2], sta_elev))
            else:
                print(f"  [경고] 잘못된 키 형식: {xs_key} — 건너뜀")
        utils.update_geometry_xs(
            filepath=config.HECRAS_GEOMETRY_FILE,
            updates=updates,
            backup=True,
        )
        made_backup = True

    if changed_banks:
        utils.update_geometry_bank_sta(
            filepath=config.HECRAS_GEOMETRY_FILE,
            bank_updates=changed_banks,
            backup=not made_backup,
        )
        made_backup = True

    # Bank Sta와 Levee 스테이션을 항상 동기화
    # (이전 실행에서 Bank Sta만 바뀐 경우도 포함)
    n_levee = utils.sync_levee_to_bank_sta(
        filepath=config.HECRAS_GEOMETRY_FILE,
        backup=not made_backup,
    )
    if n_levee == 0:
        print("  Levee 스테이션: 변경 없음 (Bank Sta와 이미 일치)")
    made_backup = True

    # Bank Sta와 Manning's n 구역 경계를 항상 동기화
    n_mann = utils.sync_mann_to_bank_sta(
        filepath=config.HECRAS_GEOMETRY_FILE,
        backup=False,
    )
    if n_mann == 0:
        print("  Manning's n 구역: 변경 없음 (Bank Sta와 이미 일치)")

    print(f"\n[완료] Step 3 (HEC-RAS 실행)을 실행하세요.")
    print(f"       원본 백업: {config.HECRAS_GEOMETRY_FILE}.bak")


if __name__ == '__main__':
    main()
