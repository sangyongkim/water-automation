@echo off
chcp 65001 > nul
echo.
echo ============================================================
echo   HEC-1 자동화 시스템  -  exe 빌드 (PyInstaller)
echo ============================================================
echo.

:: PyInstaller 설치 확인
where pyinstaller > nul 2>&1
if errorlevel 1 (
    echo [오류] PyInstaller가 설치되어 있지 않습니다.
    echo        설치 명령: pip install pyinstaller
    pause
    exit /b 1
)

:: 이전 빌드 정리
if exist build   rmdir /s /q build
if exist dist    rmdir /s /q dist
if exist hec1_auto.spec    del hec1_auto.spec
if exist make_template.spec del make_template.spec

set COMMON=--onefile --noconfirm ^
  --collect-data openpyxl ^
  --hidden-import excel_loader ^
  --hidden-import openpyxl.cell._writer

echo [1/2] hec1_auto.exe 빌드 중...
pyinstaller %COMMON% --name hec1_auto main.py
if errorlevel 1 (
    echo.
    echo [오류] hec1_auto.exe 빌드 실패
    pause
    exit /b 1
)

echo.
echo [2/2] make_template.exe 빌드 중...
pyinstaller %COMMON% --name make_template make_excel_template.py
if errorlevel 1 (
    echo.
    echo [오류] make_template.exe 빌드 실패
    pause
    exit /b 1
)

:: 빌드 중간 파일 정리
rmdir /s /q build
del hec1_auto.spec
del make_template.spec

echo.
echo ============================================================
echo   빌드 완료!
echo.
echo   dist\hec1_auto.exe    -  메인 분석 프로그램
echo   dist\make_template.exe -  input.xlsx 템플릿 생성기
echo.
echo   배포 패키지 구성:
echo     dist\hec1_auto.exe
echo     dist\make_template.exe
echo     설명서.md
echo ============================================================
echo.
pause
