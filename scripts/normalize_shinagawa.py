#!/usr/bin/env python3
"""Normalize Shinagawa Ward (品川区) Garbage Collection Schedule
Source: Official Open Data CSV (shinagawa.csv)
Output: data/normalized/shinagawa.json
"""
import csv
import json
import os
import re
import unicodedata
from typing import Dict, List, Any, Set
import pykakasi

kakasi = pykakasi.kakasi()
VALID_DAYS = {"月", "火", "水", "木", "金", "土", "日"}
TODAY_STR = "2026-09-17"


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return re.sub(r"[^a-z0-9]+", "-", romaji).strip("-")


def parse_schedule_cell(val: str, label: str) -> Dict[str, Any]:
    if not val:
        return None
    val_norm = unicodedata.normalize("NFKC", val)
    # Extract weeks if present: "第1月・第3月" -> [1, 3]
    weeks = None
    w_nums = re.findall(r"第([0-9]+)", val_norm)
    if not w_nums:
        w_nums = re.findall(r"([0-9]+)回目", val_norm)
    if ("第" in val_norm or "回" in val_norm) and w_nums:
        weeks = [int(w) for w in w_nums if int(w) <= 5]
        if not weeks:
            weeks = None

    days = []
    # If explicitly followed by 曜
    for m in re.finditer(r"([月火水木金土日])曜?", val_norm):
        d = m.group(1)
        # Avoid matching 日 from 曜日
        start_idx = m.start(1)
        if d == "日" and start_idx > 0 and val_norm[start_idx - 1] in VALID_DAYS:
            continue
        if d in VALID_DAYS and d not in days:
            days.append(d)

    if not days:
        return None

    return {
        "label": label,
        "days": days,
        "weeks": weeks,
        "time": "朝8:00まで",
    }


def split_place(place: str):
    # e.g. "八潮5丁目1～39号" -> town="八潮", chome="5丁目", sub="1～39号"
    # "上大崎1丁目" -> town="上大崎", chome="1丁目", sub=""
    # "南大井6丁目18番以外" -> town="南大井", chome="6丁目", sub="18番以外"
    p = unicodedata.normalize("NFKC", place)
    m = re.match(r"^([^\d]+)(\d+丁目)(.*)$", p)
    if m:
        return m.group(1), m.group(2), m.group(3).strip()
    m2 = re.match(r"^([^\d]+)(.*)$", p)
    if m2:
        return m2.group(1), "", m2.group(2).strip()
    return p, "", ""


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    csv_path = os.path.join(base_dir, "data", "raw", "shinagawa", "shinagawa.csv")
    out_path = os.path.join(base_dir, "data", "normalized", "shinagawa.json")

    with open(csv_path, "r", encoding="cp932", errors="ignore") as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)

    # Group by 地区名
    places: Dict[str, Dict[str, Any]] = {}
    for r in raw_rows:
        p_name = r["地区名"].strip()
        if p_name not in places:
            places[p_name] = {"rows": [], "raw": []}
        places[p_name]["rows"].append(r)
        places[p_name]["raw"].append(r)

    records = []
    used_slugs: Set[str] = set()

    TYPE_MAP = {
        "燃やすごみ": "burnable",
        "陶器・ガラス・金属ごみ": "nonburnable",
        "資源": "resource",
    }

    for p_name, group in places.items():
        town, chome, sub = split_place(p_name)
        romaji_town = to_romaji(town)

        chome_slug = to_romaji(chome) if chome else ""
        sub_slug = to_romaji(sub) if sub else ""

        slug_parts = ["shinagawa", romaji_town]
        if chome_slug:
            slug_parts.append(chome_slug)
        if sub_slug:
            slug_parts.append(sub_slug)

        base_slug = "-".join([s for s in slug_parts if s])
        base_slug = re.sub(r"[^a-z0-9\-]+", "-", base_slug).strip("-")
        base_slug = re.sub(r"-+", "-", base_slug)
        # Convert first dash after shinagawa to /
        if base_slug.startswith("shinagawa-"):
            base_slug = "shinagawa/" + base_slug[len("shinagawa-") :]
        elif base_slug == "shinagawa":
            base_slug = "shinagawa/area"

        slug = base_slug
        idx = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{idx}"
            idx += 1
        used_slugs.add(slug)

        types = {}
        for row in group["rows"]:
            cat = row["ゴミ分類区分"].strip()
            sched_str = row["収集曜日"].strip()
            target_key = TYPE_MAP.get(cat)
            if target_key:
                cell_data = parse_schedule_cell(sched_str, cat)
                if cell_data:
                    types[target_key] = cell_data

        record = {
            "pref": "東京都",
            "city": "品川区",
            "city_en": "shinagawa",
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
                "url": "https://service.linkdata.org/file/shinagawa_recycle_gomi_v2.csv",
                "fetched": TODAY_STR,
                "basis": "official_csv",
            },
            "raw": group["raw"],
        }
        records.append(record)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"shinagawa: {len(records)} records written -> {out_path}")


if __name__ == "__main__":
    main()
