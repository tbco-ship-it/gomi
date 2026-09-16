#!/usr/bin/env python3
"""
Yokohama City (横浜市) Garbage Collection Schedule Scraper (PoC)
---------------------------------------------------------------
Scrapes official HTML tables from Yokohama City's garbage collection pages:
Base URL: https://www.city.yokohama.lg.jp/kurashi/sumai-kurashi/gomi-recycle/gomi/shushuyobi/

Output: Structured JSON file containing ward, town (町丁目), days of week, and waste types.
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

YOKOHAMA_BASE_URL = "https://www.city.yokohama.lg.jp/kurashi/sumai-kurashi/gomi-recycle/gomi/shushuyobi"

YOKOHAMA_WARDS = {
    "aoba": "青葉区",
    "asahi": "旭区",
    "izumi": "泉区",
    "isogo": "磯子区",
    "kanagawa": "神奈川区",
    "kanazawa": "金沢区",
    "konan": "港南区",
    "kohoku": "港北区",
    "sakae": "栄区",
    "seya": "瀬谷区",
    "tsuzuki": "都筑区",
    "tsurumi": "鶴見区",
    "totsuka": "戸塚区",
    "naka": "中区",
    "nishi": "西区",
    "hodogaya": "保土ケ谷区",
    "midori": "緑区",
    "minami": "南区",
}

DAYS_MAP = {
    "月曜日": "月",
    "火曜日": "火",
    "水曜日": "水",
    "木曜日": "木",
    "金曜日": "金",
    "土曜日": "土",
}

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


def get_subpages_for_ward(ward_slug: str) -> List[str]:
    """Finds all 50-on subpages for a given ward."""
    index_url = f"{YOKOHAMA_BASE_URL}/{ward_slug}/index.html"
    try:
        html = fetch_html(index_url)
    except Exception as e:
        print(f"[-] Failed to fetch index for {ward_slug}: {e}", file=sys.stderr)
        return []

    # Find subpages like /shushuyobi/kohoku/agyou.html or a-e.html
    subpages = set()
    pattern = rf'href=[\"\']([^\"\']*(?:/shushuyobi/{ward_slug}/|{ward_slug}/)[^\"\']+\.html)[\"\']'
    for match in re.finditer(pattern, html):
        link = match.group(1)
        if "index.html" in link:
            continue
        if link.startswith("/"):
            full_url = f"https://www.city.yokohama.lg.jp{link}"
        elif link.startswith("http"):
            full_url = link
        else:
            full_url = f"{YOKOHAMA_BASE_URL}/{ward_slug}/{link}"
        subpages.add(full_url)

    return sorted(list(subpages))


def parse_yokohama_table(rows: List[List[str]], ward_slug: str, source_url: str) -> List[Dict[str, Any]]:
    """
    Parses table rows into structured town records.
    Yokohama table structure:
    Col 0: 五十音
    Col 1: 町名 (e.g. 大倉山1～7丁目)
    Col 2..7: 月曜日, 火曜日, 水曜日, 木曜日, 金曜日, 土曜日
    """
    if not rows:
        return []

    header = rows[0]
    day_columns: List[tuple[int, str]] = []
    for idx, col_name in enumerate(header):
        for full_day, short_day in DAYS_MAP.items():
            if full_day in col_name:
                day_columns.append((idx, short_day))
                break

    records = []
    for row in rows[1:]:
        if len(row) < 3:
            continue
        town_name = row[1].strip()
        if not town_name or town_name == "町名":
            continue

        schedule_by_day: Dict[str, str] = {}
        schedule_by_type: Dict[str, List[str]] = {
            "燃やすごみ": [],
            "プラスチック資源": [],
            "缶・びん・ペットボトル": [],
        }

        for col_idx, short_day in day_columns:
            if col_idx < len(row):
                val = row[col_idx].strip()
                schedule_by_day[short_day] = val
                if "燃やすごみ" in val:
                    schedule_by_type["燃やすごみ"].append(short_day)
                if "プラスチック" in val:
                    schedule_by_type["プラスチック資源"].append(short_day)
                if "缶" in val or "ペットボトル" in val:
                    schedule_by_type["缶・びん・ペットボトル"].append(short_day)

        # Derived rules per Yokohama official guidance
        derived_rules = {
            "燃えないごみ": schedule_by_type["燃やすごみ"],
            "スプレー缶": schedule_by_type["燃やすごみ"],
            "乾電池": schedule_by_type["燃やすごみ"],
            "小さな金属類": schedule_by_type["缶・びん・ペットボトル"],
        }

        record = {
            "prefecture": "神奈川県",
            "city": "横浜市",
            "ward_ja": YOKOHAMA_WARDS.get(ward_slug, ward_slug),
            "ward_en": ward_slug,
            "town": town_name,
            "schedule_by_day": schedule_by_day,
            "schedule_by_type": schedule_by_type,
            "derived_schedule": derived_rules,
            "collection_time": "朝8:00まで",
            "source_url": source_url,
        }
        records.append(record)

    return records


def scrape_ward(ward_slug: str, verbose: bool = True) -> List[Dict[str, Any]]:
    ward_ja = YOKOHAMA_WARDS.get(ward_slug, ward_slug)
    if verbose:
        print(f"[*] Scraping {ward_ja} ({ward_slug})...")

    subpages = get_subpages_for_ward(ward_slug)
    if not subpages:
        if verbose:
            print(f"[-] No subpages found for {ward_slug}")
        return []

    ward_records = []
    for page_url in subpages:
        try:
            html = fetch_html(page_url)
            parser = TableParser()
            parser.feed(html)
            page_records = parse_yokohama_table(parser.rows, ward_slug, page_url)
            ward_records.extend(page_records)
            time.sleep(0.2)
        except Exception as e:
            if verbose:
                print(f"[-] Error scraping {page_url}: {e}", file=sys.stderr)

    if verbose:
        print(f"[+] {ward_ja}: Extracted {len(ward_records)} towns from {len(subpages)} pages")
    return ward_records


def main():
    parser = argparse.ArgumentParser(description="Yokohama Garbage Collection Scraper PoC")
    parser.add_argument(
        "--ward",
        type=str,
        default="sample",
        help="Ward slug (e.g. 'kohoku', 'naka') or 'sample' (1-2 wards) or 'all'",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Target output JSON path",
    )
    args = parser.parse_args()

    target_wards = []
    if args.ward == "all":
        target_wards = list(YOKOHAMA_WARDS.keys())
    elif args.ward == "sample":
        target_wards = ["kohoku", "naka"]
    elif args.ward in YOKOHAMA_WARDS:
        target_wards = [args.ward]
    else:
        print(f"[!] Unknown ward slug: {args.ward}. Available: {list(YOKOHAMA_WARDS.keys())}")
        sys.exit(1)

    all_records = []
    for ward in target_wards:
        records = scrape_ward(ward, verbose=True)
        all_records.extend(records)

    output_path = args.output
    if not output_path:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_filename = "yokohama_full.json" if args.ward == "all" else "yokohama_sample.json"
        output_path = os.path.join(base_dir, "data", output_filename)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "city": "横浜市",
                "scraped_wards_count": len(target_wards),
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
