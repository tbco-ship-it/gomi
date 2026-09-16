#!/usr/bin/env python3
"""Normalize Sumida Ward (墨田区) Garbage Collection Schedule
Source: Official 12 Zone Calendars (PDFs 0810_01 ~ 0810_12)
Output: data/normalized/sumida.json
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

ZONES_DATA = [
    {
        "zone": 1,
        "areas": ["両国", "亀沢", "石原", "横網"],
        "burnable": ["月", "木"],
        "nonburnable_days": ["土"],
        "nonburnable_weeks": [1, 3],
        "resource": ["火"],
        "plastic": ["水"],
    },
    {
        "zone": 2,
        "areas": ["千歳", "緑", "立川"],
        "burnable": ["月", "木"],
        "nonburnable_days": ["土"],
        "nonburnable_weeks": [2, 4],
        "resource": ["火"],
        "plastic": ["水"],
    },
    {
        "zone": 3,
        "areas": ["太平", "横川"],
        "burnable": ["月", "木"],
        "nonburnable_days": ["水"],
        "nonburnable_weeks": [1, 3],
        "resource": ["金"],
        "plastic": ["土"],
    },
    {
        "zone": 4,
        "areas": ["菊川", "江東橋", "錦糸"],
        "burnable": ["月", "木"],
        "nonburnable_days": ["水"],
        "nonburnable_weeks": [2, 4],
        "resource": ["金"],
        "plastic": ["土"],
    },
    {
        "zone": 5,
        "areas": ["本所1〜2丁目", "東駒形1〜2丁目", "吾妻橋", "向島1〜3丁目"],
        "burnable": ["火", "金"],
        "nonburnable_days": ["月"],
        "nonburnable_weeks": [1, 3],
        "resource": ["土"],
        "plastic": ["木"],
    },
    {
        "zone": 6,
        "areas": ["向島4〜5丁目", "東向島1〜3丁目", "堤通1丁目"],
        "burnable": ["火", "金"],
        "nonburnable_days": ["月"],
        "nonburnable_weeks": [2, 4],
        "resource": ["土"],
        "plastic": ["木"],
    },
    {
        "zone": 7,
        "areas": ["押上", "京島"],
        "burnable": ["火", "金"],
        "nonburnable_days": ["木"],
        "nonburnable_weeks": [1, 3],
        "resource": ["水"],
        "plastic": ["月"],
    },
    {
        "zone": 8,
        "areas": ["本所3〜4丁目", "東駒形3〜4丁目", "業平", "文花1丁目"],
        "burnable": ["火", "金"],
        "nonburnable_days": ["木"],
        "nonburnable_weeks": [2, 4],
        "resource": ["水"],
        "plastic": ["月"],
    },
    {
        "zone": 9,
        "areas": ["堤通2丁目", "東向島4丁目", "墨田1・2・5丁目"],
        "burnable": ["水", "土"],
        "nonburnable_days": ["火"],
        "nonburnable_weeks": [1, 3],
        "resource": ["木"],
        "plastic": ["金"],
    },
    {
        "zone": 10,
        "areas": ["東向島5〜6丁目", "墨田3〜4丁目", "八広6丁目"],
        "burnable": ["水", "土"],
        "nonburnable_days": ["火"],
        "nonburnable_weeks": [2, 4],
        "resource": ["木"],
        "plastic": ["金"],
    },
    {
        "zone": 11,
        "areas": ["立花", "東墨田"],
        "burnable": ["水", "土"],
        "nonburnable_days": ["金"],
        "nonburnable_weeks": [1, 3],
        "resource": ["月"],
        "plastic": ["火"],
    },
    {
        "zone": 12,
        "areas": ["文花2〜3丁目", "八広1〜5丁目"],
        "burnable": ["水", "土"],
        "nonburnable_days": ["金"],
        "nonburnable_weeks": [2, 4],
        "resource": ["月"],
        "plastic": ["火"],
    },
]


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return re.sub(r"[^a-z0-9]+", "-", romaji).strip("-")


def split_area(raw_area: str):
    s = unicodedata.normalize("NFKC", raw_area).strip()
    m = re.match(r"^([^\d]+)(\d+.*?丁目)(.*)$", s)
    if m:
        return m.group(1), m.group(2).strip(), m.group(3).strip()
    return s, "", ""


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(base_dir, "data", "normalized", "sumida.json")

    records = []
    used_slugs: Set[str] = set()

    for z in ZONES_DATA:
        z_num = z["zone"]
        for raw_area in z["areas"]:
            town, chome, sub = split_area(raw_area)
            romaji_town = to_romaji(town)
            chome_slug = to_romaji(chome) if chome else ""
            sub_slug = to_romaji(sub) if sub else ""

            slug_parts = ["sumida", romaji_town]
            if chome_slug:
                slug_parts.append(chome_slug)
            if sub_slug:
                slug_parts.append(sub_slug)

            base_slug = "-".join([s for s in slug_parts if s])
            base_slug = re.sub(r"[^a-z0-9\-]+", "-", base_slug).strip("-")
            base_slug = re.sub(r"-+", "-", base_slug)
            if base_slug.startswith("sumida-"):
                base_slug = "sumida/" + base_slug[len("sumida-") :]
            elif base_slug == "sumida":
                base_slug = "sumida/area"

            slug = base_slug
            idx = 2
            while slug in used_slugs:
                slug = f"{base_slug}-{idx}"
                idx += 1
            used_slugs.add(slug)

            types = {
                "burnable": {
                    "label": "燃やすごみ",
                    "days": z["burnable"],
                    "weeks": None,
                    "time": "朝8:00まで",
                },
                "nonburnable": {
                    "label": "燃やさないごみ",
                    "days": z["nonburnable_days"],
                    "weeks": z["nonburnable_weeks"],
                    "time": "朝8:00まで",
                },
                "resource": {
                    "label": "資源",
                    "days": z["resource"],
                    "weeks": None,
                    "time": "朝8:00まで",
                },
                "plastic": {
                    "label": "プラスチック",
                    "days": z["plastic"],
                    "weeks": None,
                    "time": "朝8:00まで",
                },
            }

            record = {
                "pref": "東京都",
                "city": "墨田区",
                "city_en": "sumida",
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
                    "time_by": "朝8:00まで",
                    "yearend": "12/31~1/3 休止",
                },
                "source": {
                    "url": f"https://www.city.sumida.lg.jp/kurashi/gomi_recycle/kateikei/gomi-calendar.files/0810_{z_num:02d}.pdf",
                    "fetched": TODAY_STR,
                    "basis": "official_pdf",
                },
                "raw": {
                    "zone": z_num,
                    "area": raw_area,
                    "burnable": z["burnable"],
                    "nonburnable_days": z["nonburnable_days"],
                    "nonburnable_weeks": z["nonburnable_weeks"],
                    "resource": z["resource"],
                    "plastic": z["plastic"],
                },
            }
            records.append(record)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"sumida: {len(records)} records written -> {out_path}")


if __name__ == "__main__":
    main()
