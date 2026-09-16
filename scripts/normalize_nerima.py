#!/usr/bin/env python3
"""
Normalize Nerima Ward (練馬区) Garbage Collection Schedule
----------------------------------------------------------
Reads official Nerima HTML schedule tables from 7 subpages:
Source: https://www.city.nerima.tokyo.jp/kurashi/gomi/wakekata/ichiran/index.html
Raw cache: data/raw/nerima/
Output: data/normalized/nerima.json

Rules:
- 23区: pref: 東京都, city: 練馬区, city_en: nerima, ward: "", ward_en: ""
- 6 standard keys: burnable, resource, plastic, nonburnable
- Zero duplicate slugs via pykakasi
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

BASE_URL = "https://www.city.nerima.tokyo.jp/kurashi/gomi/wakekata/ichiran"
SUBPAGES = [
    "a_gyochiiki.html",
    "ka_gyochiiki.html",
    "sa_gyochiiki.html",
    "ta_gyochiiki.html",
    "na_gyochiiki.html",
    "ha_gyochiiki.html",
    "maya_gyochiiki.html",
]

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

    # Weeks: e.g. "第1・3 月曜", "第2・4 木曜"
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
    print(f"[*] Fetching Nerima HTML from {url}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        content = resp.read().decode("utf-8")
    with open(cache_file, "w", encoding="utf-8") as f:
        f.write(content)
    return content


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_dir = os.path.join(base_dir, "data", "raw", "nerima")
    out_file = os.path.join(base_dir, "data", "normalized", "nerima.json")
    os.makedirs(raw_dir, exist_ok=True)

    all_normalized = []
    used_slugs: Set[str] = set()

    for sub in SUBPAGES:
        sub_url = f"{BASE_URL}/{sub}"
        cache_path = os.path.join(raw_dir, sub)
        html = fetch_or_cache_html(sub_url, cache_path)
        soup = BeautifulSoup(html, "html.parser")
        tbl = soup.find("table")
        if not tbl:
            continue

        for tr in tbl.find_all("tr")[1:]:
            cols = [td.text.strip().replace("\n", " ") for td in tr.find_all(["th", "td"])]
            # Header: ['町 名', '丁 目', '可燃ごみ', '不燃ごみ', '容器包装プラスチック・古紙', 'びん・缶', 'ペットボトル', 'カレンダー']
            if len(cols) < 7 or cols[0].startswith("町"):
                continue

            town_raw = cols[0]
            chome_raw = cols[1]
            burn_raw = cols[2]
            nonburn_raw = cols[3]
            pla_raw = cols[4]
            res_raw = cols[5]
            pet_raw = cols[6]

            town = unicodedata.normalize("NFKC", town_raw).strip()
            chome_clean = unicodedata.normalize("NFKC", chome_raw).strip()
            chome = chome_clean if chome_clean != "全域" else ""

            t_romaji = to_romaji(town)
            chome_num = extract_nums(chome)

            slug_base = f"nerima/{t_romaji}"
            if chome_num:
                slug_base += f"-{chome_num}"

            slug_base = re.sub(r"[^a-z0-9\-/]+", "-", slug_base.lower()).strip("-")
            slug = slug_base
            idx = 2
            while slug in used_slugs:
                slug = f"{slug_base}-{idx}"
                idx += 1
            used_slugs.add(slug)

            types: Dict[str, Any] = {}
            # 1. 可燃ごみ -> burnable
            s_burn = parse_schedule_cell(burn_raw, "可燃ごみ")
            if s_burn:
                types["burnable"] = s_burn

            # 2. 不燃ごみ -> nonburnable
            s_nonburn = parse_schedule_cell(nonburn_raw, "不燃ごみ")
            if s_nonburn:
                types["nonburnable"] = s_nonburn

            # 3. 容器包装プラスチック・古紙 -> plastic
            s_pla = parse_schedule_cell(pla_raw, "容器包装プラスチック・古紙")
            if s_pla:
                types["plastic"] = s_pla

            # 4. びん・缶 -> resource
            s_res = parse_schedule_cell(res_raw, "びん・缶")
            if s_res:
                types["resource"] = s_res

            record = {
                "pref": "東京都",
                "city": "練馬区",
                "city_en": "nerima",
                "ward": "",
                "ward_en": "",
                "town": town,
                "romaji": t_romaji,
                "chome": chome,
                "sub": "",
                "slug": slug,
                "types": types,
                "rules": {
                    "holiday_collection": "祝日も収集",
                    "time_by": "8:00",
                    "yearend": "12/31~1/3 休止",
                },
                "source": {
                    "url": sub_url,
                    "fetched": TODAY_STR,
                    "basis": "official_html",
                },
                "notes": f"ペットボトル: {pet_raw}" if pet_raw else "",
                "raw": {
                    "town": town_raw,
                    "chome": chome_raw,
                    "burnable": burn_raw,
                    "nonburnable": nonburn_raw,
                    "plastic_paper": pla_raw,
                    "bottles_cans": res_raw,
                    "pet": pet_raw,
                },
            }
            all_normalized.append(record)

    print(f"[+] Total normalized Nerima records: {len(all_normalized)}")
    print(f"[+] Unique slugs: {len(used_slugs)}")

    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_normalized, f, ensure_ascii=False, indent=2)

    print(f"[✔] Wrote to {out_file}")


if __name__ == "__main__":
    main()
