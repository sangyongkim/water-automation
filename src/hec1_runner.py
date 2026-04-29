"""
hec1_runner.py
==============
HEC-1.exe를 멀티코어 환경에서 병렬 실행하고 진행 상황을 시각화합니다.

핵심 로직:
1. 격리 실행: 각 작업마다 별도 폴더를 생성하여 TAPE21 등 임시파일 충돌 방지
2. 병렬화: concurrent.futures를 사용하여 CPU 스레드만큼 동시 해석
3. 진행바: sys.stdout.write를 이용해 한 줄에서 진행률 업데이트
"""

import os
import subprocess
import shutil
import concurrent.futures
import sys

def run_hec1_isolated(hec1_exe: str, dat_file: str, out_file: str, timeout: int = 120) -> bool:
    """격리된 환경에서 HEC-1을 실행하고 결과(.OUT)를 회수합니다."""
    hec1_exe = os.path.abspath(hec1_exe)
    work_dir = os.path.dirname(os.path.abspath(dat_file))
    dat_name = os.path.basename(dat_file)
    out_name = os.path.basename(out_file)
    
    # 1. 고유 임시 폴더 생성
    base_no_ext = os.path.splitext(dat_name)[0]
    temp_dir = os.path.join(work_dir, f"temp_{base_no_ext}")
    os.makedirs(temp_dir, exist_ok=True)
    
    # 2. 파일 복사 및 실행 준비
    temp_dat = os.path.join(temp_dir, dat_name)
    temp_out = os.path.join(temp_dir, out_name)
    shutil.copy2(dat_file, temp_dat)
    
    # 3. HEC-1 표준 입력 스트림 (입력파일\n 출력파일\n DSS스킵엔터\n)
    stdin_input = f"{dat_name}\n{out_name}\n\n"
    success = False
    
    try:
        subprocess.run(
            [hec1_exe], input=stdin_input, capture_output=True,
            text=True, timeout=timeout, cwd=temp_dir
        )
        
        # 4. 결과 파일 회수: 실패했더라도 에러 분석을 위해 OUT 파일이 있다면 무조건 이동
        if os.path.isfile(temp_out):
            shutil.move(temp_out, out_file)
            success = _check_normal_end(out_file)
            
    except Exception:
        pass
    finally:
        # 5. 임시 폴더 삭제 (찌꺼기 파일 정리)
        try: shutil.rmtree(temp_dir, ignore_errors=True)
        except: pass
            
    return success

def _check_normal_end(out_file: str) -> bool:
    """정상 종료 문자열 확인"""
    try:
        with open(out_file, 'r', encoding='ascii', errors='replace') as f:
            return 'NORMAL END OF HEC-1' in f.read()
    except: return False

def _run_single_job(args):
    """병렬 처리를 위한 단일 작업 래퍼"""
    hec1_exe, job, timeout = args
    success = run_hec1_isolated(hec1_exe, job['dat'], job['out'], timeout)
    job_result = dict(job)
    job_result['success'] = success
    return job_result

def run_all(hec1_exe: str, jobs: list[dict], timeout: int = 120) -> list[dict]:
    """모든 작업을 병렬로 실행하고 진행바를 출력합니다."""
    total = len(jobs)
    max_workers = os.cpu_count() or 4
    
    print(f"  병렬 해석 시작 ({max_workers} 스레드 / 총 {total}개 케이스)")
    print("-" * 75)
    
    results = []
    args_list = [(hec1_exe, job, timeout) for job in jobs]
    completed = success_count = fail_count = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_run_single_job, args) for args in args_list]
        for future in concurrent.futures.as_completed(futures):
            job_result = future.result()
            results.append(job_result)
            completed += 1
            
            if job_result['success']: success_count += 1
            else: fail_count += 1
                
            # 진행바 업데이트
            percent = int((completed / total) * 100)
            bar = '█' * (30 * completed // total) + '░' * (30 - 30 * completed // total)
            sys.stdout.write(f"\r  진행률 |{bar}| {percent:3d}% ({completed}/{total}) [성공:{success_count}|실패:{fail_count}]")
            sys.stdout.flush()

    print("\n" + "-" * 75)
    results.sort(key=lambda x: (x['return_period'], x['duration']))
    return results