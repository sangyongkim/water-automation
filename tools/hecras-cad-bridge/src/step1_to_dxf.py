"""
Step 1: HEC-RAS geometry → AutoCAD DXF
=======================================
HEC-RAS .g0x 파일에서 횡단면 지형을 읽어 DXF로 내보냅니다.
HDF5 결과 파일이 있으면 홍수위선도 함께 그립니다.

실행: python step1_to_dxf.py
"""

import os
import sys

import config
import utils


def main():
    print("=" * 50)
    print("Step 1: HEC-RAS → DXF")
    print("=" * 50)

    # 1. geometry 파일 파싱
    if not os.path.exists(config.HECRAS_GEOMETRY_FILE):
        print(f"[오류] Geometry 파일 없음: {config.HECRAS_GEOMETRY_FILE}")
        sys.exit(1)

    print(f"\nGeometry 파일 읽는 중: {config.HECRAS_GEOMETRY_FILE}")
    xs_list = utils.parse_geometry(config.HECRAS_GEOMETRY_FILE)
    if not xs_list:
        print("[오류] 횡단면 데이터를 읽지 못했습니다.")
        sys.exit(1)
    print(f"  {len(xs_list)}개 횡단면 로드 완료")

    for xs in xs_list:
        left_bank, right_bank = xs.bank_sta
        print(f"  - {xs.river} / {xs.reach} / STA {xs.station} "
              f"({len(xs.sta_elev)}점, 제방: L={left_bank:.1f} R={right_bank:.1f})")

    # 2. 홍수위 읽기 (HDF5 있을 때만)
    wse_dict = None
    if os.path.exists(config.HECRAS_HDF_FILE):
        print(f"\nHDF5 결과 읽는 중: {config.HECRAS_HDF_FILE}")
        try:
            wse_dict = utils.read_wse_from_hdf(
                config.HECRAS_HDF_FILE,
                config.FLOOD_PROFILE_INDEX - 1,   # 0-index 변환
                xs_list
            )
            print(f"  {len(wse_dict)}개 홍수위 로드 완료")
            for key, wse in wse_dict.items():
                print(f"  - {key}: EL.{wse:.3f}")
        except Exception as e:
            print(f"  [주의] HDF5 읽기 실패 ({e}) — 홍수위선 생략")
            wse_dict = None
    else:
        print(f"\nHDF5 파일 없음 ({config.HECRAS_HDF_FILE}) — 홍수위선 생략")

    # 3. DXF 생성
    if os.path.exists(config.DXF_FILE):
        ans = input(
            f"\n[경고] 기존 DXF 파일이 있습니다: {config.DXF_FILE}\n"
            f"Step 1은 DXF를 처음부터 재생성하므로\n"
            f"AutoCAD에서 작성한 '{config.LAYER_PLANNED}' 계획단면이 모두 삭제됩니다.\n"
            f"계속하시겠습니까? (y/n): "
        ).strip().lower()
        if ans != 'y':
            print("취소되었습니다. 계획단면이 있으면 Step 2부터 진행하세요.")
            sys.exit(0)

    print(f"\nDXF 생성 중...")
    utils.create_xs_dxf(
        xs_list=xs_list,
        wse_dict=wse_dict,
        dxf_file=config.DXF_FILE,
        panel_meta_file=config.PANEL_META,
        cfg=config
    )

    print(f"\n[완료] AutoCAD에서 {config.DXF_FILE}을 열어 계획단면을 작성하세요.")
    print(f"       계획단면은 반드시 '{config.LAYER_PLANNED}' 레이어에 그려야 합니다.")


if __name__ == '__main__':
    main()
