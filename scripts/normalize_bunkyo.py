#!/usr/bin/env python3
"""Normalize Bunkyo Ward (文京区) Garbage Collection Schedule
Source: Official Open Data XLSX (bunkyo.xlsx)
Output: data/normalized/bunkyo.json
"""
import json
import os
import re
import unicodedata
from typing import Dict, List, Any, Set
import openpyxl
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
    # Extract weeks if present: "第1・第3木曜日" -> [1, 3]
    weeks = None
    w_nums = re.findall(r"第?([0-9]+)", val_norm)
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


def split_chome(chome_raw: str):
    c = unicodedata.normalize("NFKC", str(chome_raw)).strip()
    m = re.match(r"^(\d+丁目)(.*)$", c)
    if m:
        return m.group(1), m.group(2).strip()
    return c, ""


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    xlsx_path = os.path.join(base_dir, "data", "raw", "bunkyo", "bunkyo.xlsx")
    out_path = os.path.join(base_dir, "data", "normalized", "bunkyo.json")

    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    data_rows = rows[1:]

    records = []
    used_slugs: Set[str] = set()

    for r in data_rows:
        town = str(r[0]).strip()
        chome_val = str(r[1]).strip()
        chome, sub = split_chome(chome_val)

        romaji_town = to_romaji(town)
        chome_slug = to_romaji(chome) if chome else ""
        sub_slug = to_romaji(sub) if sub else ""

        slug_parts = ["bunkyo", romaji_town]
        if chome_slug:
            slug_parts.append(chome_slug)
        if sub_slug:
            slug_parts.append(sub_slug)

        base_slug = "-".join([s for s in slug_parts if s])
        base_slug = re.sub(r"[^a-z0-9\-]+", "-", base_slug).strip("-")
        base_slug = re.sub(r"-+", "-", base_slug)
        if base_slug.startswith("bunkyo-"):
            base_slug = "bunkyo/" + base_slug[len("bunkyo-") :]
        elif base_slug == "bunkyo":
            base_slug = "bunkyo/area"

        slug = base_slug
        idx = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{idx}"
            idx += 1
        used_slugs.add(slug)

        types = {}
        # r[2]: 可燃ごみ（週2回）
        if r[2]:
            c_val = parse_schedule_cell(r[2], "可燃ごみ")
            if c_val:
                types["burnable"] = c_val
        # r[3]: 不燃ごみ（月2回）
        if r[3]:
            c_val = parse_schedule_cell(r[3], "不燃ごみ")
            if c_val:
                types["nonburnable"] = c_val
        # r[4]: 資源（新聞、雑誌、雑がみ、段ボール、びん、缶、ペットボトル）（週1回）
        if r[4]:
            c_val = parse_schedule_cell(r[4], "資源")
            if c_val:
                types["resource"] = c_val
        # r[5]: 資源（プラスチック）（週1回）
        if r[5]:
            c_val = parse_schedule_cell(r[5], "資源（プラスチック）")
            if c_val:
                types["plastic"] = c_val

        raw_dict = dict(zip(header, [str(x) if x is not None else "" for x in r]))

        record = {
            "pref": "東京都",
            "city": "文京区",
            "city_en": "bunkyo",
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
                "url": "https://www.city.bunkyo.lg.jp/documents/1915/r06bunkyou-gomisyuushuu.xlsx",
                "fetched": TODAY_STR,
                "basis": "official_xlsx",
            },
            "raw": raw_dict,
        }
        records.append(record)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"bunkyo: {len(records)} records written -> {out_path}")


if __name__ == "__main__":
    main()
