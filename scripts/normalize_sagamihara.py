#!/usr/bin/env python3
"""
Normalize Sagamihara City (相模原市) Garbage Collection Schedule
--------------------------------------------------------------
Official Source: 相模原市オープンデータ 地域別収集曜日 (CSV)
URL: https://opendata.city.sagamihara.kanagawa.jp/dataset/d1172a26-2e3e-4814-9584-9a82e8a2d96b/resource/9be3d5c1-ecc6-4451-8912-50a8818fdab7/download/gomisyusyu.csv
Output: data/wip/sagamihara.json -> data/normalized/sagamihara.json
"""

import csv
import io
import json
import os
import re
import sys
import unicodedata
import pykakasi
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw", "sagamihara")
WIP_DIR = os.path.join(BASE_DIR, "data", "wip")
NORM_DIR = os.path.join(BASE_DIR, "data", "normalized")

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(WIP_DIR, exist_ok=True)
os.makedirs(NORM_DIR, exist_ok=True)

CSV_URL = "https://opendata.city.sagamihara.kanagawa.jp/dataset/d1172a26-2e3e-4814-9584-9a82e8a2d96b/resource/9be3d5c1-ecc6-4451-8912-50a8818fdab7/download/gomisyusyu.csv"
TODAY_STR = "2026-09-17"

WARD_MAP = {
    "中": ("中央区", "chuo"),
    "緑": ("緑区", "midori"),
    "南": ("南区", "minami"),
}

kakasi = pykakasi.kakasi()


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return re.sub(r"[^a-z0-9]+", "-", romaji).strip("-")


def parse_days(val: str):
    if not val:
        return []
    days = []
    for m in re.finditer(r"([月火水木金土日])", val):
        day_char = m.group(1)
        if day_char not in days:
            days.append(day_char)
    return days


def fetch_csv() -> str:
    path = os.path.join(RAW_DIR, "gomisyusyu.csv")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    resp = requests.get(CSV_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    text = resp.content.decode("utf-8-sig")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return text


def main():
    csv_text = fetch_csv()
    reader = csv.DictReader(io.StringIO(csv_text))

    records = []
    slug_counts = {}

    for row in reader:
        ward_code = row.get("区", "").strip()
        if ward_code not in WARD_MAP:
            continue
        w_ja, w_en = WARD_MAP[ward_code]

        town_raw = unicodedata.normalize("NFKC", row.get("町名・大字", "").strip())
        if not town_raw:
            continue

        types = {}

        # 1. 一般ごみ (burnable)
        burn_days = parse_days(row.get("一般ごみ", ""))
        if burn_days:
            types["burnable"] = {
                "label": "一般ごみ",
                "days": burn_days,
                "weeks": None,
                "time": "夜間" if row.get("夜間収集") else None,
            }

        # 2. 資源 (resource)
        res_days = parse_days(row.get("資源", ""))
        if res_days:
            types["resource"] = {
                "label": "資源",
                "days": res_days,
                "weeks": None,
                "time": None,
            }

        # 3. 容器包装プラ (plastic)
        pla_days = parse_days(row.get("容器包装プラ", ""))
        if pla_days:
            types["plastic"] = {
                "label": "容器包装プラ",
                "days": pla_days,
                "weeks": None,
                "time": None,
            }

        town_romaji = to_romaji(town_raw) or "town"
        base_slug = f"sagamihara/{w_en}/{town_romaji}"
        base_slug = re.sub(r"-+", "-", base_slug).strip("-").lower()

        cnt = slug_counts.get(base_slug, 0) + 1
        slug_counts[base_slug] = cnt
        slug = base_slug if cnt == 1 else f"{base_slug}-{cnt}"

        battery_val = row.get("乾電池", "").strip()

        rec = {
            "pref": "神奈川県",
            "city": "相模原市",
            "city_en": "sagamihara",
            "ward": w_ja,
            "ward_en": w_en,
            "town": town_raw,
            "chome": None,
            "sub": "夜間収集地区" if row.get("夜間収集") else None,
            "romaji": town_romaji,
            "slug": slug,
            "types": types,
            "rules": {
                "holiday_collection": "祝日も収集（年末年始除く）",
                "time_by": "8:30" if not row.get("夜間収集") else "夜間",
                "yearend": "12/31~1/3 休止",
                "battery_day": battery_val if battery_val else None,
            },
            "source": {
                "url": CSV_URL,
                "fetched": TODAY_STR,
                "basis": "official_csv",
            },
            "raw": dict(row),
        }
        records.append(rec)

    wip_file = os.path.join(WIP_DIR, "sagamihara.json")
    with open(wip_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"[✔] Generated {len(records)} records for Sagamihara -> {wip_file}")


if __name__ == "__main__":
    main()
