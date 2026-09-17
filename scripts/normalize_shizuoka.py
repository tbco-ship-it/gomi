#!/usr/bin/env python3
"""
Normalize Shizuoka City (静岡市) Garbage Collection Schedule
-----------------------------------------------------------
Official Source: 静岡市オープンデータ 収集日程表 (XLS / XLSX)
- 葵区 (aoi): 02-1.xls (葵区住所別収集日程表（R6~）)
- 駿河区 (suruga): 02-1.xls (駿河区住所別収集日程表（R6~）)
- 清水区 (shimizu): 02-2.xlsx (清水区住所別収集日程(R3~))
Output: data/wip/shizuoka.json -> data/normalized/shizuoka.json
"""

import io
import json
import os
import re
import sys
import unicodedata
import openpyxl
import pykakasi
import requests
import xlrd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw", "shizuoka")
WIP_DIR = os.path.join(BASE_DIR, "data", "wip")
NORM_DIR = os.path.join(BASE_DIR, "data", "normalized")

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(WIP_DIR, exist_ok=True)
os.makedirs(NORM_DIR, exist_ok=True)

URL_AOI_SURUGA = "https://data.bodik.jp/dataset/d2fd1d29-187c-4d02-8f79-93321e01c8a0/resource/ea0774ef-11a9-46c3-b06e-ad6421dfea1e/download/02-1.xls"
URL_SHIMIZU = "https://data.bodik.jp/dataset/10f30c45-8329-42d1-be37-06ebd5e7dc8f/resource/1a3ebcf7-e3a6-4f2a-9d69-618df7437e41/download/02-2.xlsx"
TODAY_STR = "2026-09-17"

kakasi = pykakasi.kakasi()


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return re.sub(r"[^a-z0-9]+", "-", romaji).strip("-")


def parse_schedule_str(sched_text: str):
    """Parses '火・金', '第２木曜', '第4水曜' into (days, weeks)"""
    if not sched_text:
        return [], None

    s = unicodedata.normalize("NFKC", str(sched_text)).strip()

    weeks = None
    week_m = re.search(r"第([1-5])", s)
    if week_m:
        weeks = [int(week_m.group(1))]

    days = []
    # If 曜 is present, get the char before it
    if "曜" in s:
        for m in re.finditer(r"([月火水木金土日])曜", s):
            d = m.group(1)
            if d not in days:
                days.append(d)
    else:
        for m in re.finditer(r"([月火水木金土日])", s):
            d = m.group(1)
            if d not in days:
                days.append(d)

    return days, weeks


def split_town_name(raw_town: str):
    s = unicodedata.normalize("NFKC", raw_town).strip()
    s = s.replace("\n", " ")
    sub = ""
    m_paren = re.search(r"[\(（](.*?)[\)）]", s)
    if m_paren:
        sub = m_paren.group(1).strip()
        s = re.sub(r"[\(（].*?[\)）]", "", s).strip()

    m_chome = re.search(r"([0-9０-９一二三四五六七八九十]+(?:[~～\-][0-9０-９一二三四五六七八九十]+)?(?:丁目))", s)
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


def fetch_file(url: str, filename: str) -> bytes:
    path = os.path.join(RAW_DIR, filename)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "rb") as f:
            return f.read()
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    with open(path, "wb") as f:
        f.write(resp.content)
    return resp.content


def main():
    records = []
    slug_counts = {}

    # 1. 葵区 & 駿河区
    aoi_bytes = fetch_file(URL_AOI_SURUGA, "02-1.xls")
    wb1 = xlrd.open_workbook(file_contents=aoi_bytes)

    for ward_ja, ward_en, sheet_name in [
        ("葵区", "aoi", "葵区住所別収集日程表（R6~）"),
        ("駿河区", "suruga", "駿河区住所別収集日程表（R6~）"),
    ]:
        sheet = wb1.sheet_by_name(sheet_name)
        for rx in range(2, sheet.nrows):
            row = sheet.row_values(rx)
            raw_town = str(row[1]).strip()
            if not raw_town:
                continue

            town, chome, sub = split_town_name(raw_town)
            burn_text = str(row[2]).strip()
            sodai_text = str(row[3]).strip()
            metal_text = str(row[4]).strip()

            types = {}

            b_days, b_weeks = parse_schedule_str(burn_text)
            if b_days:
                types["burnable"] = {"label": "可燃ごみ", "days": b_days, "weeks": b_weeks, "time": None}

            nb_days, nb_weeks = parse_schedule_str(sodai_text)
            if nb_days:
                types["nonburnable"] = {
                    "label": "不燃・粗大ごみ（戸別収集）",
                    "days": nb_days,
                    "weeks": nb_weeks,
                    "time": None,
                    "note": "戸別収集",
                }

            res_days, res_weeks = parse_schedule_str(metal_text)
            if res_days:
                types["resource"] = {
                    "label": "びん・缶 小物金属類",
                    "days": res_days,
                    "weeks": res_weeks,
                    "time": None,
                }

            town_romaji = to_romaji(town) or "town"
            slug_parts = ["shizuoka", ward_en, town_romaji]
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
                "city": "静岡市",
                "city_en": "shizuoka",
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
                },
                "source": {
                    "url": URL_AOI_SURUGA,
                    "fetched": TODAY_STR,
                    "basis": "official_xlsx",
                },
                "raw": {
                    "raw_town": raw_town,
                    "burnable": burn_text,
                    "nonburnable_bulky": sodai_text,
                    "bin_can_metal": metal_text,
                },
            }
            records.append(rec)

    # 2. 清水区
    shimizu_bytes = fetch_file(URL_SHIMIZU, "02-2.xlsx")
    wb2 = openpyxl.load_workbook(io.BytesIO(shimizu_bytes))
    sheet2 = wb2["清水区住所別収集日程(R3~)"]

    for row in list(sheet2.iter_rows(values_only=True))[2:]:
        if not row or len(row) < 5 or not row[1]:
            continue

        raw_town = str(row[1]).strip()
        town, chome, sub = split_town_name(raw_town)
        burn_text = str(row[2]).strip() if row[2] else ""
        nb_text = str(row[3]).strip() if row[3] else ""
        res_text = str(row[4]).strip() if row[4] else ""

        types = {}

        b_days, b_weeks = parse_schedule_str(burn_text)
        if b_days:
            types["burnable"] = {"label": "可燃ごみ", "days": b_days, "weeks": b_weeks, "time": None}

        nb_days, nb_weeks = parse_schedule_str(nb_text)
        if nb_days:
            types["nonburnable"] = {
                "label": "不燃・粗大ごみ",
                "days": nb_days,
                "weeks": nb_weeks,
                "time": None,
            }

        res_days, res_weeks = parse_schedule_str(res_text)
        if res_days:
            types["resource"] = {
                "label": "びん・缶 ペットボトル",
                "days": res_days,
                "weeks": res_weeks,
                "time": None,
            }

        town_romaji = to_romaji(town) or "town"
        slug_parts = ["shizuoka", "shimizu", town_romaji]
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
            "city": "静岡市",
            "city_en": "shizuoka",
            "ward": "清水区",
            "ward_en": "shimizu",
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
                "resource_district": res_text if not res_days else None,
            },
            "source": {
                "url": URL_SHIMIZU,
                "fetched": TODAY_STR,
                "basis": "official_xlsx",
            },
            "raw": {
                "raw_town": raw_town,
                "burnable": burn_text,
                "nonburnable_bulky": nb_text,
                "resource": res_text,
            },
        }
        records.append(rec)

    wip_file = os.path.join(WIP_DIR, "shizuoka.json")
    with open(wip_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"[✔] Generated {len(records)} records for Shizuoka -> {wip_file}")


if __name__ == "__main__":
    main()
