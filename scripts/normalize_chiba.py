#!/usr/bin/env python3
"""
Normalize Chiba City (千葉市) Garbage Collection Schedule
---------------------------------------------------------
Official Source: 千葉市役所 家庭ごみ・資源物の収集日 (HTML tables)
URL: https://www.city.chiba.jp/kankyo/junkan/shushugyomu/shushubi.html
Output: data/wip/chiba.json -> data/normalized/chiba.json
"""

import json
import os
import re
import sys
import unicodedata
import bs4
import pykakasi
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw", "chiba")
WIP_DIR = os.path.join(BASE_DIR, "data", "wip")
NORM_DIR = os.path.join(BASE_DIR, "data", "normalized")

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(WIP_DIR, exist_ok=True)
os.makedirs(NORM_DIR, exist_ok=True)

SOURCE_URL = "https://www.city.chiba.jp/kankyo/junkan/shushugyomu/shushubi.html"
TODAY_STR = "2026-09-20"

WARDS = [
    ("中央区", "chuo"),
    ("花見川区", "hanamigawa"),
    ("稲毛区", "inage"),
    ("若葉区", "wakaba"),
    ("緑区", "midori"),
    ("美浜区", "mihama"),
]

kakasi = pykakasi.kakasi()


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return re.sub(r"[^a-z0-9]+", "-", romaji).strip("-")


def parse_schedule_cell(val: str):
    if not val or val == "-" or "※" == val.strip():
        return [], None, None

    weeks = None
    if "1・3" in val or "1･3" in val:
        weeks = [1, 3]
    elif "2・4" in val or "2･4" in val:
        weeks = [2, 4]

    days = []
    for m in re.finditer(r"([月火水木金土日])", val):
        day_char = m.group(1)
        if day_char in "月火水木金土日" and day_char not in days:
            days.append(day_char)

    return days, weeks, None


def split_address(raw_town: str):
    s = unicodedata.normalize("NFKC", raw_town).strip()
    sub = ""
    m_paren = re.search(r"[\(（](.*?)[\)）]", s)
    if m_paren:
        sub = m_paren.group(1).strip()
        s = re.sub(r"[\(（].*?[\)）]", "", s).strip()

    m_chome = re.search(r"([0-9０-９一二三四五六七八九十]+(?:[~～\-][0-9０-９一二三四五六七八九十]+)?丁目)", s)
    chome = ""
    if m_chome:
        chome = m_chome.group(1)
        town = s[:m_chome.start()].strip()
        rem = s[m_chome.end():].strip()
        if rem:
            sub = f"{rem} {sub}".strip()
    else:
        m_num = re.search(r"([0-9０-９]+[~～\-][0-9０-９]+(?:丁目)?)", s)
        if m_num:
            chome = m_num.group(1)
            town = s[:m_num.start()].strip()
            rem = s[m_num.end():].strip()
            if rem:
                sub = f"{rem} {sub}".strip()
        else:
            town = s

    return town, chome if chome else None, sub if sub else None


def fetch_html() -> str:
    path = os.path.join(RAW_DIR, "shushubi.html")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    resp = requests.get(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    text = resp.text
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return text


def main():
    html_text = fetch_html()
    soup = bs4.BeautifulSoup(html_text, "html.parser")
    tables = soup.find_all("table")

    records = []
    slug_counts = {}

    for idx, (w_ja, w_en) in enumerate(WARDS):
        if idx >= len(tables):
            break
        t = tables[idx]
        for tr in t.find_all("tr"):
            tds = [unicodedata.normalize("NFKC", td.text.strip()) for td in tr.find_all(["th", "td"])]
            if not tds or "町丁名" in tds or "びん" in tds[0]:
                continue

            if len(tds) == 7:
                raw_town = tds[1]
                scheds = tds[2:]
            elif len(tds) == 6:
                raw_town = tds[0]
                scheds = tds[1:]
            else:
                continue

            town, chome, sub = split_address(raw_town)

            types = {}
            # Official header: 町丁名 | 可燃ごみ | 資源物 (びん・缶・ペットボトル, 古紙・布類, 木の枝・刈り草・葉) | 不燃ごみ・有害ごみ
            # so scheds = [可燃, びん缶ペット, 古紙布類, 木の枝, 不燃有害]. (An earlier version read column 4 as 不燃 —
            # 高洲1丁目 showed 1・3木 for 不燃 when the city says 2・4木; 1・3木 is the branches/grass day.)
            # 1. Burnable
            if len(scheds) > 0:
                b_days, b_weeks, _ = parse_schedule_cell(scheds[0])
                if b_days:
                    types["burnable"] = {"label": "可燃ごみ", "days": b_days, "weeks": b_weeks, "time": None}

            # 2. Resource (びん・缶・ペットボトル)
            if len(scheds) > 1:
                r_days, r_weeks, _ = parse_schedule_cell(scheds[1])
                if r_days:
                    types["resource"] = {"label": "びん・缶・ペットボトル", "days": r_days, "weeks": r_weeks, "time": None}

            # 3. Paper / Cloth (古紙・布類)
            if len(scheds) > 2:
                p_days, p_weeks, _ = parse_schedule_cell(scheds[2])
                if p_days:
                    types["paper_cloth"] = {"label": "古紙・布類", "days": p_days, "weeks": p_weeks, "time": None}

            # 4. Yard (木の枝・刈り草・葉) — 10:00 deadline, unlike 8:00 for everything else
            if len(scheds) > 3:
                y_days, y_weeks, _ = parse_schedule_cell(scheds[3])
                if y_days:
                    types["yard"] = {"label": "木の枝・刈り草・葉", "days": y_days, "weeks": y_weeks, "time": "10:00"}

            # 5. Nonburnable (不燃ごみ・有害ごみ)
            if len(scheds) > 4:
                nb_days, nb_weeks, _ = parse_schedule_cell(scheds[4])
                if nb_days:
                    types["nonburnable"] = {"label": "不燃ごみ・有害ごみ", "days": nb_days, "weeks": nb_weeks, "time": None}

            town_romaji = to_romaji(town) or "town"
            slug_parts = ["chiba", w_en, town_romaji]
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
                "pref": "千葉県",
                "city": "千葉市",
                "city_en": "chiba",
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
                    "time_by": "8:00",
                    "yearend": "12/31~1/3 休止",
                },
                "source": {
                    "url": SOURCE_URL,
                    "fetched": TODAY_STR,
                    "basis": "official_html",
                },
                "raw": {
                    "raw_town": raw_town,
                    "burnable": scheds[0] if len(scheds) > 0 else "",
                    "bin_can_pet": scheds[1] if len(scheds) > 1 else "",
                    "paper_cloth": scheds[2] if len(scheds) > 2 else "",
                    "tree_branch": scheds[3] if len(scheds) > 3 else "",
                    "nonburnable": scheds[4] if len(scheds) > 4 else "",
                },
            }
            records.append(rec)

    wip_file = os.path.join(WIP_DIR, "chiba.json")
    with open(wip_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"[✔] Generated {len(records)} records for Chiba -> {wip_file}")


if __name__ == "__main__":
    main()
