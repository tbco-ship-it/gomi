#!/usr/bin/env python3
"""Normalize Itabashi Ward (板橋区) Garbage Collection Schedule
Source: Official PDF (itabashi.pdf Page 2)
Output: data/normalized/itabashi.json
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
    w_nums = re.findall(r"([0-9]+)", val_norm.split("回目")[0] if "回目" in val_norm else "")
    if "回目" in val_norm and w_nums:
        weeks = [int(w) for w in w_nums if int(w) <= 5]

    days = []
    # If 曜 is present
    for m in re.finditer(r"([月火水木金土日])曜?", val_norm):
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
    m = re.match(r"^([^\d]+)(\d+.*?丁目)(.*)$", s)
    if m:
        return m.group(1), m.group(2).strip(), m.group(3).strip()
    return s, "", ""


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pdf_path = os.path.join(base_dir, "data", "raw", "itabashi", "itabashi.pdf")
    out_path = os.path.join(base_dir, "data", "normalized", "itabashi.json")

    with pdfplumber.open(pdf_path) as pdf:
        p = pdf.pages[1]
        txt = p.extract_text() or ""

    pattern = re.compile(
        r"([^\s]+?)\s+([月火水木金土日])\s+([月火水木金土日・]+)\s+(毎月[0-9１-９・〜]+回目の[月火水木金土日])\s+(東清掃|西清掃)"
    )

    records = []
    used_slugs: Set[str] = set()

    for l in txt.splitlines():
        l_norm = unicodedata.normalize("NFKC", l)
        for m in pattern.findall(l_norm):
            raw_area = m[0].strip()
            raw_res = m[1].strip()
            raw_burn = m[2].strip()
            raw_non = m[3].strip()
            office = m[4].strip()

            town, chome, sub = split_area(raw_area)
            romaji_town = to_romaji(town)
            chome_slug = to_romaji(chome) if chome else ""
            sub_slug = to_romaji(sub) if sub else ""

            slug_parts = ["itabashi", romaji_town]
            if chome_slug:
                slug_parts.append(chome_slug)
            if sub_slug:
                slug_parts.append(sub_slug)

            base_slug = "-".join([s for s in slug_parts if s])
            base_slug = re.sub(r"[^a-z0-9\-]+", "-", base_slug).strip("-")
            base_slug = re.sub(r"-+", "-", base_slug)
            if base_slug.startswith("itabashi-"):
                base_slug = "itabashi/" + base_slug[len("itabashi-") :]
            elif base_slug == "itabashi":
                base_slug = "itabashi/area"

            slug = base_slug
            idx = 2
            while slug in used_slugs:
                slug = f"{base_slug}-{idx}"
                idx += 1
            used_slugs.add(slug)

            types = {}
            c_burn = parse_schedule_cell(raw_burn, "可燃ごみ")
            if c_burn:
                types["burnable"] = c_burn

            c_non = parse_schedule_cell(raw_non, "不燃ごみ")
            if c_non:
                types["nonburnable"] = c_non

            c_res = parse_schedule_cell(raw_res, "資源")
            if c_res:
                types["resource"] = c_res

            raw_dict = {
                "地域": raw_area,
                "資源": raw_res,
                "可燃ごみ": raw_burn,
                "不燃ごみ": raw_non,
                "管轄の事務所": office,
            }

            record = {
                "pref": "東京都",
                "city": "板橋区",
                "city_en": "itabashi",
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
                    "url": "https://www.city.itabashi.tokyo.jp/tetsuduki/gomi/recycle/1000673.html",
                    "fetched": TODAY_STR,
                    "basis": "official_pdf",
                },
                "raw": raw_dict,
            }
            records.append(record)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"itabashi: {len(records)} records written -> {out_path}")


if __name__ == "__main__":
    main()
