#!/usr/bin/env python3
"""
Normalize Hamamatsu City (浜松市) Garbage Collection Schedule
-----------------------------------------------------------
Official Source: 浜松市役所
- 町別カレンダーNo一覧: https://www.city.hamamatsu.shizuoka.jp/documents/14182/machibetsuichiran2026.csv
- カレンダーNo別収集日一覧: https://www.city.hamamatsu.shizuoka.jp/documents/14182/syusyubiichiran2026.csv
Output: data/wip/hamamatsu.json -> data/normalized/hamamatsu.json
"""

import csv
import io
import json
import os
import re
import sys
import unicodedata
import pykakasi
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw", "hamamatsu")
WIP_DIR = os.path.join(BASE_DIR, "data", "wip")
NORM_DIR = os.path.join(BASE_DIR, "data", "normalized")

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(WIP_DIR, exist_ok=True)
os.makedirs(NORM_DIR, exist_ok=True)

URL_MACHI = "https://www.city.hamamatsu.shizuoka.jp/documents/14182/machibetsuichiran2026.csv"
URL_SYU = "https://www.city.hamamatsu.shizuoka.jp/documents/14182/syusyubiichiran2026.csv"
TODAY_STR = "2026-09-17"

WARD_MAP = {
    "中央区": "chuo",
    "浜名区": "hamana",
    "天竜区": "tenryu",
}

kakasi = pykakasi.kakasi()


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return re.sub(r"[^a-z0-9]+", "-", romaji).strip("-")


def fetch_file(url: str, fname: str) -> str:
    path = os.path.join(RAW_DIR, fname)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    text = resp.content.decode("cp932", errors="replace")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return text


def build_area_schedules(syu_text: str):
    """Summarizes 365-day schedule into weekly days per item for each area No."""
    reader = csv.DictReader(io.StringIO(syu_text))
    area_cols = [c for c in reader.fieldnames if "収集区域" in c]

    # Map area_num -> item -> list of days
    # Items: burnable (可燃), plastic (プラマーク), nonburnable (不燃), resource (びん・かん・ペット)
    area_map = {}
    day_counts = {col.replace("収集区域", ""): {} for col in area_cols}

    for r in reader:
        yobi = r.get("曜日", "").strip()
        if yobi not in "月火水木金土日":
            continue
        for col in area_cols:
            no_str = col.replace("収集区域", "")
            raw_val = r.get(col, "").strip()
            if not raw_val:
                continue

            sub_items = []
            if "可燃" in raw_val:
                sub_items.append("burnable")
            if "プラ" in raw_val:
                sub_items.append("plastic")
            if "不燃" in raw_val:
                sub_items.append("nonburnable")
            if "びん" in raw_val or "かん" in raw_val or "ペット" in raw_val:
                sub_items.append("resource")

            for it in sub_items:
                if it not in day_counts[no_str]:
                    day_counts[no_str][it] = {}
                day_counts[no_str][it][yobi] = day_counts[no_str][it].get(yobi, 0) + 1

    # Format into types
    order = ["月", "火", "水", "木", "金", "土", "日"]
    labels = {
        "burnable": "可燃ごみ",
        "plastic": "プラスチック製容器包装",
        "nonburnable": "不燃ごみ",
        "resource": "資源物（びん・かん・ペットボトル）",
    }

    for no_str, items in day_counts.items():
        area_types = {}
        for it, counts in items.items():
            # Keep weekdays that have at least 10 collections in the year
            valid_days = [d for d in order if counts.get(d, 0) >= 8]
            if valid_days:
                area_types[it] = {
                    "label": labels.get(it, it),
                    "days": valid_days,
                    "weeks": None,
                    "time": None,
                }
        area_map[no_str] = area_types

    return area_map


def split_town_name(raw_town: str):
    s = unicodedata.normalize("NFKC", raw_town).strip()
    sub = ""
    m_paren = re.search(r"[\(（](.*?)[\)）]", s)
    if m_paren:
        sub = m_paren.group(1).strip()
        s = re.sub(r"[\(（].*?[\)）]", "", s).strip()

    m_chome = re.search(r"([0-9０-９一二三四五六七八九十]+(?:[~～\-]+[0-9０-９一二三四五六七八九十]+)?(?:丁目))", s)
    chome = ""
    if m_chome:
        chome = m_chome.group(1)
        town = s[:m_chome.start()].strip()
        rem = s[m_chome.end():].strip()
        if rem:
            sub = f"{rem} {sub}".strip()
    else:
        town = s

    return town, chome if chome else None, sub if sub else None


def main():
    machi_text = fetch_file(URL_MACHI, "machibetsuichiran2026.csv")
    syu_text = fetch_file(URL_SYU, "syusyubiichiran2026.csv")

    area_schedules = build_area_schedules(syu_text)

    reader = csv.DictReader(io.StringIO(machi_text))
    records = []
    slug_counts = {}

    for row in reader:
        ward_ja = row.get("行政区", "").strip()
        if ward_ja not in WARD_MAP:
            continue
        ward_en = WARD_MAP[ward_ja]

        raw_town = row.get("町名", "").strip()
        yomi = row.get("読み", "").strip()
        cal_no = row.get("No.", "").strip()

        town, chome, sub = split_town_name(raw_town)
        types = area_schedules.get(cal_no, {})

        town_romaji = to_romaji(yomi if yomi else town) or "town"
        slug_parts = ["hamamatsu", ward_en, town_romaji]
        if chome:
            nums = "".join(re.findall(r"\d+", unicodedata.normalize("NFKC", chome)))
            slug_parts.append(f"{nums}chome" if nums else to_romaji(chome))
        if sub:
            sub_r = to_romaji(sub)
            if sub_r:
                slug_parts.append(sub_r[:20])

        base_slug = "/".join(slug_parts)
        base_slug = re.sub(r"-+", "-", base_slug).strip("-")
        base_slug = re.sub(r"/+", "/", base_slug).lower()

        cnt = slug_counts.get(base_slug, 0) + 1
        slug_counts[base_slug] = cnt
        slug = base_slug if cnt == 1 else f"{base_slug}-{cnt}"

        rec = {
            "pref": "静岡県",
            "city": "浜松市",
            "city_en": "hamamatsu",
            "ward": ward_ja,
            "ward_en": ward_en,
            "town": town,
            "chome": chome,
            "sub": sub,
            "romaji": town_romaji,
            "slug": slug,
            "types": types,
            "rules": {
                "holiday_collection": "祝日も収集（年末年始除く）",
                "time_by": "8:30",
                "yearend": "12/31~1/3 休止",
                "calendar_no": cal_no,
            },
            "source": {
                "url": "https://www.city.hamamatsu.shizuoka.jp/ippai/gomi/dashikata/calendar/index.html",
                "fetched": TODAY_STR,
                "basis": "official_csv",
            },
            "raw": dict(row),
        }
        records.append(rec)

    wip_file = os.path.join(WIP_DIR, "hamamatsu.json")
    with open(wip_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"[✔] Generated {len(records)} records for Hamamatsu -> {wip_file}")


if __name__ == "__main__":
    main()
