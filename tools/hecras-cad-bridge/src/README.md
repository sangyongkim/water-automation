# HEC-RAS CAD Bridge

HEC-RAS 홍수 해석 ↔ AutoCAD 횡단면 자동 연동 도구

## 빠른 시작

1. `config.py` 열어 HEC-RAS **설치 경로**(`HECRAS_EXE`)와 **COM ID**(`HECRAS_COM_ID`) 확인
2. `hecras_launcher.exe` 더블클릭
3. 메뉴 `0` → 프로젝트 경로·DXF 경로·홍수위 프로파일 설정
4. 메뉴 `5` → 환경 점검
5. 메뉴 `1` → Step 1 시작

> Python 설치 불필요 — 실행 환경이 exe에 내장되어 있습니다.

## 작업 순서

```
Step 0 (메뉴 0): 경로·프로파일 설정 (프로젝트 바뀔 때마다)
Step 1 (메뉴 1): HEC-RAS geometry → DXF
  ↓  AutoCAD에서 계획단면 작성 (레이어: "계획단면")
Step 2 (메뉴 2): DXF → HEC-RAS geometry 업데이트
Step 3 (메뉴 3): HEC-RAS 자동 실행 → 홍수위 추출
Step 4 (메뉴 4): 홍수위 → DXF 갱신
  ↓  여유고 부족 단면 있으면 Step 2부터 반복
```

자세한 내용은 **사용설명서.md** 를 참고하세요.
