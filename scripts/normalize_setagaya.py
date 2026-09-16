#!/usr/bin/env python3
"""
Normalize Setagaya Ward (世田谷区) Garbage Collection Schedule
-------------------------------------------------------------
Reads official Open Data CSV (Shift-JIS/CP932):
data/raw/setagaya/setagaya.csv
and converts into unified schema:
data/normalized/setagaya.json

Schema rules:
- Top-level pure JSON array
- Standard waste type keys: burnable, resource, plastic, paper_cloth, nonburnable, bulky
  - 可燃ごみ -> burnable
  - 資源 -> resource
  - ペットボトル -> plastic
  - 不燃ごみ -> nonburnable
- 23区: pref: 東京都, city: 世田谷区, city_en: setagaya, ward: "", ward_en: ""
- Unique slugs (0 duplicates) generated via pykakasi
- source.fetched: 2026-09-17
"""

import csv
import json
import os
import re
import sys
import unicodedata
import urllib.request
from typing import Dict, List, Any, Set
import pykakasi

SETAGAYA_CSV_URL = "https://www.city.setagaya.lg.jp/documents/416/27-08-26.csv"
VALID_DAYS = {"月", "火", "水", "木", "金", "土", "日"}
TODAY_STR = "2026-09-17"

kakasi = pykakasi.kakasi()


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return re.sub(r"[^a-z0-9]+", "-", romaji).strip("-")


def extract_nums(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    nums = re.findall(r"\d+", text)
    return "-".join(nums) if nums else ""


def download_setagaya_csv_if_needed(raw_dir: str) -> str:
    os.makedirs(raw_dir, exist_ok=True)
    csv_path = os.path.join(raw_dir, "setagaya.csv")
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        print(f"[*] Downloading Setagaya CSV from {SETAGAYA_CSV_URL}...")
        req = urllib.request.Request(SETAGAYA_CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read()
        with open(csv_path, "wb") as f:
            f.write(content)
    return csv_path


def parse_schedule_field(val: str, label: str):
    """
    Parses day and week from strings like:
    - '木曜日' -> days: ['木'], weeks: None
    - '水曜日・土曜日' -> days: ['水', '土'], weeks: None
    - '2回目・4回目の月曜日' -> days: ['月'], weeks: [2, 4]
    - '1回目・3回目の土曜日' -> days: ['土'], weeks: [1, 3]
    """
    if not val:
        return None

    days = []
    for char in val:
        if char in VALID_DAYS and char not in days:
            days.append(char)

    weeks = None
    if "回目" in val:
        raw_nums = re.findall(r"(\d+)回目", unicodedata.normalize("NFKC", val))
        if raw_nums:
            weeks = sorted([int(n) for n in raw_nums])

    return {
        "label": label,
        "days": days,
        "weeks": weeks,
        "time": "朝8:00まで",
    }


def normalize_setagaya(raw_dir: str, output_path: str):
    csv_path = download_setagaya_csv_if_needed(raw_dir)

    with open(csv_path, "r", encoding="cp932", errors="replace") as f:
        lines = [line.strip() for line in f if line.strip()]

    if len(lines) < 2:
        raise ValueError("Setagaya CSV is too short or empty!")

    # Line 0 is note header, Line 1 is column headers
    reader = csv.DictReader(lines[1:])

    records: List[Dict[str, Any]] = []
    used_slugs: Set[str] = set()

    for row in reader:
        town = row.get("町名", "").strip()
        chome_raw = row.get("丁目", "").strip()
        if not town:
            continue

        chome_norm = unicodedata.normalize("NFKC", chome_raw).replace("～", "~")
        chome = f"{chome_norm}丁目" if chome_norm and not chome_norm.endswith("丁目") else chome_norm

        t_romaji = to_romaji(town)
        nums = extract_nums(chome_norm)

        base_slug = f"setagaya/{t_romaji}" + (f"-{nums}" if nums else "")
        slug = base_slug
        idx = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{idx}"
            idx += 1
        used_slugs.add(slug)

        types: Dict[str, Any] = {}

        # 1. 資源
        res_info = parse_schedule_field(row.get("資源（週1回）", "").strip(), "資源")
        if res_info:
            types["resource"] = res_info

        # 2. 可燃ごみ
        burn_info = parse_schedule_field(row.get("可燃ごみ（週2回）", "").strip(), "可燃ごみ")
        if burn_info:
            types["burnable"] = burn_info

        # 3. 不燃ごみ
        nonburn_info = parse_schedule_field(row.get("不燃ごみ（月2回）", "").strip(), "不燃ごみ")
        if nonburn_info:
            types["nonburnable"] = nonburn_info

        # 4. ペットボトル
        pet_info = parse_schedule_field(row.get("ペットボトル（月2回）", "").strip(), "ペットボトル")
        if pet_info:
            types["plastic"] = pet_info

        record = {
            "pref": "東京都",
            "city": "世田谷区",
            "city_en": "setagaya",
            "ward": "",
            "ward_en": "",
            "town": town,
            "romaji": t_romaji,
            "chome": chome,
            "sub": "",
            "slug": slug,
            "types": types,
            "rules": {
                "holiday_collection": "祝日も収集",
                "time_by": "8:00",
                "yearend": "12/31~1/3 休止",
            },
            "source": {
                "url": SETAGAYA_CSV_URL,
                "fetched": TODAY_STR,
                "basis": "official_csv",
            },
            "notes": f"管轄清掃事務所: {row.get('管轄清掃事務所', '').strip()}",
            "raw": {k: v for k, v in row.items() if v},
        }
        records.append(record)

    assert len(records) > 0, "No records produced for Setagaya!"
    assert len(records) == len(used_slugs), f"Slug collision in Setagaya! {len(records)} != {len(used_slugs)}"

    for r in records:
        assert re.match(r"^[a-z0-9\-/]+$", r["slug"]), f"Invalid slug characters: {r['slug']}"
        for t_k, t_v in r["types"].items():
            assert t_k in {"burnable", "resource", "plastic", "paper_cloth", "nonburnable", "bulky"}, f"Invalid type key: {t_k}"
            for d in t_v["days"]:
                assert d in VALID_DAYS, f"Invalid day {d} in record {r['slug']}"

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"[✔] Setagaya normalized: {len(records)} records saved to {output_path}")
    print(f"[✔] Unique slugs: {len(used_slugs)} (collisions: 0)")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_dir = os.path.join(base_dir, "data", "raw", "setagaya")
    output_file = os.path.join(base_dir, "data", "normalized", "setagaya.json")
    normalize_setagaya(raw_dir, output_file)
