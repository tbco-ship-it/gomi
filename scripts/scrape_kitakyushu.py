#!/usr/bin/env python3
"""
Kitakyushu City (北九州市) Garbage Collection Schedule Scraper (PoC)
-----------------------------------------------------------------
Scrapes official HTML tables from Kitakyushu City's garbage collection pages:
Hub URL: https://www.city.kitakyushu.lg.jp/kurashi/menu01_0394.html

Output: Structured JSON file containing ward, town (町名), days of week, and waste types.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser
from typing import Dict, List, Any, Optional

KITAKYUSHU_WARDS = [
    {
        "name_ja": "門司区",
        "slug": "moji",
        "url": "https://www.city.kitakyushu.lg.jp/contents/924_10095.html",
    },
    {
        "name_ja": "小倉北区",
        "slug": "kokurakita",
        "url": "https://www.city.kitakyushu.lg.jp/contents/924_10102.html",
    },
    {
        "name_ja": "小倉南区",
        "slug": "kokuraminami",
        "url": "https://www.city.kitakyushu.lg.jp/contents/924_10107.html",
    },
    {
        "name_ja": "若松区",
        "slug": "wakamatsu",
        "url": "https://www.city.kitakyushu.lg.jp/contents/924_10114.html",
    },
    {
        "name_ja": "八幡東区",
        "slug": "yahatahigashi",
        "url": "https://www.city.kitakyushu.lg.jp/contents/924_10121.html",
    },
    {
        "name_ja": "八幡西区",
        "slug": "yahatanishi",
        "url": "https://www.city.kitakyushu.lg.jp/contents/924_10122.html",
    },
    {
        "name_ja": "戸畑区",
        "slug": "tobata",
        "url": "https://www.city.kitakyushu.lg.jp/contents/924_10128.html",
    },
]

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.current_row: List[str] = []
        self.current_cell: List[str] = []
        self.rows: List[List[str]] = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.in_row = True
            self.current_row = []
        elif self.in_row and tag in ("th", "td"):
            self.in_cell = True
            self.current_cell = []

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
        elif tag == "tr" and self.in_row:
            self.in_row = False
            if self.current_row:
                self.rows.append(self.current_row)
        elif tag in ("th", "td") and self.in_cell:
            self.in_cell = False
            cell_text = " ".join("".join(self.current_cell).split())
            self.current_row.append(cell_text)

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell.append(data)


def fetch_html(url: str, retries: int = 3) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            if attempt == retries - 1:
                raise e
            time.sleep(1.0)
    return ""


def clean_days(text: str) -> List[str]:
    """Converts '月曜日・木曜日' to ['月', '木'] without falsely capturing '日' from '曜日'."""
    cleaned = text.replace("曜日", "")
    found = []
    for day in ["月", "火", "水", "木", "金", "土", "日"]:
        if day in cleaned:
            found.append(day)
    return found


def parse_kitakyushu_table(rows: List[List[str]], ward_info: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Kitakyushu table format:
    Col 0: 50音 (optional or empty)
    Col 1: 町名 (e.g. 青葉1～2丁目)
    Col 2: 家庭ごみの収集日 (e.g. 月曜日・木曜日)
    Col 3: プラスチックの収集日 (e.g. 火曜日)
    Col 4: 粗大ごみの収集日（事前申込制） (e.g. 第4水曜日)
    """
    records = []
    for row in rows:
        if len(row) < 4:
            continue
        if "町名" in row[1] or "家庭ごみ" in row[2]:
            continue

        town_name = row[1].strip()
        if not town_name:
            continue

        burnable_raw = row[2].strip()
        plastic_raw = row[3].strip()
        bulky_raw = row[4].strip() if len(row) > 4 else ""

        burnable_days = clean_days(burnable_raw)
        plastic_days = clean_days(plastic_raw)

        # Build daily inverted schedule
        days_map: Dict[str, List[str]] = {
            "月": [],
            "火": [],
            "水": ["缶・びん・ペットボトル"],  # Citywide rule: every Wednesday
            "木": [],
            "金": [],
            "土": [],
        }

        for d in burnable_days:
            if d in days_map:
                days_map[d].append("家庭ごみ(燃えるごみ)")
        for d in plastic_days:
            if d in days_map:
                days_map[d].append("プラスチック")

        record = {
            "prefecture": "福岡県",
            "city": "北九州市",
            "ward_ja": ward_info["name_ja"],
            "ward_en": ward_info["slug"],
            "town": town_name,
            "schedule": {
                "家庭ごみ": burnable_days,
                "プラスチック": plastic_days,
                "かん・びん・ペットボトル": ["水"],  # Citywide
                "粗大ごみ": bulky_raw,
            },
            "schedule_by_day": days_map,
            "citywide_rules": {
                "cans_bottles_pet": "毎週水曜日",
                "holiday_collection": "祝日も通常どおり収集",
                "collection_time": "朝8:30まで",
                "bulky_reservation": "粗大ごみ受付センター事前申込制",
            },
            "raw_text": {
                "burnable": burnable_raw,
                "plastic": plastic_raw,
                "bulky": bulky_raw,
            },
            "source_url": ward_info["url"],
        }
        records.append(record)

    return records


def main():
    parser = argparse.ArgumentParser(description="Kitakyushu Garbage Collection Scraper PoC")
    parser.add_argument(
        "--ward",
        type=str,
        default="all",
        help="Ward slug (e.g. 'kokurakita') or 'all' (default)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Target output JSON path",
    )
    args = parser.parse_args()

    targets = []
    if args.ward == "all":
        targets = KITAKYUSHU_WARDS
    else:
        matched = [w for w in KITAKYUSHU_WARDS if w["slug"] == args.ward]
        if not matched:
            print(f"[!] Unknown ward slug: {args.ward}")
            sys.exit(1)
        targets = matched

    all_records = []
    for ward_info in targets:
        print(f"[*] Scraping {ward_info['name_ja']} ({ward_info['slug']})...")
        try:
            html = fetch_html(ward_info["url"])
            p = TableParser()
            p.feed(html)
            records = parse_kitakyushu_table(p.rows, ward_info)
            all_records.extend(records)
            print(f"[+] {ward_info['name_ja']}: Extracted {len(records)} towns")
            time.sleep(0.3)
        except Exception as e:
            print(f"[-] Error scraping {ward_info['name_ja']}: {e}", file=sys.stderr)

    output_path = args.output
    if not output_path:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_path = os.path.join(base_dir, "data", "kitakyushu.json")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "city": "北九州市",
                "scraped_wards_count": len(targets),
                "total_towns": len(all_records),
                "data": all_records,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"\n[✔] Successfully saved {len(all_records)} records to {output_path}")


if __name__ == "__main__":
    main()
