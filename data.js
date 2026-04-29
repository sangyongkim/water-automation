const toolsData = [
    {
        id: 1,
        title: "HEC-1 자동화 도구",
        description: "HEC-1을 사용하여 임계지속기간을 산정하고 각 빈도별 홍수량을 자동으로 추출하는 도구입니다. (v0.6 배포판)",
        version: "v0.6.0",
        date: "2026-04-29",
        category: "수문해석",
        fileName: "hec1_auto_v0.6_dist.zip",
        filePath: "tools/hec1-auto/dist/hec1_auto_v0.6_dist.zip",
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
        title: "WAMIS 시강우 수집기",
        description: "WAMIS 강우관측소의 시강우 데이터를 자동으로 수집하여 CSV로 저장하는 도구입니다. 6개월 조회 제한을 자동 분할하여 장기간 데이터를 연속 수집하며, 5개 관할기관(K-water·기상청·환경부·농어촌공사·한수원) 관측소를 모두 지원합니다. (v1.0 배포판)",
        version: "v1.0.0",
        date: "2026-04-29",
        category: "수문해석",
        fileName: "wamis_rainfall_v1.0.zip",
        filePath: "tools/wamis-rainfall/dist/wamis_rainfall_v1.0.zip",
        tags: ["WAMIS", "시강우", "강우관측소", "자동수집", "배포판"]
    }
    // 여기에 새로운 도구를 추가하세요
];
