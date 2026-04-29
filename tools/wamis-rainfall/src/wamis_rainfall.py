"""
WAMIS 시강우 데이터 자동 수집기
- POST /wkw/rf_hrdata_list.do  → JSON 응답
- 응답 필드: ymdh(YYYYMMDDHH), rf(강우량), vyrf(검증), oyrf(원시)
- 6개월 단위 분할 요청
- 다중 관측소 지원

[organ 코드 실험 결과]
WAMIS 강우관측소 관할기관은 5개(기상청·환경부·K-water·농어촌공사·한수원)이나,
API 내부적으로는 DB가 2개 그룹으로 분리되어 있음:
  - organ=04 (K-water 전용 DB): organ=04만 응답
  - organ=01/02/03/05 (비K-water 공유 DB): 어떤 비-04 코드로 요청해도 동일 데이터 반환
따라서 AUTO_ORGANS = ["04", "01"] 두 가지 시도로 모든 관측소 커버 가능.
"""

import time
import logging
import argparse
from io import StringIO
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

import requests
import pandas as pd

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

BASE_URL = "https://www.wamis.go.kr"
API_URL  = f"{BASE_URL}/wkw/rf_hrdata_list.do"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE_URL}/wkw/rf_hrdata.do",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

REQUEST_DELAY = 1.5   # 요청 간 대기 (초)
MAX_RETRIES   = 3     # 실패 시 재시도 횟수
RETRY_WAIT    = 5     # 재시도 대기 (초)
PERIOD_MONTHS = 6     # 1회 최대 조회 기간 (월)
# organ 자동감지 시도 순서
# 04 = K-water 전용 DB / 01 = 나머지 4개 기관 공유 DB (어느 비-04 코드나 동일)
AUTO_ORGANS = ["04", "01"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 유틸리티
# ---------------------------------------------------------------------------

def split_period(start: datetime, end: datetime):
    """start ~ end 를 PERIOD_MONTHS 단위로 분할하여 (s, e) 쌍을 yield."""
    current = start
    while current <= end:
        period_end = current + relativedelta(months=PERIOD_MONTHS) - timedelta(days=1)
        if period_end > end:
            period_end = end
        yield current, period_end
        current = period_end + timedelta(days=1)


def parse_json(data: dict, station_code: str) -> pd.DataFrame | None:
    """
    WAMIS JSON 응답 파싱.
    응답 구조: {"max": [...], "rows": [{"ymdh": "2024010101", "rf": "0", ...}]}
    ymdh 포맷: YYYYMMDDHH (10자리)
    rf   : 관측 강우량 (mm), null 허용
    vyrf : 검증 강우량 (mm), null 허용
    oyrf : 원시 강우량 (mm), null 허용
    """
    rows = data.get("rows")
    if not rows:
        return None

    df = pd.DataFrame(rows)

    df["datetime"] = pd.to_datetime(df["ymdh"], format="%Y%m%d%H", errors="coerce")
    for col in ("rf", "vyrf", "oyrf"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["station"] = station_code

    # 최종 컬럼 순서 정리
    keep = ["station", "datetime", "rf", "vyrf", "oyrf"]
    df = df[[c for c in keep if c in df.columns]]
    df = df.rename(columns={"rf": "rainfall_mm", "vyrf": "verified_mm", "oyrf": "original_mm"})
    return df.sort_values("datetime").reset_index(drop=True)


# ---------------------------------------------------------------------------
# 핵심 수집 로직
# ---------------------------------------------------------------------------

def init_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get(BASE_URL, timeout=15)
        log.info("세션 초기화 완료")
    except requests.RequestException as e:
        log.warning(f"세션 초기화 중 오류 (계속 진행): {e}")
    return session


def fetch_period(
    session: requests.Session,
    station_code: str,
    organ: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame | None:
    """단일 기간의 시강우 데이터를 요청하고 DataFrame을 반환."""
    payload = {
        "code":  station_code,
        "organ": organ,
        "date1": start.strftime("%Y%m%d"),
        "date2": end.strftime("%Y%m%d"),
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.post(API_URL, data=payload, timeout=30)
            resp.raise_for_status()

            data = resp.json()
            df = parse_json(data, station_code)

            if df is None or df.empty:
                log.warning(f"  데이터 없음: {start.date()} ~ {end.date()}")
                return None

            log.info(f"  수집 성공: {start.date()} ~ {end.date()} ({len(df)}행)")
            return df

        except (requests.RequestException, ValueError) as e:
            log.warning(f"  요청 실패 ({attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_WAIT)

    log.error(f"  최대 재시도 초과: {start.date()} ~ {end.date()}")
    return None


def detect_organ(
    session: requests.Session,
    station_code: str,
    probe_date: datetime,
) -> str | None:
    """지정 organ이 데이터를 반환하지 않을 때 유효한 organ 코드를 자동 탐색."""
    probe_end = probe_date + relativedelta(months=1) - timedelta(days=1)
    for organ in AUTO_ORGANS:
        payload = {
            "code":  station_code,
            "organ": organ,
            "date1": probe_date.strftime("%Y%m%d"),
            "date2": probe_end.strftime("%Y%m%d"),
        }
        try:
            resp = session.post(API_URL, data=payload, timeout=20)
            rows = resp.json().get("rows", [])
            if rows:
                log.info(f"  organ 자동감지: {organ}")
                return organ
        except Exception:
            pass
    return None


def collect_station(
    session: requests.Session,
    station_code: str,
    organ: str,
    start_date: datetime,
    end_date: datetime,
) -> pd.DataFrame:
    """관측소 1개의 전체 기간 데이터를 수집하여 반환."""
    log.info(f"[관측소 {station_code}] {start_date.date()} ~ {end_date.date()} 수집 시작")
    chunks = []
    organ_detected = False

    for s, e in split_period(start_date, end_date):
        df = fetch_period(session, station_code, organ, s, e)

        # 첫 번째 기간에서 데이터가 없으면 organ 자동감지 시도 (1회만)
        if df is None and not organ_detected:
            detected = detect_organ(session, station_code, s)
            if detected:
                organ = detected
                df = fetch_period(session, station_code, organ, s, e)
            organ_detected = True

        if df is not None:
            chunks.append(df)
        time.sleep(REQUEST_DELAY)

    if not chunks:
        log.warning(f"[관측소 {station_code}] 수집된 데이터 없음")
        return pd.DataFrame()

    result = pd.concat(chunks, ignore_index=True).drop_duplicates(subset=["station", "datetime"])
    log.info(f"[관측소 {station_code}] 총 {len(result)}행 수집 완료")
    return result


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

BANNER = """
================================================
  WAMIS 시강우 데이터 자동 수집기 v1.0
  https://www.wamis.go.kr
================================================
"""


def prompt_input(label: str, default: str) -> str:
    val = input(f"  {label} [{default}]: ").strip()
    return val if val else default


def interactive_mode() -> dict:
    """더블클릭 실행 시 사용자 입력을 대화형으로 받는다."""
    print(BANNER)
    print("【대화형 모드】 Enter 키를 누르면 [ ] 안의 기본값을 사용합니다.\n")

    today = datetime.today().strftime("%Y%m%d")

    raw_codes = prompt_input("관측소 코드 (여러 개면 쉼표로 구분, 예: 10011100,10234010)", "10011100")
    codes = [c.strip() for c in raw_codes.split(",") if c.strip()]

    start = prompt_input("시작일 (YYYYMMDD)", "20200101")
    end   = prompt_input("종료일 (YYYYMMDD)", today)
    out   = prompt_input("저장 파일명 (.csv)", "wamis_rainfall.csv")
    if not out.endswith(".csv"):
        out += ".csv"

    print()
    return {"codes": codes, "organ": "04", "start": start, "end": end, "out": out}


def parse_args():
    parser = argparse.ArgumentParser(
        description="WAMIS 시강우 데이터 자동 수집기",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 관측소 1개, 2024년 전체
  wamis_rainfall.exe --codes 10011100 --start 20240101 --end 20241231

  # 관측소 여러 개, 2020~2022년
  wamis_rainfall.exe --codes 10011100 10014010 --start 20200101 --end 20221231 --out multi.csv
""",
    )
    parser.add_argument(
        "-c", "--codes",
        nargs="+",
        metavar="CODE",
        help="관측소 코드 (여러 개 가능)",
    )
    parser.add_argument(
        "-o", "--organ",
        default="04",
        help="기관 코드 (기본: 04 = K-water, 자동감지됨)",
    )
    parser.add_argument(
        "--start",
        help="시작일 YYYYMMDD",
    )
    parser.add_argument(
        "--end",
        default=datetime.today().strftime("%Y%m%d"),
        help="종료일 YYYYMMDD (기본: 오늘)",
    )
    parser.add_argument(
        "--out",
        default="wamis_rainfall.csv",
        help="출력 파일명 (기본: wamis_rainfall.csv)",
    )
    return parser.parse_args()


def main():
    import sys

    # Windows 콘솔 UTF-8 출력 설정
    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    args = parse_args()

    # 필수 인자가 없으면 대화형 모드
    if not args.codes or not args.start:
        params = interactive_mode()
    else:
        print(BANNER)
        params = {
            "codes": args.codes,
            "organ": args.organ,
            "start": args.start,
            "end":   args.end,
            "out":   args.out,
        }

    def wait_exit():
        try:
            input("\nEnter 키를 눌러 종료...")
        except (EOFError, OSError):
            pass

    try:
        start_dt = datetime.strptime(params["start"], "%Y%m%d")
        end_dt   = datetime.strptime(params["end"],   "%Y%m%d")
    except ValueError:
        log.error("날짜 형식 오류 - YYYYMMDD 형식으로 입력하세요.")
        wait_exit()
        sys.exit(1)

    if start_dt > end_dt:
        log.error("시작일이 종료일보다 늦습니다.")
        wait_exit()
        sys.exit(1)

    session = init_session()
    all_frames = []

    for code in params["codes"]:
        df = collect_station(session, code, params["organ"], start_dt, end_dt)
        if not df.empty:
            all_frames.append(df)

    if not all_frames:
        log.error("수집된 데이터가 없습니다.")
        wait_exit()
        sys.exit(1)

    final = pd.concat(all_frames, ignore_index=True)
    final.to_csv(params["out"], index=False, encoding="utf-8-sig")
    log.info(f"저장 완료: {params['out']} ({len(final)}행, {final['station'].nunique()}개 관측소)")

    wait_exit()


if __name__ == "__main__":
    main()
