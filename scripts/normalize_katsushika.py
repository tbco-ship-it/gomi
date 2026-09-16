#!/usr/bin/env python3
"""Normalize Katsushika Ward (葛飾区) Garbage Collection Schedule
Source: Official Web & Simplified Calendar PDFs (https://www.city.katsushika.lg.jp/kurashi/1000048/1017199/1020038.html)
Output: data/wip/katsushika.json -> data/normalized/katsushika.json
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

# 16 Collection Area Schedule Patterns:
# (burnable_days, nonburnable_days, nonburnable_weeks, resource_days, plastic_days)
KATSUSHIKA_PATTERNS = {
    1: (["月", "木"], ["金"], [2, 4], ["水"], ["土"]),
    2: (["月", "木"], ["金"], [1, 3], ["水"], ["土"]),
    3: (["月", "木"], ["火"], [1, 3], ["金"], ["水"]),
    4: (["月", "木"], ["火"], [2, 4], ["金"], ["水"]),
    5: (["月", "木"], ["火"], [1, 3], ["金"], ["土"]),
    6: (["月", "木"], ["火"], [2, 4], ["金"], ["土"]),
    7: (["火", "金"], ["土"], [2, 4], ["月"], ["木"]),
    8: (["火", "金"], ["土"], [1, 3], ["月"], ["木"]),
    9: (["火", "金"], ["水"], [1, 3], ["土"], ["月"]),
    10: (["火", "金"], ["水"], [2, 4], ["土"], ["月"]),
    11: (["火", "金"], ["水"], [2, 4], ["土"], ["木"]),
    12: (["水", "土"], ["木"], [2, 4], ["火"], ["金"]),
    13: (["水", "土"], ["木"], [1, 3], ["火"], ["金"]),
    14: (["水", "土"], ["月"], [2, 4], ["木"], ["火"]),
    15: (["水", "土"], ["月"], [1, 3], ["木"], ["火"]),
    16: (["水", "土"], ["月"], [1, 3], ["木"], ["金"]),
}

# Raw area definitions from official Katsushika page
KATSUSHIKA_AREAS = [
    (1, ["お花茶屋1～3丁目", "小菅1～4丁目", "東堀切1～3丁目", "堀切6～8丁目"]),
    (2, ["宝町1・2丁目", "堀切1～5丁目", "四つ木3・4丁目"]),
    (3, ["青戸3～6丁目", "立石5・6丁目"]),
    (4, ["青戸1・2丁目", "立石1・4・7・8丁目", "東立石1～4丁目"]),
    (5, ["白鳥1～3丁目", "四つ木1・2・5丁目"]),
    (6, ["立石2・3丁目"]),
    (7, ["新宿6丁目", "西水元1～6丁目", "東水元4～6丁目", "水元1～5丁目", "南水元1～4丁目"]),
    (8, ["金町4・5丁目", "新宿2・4・5丁目", "東金町1～8丁目", "東水元1～3丁目"]),
    (9, ["亀有1～5丁目", "西亀有1～4丁目"]),
    (10, ["青戸7・8丁目", "白鳥4丁目"]),
    (11, ["金町1・2丁目", "柴又1～3丁目", "高砂5～8丁目", "新宿1・3丁目"]),
    (12, ["金町3・6丁目", "鎌倉1～4丁目", "柴又4～7丁目", "高砂2～4丁目"]),
    (13, ["奥戸1～9丁目", "高砂1丁目", "細田1～5丁目"]),
    (14, ["新小岩1丁目", "西新小岩1～5丁目", "東四つ木1～4丁目"]),
    (15, ["新小岩2～4丁目"]),
    (16, ["東新小岩1～8丁目"]),
]


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return re.sub(r"[^a-z0-9]+", "-", romaji).strip("-")


def expand_items(item_str: str) -> List[tuple]:
    """Expands 'お花茶屋1～3丁目' into [('お花茶屋', '1丁目'), ('お花茶屋', '2丁目'), ('お花茶屋', '3丁目')]
    and '宝町1・2丁目' into [('宝町', '1丁目'), ('宝町', '2丁目')]."""
    item_str = unicodedata.normalize("NFKC", item_str).strip()
    m = re.match(r"^([^\d]+)([\d・~～\s]+丁目)$", item_str)
    if not m:
        return [(item_str, "")]

    town = m.group(1).strip()
    chome_part = m.group(2).replace("丁目", "").strip()

    chomes = []
    # Check range like 1~3 or 1～3
    range_m = re.match(r"^(\d+)[~～\-](\d+)$", chome_part)
    if range_m:
        start = int(range_m.group(1))
        end = int(range_m.group(2))
        for n in range(start, end + 1):
            chomes.append(f"{n}丁目")
    elif "・" in chome_part or "," in chome_part:
        parts = re.split(r"[・,\s]+", chome_part)
        for p in parts:
            if p.isdigit():
                chomes.append(f"{p}丁目")
    elif chome_part.isdigit():
        chomes.append(f"{chome_part}丁目")
    else:
        chomes.append(m.group(2))

    return [(town, c) for c in chomes]


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(base_dir, "data", "wip", "katsushika.json")

    records = []
    used_slugs: Set[str] = set()

    for area_id, area_list in KATSUSHIKA_AREAS:
        burn_days, non_days, non_weeks, res_days, pla_days = KATSUSHIKA_PATTERNS[area_id]

        for entry_raw in area_list:
            expanded = expand_items(entry_raw)
            for town, chome in expanded:
                romaji_town = to_romaji(town)
                chome_slug = to_romaji(chome) if chome else ""

                slug_parts = ["katsushika", romaji_town]
                if chome_slug:
                    slug_parts.append(chome_slug)

                base_slug = "-".join([s for s in slug_parts if s])
                base_slug = re.sub(r"[^a-z0-9\-]+", "-", base_slug).strip("-")
                base_slug = re.sub(r"-+", "-", base_slug)
                if base_slug.startswith("katsushika-"):
                    base_slug = "katsushika/" + base_slug[len("katsushika-") :]
                elif base_slug == "katsushika":
                    base_slug = "katsushika/area"

                slug = base_slug
                idx = 2
                while slug in used_slugs:
                    slug = f"{base_slug}-{idx}"
                    idx += 1
                used_slugs.add(slug)

                types = {
                    "burnable": {
                        "label": "燃やすごみ",
                        "days": burn_days,
                        "weeks": None,
                        "time": "朝8:00まで",
                    },
                    "nonburnable": {
                        "label": "燃やさないごみ",
                        "days": non_days,
                        "weeks": non_weeks,
                        "time": "朝8:00まで",
                    },
                    "resource": {
                        "label": "資源",
                        "days": res_days,
                        "weeks": None,
                        "time": "朝8:00まで",
                    },
                    "plastic": {
                        "label": "プラスチック製容器包装",
                        "days": pla_days,
                        "weeks": None,
                        "time": "朝8:00まで",
                    },
                }

                record = {
                    "pref": "東京都",
                    "city": "葛飾区",
                    "city_en": "katsushika",
                    "ward": "",
                    "ward_en": "",
                    "town": town,
                    "chome": chome,
                    "sub": "",
                    "romaji": romaji_town,
                    "slug": slug,
                    "types": types,
                    "rules": {
                        "holiday_collection": "祝日も収集（年末年始を除く）",
                        "time_by": "朝8:00まで",
                        "yearend": "12/31~1/3 休止",
                    },
                    "source": {
                        "url": "https://www.city.katsushika.lg.jp/kurashi/1000048/1017199/1020038.html",
                        "fetched": TODAY_STR,
                        "basis": "official_pdf",
                    },
                    "raw": {
                        "area_id": area_id,
                        "raw_entry": entry_raw,
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

    print(f"katsushika: {len(records)} records written -> {out_path}")


if __name__ == "__main__":
    main()
