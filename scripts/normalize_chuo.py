#!/usr/bin/env python3
"""Normalize Chuo Ward (中央区) Garbage Collection Schedule
Source: Official Open Data CSV (gomitoshigen.csv)
Output: data/normalized/chuo.json
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


def extract_nums(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    nums = re.findall(r"\d+", text)
    return "-".join(nums) if nums else ""


def parse_schedule_cell(val: str, label: str) -> Dict[str, Any]:
    if not val:
        return None
    val_norm = unicodedata.normalize("NFKC", val).strip()
    if val_norm in ("なし", "-", "ー", "―", "収集していません"):
        return None

    # Weeks if present
    weeks = None
    w_nums = re.findall(r"第?([0-9]+)", val_norm)
    if ("第" in val_norm or "回" in val_norm) and w_nums:
        weeks = [int(w) for w in w_nums if int(w) <= 5]
        if not weeks:
            weeks = None

    # Handle day ranges: e.g. "月曜日~土曜日" or "月曜日～土曜日"
    days = []
    m_range = re.search(r"([月火水木金土日])曜日?[~～\-]([月火水木金土日])曜日?", val_norm)
    if m_range:
        d_order = ["月", "火", "水", "木", "金", "土", "日"]
        start_idx = d_order.index(m_range.group(1))
        end_idx = d_order.index(m_range.group(2))
        if start_idx <= end_idx:
            days = d_order[start_idx:end_idx+1]
    else:
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
        "time": "朝8:00まで",
    }


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_file = os.path.join(base_dir, "data", "raw", "chuo", "chuo.csv")
    out_file = os.path.join(base_dir, "data", "normalized", "chuo.json")

    with open(raw_file, "r", encoding="cp932", errors="replace") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    all_normalized = []
    used_slugs: Set[str] = set()

    for r in rows:
        town = r.get("町名", "").strip()
        chome_val = r.get("丁目", "").strip()
        chome = "" if chome_val == "全域" else chome_val

        t_romaji = to_romaji(town) or "town"
        chome_nums = extract_nums(chome)
        slug_base = f"chuo/{t_romaji}"
        if chome_nums:
            slug_base += f"-{chome_nums}"
        elif chome:
            slug_base += f"-{to_romaji(chome)}"
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

        s_pla = parse_schedule_cell(r.get("プラマーク", ""), "プラマーク")
        if s_pla:
            types["plastic"] = s_pla

        s_res = parse_schedule_cell(r.get("資源", ""), "資源")
        if s_res:
            types["resource"] = s_res

        s_bulk = parse_schedule_cell(r.get("粗大ごみ", ""), "粗大ごみ")
        if s_bulk:
            s_bulk["note"] = "申込制"
            types["bulky"] = s_bulk

        rec = {
            "pref": "東京都",
            "city": "中央区",
            "city_en": "chuo",
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
                "url": "https://www.city.chuo.lg.jp/documents/984/gomitoshigen.csv",
                "fetched": TODAY_STR,
                "basis": "official_csv"
            },
            "raw": dict(r)
        }
        all_normalized.append(rec)

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_normalized, f, ensure_ascii=False, indent=2)

    print(f"chuo: {len(all_normalized)} records written -> {out_file}")


if __name__ == "__main__":
    main()
