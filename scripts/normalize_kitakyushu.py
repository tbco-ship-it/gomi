#!/usr/bin/env python3
"""
Normalize Kitakyushu City (北九州市) Garbage Collection Schedule
----------------------------------------------------------------
Reads data/kitakyushu.json (824 records) and converts them into unified schema:
data/normalized/kitakyushu.json

Schema rules:
- Top-level pure JSON array
- Standard waste type keys: burnable, resource, plastic, paper_cloth, nonburnable, bulky
- Preserves bulky week schedule (e.g. 第2木曜日 -> days: ["木"], weeks: [2], note: "事前申込制")
- Preserves collection time slot (朝8:30まで)
- Unique slugs (0 duplicates) generated via pykakasi (passport romaji)
- source.fetched: 2026-09-17
"""

import json
import os
import re
import sys
from typing import Dict, List, Any, Set, Tuple
import pykakasi

VALID_DAYS = {"月", "火", "水", "木", "金", "土", "日"}
TODAY_STR = "2026-09-17"

kakasi = pykakasi.kakasi()


def clean_slug_part(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    s = re.sub(r"-+", "-", s)
    return s


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return clean_slug_part(romaji)


def extract_nums(text: str) -> str:
    if not text:
        return ""
    text = text.translate(str.maketrans("０１２３４５６７８９一二三四五六七八九十", "01234567891234567891"))
    nums = re.findall(r"\d+", text)
    return "-".join(nums) if nums else ""


def parse_town_str(raw_town: str) -> Tuple[str, str, str]:
    raw_town = raw_town.strip().lstrip("※*・# ").strip()

    note_part = ""
    if "※" in raw_town:
        parts = raw_town.split("※", 1)
        raw_town = parts[0]
        note_part = parts[1].strip()

    m_paren = re.search(r"[（\(](.*?)[）\)]", raw_town)
    paren_sub = m_paren.group(1).strip() if m_paren else ""
    base = re.sub(r"[（\(].*?[）\)]", "", raw_town).strip()

    sub_parts = [p for p in [paren_sub, note_part] if p]
    sub = " ".join(sub_parts)

    m_chome = re.search(r"([0-9０-９一二三四五六七八九十・～~〜\-]+丁目.*)$", base)
    if m_chome:
        chome = m_chome.group(1)
        town = base[: m_chome.start()]
    else:
        m_banchi = re.search(r"([0-9０-９一二三四五六七八九十・～~〜\-]+番(?:地)?.*)$", base)
        if m_banchi:
            chome = m_banchi.group(1)
            town = base[: m_banchi.start()]
        else:
            chome = ""
            town = base

    if not town and chome:
        town = chome
        chome = ""

    return town.strip(), chome.strip(), sub.strip()


def normalize_kitakyushu(input_path: str, output_path: str):
    if not os.path.exists(input_path):
        print(f"[!] Input file missing: {input_path}", file=sys.stderr)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw_records = data.get("data", []) if isinstance(data, dict) else data

    records: List[Dict[str, Any]] = []
    used_slugs: Set[str] = set()

    for r in raw_records:
        ward_ja = r.get("ward_ja", "").strip()
        ward_en = r.get("ward_en", "").strip()
        raw_town = r.get("town", "").strip()

        town, chome, sub = parse_town_str(raw_town)
        t_romaji = to_romaji(town)

        nums_c = extract_nums(chome)
        nums_s = extract_nums(sub)

        slug_parts = [t_romaji]
        if nums_c:
            slug_parts.append(nums_c)
        if nums_s:
            slug_parts.append(nums_s)

        base_slug = f"kitakyushu/{ward_en}/" + "-".join(slug_parts)
        slug = base_slug
        idx = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{idx}"
            idx += 1
        used_slugs.add(slug)

        types: Dict[str, Any] = {}
        sched = r.get("schedule", {})
        time_slot = r.get("citywide_rules", {}).get("collection_time", "朝8:30まで")

        if sched.get("家庭ごみ"):
            days = [d for d in sched["家庭ごみ"] if d in VALID_DAYS]
            if days:
                types["burnable"] = {
                    "label": "家庭ごみ",
                    "days": days,
                    "weeks": None,
                    "time": time_slot,
                }

        if sched.get("プラスチック"):
            days = [d for d in sched["プラスチック"] if d in VALID_DAYS]
            if days:
                types["plastic"] = {
                    "label": "プラスチック",
                    "days": days,
                    "weeks": None,
                    "time": time_slot,
                }

        if sched.get("かん・びん・ペットボトル"):
            days = [d for d in sched["かん・びん・ペットボトル"] if d in VALID_DAYS]
            if days:
                types["resource"] = {
                    "label": "かん・びん・ペットボトル",
                    "days": days,
                    "weeks": None,
                    "time": time_slot,
                }

        bulky_str = sched.get("粗大ごみ", "")
        if bulky_str:
            m_b = re.search(r"第([0-9１-４])([月火水木金土日])", bulky_str)
            if m_b:
                w_num = int(m_b.group(1).translate(str.maketrans("１２３４", "1234")))
                d_char = m_b.group(2)
                types["bulky"] = {
                    "label": "粗大ごみ",
                    "days": [d_char],
                    "weeks": [w_num],
                    "time": None,
                    "note": "事前申込制",
                }
            else:
                types["bulky"] = {
                    "label": "粗大ごみ",
                    "days": [],
                    "weeks": None,
                    "time": None,
                    "note": bulky_str,
                }

        record = {
            "pref": "福岡県",
            "city": "北九州市",
            "city_en": "kitakyushu",
            "ward": ward_ja,
            "ward_en": ward_en,
            "town": town,
            "romaji": t_romaji,
            "chome": chome,
            "sub": sub,
            "slug": slug,
            "types": types,
            "rules": {
                "holiday_collection": "祝日も通常どおり収集",
                "time_by": "8:30",
                "yearend": "12/31~1/3 休止",
            },
            "source": {
                "url": r.get("source_url", "https://www.city.kitakyushu.lg.jp/kurashi/menu01_0394.html"),
                "fetched": TODAY_STR,
                "basis": "official_html",
            },
            "notes": "同一町でも番地で異なる場合は sub に分岐名",
            "raw": r,
        }
        records.append(record)

    # Verification
    assert len(records) > 0, "No records generated!"
    assert len(records) == len(used_slugs), f"Slug collision detected! {len(records)} != {len(used_slugs)}"

    for rec in records:
        assert re.match(r"^[a-z0-9\-/]+$", rec["slug"]), f"Invalid slug characters: {rec['slug']}"
        for t_k, t_v in rec["types"].items():
            assert t_k in {"burnable", "resource", "plastic", "paper_cloth", "nonburnable", "bulky"}, f"Invalid type key: {t_k}"
            for d in t_v["days"]:
                assert d in VALID_DAYS, f"Invalid day {d} in record {rec['slug']}"

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"[✔] Kitakyushu normalized successfully: {len(records)} records saved to {output_path}")
    print(f"[✔] Slugs: {len(used_slugs)} unique (duplicates: 0)")
    print("[✔] Days validation: passed for all records")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    input_file = os.path.join(base_dir, "data", "kitakyushu.json")
    output_file = os.path.join(base_dir, "data", "normalized", "kitakyushu.json")
    normalize_kitakyushu(input_file, output_file)
