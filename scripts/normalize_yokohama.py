#!/usr/bin/env python3
"""
Normalize Yokohama City (横浜市) Garbage Collection Schedule
------------------------------------------------------------
Reads data/yokohama_full.json (1,088 records) and converts them into unified schema:
data/normalized/yokohama.json

Schema rules:
- Top-level pure JSON array
- Standard waste type keys: burnable, resource, plastic, paper_cloth, nonburnable, bulky
- Preserves collection time slot (朝8:00まで)
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


import unicodedata


def parse_town_str(raw_town: str) -> Tuple[str, str, str]:
    raw_town = unicodedata.normalize("NFKC", raw_town).strip().lstrip("*#※・ ")
    sub_parts: List[str] = []

    # 1. ※ notes
    if "※" in raw_town:
        parts = raw_town.split("※")
        raw_town = parts[0].strip()
        for p in parts[1:]:
            if p.strip():
                sub_parts.append(p.strip())

    # 2. 【...】 brackets
    while "【" in raw_town and "】" in raw_town:
        m = re.search(r"【(.*?)】", raw_town)
        if not m:
            break
        sub_parts.append(m.group(1).strip())
        raw_town = raw_town[: m.start()] + raw_town[m.end() :]
        raw_town = raw_town.strip()

    # 3. (...) parens
    while "(" in raw_town and ")" in raw_town:
        m = re.search(r"\(([^()]*)\)", raw_town)
        if not m:
            break
        sub_parts.append(m.group(1).strip())
        raw_town = raw_town[: m.start()] + raw_town[m.end() :]
        raw_town = raw_town.strip()

    # Unclosed paren like '(本牧通り沿い'
    if "(" in raw_town:
        m = re.search(r"\(+(.*)$", raw_town)
        if m:
            sub_parts.append(m.group(1).strip())
            raw_town = raw_town[: m.start()].strip()

    base = raw_town.strip()

    # 4. Check 丁目
    m_chome = re.search(r"([0-9・~〜\-]+丁目)", base)
    if m_chome:
        chome = m_chome.group(1).strip()
        town = base[: m_chome.start()].strip()
        extra = base[m_chome.end() :].strip()
        if extra:
            sub_parts.insert(0, extra)
    else:
        chome = ""
        m_dig = re.search(r"(第?\d+.*)$", base)
        if m_dig:
            town = base[: m_dig.start()].strip()
            sub_parts.insert(0, m_dig.group(1).strip())
        else:
            text_sub_pat = r"(京急線.*側|称名寺一方通行側|環状線.*|柏葉公園通り側|本牧通り.*側|共立学園周辺|大鳥小学校周辺|バス通り周辺|平楽境|の一部.*)$"
            m_text = re.search(text_sub_pat, base)
            if m_text:
                town = base[: m_text.start()].strip()
                sub_parts.insert(0, m_text.group(1).strip())
            else:
                town = base

    if town == "野庭町野庭町":
        town = "野庭町"
    if town.endswith("の一部"):
        sub_parts.insert(0, "一部")
        town = town[:-3].strip()

    sub = " ".join(p for p in sub_parts if p).strip()
    return town.strip(), chome.strip(), sub.strip()


def normalize_yokohama(input_path: str, output_path: str):
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

        base_slug = f"yokohama/{ward_en}/" + "-".join(slug_parts)
        slug = base_slug
        idx = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{idx}"
            idx += 1
        used_slugs.add(slug)

        types: Dict[str, Any] = {}
        st = r.get("schedule_by_type", {})
        ds = r.get("derived_schedule", {})
        time_slot = r.get("collection_time", "朝8:00まで")

        if st.get("燃やすごみ"):
            days = [d for d in st["燃やすごみ"] if d in VALID_DAYS]
            if days:
                types["burnable"] = {
                    "label": "燃やすごみ",
                    "days": days,
                    "weeks": None,
                    "time": time_slot,
                }

        if st.get("プラスチック資源"):
            days = [d for d in st["プラスチック資源"] if d in VALID_DAYS]
            if days:
                types["plastic"] = {
                    "label": "プラスチック資源",
                    "days": days,
                    "weeks": None,
                    "time": time_slot,
                }

        if st.get("缶・びん・ペットボトル"):
            days = [d for d in st["缶・びん・ペットボトル"] if d in VALID_DAYS]
            if days:
                types["resource"] = {
                    "label": "缶・びん・ペットボトル",
                    "days": days,
                    "weeks": None,
                    "time": time_slot,
                }

        if ds.get("燃えないごみ"):
            days = [d for d in ds["燃えないごみ"] if d in VALID_DAYS]
            if days:
                types["nonburnable"] = {
                    "label": "燃えないごみ",
                    "days": days,
                    "weeks": None,
                    "time": time_slot,
                }

        rules = {
            "holiday_collection": "祝日も収集",
            "time_by": "8:00",
            "yearend": "12/31~1/3 休止",
        }
        if not types:
            raw_sbd = r.get("schedule_by_day", {})
            note_candidates = [v for v in raw_sbd.values() if "問合" in v or "事務所" in v]
            if note_candidates:
                rules["note"] = note_candidates[0]
            elif raw_sbd:
                rules["note"] = ", ".join(raw_sbd.values())
            else:
                rules["note"] = "事務所にお問合せください"

        record = {
            "pref": "神奈川県",
            "city": "横浜市",
            "city_en": "yokohama",
            "ward": ward_ja,
            "ward_en": ward_en,
            "town": town,
            "romaji": t_romaji,
            "chome": chome,
            "sub": sub,
            "slug": slug,
            "types": types,
            "rules": rules,
            "source": {
                "url": r.get("source_url", "https://www.city.yokohama.lg.jp/kurashi/sumai-kurashi/gomi-recycle/gomi/shushu/"),
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

    print(f"[✔] Yokohama normalized successfully: {len(records)} records saved to {output_path}")
    print(f"[✔] Slugs: {len(used_slugs)} unique (duplicates: 0)")
    print("[✔] Days validation: passed for all records")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    input_file = os.path.join(base_dir, "data", "yokohama_full.json")
    output_file = os.path.join(base_dir, "data", "normalized", "yokohama.json")
    normalize_yokohama(input_file, output_file)
