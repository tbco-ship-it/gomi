#!/usr/bin/env python3
"""Normalize Koto Ward (江東区) Garbage Collection Schedule
Source: Official Open Data CSV (131083_201_kotocity_waste_recycle_collectionday.csv)
Output: data/normalized/koto.json
"""
import csv
import json
import os
import re
import unicodedata
from typing import Dict, List, Any, Set, Tuple
import pykakasi

kakasi = pykakasi.kakasi()
VALID_DAYS = {"月", "火", "水", "木", "金", "土", "日"}
TODAY_STR = "2026-09-17"


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


def split_town_chome(addr: str) -> Tuple[str, str]:
    s = unicodedata.normalize("NFKC", addr).strip()
    m_chome = re.search(r"([0-9・～~]+丁目.*)", s)
    if m_chome:
        chome = m_chome.group(1).strip()
        town = s[:m_chome.start()].strip()
        return town, chome
    return s, ""


def parse_schedule_cell(val: str, label: str) -> Dict[str, Any]:
    if not val:
        return None
    val_norm = unicodedata.normalize("NFKC", val).strip()

    weeks = None
    w_nums = re.findall(r"第?([0-9]+)", val_norm)
    if ("第" in val_norm or "回" in val_norm) and w_nums:
        weeks = [int(w) for w in w_nums if int(w) <= 5]

    days = []
    # e.g. "月・木", "水", "（隔週）土"
    for ch in val_norm:
        if ch in VALID_DAYS and ch not in days:
            days.append(ch)

    if not days:
        return None

    return {
        "label": label,
        "days": days,
        "weeks": weeks,
        "time": "朝8:00まで",
    }


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_file = os.path.join(base_dir, "data", "raw", "koto", "koto.csv")
    out_file = os.path.join(base_dir, "data", "normalized", "koto.json")

    with open(raw_file, "r", encoding="cp932", errors="replace") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    all_normalized = []
    used_slugs: Set[str] = set()

    for r in rows:
        raw_addr = r.get("住所", "").strip()
        town, chome = split_town_chome(raw_addr)

        t_romaji = to_romaji(town) or "town"
        chome_nums = extract_nums(chome)
        slug_base = f"koto/{t_romaji}"
        if chome_nums:
            slug_base += f"-{chome_nums}"
        slug_base = re.sub(r"[^a-z0-9\-/]+", "-", slug_base.lower()).strip("-")

        slug = slug_base
        idx = 2
        while slug in used_slugs:
            slug = f"{slug_base}-{idx}"
            idx += 1
        used_slugs.add(slug)

        types: Dict[str, Any] = {}
        s_burn = parse_schedule_cell(r.get("燃やすごみ", ""), "燃やすごみ")
        if s_burn:
            types["burnable"] = s_burn

        s_non = parse_schedule_cell(r.get("燃やさないごみ", ""), "燃やさないごみ")
        if s_non:
            types["nonburnable"] = s_non

        s_pla = parse_schedule_cell(r.get("プラスチック", ""), "プラスチック")
        if s_pla:
            types["plastic"] = s_pla

        s_res = parse_schedule_cell(r.get("資源", ""), "資源")
        if s_res:
            types["resource"] = s_res

        rec = {
            "pref": "東京都",
            "city": "江東区",
            "city_en": "koto",
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
                "time_by": "朝8:00まで",
                "yearend": "12/31~1/3 休止"
            },
            "source": {
                "url": "https://www.opendata.metro.tokyo.lg.jp/koto/131083_201_kotocity_waste_recycle_collectionday.csv",
                "fetched": TODAY_STR,
                "basis": "official_csv"
            },
            "raw": dict(r)
        }
        all_normalized.append(rec)

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_normalized, f, ensure_ascii=False, indent=2)

    print(f"koto: {len(all_normalized)} records written -> {out_file}")


if __name__ == "__main__":
    main()
