const toolsData = [
    {
        id: 1,
        title: "HEC-1 자동화 도구",
        description: "HEC-1을 사용하여 임계지속기간을 산정하고 각 빈도별 홍수량을 자동으로 추출하는 도구입니다. (v0.6 배포판)",
        version: "v0.7.0",
        date: "2026-05-24",
        category: "수문해석",
        fileName: "hec1_auto_v0.7_dist.zip",
        filePath: "tools/hec1-auto/dist/hec1_auto_v0.7_dist.zip",
        tags: ["HEC-1", "임계지속기간", "홍수량산정", "배포판"]
    }
    ,
    {
        id: 2,
        title: "HEC-RAS CAD Bridge",
        description: "HEC-RAS 홍수 해석 결과와 AutoCAD 횡단면 도면을 자동 연동하는 도구입니다. Geometry → DXF 내보내기, 계획단면 → HEC-RAS 업데이트, 홍수위 자동 추출 및 DXF 갱신을 지원합니다. (v1.3 배포판)",
        version: "v1.3.0",
        date: "2026-04-29",
        category: "수리해석",
        fileName: "hecras_launcher_v1.3.zip",
        filePath: "tools/hecras-cad-bridge/dist/hecras_launcher_v1.3.zip",
        tags: ["HEC-RAS", "AutoCAD", "DXF", "횡단면", "홍수위", "배포판"]
    }
    ,
    {
        id: 3,
        title: "HEC-RAS 횡단면 지형데이터 생성기",
        description: "측량 횡단 야장(CSV)을 입력받아 HEC-RAS Geometry 파일(.g01)과 프로젝트 파일(.prj)을 자동 생성하는 도구입니다. 거리형·No형 측점, Bank Station, Levee, Manning's n, 구조물 Description을 자동 처리하며 HEC-RAS 5.x 포맷에 완전 호환됩니다. (v1.0 배포판)",
        version: "v1.0.0",
        date: "2026-05-02",
        category: "수리해석",
        fileName: "hecras_geo_v1.0_dist.zip",
        filePath: "tools/hecras-geo/dist/hecras_geo_v1.0_dist.zip",
        tags: ["HEC-RAS", "횡단면", "지형데이터", "Geometry", "측량야장", "배포판"]
    }
    // 여기에 새로운 도구를 추가하세요
];
