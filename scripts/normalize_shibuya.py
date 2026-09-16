#!/usr/bin/env python3
"""Normalize Shibuya Ward (渋谷区) Garbage Collection Schedule
Source: Official Multilingual Pamphlet (syuusyuyoubi.pdf)
Output: data/normalized/shibuya.json
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

SHIBUYA_ROWS = [
    # Left column
    ("上原", "1丁目", "", ["水", "土"], ["月"], [2], ["火"]),
    ("上原", "2丁目・3丁目", "", ["水", "土"], ["火"], [3], ["月"]),
    ("鶯谷町", "", "", ["水", "土"], ["月"], [3], ["火"]),
    ("宇田川町", "", "繁華街は7:30", ["水", "土"], ["月"], [1], ["火"]),
    ("恵比寿", "1丁目・2丁目", "", ["月", "木"], ["金"], [1], ["土"]),
    ("恵比寿", "3丁目・4丁目", "", ["月", "木"], ["土"], [3], ["金"]),
    ("恵比寿西", "1丁目・2丁目", "", ["月", "木"], ["土"], [1], ["金"]),
    ("恵比寿南", "1丁目", "", ["月", "木"], ["土"], [3], ["金"]),
    ("恵比寿南", "2丁目・3丁目", "", ["月", "木"], ["土"], [1], ["金"]),
    ("大山町", "", "", ["水", "土"], ["火"], [4], ["月"]),
    ("神山町", "", "", ["水", "土"], ["火"], [1], ["月"]),
    ("桜丘町", "", "繁華街は7:30", ["水", "土"], ["月"], [1], ["火"]),
    ("笹塚", "1丁目", "52〜64番除く", ["水", "土"], ["火"], [4], ["月"]),
    ("笹塚", "1丁目(52〜64)・2丁目・3丁目", "", ["月", "木"], ["金"], [4], ["土"]),
    ("猿楽町", "", "", ["水", "土"], ["月"], [3], ["火"]),
    ("渋谷", "1丁目〜4丁目", "", ["火", "金"], ["木"], [1], ["水"]),
    ("渋谷", "", "7:30から収集を始める地域", ["火", "金"], ["水"], [2], ["木"]),
    ("松濤", "1丁目・2丁目", "", ["水", "土"], ["月"], [1], ["火"]),
    ("松濤", "", "7:30から収集を始める地域", ["月", "木"], ["金"], [2], ["土"]),
    ("神宮前", "1丁目", "繁華街は7:30", ["火", "金"], ["水"], [2], ["木"]),
    ("神宮前", "2丁目〜4丁目", "繁華街は7:30", ["火", "金"], ["水"], [1], ["木"]),
    ("神宮前", "5丁目", "", ["火", "金"], ["木"], [1], ["水"]),
    ("神宮前", "6丁目", "繁華街は7:30", ["火", "金"], ["水"], [3], ["木"]),
    ("神泉町", "", "", ["水", "土"], ["月"], [1], ["火"]),
    ("神泉町", "", "7:30から収集を始める地域", ["月", "木"], ["金"], [2], ["土"]),
    ("神南", "1丁目", "繁華街は7:30", ["水", "土"], ["月"], [1], ["火"]),
    # Right column
    ("千駄ヶ谷", "1丁目〜4丁目", "", ["火", "金"], ["水"], [3], ["木"]),
    ("千駄ヶ谷", "5丁目・6丁目", "", ["火", "金"], ["水"], [4], ["木"]),
    ("代官山町", "", "", ["水", "土"], ["月"], [3], ["火"]),
    ("道玄坂", "1丁目・2丁目1〜10", "7:30", ["水", "土"], ["月"], [2], ["火"]),
    ("道玄坂", "2丁目(1〜10除く)", "7:30", ["月", "木"], ["金"], [1], ["土"]),
    ("富ヶ谷", "1丁目", "", ["水", "土"], ["火"], [1], ["月"]),
    ("富ヶ谷", "2丁目", "", ["水", "土"], ["火"], [3], ["月"]),
    ("南平台町", "", "", ["水", "土"], ["月"], [3], ["火"]),
    ("西原", "1丁目〜3丁目", "", ["水", "土"], ["火"], [2], ["月"]),
    ("幡ヶ谷", "1丁目", "", ["火", "金"], ["火"], [4], ["木"]),
    ("幡ヶ谷", "2丁目", "", ["火", "金"], ["水"], [2], ["木"]),
    ("幡ヶ谷", "3丁目", "", ["月", "木"], ["金"], [2], ["土"]),
    ("鉢山町", "", "", ["水", "土"], ["月"], [3], ["火"]),
    ("初台", "1丁目・2丁目", "", ["水", "土"], ["月"], [4], ["火"]),
    ("東", "1丁目〜4丁目", "", ["火", "金"], ["木"], [3], ["水"]),
    ("広尾", "1丁目〜5丁目", "", ["月", "木"], ["金"], [3], ["土"]),
    ("本町", "1丁目", "", ["火", "金"], ["水"], [4], ["木"]),
    ("本町", "2丁目・4丁目・6丁目", "", ["月", "木"], ["土"], [2], ["金"]),
    ("本町", "3丁目・5丁目", "", ["月", "木"], ["土"], [4], ["金"]),
    ("円山町", "", "7:30", ["月", "木"], ["金"], [2], ["土"]),
    ("元代々木町", "", "", ["水", "土"], ["月"], [4], ["火"]),
    ("代々木", "1丁目・2丁目", "", ["火", "金"], ["木"], [2], ["水"]),
    ("代々木", "3丁目・4丁目(8除く)", "", ["火", "金"], ["木"], [4], ["水"]),
    ("代々木", "4丁目8・5丁目57〜68", "", ["水", "土"], ["火"], [1], ["月"]),
    ("代々木", "5丁目(57〜68除く)", "", ["水", "土"], ["月"], [2], ["火"]),
    ("代々木神園町", "", "", ["水", "土"], ["火"], [1], ["月"]),
]


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return re.sub(r"[^a-z0-9]+", "-", romaji).strip("-")


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(base_dir, "data", "normalized", "shibuya.json")

    records = []
    used_slugs: Set[str] = set()

    for town, chome, sub, burn_days, non_days, non_weeks, res_days in SHIBUYA_ROWS:
        romaji_town = to_romaji(town)
        chome_slug = to_romaji(chome) if chome else ""
        sub_slug = to_romaji(sub) if sub else ""

        slug_parts = ["shibuya", romaji_town]
        if chome_slug:
            slug_parts.append(chome_slug)
        if sub_slug:
            slug_parts.append(sub_slug)

        base_slug = "-".join([s for s in slug_parts if s])
        base_slug = re.sub(r"[^a-z0-9\-]+", "-", base_slug).strip("-")
        base_slug = re.sub(r"-+", "-", base_slug)
        if base_slug.startswith("shibuya-"):
            base_slug = "shibuya/" + base_slug[len("shibuya-") :]
        elif base_slug == "shibuya":
            base_slug = "shibuya/area"

        slug = base_slug
        idx = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{idx}"
            idx += 1
        used_slugs.add(slug)

        types = {
            "burnable": {
                "label": "可燃ごみ",
                "days": burn_days,
                "weeks": None,
                "time": "朝8:00まで" if "7:30" not in sub else "朝7:30まで",
            },
            "nonburnable": {
                "label": "不燃ごみ",
                "days": non_days,
                "weeks": non_weeks,
                "time": "朝8:00まで" if "7:30" not in sub else "朝7:30まで",
            },
            "resource": {
                "label": "資源回収日",
                "days": res_days,
                "weeks": None,
                "time": "朝8:00まで" if "7:30" not in sub else "朝7:30まで",
            },
        }

        record = {
            "pref": "東京都",
            "city": "渋谷区",
            "city_en": "shibuya",
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
                "time_by": "朝8:00まで（繁華街等は朝7:30まで）",
                "yearend": "12/31~1/3 休止",
            },
            "source": {
                "url": "https://files.city.shibuya.tokyo.jp/assets/12995aba8b194961be709ba879857f70/d8abc1886ec44007b30ec5c29999b2d3/syuusyuyoubi.pdf",
                "fetched": TODAY_STR,
                "basis": "official_pdf",
            },
            "raw": {
                "town": town,
                "chome": chome,
                "sub": sub,
                "burnable": burn_days,
                "nonburnable": non_days,
                "nonburnable_weeks": non_weeks,
                "resource": res_days,
            },
        }
        records.append(record)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"shibuya: {len(records)} records written -> {out_path}")


if __name__ == "__main__":
    main()
