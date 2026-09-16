#!/usr/bin/env python3
"""Normalize Taito Ward (台東区) Garbage Collection Schedule
Source: Official Open Data CSV (tiikibetusyuusyuuyoubiitiran.csv)
Output: data/normalized/taito.json
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


def split_town_chome(name: str) -> Tuple[str, str]:
    s = unicodedata.normalize("NFKC", name).strip()
    # e.g. "浅草1丁目・浅草2丁目" -> town="浅草", chome="1・2丁目"
    m_chome_parts = re.findall(r"([0-9]+)丁目", s)
    if m_chome_parts:
        town = re.sub(r"[0-9]+丁目", "", s)
        town = re.sub(r"[・、\s]+", "", town)
        # remove duplicate town name if it was repeated: e.g. "浅草浅草" -> "浅草"
        parts = re.split(r"[0-9]+丁目", s)
        town_candidate = parts[0].replace("・", "").strip()
        chome = "・".join(m_chome_parts) + "丁目"
        return town_candidate or town, chome
    return s, ""


def parse_schedule_cell(val: str, label: str) -> Dict[str, Any]:
    if not val:
        return None
    val_norm = unicodedata.normalize("NFKC", val).strip()

    weeks = None
    w_nums = re.findall(r"([0-9]+)回目", val_norm)
    if not w_nums:
        w_nums = re.findall(r"第([0-9]+)", val_norm)
    if w_nums:
        weeks = [int(w) for w in w_nums if int(w) <= 5]

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
        "time": "朝8:00まで",
    }


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_file = os.path.join(base_dir, "data", "raw", "taito", "taito.csv")
    out_file = os.path.join(base_dir, "data", "normalized", "taito.json")

    with open(raw_file, "r", encoding="cp932", errors="replace") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    all_normalized = []
    used_slugs: Set[str] = set()

    for r in rows:
        raw_name = r.get("町丁名", "").strip()
        town, chome = split_town_chome(raw_name)

        t_romaji = to_romaji(town) or "town"
        chome_nums = extract_nums(chome)
        slug_base = f"taito/{t_romaji}"
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

        s_res = parse_schedule_cell(r.get("資源", ""), "資源")
        if s_res:
            types["resource"] = s_res

        rec = {
            "pref": "東京都",
            "city": "台東区",
            "city_en": "taito",
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
                "url": "https://www.city.taito.lg.jp/kusei/online/opendata/koutu/gomibunbetuitiran.files/tiikibetusyuusyuuyoubiitiran.csv",
                "fetched": TODAY_STR,
                "basis": "official_csv"
            },
            "raw": dict(r)
        }
        all_normalized.append(rec)

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_normalized, f, ensure_ascii=False, indent=2)

    print(f"taito: {len(all_normalized)} records written -> {out_file}")


if __name__ == "__main__":
    main()
