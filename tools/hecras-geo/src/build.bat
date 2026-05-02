@echo off
chcp 65001 > nul
title HEC-RAS 횡단면 지형데이터 생성기 빌드

echo.
echo ================================================
echo   HEC-RAS 횡단면 지형데이터 생성기 빌드
echo ================================================
echo.

:: PyInstaller 확인
python -m PyInstaller --version > nul 2>&1
if %errorlevel% neq 0 (
    echo PyInstaller를 설치합니다...
    pip install pyinstaller
    if %errorlevel% neq 0 (
        echo [오류] PyInstaller 설치 실패
        pause
        exit /b 1
    )
)

echo PyInstaller 버전:
python -m PyInstaller --version
echo.

:: 이전 빌드 정리
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist
echo 이전 빌드 정리 완료
echo.

:: 빌드 실행
echo 빌드 시작 (수 분 소요될 수 있습니다)...
echo.
python -m PyInstaller hecras_geo.spec --noconfirm

if %errorlevel% neq 0 (
    echo.
    echo [오류] 빌드 실패. 위 오류 메시지를 확인하세요.
    pause
    exit /b 1
)

:: 배포 폴더에 부속 파일 복사
echo.
echo 부속 파일 복사 중...
copy /y 설명서.md         dist\hecras_geo\설명서.md         > nul
copy /y fieldbook.csv    dist\hecras_geo\fieldbook.csv    > nul
copy /y requirements.txt dist\hecras_geo\requirements.txt > nul
copy /y hecras_geo.py    dist\hecras_geo\hecras_geo.py    > nul

:: 배포 ZIP 생성
set VERSION=v1.0
set ZIP_NAME=..\dist\hecras_geo_%VERSION%_dist.zip

echo.
echo 배포 ZIP 생성 중: %ZIP_NAME%
powershell -Command "Compress-Archive -Path 'dist\hecras_geo' -DestinationPath '%ZIP_NAME%' -Force"

if %errorlevel% neq 0 (
    echo [오류] ZIP 생성 실패
    pause
    exit /b 1
)

echo.
echo ================================================
echo   빌드 완료!
echo ================================================
echo.
echo 배포 파일: %ZIP_NAME%
echo.
dir "..\dist\hecras_geo_%VERSION%_dist.zip" 2>nul
echo.
echo 배포 내용물:
echo   hecras_geo.exe   - 실행 파일 (Python 불필요)
echo   hecras_geo.py    - 소스 코드
echo   설명서.md         - 사용 설명서
echo   fieldbook.csv    - 샘플 입력 야장
echo   requirements.txt - Python 패키지 목록
echo.
pause
