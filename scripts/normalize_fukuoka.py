#!/usr/bin/env python3
"""
Normalize Fukuoka City (福岡市) Garbage Collection Schedule
------------------------------------------------------------
Crawls and normalizes official Fukuoka garbage collection data:
Source: https://kateigomi-bunbetsu.city.fukuoka.lg.jp/dates/search
Raw cache: data/raw/fukuoka/
Output: data/normalized/fukuoka.json

Rules:
- 7 Wards: 東区(higashi), 博多区(hakata), 中央区(chuo), 南区(minami), 城南区(jonan), 早良区(sawara), 西区(nishi)
- 6 standard keys: burnable, nonburnable, resource
- Genuine Sunday collection exists in Fukuoka (night collection: 日曜日・水曜日)
- pykakasi slug with 0 duplicates
- source.fetched: 2026-09-17
"""

import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
from typing import Dict, List, Any, Set, Tuple
import pykakasi
from bs4 import BeautifulSoup

BASE_URL = "https://kateigomi-bunbetsu.city.fukuoka.lg.jp"
VALID_DAYS = {"月", "火", "水", "木", "金", "土", "日"}
TODAY_STR = "2026-09-17"

WARDS = [
    (1, "東区", "higashi"),
    (2, "博多区", "hakata"),
    (3, "中央区", "chuo"),
    (4, "南区", "minami"),
    (5, "城南区", "jonan"),
    (6, "早良区", "sawara"),
    (7, "西区", "nishi"),
]

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


def parse_schedule_text(val: str, label: str) -> Dict[str, Any]:
    if not val:
        return None
    val_norm = unicodedata.normalize("NFKC", val)
    
    # Weeks: e.g. "１回目の月曜日" -> [1], "3回目の水曜日" -> [3]
    weeks = None
    m_week = re.search(r"(\d+)回目", val_norm)
    if m_week:
        weeks = [int(m_week.group(1))]

    # Days: strip "曜日", "曜"
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
        "time": "日没から夜12時まで",
    }


def split_town_chome(raw_town: str) -> Tuple[str, str]:
    raw_town = unicodedata.normalize("NFKC", raw_town).strip()
    m = re.match(r"^(.*?)(\d+丁目)?$", raw_town)
    if m and m.group(2):
        return m.group(1), m.group(2)
    return raw_town, ""


def fetch_ward_records(ward_id: int, ward_name: str, ward_en: str, raw_dir: str) -> List[Dict[str, Any]]:
    os.makedirs(raw_dir, exist_ok=True)
    raw_file = os.path.join(raw_dir, f"ward_{ward_id}_{ward_en}.json")
    
    if os.path.exists(raw_file):
        with open(raw_file, "r", encoding="utf-8") as f:
            return json.load(f)

    print(f"[*] Fetching Fukuoka {ward_name} ({ward_en})...")
    records = []
    page = 1
    while True:
        url = f"{BASE_URL}/dates/index/ward:{ward_id}/is_ward:1/page:{page}" if page > 1 else f"{BASE_URL}/dates/index/ward:{ward_id}/is_ward:1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8")

        soup = BeautifulSoup(html, "html.parser")
        for dl in soup.find_all("dl", class_="accordion data"):
            dt = dl.find("dt")
            item = {"raw_dt": dt.text.strip() if dt else ""}
            for ul in dl.find_all("ul"):
                title_li = ul.find("li", class_="title")
                lis = ul.find_all("li")
                if title_li and len(lis) > 1:
                    item[title_li.text.strip()] = lis[1].text.strip()
            records.append(item)

        next_a = soup.find("a", rel="next")
        if not next_a:
            break
        page += 1
        time.sleep(0.1)

    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    return records


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_dir = os.path.join(base_dir, "data", "raw", "fukuoka")
    out_file = os.path.join(base_dir, "data", "normalized", "fukuoka.json")

    all_normalized = []
    used_slugs: Set[str] = set()

    for ward_id, ward_name, ward_en in WARDS:
        ward_items = fetch_ward_records(ward_id, ward_name, ward_en, raw_dir)
        for item in ward_items:
            raw_town = item.get("町名", "") or item.get("raw_dt", "")
            town, chome = split_town_chome(raw_town)
            banchi = item.get("番号（番地）", "").strip()

            t_romaji = to_romaji(town)
            chome_num = extract_nums(chome)
            banchi_num = extract_nums(banchi)

            slug_base = f"fukuoka/{ward_en}/{t_romaji}"
            if chome_num:
                slug_base += f"-{chome_num}"
            if banchi_num:
                slug_base += f"-{banchi_num[:30]}"  # cap length if too long

            # Ensure ASCII only
            slug_base = re.sub(r"[^a-z0-9\-/]+", "-", slug_base.lower()).strip("-")
            slug = slug_base
            idx = 2
            while slug in used_slugs:
                slug = f"{slug_base}-{idx}"
                idx += 1
            used_slugs.add(slug)

            types: Dict[str, Any] = {}
            if "燃えるごみ" in item:
                s = parse_schedule_text(item["燃えるごみ"], "燃えるごみ")
                if s:
                    types["burnable"] = s

            if "燃えないごみ" in item:
                s = parse_schedule_text(item["燃えないごみ"], "燃えないごみ")
                if s:
                    types["nonburnable"] = s

            if "空きびん・ペットボトル" in item:
                s = parse_schedule_text(item["空きびん・ペットボトル"], "空きびん・ペットボトル")
                if s:
                    types["resource"] = s

            record = {
                "pref": "福岡県",
                "city": "福岡市",
                "city_en": "fukuoka",
                "ward": ward_name,
                "ward_en": ward_en,
                "town": town,
                "romaji": t_romaji,
                "chome": chome,
                "sub": banchi,
                "slug": slug,
                "types": types,
                "rules": {
                    "holiday_collection": "祝日も収集",
                    "time_by": "日没から夜12時まで",
                    "yearend": "12/31~1/3 休止",
                },
                "source": {
                    "url": f"{BASE_URL}/dates/search",
                    "fetched": TODAY_STR,
                    "basis": "official_html",
                },
                "raw": item,
            }
            all_normalized.append(record)

    print(f"[+] Total normalized Fukuoka records: {len(all_normalized)}")
    print(f"[+] Unique slugs: {len(used_slugs)}")

    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_normalized, f, ensure_ascii=False, indent=2)

    print(f"[✔] Wrote to {out_file}")


if __name__ == "__main__":
    main()
