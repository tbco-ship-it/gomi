#!/usr/bin/env python3
"""
Normalize Osaka City (大阪市) Garbage Collection Schedule
--------------------------------------------------------
Reads 24 ward CSV files (30,381 rows) and converts them into unified schema:
data/normalized/osaka.json

Schema rules:
- Top-level pure JSON array
- Standard waste type keys: burnable, resource, plastic, paper_cloth, nonburnable, bulky
- Preserves collection time slot in type.time
- Unique slugs (0 duplicates) generated via pykakasi (passport romaji)
- source.fetched: 2026-09-17
"""

import csv
import json
import os
import re
import sys
import time
import urllib.request
from typing import Dict, List, Any, Set
import pykakasi

OSAKA_WARDS_MAP = {
    "kita": "北区",
    "miyakojima": "都島区",
    "fukushima": "福島区",
    "konohana": "此花区",
    "chuo": "中央区",
    "nishi": "西区",
    "minato": "港区",
    "taisho": "大正区",
    "tennoji": "天王寺区",
    "naniwa": "浪速区",
    "nishiyodogawa": "西淀川区",
    "yodogawa": "淀川区",
    "higashiyodogawa": "東淀川区",
    "higashinari": "東成区",
    "ikuno": "生野区",
    "asahi": "旭区",
    "joto": "城東区",
    "tsurumi": "鶴見区",
    "abeno": "阿倍野区",
    "suminoe": "住之江区",
    "sumiyoshi": "住吉区",
    "higashisumiyoshi": "東住吉区",
    "hirano": "平野区",
    "nishinari": "西成区",
}

VALID_DAYS = {"月", "火", "水", "木", "金", "土", "日"}
TODAY_STR = "2026-09-17"

kakasi = pykakasi.kakasi()


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    # passport romaji outputs 'o' instead of 'ou' for long vowels (e.g. ikedacho)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return romaji


def extract_nums(text: str) -> str:
    if not text:
        return ""
    text = text.translate(str.maketrans("０１２３４５６７８９一二三四五六七八九十", "01234567891234567891"))
    nums = re.findall(r"\d+", text)
    return "-".join(nums) if nums else ""


def download_osaka_csvs_if_needed(raw_dir: str):
    os.makedirs(raw_dir, exist_ok=True)
    for ward_slug, ward_ja in OSAKA_WARDS_MAP.items():
        csv_path = os.path.join(raw_dir, f"{ward_slug}.csv")
        if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
            url = f"https://www.city.osaka.lg.jp/contents/wdu150/trashmap/{ward_slug}.csv"
            print(f"[*] Downloading {ward_ja} ({ward_slug}.csv)...")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                content = resp.read()
            with open(csv_path, "wb") as f:
                f.write(content)
            time.sleep(0.1)


def normalize_osaka(raw_dir: str, output_path: str):
    download_osaka_csvs_if_needed(raw_dir)

    records: List[Dict[str, Any]] = []
    used_slugs: Set[str] = set()

    for ward_slug, ward_ja in OSAKA_WARDS_MAP.items():
        csv_path = os.path.join(raw_dir, f"{ward_slug}.csv")
        if not os.path.exists(csv_path):
            print(f"[!] Missing file: {csv_path}", file=sys.stderr)
            continue

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ward = row.get("地区名1", "").strip()
                town = row.get("地区名2", "").strip()
                if not ward and not town:
                    # Skip trailing empty lines
                    continue

                c3 = row.get("地区名3", "").strip()
                c4 = row.get("地区名4", "").strip()
                c5 = row.get("地区名5", "").strip()
                note = row.get("備考", "").strip()

                chome = c3
                sub_parts = [p for p in [c4, c5, note] if p]
                sub = " ".join(sub_parts)

                t_romaji = to_romaji(town)
                num_c3 = extract_nums(c3)
                num_c4 = extract_nums(c4) if "丁目" in c3 else ""

                slug_parts = [t_romaji]
                if num_c3:
                    slug_parts.append(num_c3)
                if num_c4:
                    slug_parts.append(num_c4)

                base_slug = f"osaka/{ward_slug}/" + "-".join(slug_parts)
                slug = base_slug
                idx = 2
                while slug in used_slugs:
                    slug = f"{base_slug}-{idx}"
                    idx += 1
                used_slugs.add(slug)

                # Parse waste collection types and preserve time slots
                types: Dict[str, Any] = {}
                mapping = [
                    ("普通ごみ", "burnable", "普通ごみ"),
                    ("資源ごみ", "resource", "資源ごみ"),
                    ("プラスチック資源", "plastic", "プラスチック資源"),
                    ("古紙衣類", "paper_cloth", "古紙・衣類"),
                ]

                for prefix, key, label in mapping:
                    days: List[str] = []
                    times: List[str] = []
                    for col_name, val in row.items():
                        if val and col_name.startswith(prefix + "_"):
                            time_slot = col_name.split("_", 1)[1]
                            if time_slot != "収集時間要問合せ":
                                times.append(time_slot)
                            else:
                                times.append("要問合せ")
                            for char in val:
                                if char in VALID_DAYS and char not in days:
                                    days.append(char)

                    if days:
                        types[key] = {
                            "label": label,
                            "days": days,
                            "weeks": None,
                            "time": ", ".join(times) if times else None,
                        }

                record = {
                    "pref": "大阪府",
                    "city": "大阪市",
                    "city_en": "osaka",
                    "ward": ward or ward_ja,
                    "ward_en": ward_slug,
                    "town": town,
                    "romaji": t_romaji,
                    "chome": chome,
                    "sub": sub,
                    "slug": slug,
                    "types": types,
                    "rules": {
                        "holiday_collection": "祝日も収集",
                        "time_by": "8:30",
                        "yearend": "12/31~1/3 休止",
                    },
                    "source": {
                        "url": f"https://www.city.osaka.lg.jp/contents/wdu150/trashmap/{ward_slug}.csv",
                        "fetched": TODAY_STR,
                        "basis": "official_csv",
                    },
                    "notes": "同一町でも番地で異なる場合は sub に分岐名",
                    "raw": {col: v for col, v in row.items() if v},
                }
                records.append(record)

    # Verification
    assert len(records) > 0, "No records generated!"
    assert len(records) == len(used_slugs), f"Slug collision detected! {len(records)} != {len(used_slugs)}"

    for r in records:
        assert re.match(r"^[a-z0-9\-/]+$", r["slug"]), f"Invalid slug characters: {r['slug']}"
        for t_k, t_v in r["types"].items():
            assert t_k in {"burnable", "resource", "plastic", "paper_cloth", "nonburnable", "bulky"}, f"Invalid type key: {t_k}"
            for d in t_v["days"]:
                assert d in VALID_DAYS, f"Invalid day {d} in record {r['slug']}"

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"[✔] Osaka normalized successfully: {len(records)} records saved to {output_path}")
    print(f"[✔] Slugs: {len(used_slugs)} unique (duplicates: 0)")
    print("[✔] Days validation: passed for all records")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_dir = os.path.join(base_dir, "data", "raw", "osaka")
    output_file = os.path.join(base_dir, "data", "normalized", "osaka.json")
    normalize_osaka(raw_dir, output_file)
