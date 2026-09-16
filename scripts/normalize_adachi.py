#!/usr/bin/env python3
"""
Normalize Adachi Ward (足立区) Garbage Collection Schedule
---------------------------------------------------------
Reads official Adachi City collection schedule HTML:
Source: https://www.city.adachi.tokyo.jp/seso/kurashi/sche.html
Raw cache: data/raw/adachi/sche.html
Output: data/normalized/adachi.json

Rules:
- Tokyo 23 Ward: pref: 東京都, city: 足立区, city_en: adachi, ward: ""
- 6 standard keys: burnable, resource, plastic, paper_cloth, nonburnable, bulky
- pykakasi slug with 0 duplicates
- source.fetched: 2026-09-17
"""

import json
import os
import re
import sys
import unicodedata
import urllib.request
from typing import Dict, List, Any, Set, Tuple
from bs4 import BeautifulSoup
import pykakasi

PAGE_URL = "https://www.city.adachi.tokyo.jp/seso/kurashi/sche.html"
TODAY_STR = "2026-09-17"
VALID_DAYS = {"月", "火", "水", "木", "金", "土", "日"}

kakasi = pykakasi.kakasi()


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return re.sub(r"[^a-z0-9]+", "-", romaji).strip("-")


def extract_nums(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    nums = re.findall(r"\d+", text)
    return "-".join(nums) if nums else ""


def parse_clean_days(val: str) -> List[str]:
    """Strictly matches ([月火水木金土日])曜."""
    if not val:
        return []
    val_norm = unicodedata.normalize("NFKC", val)
    days = []
    for m in re.finditer(r"([月火水木金土日])曜", val_norm):
        d = m.group(1)
        if d in VALID_DAYS and d not in days:
            days.append(d)
    return days


def parse_week_and_days(val: str) -> Tuple[List[int], List[str]]:
    """Parse string like '第2・4火曜日' into ([2, 4], ['火'])."""
    if not val:
        return [], []
    val_norm = unicodedata.normalize("NFKC", val)
    days = parse_clean_days(val_norm)
    weeks = []
    nums = re.findall(r"\d+", val_norm)
    if nums:
        # Check if preceded by 第
        if "第" in val_norm:
            weeks = [int(x) for x in nums if int(x) in [1, 2, 3, 4, 5]]
    return weeks, days


def download_adachi_html(raw_dir: str) -> str:
    os.makedirs(raw_dir, exist_ok=True)
    html_path = os.path.join(raw_dir, "sche.html")
    if not os.path.exists(html_path) or os.path.getsize(html_path) == 0:
        print(f"[*] Downloading Adachi HTML from {PAGE_URL}...")
        req = urllib.request.Request(PAGE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            with open(html_path, "wb") as f:
                f.write(data)
        print(f"[+] Downloaded Adachi HTML ({os.path.getsize(html_path)} bytes)")
    return html_path


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_dir = os.path.join(base_dir, "data", "raw", "adachi")
    out_file = os.path.join(base_dir, "data", "normalized", "adachi.json")

    html_path = download_adachi_html(raw_dir)

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        print("[!] table not found in Adachi HTML!", file=sys.stderr)
        sys.exit(1)

    rows = table.find_all("tr")
    print(f"[*] Total rows in Adachi table: {len(rows)}")

    all_normalized = []
    used_slugs: Set[str] = set()

    # row[0] is header
    for r in rows[1:]:
        tds = [unicodedata.normalize("NFKC", td.get_text().strip()) for td in r.find_all(["th", "td"])]
        if len(tds) < 5 or "地域" in tds[0]:
            continue

        area_raw = tds[0]
        burn_raw = tds[1]
        pla_raw = tds[2]
        nonburn_raw = tds[3]
        res_raw = tds[4]

        # Parse town, chome, sub from area_raw: e.g. "青井1~6丁目", "伊興本町1、2丁目", "扇2丁目"
        # Match chome pattern
        m_ch = re.search(r"(\d+[~〜、\d]*丁目)", area_raw)
        if m_ch:
            chome = m_ch.group(1).replace("~", "～")
            town = area_raw[:m_ch.start()].strip()
            sub = area_raw[m_ch.end():].strip()
        else:
            town = area_raw
            chome = ""
            sub = ""

        types: Dict[str, Any] = {}

        # Burnable
        burn_days = parse_clean_days(burn_raw)
        if burn_days:
            types["burnable"] = {
                "label": "燃やすごみ",
                "days": burn_days,
                "weeks": None,
                "time": "朝8:00まで",
            }

        # Plastic
        pla_days = parse_clean_days(pla_raw)
        if pla_days:
            types["plastic"] = {
                "label": "プラスチック",
                "days": pla_days,
                "weeks": None,
                "time": "朝8:00まで",
            }

        # Nonburnable
        nb_weeks, nb_days = parse_week_and_days(nonburn_raw)
        if nb_days:
            types["nonburnable"] = {
                "label": "燃やさないごみ",
                "days": nb_days,
                "weeks": nb_weeks if nb_weeks else None,
                "time": "朝8:00まで",
            }

        # Resource
        res_days = parse_clean_days(res_raw)
        if res_days:
            types["resource"] = {
                "label": "資源",
                "days": res_days,
                "weeks": None,
                "time": "朝8:00まで",
            }

        rules = {
            "holiday_collection": "祝日も収集",
            "time_by": "8:00",
            "yearend": "12/31~1/3 休止",
        }

        t_romaji = to_romaji(town)
        chome_num = extract_nums(chome)

        slug_base = f"adachi/{t_romaji}"
        if chome_num:
            slug_base += f"-{chome_num}"
        if sub:
            sub_clean = to_romaji(sub)[:15]
            if sub_clean:
                slug_base += f"-{sub_clean}"

        slug_base = re.sub(r"[^a-z0-9\-/]+", "-", slug_base.lower()).strip("-")
        slug = slug_base
        idx = 2
        while slug in used_slugs:
            slug = f"{slug_base}-{idx}"
            idx += 1
        used_slugs.add(slug)

        record = {
            "pref": "東京都",
            "city": "足立区",
            "city_en": "adachi",
            "ward": "",
            "ward_en": "",
            "town": town,
            "romaji": t_romaji,
            "chome": chome,
            "sub": sub,
            "slug": slug,
            "types": types,
            "rules": rules,
            "source": {
                "url": PAGE_URL,
                "fetched": TODAY_STR,
                "basis": "official_html_table",
            },
            "raw": {
                "area": area_raw,
                "burnable": burn_raw,
                "plastic": pla_raw,
                "nonburnable": nonburn_raw,
                "resource": res_raw,
            },
        }
        all_normalized.append(record)

    print(f"[+] Total normalized Adachi records: {len(all_normalized)}")
    print(f"[+] Unique slugs: {len(used_slugs)}")

    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_normalized, f, ensure_ascii=False, indent=2)

    print(f"[✔] Wrote to {out_file}")


if __name__ == "__main__":
    main()
