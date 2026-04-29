@echo off
chcp 65001 > nul
title HEC-RAS CAD Bridge EXE 빌드

echo.
echo ================================================
echo   HEC-RAS CAD Bridge EXE 빌드
echo ================================================
echo.

:: PyInstaller 확인 및 설치
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
if exist dist\hecras_launcher (
    echo 이전 빌드 폴더 정리 중...
    rmdir /s /q dist\hecras_launcher
)
if exist build\hecras_launcher (
    rmdir /s /q build\hecras_launcher
)

:: 빌드 실행
echo 빌드 시작 (수 분 소요될 수 있습니다)...
echo.
python -m PyInstaller launcher.spec --noconfirm

if %errorlevel% neq 0 (
    echo.
    echo [오류] 빌드 실패. 위 오류 메시지를 확인하세요.
    pause
    exit /b 1
)

:: config.py를 dist 폴더에 복사 (사용자 편집용)
echo.
echo config.py 복사 중...
copy /y config.py dist\hecras_launcher\config.py > nul

:: 사용설명서도 복사
copy /y 사용설명서.md dist\hecras_launcher\사용설명서.md > nul
copy /y README.md dist\hecras_launcher\README.md > nul

:: 빌드 결과 확인
echo.
echo ================================================
echo   빌드 완료!
echo ================================================
echo.
echo 배포 폴더: dist\hecras_launcher\
echo.
dir dist\hecras_launcher\hecras_launcher.exe 2>nul
echo.
echo 배포 방법:
echo   dist\hecras_launcher\ 폴더를 통째로 압축하여 전달
echo.
echo 수신자 사용법:
echo   1. 폴더 압축 해제
echo   2. config.py 를 텍스트 편집기로 열어 경로 수정
echo   3. hecras_launcher.exe 더블클릭
echo.
pause
