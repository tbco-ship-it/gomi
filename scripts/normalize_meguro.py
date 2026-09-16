#!/usr/bin/env python3
"""Normalize Meguro Ward (目黒区) Garbage Collection Schedule
Source: Official PDF (youbi.pdf)
Output: data/normalized/meguro.json
"""
import json
import os
import re
import unicodedata
from typing import Dict, List, Any, Set
import pdfplumber
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
    val_norm = unicodedata.normalize("NFKC", str(val))

    weeks = None
    w_nums = re.findall(r"第?\s*([0-9]+)", val_norm)
    if ("第" in val_norm or "回" in val_norm) and w_nums:
        weeks = [int(w) for w in w_nums if int(w) <= 5]
        if not weeks:
            weeks = None

    days = []
    for m in re.finditer(r"([月火水木金土日])曜", val_norm):
        d = m.group(1)
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


def split_area(raw_area: str):
    s = unicodedata.normalize("NFKC", raw_area).strip()
    m = re.match(r"^([^\d]+)(\d+.*?丁目.*)$", s)
    if m:
        return m.group(1), m.group(2).strip(), ""
    return s, "", ""


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pdf_path = os.path.join(base_dir, "data", "raw", "meguro", "youbi.pdf")
    out_path = os.path.join(base_dir, "data", "normalized", "meguro.json")

    all_rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for p in pdf.pages:
            tables = p.extract_tables()
            for t in tables:
                for r in t:
                    if r[1] and r[1] not in ["地 域", None] and r[2] != "週１回":
                        all_rows.append(r)

    records = []
    used_slugs: Set[str] = set()

    for r in all_rows:
        raw_area = r[1].replace("\n", "").strip()
        raw_res = r[2].replace("\n", "").strip()
        raw_burn = r[3].replace("\n", "").strip()
        raw_non = r[4].replace("\n", "").strip()

        town, chome, sub = split_area(raw_area)
        romaji_town = to_romaji(town)
        chome_slug = to_romaji(chome) if chome else ""
        sub_slug = to_romaji(sub) if sub else ""

        slug_parts = ["meguro", romaji_town]
        if chome_slug:
            slug_parts.append(chome_slug)
        if sub_slug:
            slug_parts.append(sub_slug)

        base_slug = "-".join([s for s in slug_parts if s])
        base_slug = re.sub(r"[^a-z0-9\-]+", "-", base_slug).strip("-")
        base_slug = re.sub(r"-+", "-", base_slug)
        if base_slug.startswith("meguro-"):
            base_slug = "meguro/" + base_slug[len("meguro-") :]
        elif base_slug == "meguro":
            base_slug = "meguro/area"

        slug = base_slug
        idx = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{idx}"
            idx += 1
        used_slugs.add(slug)

        types = {}
        c_burn = parse_schedule_cell(raw_burn, "燃やすごみ")
        if c_burn:
            types["burnable"] = c_burn

        c_non = parse_schedule_cell(raw_non, "燃やさないごみ")
        if c_non:
            types["nonburnable"] = c_non

        c_res = parse_schedule_cell(raw_res, "資源")
        if c_res:
            types["resource"] = c_res

        raw_dict = {
            "地域": raw_area,
            "資源": raw_res,
            "燃やすごみ": raw_burn,
            "燃やさないごみ": raw_non,
        }

        record = {
            "pref": "東京都",
            "city": "目黒区",
            "city_en": "meguro",
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
                "url": "https://www.city.meguro.tokyo.jp/documents/4335/h28syuusyuuyoubi.pdf",
                "fetched": TODAY_STR,
                "basis": "official_pdf",
            },
            "raw": raw_dict,
        }
        records.append(record)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"meguro: {len(records)} records written -> {out_path}")


if __name__ == "__main__":
    main()
