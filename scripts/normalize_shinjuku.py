#!/usr/bin/env python3
"""
Normalize Shinjuku Ward (新宿区) Garbage Collection Schedule
------------------------------------------------------------
Reads official Shinjuku HTML schedule table:
Source: https://www.city.shinjuku.lg.jp/seikatsu/file09_01_00001.html
Raw cache: data/raw/shinjuku/
Output: data/normalized/shinjuku.json

Rules:
- 23区: pref: 東京都, city: 新宿区, city_en: shinjuku, ward: "", ward_en: ""
- 6 standard keys: burnable, resource, nonburnable
- Slug: shinjuku/{romaji}
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
import pykakasi
from bs4 import BeautifulSoup

SHINJUKU_URL = "https://www.city.shinjuku.lg.jp/seikatsu/file09_01_00001.html"
VALID_DAYS = {"月", "火", "水", "木", "金", "土", "日"}
TODAY_STR = "2026-09-17"

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


def parse_schedule_cell(val: str, label: str) -> Dict[str, Any]:
    if not val:
        return None
    val_norm = unicodedata.normalize("NFKC", val)

    # Weeks: e.g. "1・3番目の水曜日" -> [1, 3], "2・4番目の土曜日" -> [2, 4]
    weeks = None
    m_weeks = re.search(r"([0-9・、]+)番目", val_norm)
    if m_weeks:
        w_nums = re.findall(r"\d+", m_weeks.group(1))
        if w_nums:
            weeks = [int(w) for w in w_nums]

    # Clean days: strip "曜日", "曜"
    clean = re.sub(r"曜日?", "", val_norm)
    days = []
    for ch in clean:
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


def split_address(addr: str) -> Tuple[str, str, str]:
    """Splits address into (town, chome, sub)"""
    s = unicodedata.normalize("NFKC", addr).strip()

    sub = ""
    m_paren = re.search(r"[\(（](.*?)[\)）]", s)
    if m_paren:
        sub = m_paren.group(1).strip()
        s = re.sub(r"[\(（].*?[\)）]", "", s).strip()

    m_chome = re.search(r"([0-9・～~]+丁目)", s)
    if m_chome:
        chome = m_chome.group(1)
        town = s.replace(chome, "").strip()
        return town, chome, sub

    return s, "", sub


def fetch_or_cache_html(url: str, cache_file: str) -> str:
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 0:
        with open(cache_file, "r", encoding="utf-8") as f:
            return f.read()
    print(f"[*] Fetching Shinjuku HTML from {url}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        content = resp.read().decode("utf-8")
    with open(cache_file, "w", encoding="utf-8") as f:
        f.write(content)
    return content


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_dir = os.path.join(base_dir, "data", "raw", "shinjuku")
    out_file = os.path.join(base_dir, "data", "normalized", "shinjuku.json")
    os.makedirs(raw_dir, exist_ok=True)

    html = fetch_or_cache_html(SHINJUKU_URL, os.path.join(raw_dir, "shinjuku_schedule.html"))
    soup = BeautifulSoup(html, "html.parser")

    tables = soup.find_all("table")
    all_normalized = []
    used_slugs: Set[str] = set()

    for tbl in tables:
        for tr in tbl.find_all("tr"):
            cols = [td.text.strip() for td in tr.find_all(["th", "td"])]
            # Header: ['町名の頭文字', '集積所の住所', '資源の回収日', '燃やすごみの収集日', '金属・陶器・ガラスごみの収集日', '管轄', 'カレンダー']
            if len(cols) < 5 or cols[0] == "町名の頭文字":
                continue

            addr_raw = cols[1]
            res_raw = cols[2]
            burn_raw = cols[3]
            nonburn_raw = cols[4]
            kankatsu = cols[5] if len(cols) > 5 else ""

            town, chome, sub = split_address(addr_raw)
            t_romaji = to_romaji(town)
            if not t_romaji:
                t_romaji = "town"

            chome_num = extract_nums(chome)
            sub_clean = unicodedata.normalize("NFKC", sub).strip()

            slug_base = f"shinjuku/{t_romaji}"
            if chome_num:
                slug_base += f"-{chome_num}"
            if sub_clean:
                sub_romaji = to_romaji(sub_clean)[:20]
                if sub_romaji:
                    slug_base += f"-{sub_romaji}"

            slug_base = re.sub(r"[^a-z0-9\-/]+", "-", slug_base.lower()).strip("-")
            slug = slug_base
            idx = 2
            while slug in used_slugs:
                slug = f"{slug_base}-{idx}"
                idx += 1
            used_slugs.add(slug)

            types: Dict[str, Any] = {}
            # 1. 資源
            s_res = parse_schedule_cell(res_raw, "資源")
            if s_res:
                types["resource"] = s_res
            # 2. 燃やすごみ
            s_burn = parse_schedule_cell(burn_raw, "燃やすごみ")
            if s_burn:
                types["burnable"] = s_burn
            # 3. 金属・陶器・ガラスごみ
            s_nonburn = parse_schedule_cell(nonburn_raw, "金属・陶器・ガラスごみ")
            if s_nonburn:
                types["nonburnable"] = s_nonburn

            record = {
                "pref": "東京都",
                "city": "新宿区",
                "city_en": "shinjuku",
                "ward": "",
                "ward_en": "",
                "town": town,
                "romaji": t_romaji,
                "chome": chome,
                "sub": sub_clean,
                "slug": slug,
                "types": types,
                "rules": {
                    "holiday_collection": "祝日も収集",
                    "time_by": "8:00",
                    "yearend": "12/31~1/3 休止",
                },
                "source": {
                    "url": SHINJUKU_URL,
                    "fetched": TODAY_STR,
                    "basis": "official_html",
                },
                "notes": f"管轄: {kankatsu}" if kankatsu else "",
                "raw": {
                    "address": addr_raw,
                    "resource": res_raw,
                    "burnable": burn_raw,
                    "nonburnable": nonburn_raw,
                    "kankatsu": kankatsu,
                },
            }
            all_normalized.append(record)

    print(f"[+] Total normalized Shinjuku records: {len(all_normalized)}")
    print(f"[+] Unique slugs: {len(used_slugs)}")

    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_normalized, f, ensure_ascii=False, indent=2)

    print(f"[✔] Wrote to {out_file}")


if __name__ == "__main__":
    main()
