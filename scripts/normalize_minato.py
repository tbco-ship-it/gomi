#!/usr/bin/env python3
"""Normalize Minato Ward (港区) Garbage Collection Schedule
Source: Official Web & PDFs (https://www.city.minato.tokyo.jp/unei/2025gomikarenda.html)
Output: data/wip/minato.json -> data/normalized/minato.json
"""
import json
import os
import re
import unicodedata
from typing import Dict, List, Any, Set
import pykakasi

kakasi = pykakasi.kakasi()
VALID_DAYS = {"月", "火", "水", "木", "金", "土", "日"}
TODAY_STR = "2026-09-17"

# 15 Calendar Schedule Patterns:
# (burnable_days, nonburnable_days, nonburnable_weeks, resource_days, plastic_days)
CALENDAR_PATTERNS = {
    1: (["月", "木"], ["火"], [2, 4], ["土"], ["水"]),
    2: (["月", "木"], ["火"], [1, 3], ["土"], ["水"]),
    3: (["月", "木"], ["金"], [2, 4], ["水"], ["土"]),
    4: (["月", "木"], ["金"], [1, 3], ["水"], ["土"]),
    5: (["火", "金"], ["土"], [2, 4], ["木"], ["月"]),
    6: (["火", "金"], ["水"], [1, 3], ["月"], ["木"]),
    7: (["火", "金"], ["土"], [1, 3], ["木"], ["月"]),
    8: (["火", "金"], ["水"], [2, 4], ["月"], ["木"]),
    9: (["水", "土"], ["木"], [2, 4], ["火"], ["金"]),
    10: (["水", "土"], ["木"], [1, 3], ["火"], ["金"]),
    11: (["水", "土"], ["月"], [2, 4], ["金"], ["火"]),
    12: (["水", "土"], ["月"], [1, 3], ["金"], ["火"]),
    13: (["火", "木", "土"], ["水"], None, ["金"], ["月"]), # 繁華街（新橋）
    14: (["月", "水", "金"], ["火"], None, ["木"], ["土"]), # 繁華街（六本木）
    15: ([], ["月"], None, ["火"], ["木"]), # 台場（不燃:月, 瓶缶:火, プラ:木, 古紙:土, 可燃:管路収集）
}

MINATO_AREAS = [
    ('赤坂1丁目', 1),
    ('赤坂2・6・9丁目', 3),
    ('赤坂3・4・5・7・8丁目', 4),
    ('麻布十番1～4丁目', 9),
    ('麻布台1丁目', 1),
    ('麻布台2・3丁目', 9),
    ('麻布永坂町', 9),
    ('麻布狸穴町', 9),
    ('愛宕1・2丁目', 1),
    ('海岸1丁目', 5),
    ('海岸2・3丁目', 6),
    ('北青山1～3丁目', 5),
    ('港南1～5丁目', 4),
    ('芝1・2・5丁目', 7),
    ('芝3丁目', 11),
    ('芝4丁目', 8),
    ('芝浦1～3丁目', 8),
    ('芝浦4丁目', 6),
    ('芝公園1・2丁目', 5),
    ('芝公園3・4丁目', 1),
    ('芝大門1・2丁目', 5),
    ('白金1・3・5丁目', 2),
    ('白金2・4・6丁目', 10),
    ('白金台1丁目', 9),
    ('白金台2～5丁目', 10),
    ('新橋1丁目', 2),
    ('新橋2丁目1～5番、10～14番、18～21番', 5),
    ('新橋2丁目6～9番、15～17番', 13),
    ('新橋3丁目1～7番、26番', 5),
    ('新橋3丁目8～25番', 13),
    ('新橋4丁目1～3番、9番、19番4号、22～31番', 5),
    ('新橋4丁目5～7番、10・11番、14・15番、18～21番（19番4号除く）', 13),
    ('新橋5・6丁目', 5),
    ('台場1・2丁目', 15),
    ('高輪1・2丁目', 1),
    ('高輪3・4丁目', 3),
    ('虎ノ門1～5丁目', 1),
    ('西麻布1丁目', 7),
    ('西麻布2・3丁目', 8),
    ('西麻布4丁目', 5),
    ('西新橋1～3丁目', 2),
    ('浜松町1・2丁目', 5),
    ('東麻布1～3丁目', 9),
    ('東新橋1・2丁目', 5),
    ('三田1丁目', 9),
    ('三田2～5丁目', 11),
    ('南青山1・2丁目', 7),
    ('南青山3～6丁目', 6),
    ('南青山7丁目', 5),
    ('南麻布1～4丁目', 12),
    ('南麻布5丁目', 8),
    ('元赤坂1・2丁目', 4),
    ('元麻布1～3丁目', 12),
    ('六本木1丁目', 1),
    ('六本木2丁目', 3),
    ('六本木3丁目1～7番、15番2～21号・29号、16～18番', 1),
    ('六本木3丁目8～14番、15番22～25号', 14),
    ('六本木4丁目1～3番', 3),
    ('六本木4丁目4～12番', 14),
    ('六本木5丁目1～3番', 14),
    ('六本木5丁目4～18番', 2),
    ('六本木6丁目', 2),
    ('六本木7丁目1～12番、13番1号・9～11号、15～23番', 7),
    ('六本木7丁目13番5～8号、14番', 14),
]


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return re.sub(r"[^a-z0-9]+", "-", romaji).strip("-")


def parse_area_string(raw: str):
    s = unicodedata.normalize("NFKC", raw).strip()
    m = re.match(r"^([^\d]+)(\d+.*?丁目)(.*)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
    m2 = re.match(r"^([^\d]+)(\d+丁目)(.*)$", s)
    if m2:
        return m2.group(1).strip(), m2.group(2).strip(), m2.group(3).strip()
    return s, "", ""


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(base_dir, "data", "wip", "minato.json")

    records = []
    used_slugs: Set[str] = set()

    for raw_text, cal_num in MINATO_AREAS:
        town, chome, sub = parse_area_string(raw_text)
        burn_days, non_days, non_weeks, res_days, pla_days = CALENDAR_PATTERNS[cal_num]

        romaji_town = to_romaji(town)
        chome_slug = to_romaji(chome) if chome else ""
        sub_slug = to_romaji(sub) if sub else ""

        slug_parts = ["minato", romaji_town]
        if chome_slug:
            slug_parts.append(chome_slug)
        if sub_slug:
            slug_parts.append(sub_slug)

        base_slug = "-".join([s for s in slug_parts if s])
        base_slug = re.sub(r"[^a-z0-9\-]+", "-", base_slug).strip("-")
        base_slug = re.sub(r"-+", "-", base_slug)
        if base_slug.startswith("minato-"):
            base_slug = "minato/" + base_slug[len("minato-") :]
        elif base_slug == "minato":
            base_slug = "minato/area"

        slug = base_slug
        idx = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{idx}"
            idx += 1
        used_slugs.add(slug)

        time_str = "朝8:00まで"
        if cal_num in (13, 14, 15) or "繁華街" in sub:
            time_str = "朝7:30まで"

        types = {}
        if burn_days:
            types["burnable"] = {
                "label": "可燃ごみ",
                "days": burn_days,
                "weeks": None,
                "time": time_str,
            }
        elif cal_num == 15:
            # Daiba uses pneumatic collection
            pass

        if non_days:
            types["nonburnable"] = {
                "label": "不燃ごみ",
                "days": non_days,
                "weeks": non_weeks,
                "time": time_str,
            }

        if res_days:
            types["resource"] = {
                "label": "資源" if cal_num != 15 else "飲食用びん・かん",
                "days": res_days,
                "weeks": None,
                "time": time_str,
            }

        if pla_days:
            types["plastic"] = {
                "label": "資源プラスチック",
                "days": pla_days,
                "weeks": None,
                "time": time_str,
            }

        if cal_num == 15:
            types["paper_cloth"] = {
                "label": "ペットボトル・古紙",
                "days": ["土"],
                "weeks": None,
                "time": time_str,
            }

        rules_note = {}
        if cal_num == 15:
            rules_note["note"] = "台場地区の可燃ごみは管路収集（24時間投入可能）"

        record = {
            "pref": "東京都",
            "city": "港区",
            "city_en": "minato",
            "ward": "",
            "ward_en": "",
            "town": town,
            "chome": chome,
            "sub": sub,
            "romaji": romaji_town,
            "slug": slug,
            "types": types,
            "rules": {
                "holiday_collection": "祝日も収集（年末年始を除く）",
                "time_by": time_str,
                "yearend": "12/31~1/3 休止",
                **rules_note,
            },
            "source": {
                "url": "https://www.city.minato.tokyo.jp/unei/2025gomikarenda.html",
                "fetched": TODAY_STR,
                "basis": "official_pdf",
            },
            "raw": {
                "area_raw": raw_text,
                "calendar_num": cal_num,
                "burnable": burn_days,
                "nonburnable": non_days,
                "nonburnable_weeks": non_weeks,
                "resource": res_days,
                "plastic": pla_days,
            },
        }
        records.append(record)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"minato: {len(records)} records written -> {out_path}")


if __name__ == "__main__":
    main()
