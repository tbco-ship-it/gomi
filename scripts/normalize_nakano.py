#!/usr/bin/env python3
"""Normalize Nakano Ward (中野区) Garbage Collection Schedule
Source: Official Open Data CSV (opendata_550239.csv)
Output: data/normalized/nakano.json
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
    # Extract weeks if present: "第2;第4土曜日" -> [2, 4]
    weeks = None
    w_nums = re.findall(r"第?([0-9]+)", val_norm)
    if ("第" in val_norm or "回" in val_norm) and w_nums:
        weeks = [int(w) for w in w_nums if int(w) <= 5]
        if not weeks:
            weeks = None

    # Clean days: find char immediately preceding 曜
    days = []
    for m in re.finditer(r"([月火水木金土日])曜", val_norm):
        d = m.group(1)
        if d in VALID_DAYS and d not in days:
            days.append(d)
    if not days:
        for ch in val_norm:
            if ch in VALID_DAYS and ch not in days:
                days.append(ch)

    if not days:
        return None

    return {
        "label": label,
        "days": days,
        "weeks": weeks,
        "time": "朝8:00まで" if label != "びん,ペットボトル" else "朝8:30まで",
    }


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_file = os.path.join(base_dir, "data", "raw", "nakano", "nakano.csv")
    out_file = os.path.join(base_dir, "data", "normalized", "nakano.json")

    with open(raw_file, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    all_normalized = []
    used_slugs: Set[str] = set()

    for r in rows:
        town = r.get("町名", "").strip()
        chome_raw = r.get("丁目", "").strip()
        # Format chome: e.g. "1;2;4;5" -> "1・2・4・5丁目", "3" -> "3丁目"
        if chome_raw:
            parts = [p.strip() for p in re.split(r"[;；,、]", chome_raw) if p.strip()]
            chome = "・".join(parts) + "丁目"
            chome_slug_part = "-".join(parts)
        else:
            chome = ""
            chome_slug_part = ""

        t_romaji = to_romaji(town) or "town"
        slug_base = f"nakano/{t_romaji}"
        if chome_slug_part:
            slug_base += f"-{chome_slug_part}"
        slug_base = re.sub(r"[^a-z0-9\-/]+", "-", slug_base.lower()).strip("-")

        slug = slug_base
        idx = 2
        while slug in used_slugs:
            slug = f"{slug_base}-{idx}"
            idx += 1
        used_slugs.add(slug)

        types: Dict[str, Any] = {}
        # 1. 燃やすごみ -> burnable
        s_burn = parse_schedule_cell(r.get("燃やすごみ", ""), "燃やすごみ")
        if s_burn:
            types["burnable"] = s_burn

        # 2. 陶器,ガラス,金属ごみ -> nonburnable
        s_non = parse_schedule_cell(r.get("陶器,ガラス,金属ごみ", ""), "陶器,ガラス,金属ごみ")
        if s_non:
            types["nonburnable"] = s_non

        # 3. 資源プラスチック -> plastic
        s_pla = parse_schedule_cell(r.get("資源プラスチック", ""), "資源プラスチック")
        if s_pla:
            types["plastic"] = s_pla

        # 4. びん,ペットボトル -> resource
        s_res = parse_schedule_cell(r.get("びん,ペットボトル", ""), "びん,ペットボトル")
        if s_res:
            types["resource"] = s_res

        rec = {
            "pref": "東京都",
            "city": "中野区",
            "city_en": "nakano",
            "ward": "",
            "ward_en": "",
            "town": town,
            "chome": chome,
            "sub": "",
            "romaji": t_romaji,
            "slug": slug,
            "types": types,
            "rules": {
                "holiday_collection": "祝日も収集（年末年始を除く）",
                "time_by": "朝8:00まで（びん・ペットボトルは朝8:30まで）",
                "yearend": "12/31~1/3 休止"
            },
            "source": {
                "url": "https://www2.wagmap.jp/nakanodatamap/nakanodatamap/opendatafile/map_1/CSV/opendata_550239.csv",
                "fetched": TODAY_STR,
                "basis": "official_csv"
            },
            "raw": dict(r)
        }
        all_normalized.append(rec)

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_normalized, f, ensure_ascii=False, indent=2)

    print(f"nakano: {len(all_normalized)} records written -> {out_file}")


if __name__ == "__main__":
    main()
