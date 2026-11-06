# ゴミ収集日 통합 스키마 v1 (2026-09-17)

`data/normalized/<city_en>.json` — 도시당 1파일, JSON 배열. 레코드 1개 = 검색 단위 1개(町丁目, 필요 시 番地 분기).

```json
{
  "pref": "大阪府", "city": "大阪市", "city_en": "osaka", "ward": "北区", "ward_en": "kita",
  "town": "池田町", "chome": "1番", "sub": "ローレルハイツ北天満",
  "slug": "osaka/kita/ikedacho-1",
  "types": {
    "burnable":   {"label": "普通ごみ",        "days": ["月","木"], "weeks": null, "time": "8:30~10:30"},
    "resource":   {"label": "資源ごみ",        "days": ["木"],     "weeks": null, "time": null},
    "plastic":    {"label": "プラスチック資源", "days": ["月"],     "weeks": null, "time": null},
    "paper_cloth":{"label": "古紙・衣類",      "days": ["木"],     "weeks": null, "time": null},
    "nonburnable":{"label": "燃えないごみ",    "days": ["火"],     "weeks": [2,4], "time": null},
    "bulky":      {"label": "粗大ごみ",        "days": ["木"],     "weeks": [2],   "time": null, "note": "申込制"}
  },
  "rules": {"holiday_collection": "祝日も収集", "time_by": "8:30", "yearend": "12/31~1/3 休止"},
  "source": {"url": "https://www.city.osaka.lg.jp/contents/wdu150/trashmap/kita.csv", "fetched": "2026-09-17", "basis": "official_csv|official_html|official_xlsx|official_pdf"},
  "notes": "同一町でも番地で異なる場合は sub に分岐名"
}
```

규칙
- `types` 키는 위 6개 표준 키만 사용. 도시 고유 명칭은 `label`에 보존. 해당 없으면 키 생략.
- `days`: 요일 문자(月火水木金土日). `weeks`: 격주/월N회면 [1,3] 같은 주차 배열, 매주면 null. `time`: 수거 시간대 문자열 또는 null.
- `data/yearend.json`은 연도별 검증 출처와 표시 상태를 담습니다. `kind`는 `confirmed`(해당 연도 공지에서 날짜 확인), `annual`(통년 규칙), `unconfirmed`(날짜 미확정), `previous`(전년 참고)입니다. 전년 행은 주간 수거 계산에 쓰지 않고 연말연시 안내 페이지의 `昨年(YYYY-YY)は…` 참고 줄에만 표시합니다.
- `data/yearend.json`의 확인된 `period`는 `{ "start": "2026-12-31", "end": "2027-01-03" }` 형식이며, 시작일·종료일을 포함합니다. `source_url`은 연말연시 공식 안내, `display_note`는 사용자에게 보일 출처 설명입니다. 날짜가 없거나 `kind`가 `unconfirmed`이면 날짜를 화면에 표시하지 않고 요일 수거 계산에도 적용하지 않습니다. 기존 `rules.yearend` 문자열은 연도별 검증 증거가 아니므로 확정으로 취급하지 않습니다.
- `slug`: 로마자 `city_en/ward_en/<町 로마자>-<丁目·番地>` (ASCII만, 소문자, 하이픈). 町 로마자는 `pykakasi`로 생성해 `romaji` 필드에도 저장.
- 원본 필드는 버리지 말고 `raw`에 그대로 보관(디버깅용, 사이트엔 안 씀).
- 검증: 한 도시 파일에 slug 중복 0, days 값이 요일 집합 밖이면 실패.
