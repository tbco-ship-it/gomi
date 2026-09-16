#!/usr/bin/env python3
"""Normalize Chiyoda Ward (千代田区) Garbage Collection Schedule
Source: Official PDF (hayami.pdf)
Output: data/normalized/chiyoda.json
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
KANJI_MAP = {
    "一": "1",
    "二": "2",
    "三": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
    "十": "10",
}


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return re.sub(r"[^a-z0-9]+", "-", romaji).strip("-")


def parse_schedule_cell(val: str, label: str) -> Dict[str, Any]:
    if not val:
        return None
    val_norm = unicodedata.normalize("NFKC", str(val))

    weeks = None
    w_nums = re.findall(r"第?([0-9]+)", val_norm)
    if ("第" in val_norm or "回" in val_norm) and w_nums:
        weeks = [int(w) for w in w_nums if int(w) <= 5]
        if not weeks:
            weeks = None

    days = []
    if "曜" in val_norm:
        for m in re.finditer(r"([月火水木金土日])曜", val_norm):
            d = m.group(1)
            if d not in days:
                days.append(d)
    else:
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


def split_addr(addr: str):
    a = unicodedata.normalize("NFKC", addr).strip()
    m = re.match(r"^([^\d一二三四五六七八九]+)(.+?丁目)(.*)$", a)
    if m:
        town = m.group(1)
        chome = m.group(2)
        sub = m.group(3).strip()
        for k, v in KANJI_MAP.items():
            chome = chome.replace(k, v)
        return town, chome, sub
    m2 = re.match(r"^([^\d]+)(\d+.*?番.*)$", a)
    if m2:
        return m2.group(1), "", m2.group(2).strip()
    return a, "", ""


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pdf_path = os.path.join(base_dir, "data", "raw", "chiyoda", "hayami.pdf")
    out_path = os.path.join(base_dir, "data", "normalized", "chiyoda.json")

    all_rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for p in pdf.pages:
            tables = p.extract_tables()
            if tables:
                for r in tables[0][3:]:
                    if r[1]:
                        all_rows.append(r)

    records = []
    used_slugs: Set[str] = set()

    for r in all_rows:
        addr_raw = r[1].strip()
        burn_raw = r[2].strip() if r[2] else ""
        non_raw = r[3].strip() if r[3] else ""
        res_raw = r[4].strip() if r[4] else ""
        pla_raw = r[5].strip() if len(r) > 5 and r[5] else ""

        town, chome, sub = split_addr(addr_raw)
        romaji_town = to_romaji(town)
        chome_slug = to_romaji(chome) if chome else ""
        sub_slug = to_romaji(sub) if sub else ""

        slug_parts = ["chiyoda", romaji_town]
        if chome_slug:
            slug_parts.append(chome_slug)
        if sub_slug:
            slug_parts.append(sub_slug)

        base_slug = "-".join([s for s in slug_parts if s])
        base_slug = re.sub(r"[^a-z0-9\-]+", "-", base_slug).strip("-")
        base_slug = re.sub(r"-+", "-", base_slug)
        if base_slug.startswith("chiyoda-"):
            base_slug = "chiyoda/" + base_slug[len("chiyoda-") :]
        elif base_slug == "chiyoda":
            base_slug = "chiyoda/area"

        slug = base_slug
        idx = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{idx}"
            idx += 1
        used_slugs.add(slug)

        types = {}
        c_burn = parse_schedule_cell(burn_raw, "燃やすごみ")
        if c_burn:
            types["burnable"] = c_burn

        c_non = parse_schedule_cell(non_raw, "燃やさないごみ")
        if c_non:
            types["nonburnable"] = c_non

        c_res = parse_schedule_cell(res_raw, "資源")
        if c_res:
            types["resource"] = c_res

        c_pla = parse_schedule_cell(pla_raw, "プラスチック")
        if c_pla:
            types["plastic"] = c_pla

        raw_dict = {
            "カナ": r[0] if r[0] else "",
            "住所": r[1],
            "燃やすごみ": r[2],
            "燃やさないごみ": r[3],
            "資源": r[4],
            "プラスチック": r[5] if len(r) > 5 else "",
        }

        record = {
            "pref": "東京都",
            "city": "千代田区",
            "city_en": "chiyoda",
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
                "url": "https://www.city.chiyoda.lg.jp/koho/kurashi/gomi/wakekata/hayami.html",
                "fetched": TODAY_STR,
                "basis": "official_pdf",
            },
            "raw": raw_dict,
        }
        records.append(record)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"chiyoda: {len(records)} records written -> {out_path}")


if __name__ == "__main__":
    main()
