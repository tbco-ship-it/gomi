#!/usr/bin/env python3
"""Normalize Suginami Ward (杉並区) Garbage Collection Schedule
Source: Official threeR calendar (suginami_raw.json)
Output: data/normalized/suginami.json
"""
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


def split_chome_sub(chome_raw: str):
    c = unicodedata.normalize("NFKC", chome_raw).strip()
    m = re.match(r"^(\d+.*?丁目)(.*)$", c)
    if m:
        return m.group(1), m.group(2).strip()
    return c, ""


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_path = os.path.join(base_dir, "data", "raw", "suginami", "suginami_raw.json")
    out_path = os.path.join(base_dir, "data", "normalized", "suginami.json")

    with open(raw_path, "r", encoding="utf-8") as f:
        raw_items = json.load(f)

    records = []
    used_slugs: Set[str] = set()

    for item in raw_items:
        town = item["town"]
        chome_val = item.get("chome", "")
        chome, sub = split_chome_sub(chome_val)

        romaji_town = to_romaji(town)
        chome_slug = to_romaji(chome) if chome else ""
        sub_slug = to_romaji(sub) if sub else ""

        slug_parts = ["suginami", romaji_town]
        if chome_slug:
            slug_parts.append(chome_slug)
        if sub_slug:
            slug_parts.append(sub_slug)

        base_slug = "-".join([s for s in slug_parts if s])
        base_slug = re.sub(r"[^a-z0-9\-]+", "-", base_slug).strip("-")
        base_slug = re.sub(r"-+", "-", base_slug)
        if base_slug.startswith("suginami-"):
            base_slug = "suginami/" + base_slug[len("suginami-") :]
        elif base_slug == "suginami":
            base_slug = "suginami/area"

        slug = base_slug
        idx = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{idx}"
            idx += 1
        used_slugs.add(slug)

        types = {}
        if item.get("burnable"):
            types["burnable"] = {
                "label": "可燃ごみ",
                "days": item["burnable"],
                "weeks": None,
                "time": "朝8:30まで",
            }
        if item.get("nonburnable"):
            types["nonburnable"] = {
                "label": "不燃ごみ",
                "days": item["nonburnable"],
                "weeks": item.get("nonburnable_weeks"),
                "time": "朝8:30まで",
            }
        # Combine binkan and pet for resource
        res_days = sorted(list(set((item.get("binkan") or []) + (item.get("pet") or []))))
        if res_days:
            types["resource"] = {
                "label": "びん・かん・ペットボトル",
                "days": res_days,
                "weeks": None,
                "time": "朝8:30まで",
            }
        if item.get("plastic"):
            types["plastic"] = {
                "label": "プラ",
                "days": item["plastic"],
                "weeks": None,
                "time": "朝8:30まで",
            }
        if item.get("paper"):
            types["paper_cloth"] = {
                "label": "古紙",
                "days": item["paper"],
                "weeks": None,
                "time": "朝8:30まで",
            }

        record = {
            "pref": "東京都",
            "city": "杉並区",
            "city_en": "suginami",
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
                "time_by": "朝8:30まで",
                "yearend": "12/31~1/3 休止",
            },
            "source": {
                "url": f"https://manage.delight-system.com/threeR/web/calendar?menu=calendar&jichitaiId=suginamiku&areaId={item['areaId']}",
                "fetched": TODAY_STR,
                "basis": "official_html",
            },
            "raw": item,
        }
        records.append(record)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"suginami: {len(records)} records written -> {out_path}")


if __name__ == "__main__":
    main()
