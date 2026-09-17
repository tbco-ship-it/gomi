#!/usr/bin/env python3
"""
Normalize Sendai City (仙台市) Garbage Collection Schedule
---------------------------------------------------------
Official Source: 仙台市役所 収集曜日一覧 (PDF)
- 青葉区: 01_aoba.pdf
- 宮城野区: 02_miyagino.pdf
- 若林区: 03_wakabayashi.pdf
- 太白区: 04_taihaku.pdf
- 泉区: 05_izumi.pdf
Output: data/wip/sendai.json -> data/normalized/sendai.json
"""

import io
import json
import os
import re
import sys
import unicodedata
import pdfplumber
import pykakasi
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw", "sendai")
WIP_DIR = os.path.join(BASE_DIR, "data", "wip")
NORM_DIR = os.path.join(BASE_DIR, "data", "normalized")

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(WIP_DIR, exist_ok=True)
os.makedirs(NORM_DIR, exist_ok=True)

PDF_BASE_URL = "https://www.city.sendai.jp/haiki-shido/kurashi/machi/genryo/gomi/yobi/documents/"
SOURCE_PAGE = "https://www.city.sendai.jp/haiki-shido/kurashi/machi/genryo/gomi/yobi/ichiran.html"
TODAY_STR = "2026-09-17"

WARDS = [
    ("青葉区", "aoba", "01_aoba.pdf"),
    ("宮城野区", "miyagino", "02_miyagino.pdf"),
    ("若林区", "wakabayashi", "03_wakabayashi.pdf"),
    ("太白区", "taihaku", "04_taihaku.pdf"),
    ("泉区", "izumi", "05_izumi.pdf"),
]

kakasi = pykakasi.kakasi()


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return re.sub(r"[^a-z0-9]+", "-", romaji).strip("-")


def parse_schedule_cell(val: str):
    """Parses '月・木', '1･3金', '2・4水' into (days, weeks, note)"""
    if not val or "家庭ごみ集積所なし" in val or "なし" in val:
        return [], None, val if val else None

    weeks = None
    if "1･3" in val or "1・3" in val or "1,3" in val:
        weeks = [1, 3]
    elif "2･4" in val or "2・4" in val or "2,4" in val:
        weeks = [2, 4]

    days = []
    for m in re.finditer(r"([月火水木金土日])", val):
        day_char = m.group(1)
        # Avoid false positive from 曜日 if any (here day_char is in 月火水木金土日)
        if day_char in "月火水木金土日" and day_char not in days:
            days.append(day_char)

    return days, weeks, None


def split_address(addr: str):
    """Splits raw address into town, chome, sub"""
    s = unicodedata.normalize("NFKC", addr).strip()
    sub = ""
    # Extract parenthesis
    m_paren = re.search(r"[\(（](.*?)[\)）]", s)
    if m_paren:
        sub = m_paren.group(1).strip()
        s = re.sub(r"[\(（].*?[\)）]", "", s).strip()

    # Extract chome
    m_chome = re.search(r"([0-9０-９一二三四五六七八九十]+丁目)", s)
    chome = ""
    if m_chome:
        chome = m_chome.group(1)
        rem = s[m_chome.end():].strip()
        town = s[:m_chome.start()].strip()
        if rem:
            sub = f"{rem} {sub}".strip()
    else:
        # Check numbers like 13,16~18
        m_num = re.search(r"(\d+.*)$", s)
        if m_num:
            town = s[:m_num.start()].strip()
            sub = f"{m_num.group(1)} {sub}".strip()
        else:
            town = s

    return town, chome if chome else None, sub if sub else None


def fetch_pdf(filename: str) -> bytes:
    path = os.path.join(RAW_DIR, filename)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "rb") as f:
            return f.read()
    url = PDF_BASE_URL + filename
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    with open(path, "wb") as f:
        f.write(resp.content)
    return resp.content


def main():
    records = []
    slug_counts = {}

    for w_ja, w_en, fname in WARDS:
        pdf_bytes = fetch_pdf(fname)
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for p_num, page in enumerate(pdf.pages):
                for t in page.extract_tables():
                    for row in t:
                        if not row or len(row) < 6:
                            continue
                        if row[0] == "50音" or not row[1]:
                            continue

                        raw_addr = row[1].strip().replace("\n", "")
                        town, chome, sub = split_address(raw_addr)

                        # Types
                        types = {}

                        # Burnable
                        burn_days, burn_weeks, burn_note = parse_schedule_cell(row[2])
                        if burn_days:
                            types["burnable"] = {
                                "label": "家庭ごみ",
                                "days": burn_days,
                                "weeks": burn_weeks,
                                "time": None,
                            }

                        # Plastic
                        pla_days, pla_weeks, pla_note = parse_schedule_cell(row[3])
                        if pla_days:
                            types["plastic"] = {
                                "label": "プラスチック資源",
                                "days": pla_days,
                                "weeks": pla_weeks,
                                "time": None,
                            }

                        # Resource (cans, bottles, batteries)
                        res_days, res_weeks, res_note = parse_schedule_cell(row[4])
                        if res_days:
                            types["resource"] = {
                                "label": "缶・びん・ペットボトル・廃乾電池類",
                                "days": res_days,
                                "weeks": res_weeks,
                                "time": None,
                            }

                        # Paper / Cloth
                        pap_days, pap_weeks, pap_note = parse_schedule_cell(row[5])
                        if pap_days:
                            types["paper_cloth"] = {
                                "label": "紙類",
                                "days": pap_days,
                                "weeks": pap_weeks,
                                "time": None,
                            }

                        # Generate slug
                        town_romaji = to_romaji(town)
                        if not town_romaji:
                            town_romaji = "town"

                        slug_parts = ["sendai", w_en, town_romaji]
                        if chome:
                            chome_num = "".join(re.findall(r"\d+", unicodedata.normalize("NFKC", chome)))
                            slug_parts.append(f"{chome_num}chome" if chome_num else to_romaji(chome))
                        if sub:
                            sub_slug = to_romaji(sub)
                            if sub_slug:
                                slug_parts.append(sub_slug[:30])

                        base_slug = "/".join(slug_parts)
                        base_slug = re.sub(r"-+", "-", base_slug).strip("-")
                        base_slug = re.sub(r"/+", "/", base_slug).lower()

                        cnt = slug_counts.get(base_slug, 0) + 1
                        slug_counts[base_slug] = cnt
                        slug = base_slug if cnt == 1 else f"{base_slug}-{cnt}"

                        rec = {
                            "pref": "宮城県",
                            "city": "仙台市",
                            "city_en": "sendai",
                            "ward": w_ja,
                            "ward_en": w_en,
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
                            },
                            "source": {
                                "url": SOURCE_PAGE,
                                "fetched": TODAY_STR,
                                "basis": "official_pdf",
                            },
                            "raw": {
                                "kana": row[0].strip() if row[0] else "",
                                "address": raw_addr,
                                "katei": row[2].strip() if row[2] else "",
                                "plastic": row[3].strip() if row[3] else "",
                                "can_bin": row[4].strip() if row[4] else "",
                                "paper": row[5].strip() if row[5] else "",
                            },
                        }
                        records.append(rec)

    wip_file = os.path.join(WIP_DIR, "sendai.json")
    with open(wip_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"[✔] Generated {len(records)} records for Sendai -> {wip_file}")


if __name__ == "__main__":
    main()
