#!/usr/bin/env python3
"""
Normalize Edogawa Ward (江戸川区) Garbage Collection Schedule
------------------------------------------------------------
Reads official Edogawa HTML schedule table:
Source: https://www.city.edogawa.tokyo.jp/e025/kurashi/gomi_recycle/kategomi/yobihyo.html
Raw cache: data/raw/edogawa/
Output: data/normalized/edogawa.json

Rules:
- 23区: pref: 東京都, city: 江戸川区, city_en: edogawa, ward: "", ward_en: ""
- 6 standard keys: burnable, resource, nonburnable
- Slug: edogawa/{romaji}
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

EDOGAWA_URL = "https://www.city.edogawa.tokyo.jp/e025/kurashi/gomi_recycle/kategomi/yobihyo.html"
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
    if not val or val.strip() == "-":
        return None
    val_norm = unicodedata.normalize("NFKC", val)

    # Weeks: e.g. "第1・3金曜日" -> [1, 3], "第2・4月曜日" -> [2, 4]
    weeks = None
    m_weeks = re.search(r"第([0-9・、]+)", val_norm)
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


def fetch_or_cache_html(url: str, cache_file: str) -> str:
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 0:
        with open(cache_file, "r", encoding="utf-8") as f:
            return f.read()
    print(f"[*] Fetching Edogawa HTML from {url}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        content = resp.read().decode("utf-8")
    with open(cache_file, "w", encoding="utf-8") as f:
        f.write(content)
    return content


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_dir = os.path.join(base_dir, "data", "raw", "edogawa")
    out_file = os.path.join(base_dir, "data", "normalized", "edogawa.json")
    os.makedirs(raw_dir, exist_ok=True)

    html = fetch_or_cache_html(EDOGAWA_URL, os.path.join(raw_dir, "edogawa_yobihyo.html"))
    soup = BeautifulSoup(html, "html.parser")

    all_normalized = []
    used_slugs: Set[str] = set()

    for tbl in soup.find_all("table"):
        current_town = ""
        for tr in tbl.find_all("tr")[1:]:
            tds = tr.find_all(["th", "td"])
            txts = [td.text.strip().replace("\n", " ") for td in tds]
            if len(tds) == 6:
                current_town = txts[0]
                chome_raw = txts[1]
                res_raw = txts[2]
                burn_raw = txts[3]
                nonburn_raw = txts[4]
                kankatsu = txts[5]
            elif len(tds) == 5:
                chome_raw = txts[0]
                res_raw = txts[1]
                burn_raw = txts[2]
                nonburn_raw = txts[3]
                kankatsu = txts[4]
            else:
                continue

            town = unicodedata.normalize("NFKC", current_town).strip()
            chome_clean = unicodedata.normalize("NFKC", chome_raw).strip()

            # Separate sub-condition from chome
            chome = chome_clean
            sub = ""
            m_paren = re.search(r"[\(（](.*?)[\)）]", chome_clean)
            if m_paren:
                sub = m_paren.group(1).strip()
                chome = re.sub(r"[\(（].*?[\)）]", "", chome_clean).strip()

            if chome == "全域":
                chome = ""

            t_romaji = to_romaji(town)
            chome_num = extract_nums(chome)
            sub_clean = unicodedata.normalize("NFKC", sub).strip()

            slug_base = f"edogawa/{t_romaji}"
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
            # 3. 燃やさないごみ
            s_nonburn = parse_schedule_cell(nonburn_raw, "燃やさないごみ")
            if s_nonburn:
                types["nonburnable"] = s_nonburn

            clean_kankatsu = re.sub(r"^管轄\s*", "", kankatsu).strip()

            record = {
                "pref": "東京都",
                "city": "江戸川区",
                "city_en": "edogawa",
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
                    "url": EDOGAWA_URL,
                    "fetched": TODAY_STR,
                    "basis": "official_html",
                },
                "notes": f"管轄: {clean_kankatsu}" if clean_kankatsu else "",
                "raw": {
                    "town": current_town,
                    "chome": chome_raw,
                    "resource": res_raw,
                    "burnable": burn_raw,
                    "nonburnable": nonburn_raw,
                    "kankatsu": kankatsu,
                },
            }
            all_normalized.append(record)

    print(f"[+] Total normalized Edogawa records: {len(all_normalized)}")
    print(f"[+] Unique slugs: {len(used_slugs)}")

    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_normalized, f, ensure_ascii=False, indent=2)

    print(f"[✔] Wrote to {out_file}")


if __name__ == "__main__":
    main()
