"""
Step 4: 새 홍수위 → DXF 홍수위선 업데이트
==========================================
Step 3에서 추출한 홍수위(wse_results.json)로
DXF의 '홍수위' 레이어를 갱신합니다.

실행: python step4_update_dxf.py
"""

import json
import os
import sys

import config
import utils


def main():
    print("=" * 50)
    print("Step 4: DXF 홍수위선 업데이트")
    print("=" * 50)

    # 1. WSE JSON 읽기
    if not os.path.exists(config.WSE_JSON_FILE):
        print(f"[오류] WSE 파일 없음: {config.WSE_JSON_FILE}")
        print("  Step 3을 먼저 실행하세요.")
        sys.exit(1)

    with open(config.WSE_JSON_FILE, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    # 메타데이터 키(_로 시작) 분리
    profile_name = raw.get('_profile', '')
    wse_dict = {k: v for k, v in raw.items() if not k.startswith('_')}

    profile_label = f"  (프로파일: {profile_name})" if profile_name else ""
    print(f"\nWSE 읽기 완료: {len(wse_dict)}개 단면{profile_label}")
    for key, wse in wse_dict.items():
        print(f"  {key}: EL.{wse:.3f}")

    # 2. DXF 파일 확인
    if not os.path.exists(config.DXF_FILE):
        print(f"[오류] DXF 파일 없음: {config.DXF_FILE}")
        sys.exit(1)

    if not os.path.exists(config.PANEL_META):
        print(f"[오류] 패널 메타 파일 없음: {config.PANEL_META}")
        print("  Step 1을 다시 실행하세요.")
        sys.exit(1)

    # 3. 제방 부족 단면 확인 (홍수위 > 제방 최고 표고)
    print("\n제방 여유고 검토:")
    xs_list = utils.parse_geometry(config.HECRAS_GEOMETRY_FILE)
    xs_by_key = {xs.key: xs for xs in xs_list}

    for key, wse in wse_dict.items():
        xs = xs_by_key.get(key)
        if xs and xs.sta_elev:
            left_sta, right_sta = xs.bank_sta
            left_elev  = utils._interp_elev(xs.sta_elev, left_sta)
            right_elev = utils._interp_elev(xs.sta_elev, right_sta)
            levee_top  = max(left_elev, right_elev)
            freeboard  = levee_top - wse

            status = "OK" if freeboard >= 0 else f"[부족 {abs(freeboard):.2f}m]"
            print(f"  {key}: WSE={wse:.3f}, 제방고={levee_top:.3f}, "
                  f"여유고={freeboard:+.3f}m  {status}")

    # 4. DXF 홍수위 업데이트
    print(f"\nDXF 홍수위 업데이트 중: {config.DXF_FILE}")
    utils.update_dxf_wse(
        dxf_file=config.DXF_FILE,
        panel_meta_file=config.PANEL_META,
        wse_dict=wse_dict,
        flood_layer=config.LAYER_FLOOD,
        text_layer=config.LAYER_TEXT,
        text_height=config.TEXT_HEIGHT
    )

    print(f"\n[완료] AutoCAD에서 {config.DXF_FILE}을 다시 열어 결과를 확인하세요.")
    print("  제방 부족 단면은 계획단면을 수정하고 Step 2부터 반복합니다.")


if __name__ == '__main__':
    main()
