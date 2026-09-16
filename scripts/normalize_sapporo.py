#!/usr/bin/env python3
"""
Normalize Sapporo City (札幌市) Garbage Collection Schedule
-----------------------------------------------------------
Reads official Sapporo screen-reader accessible collection schedule:
Source: https://www.city.sapporo.jp/seiso/kaisyu/yomiage/index.html
Raw cache: data/raw/sapporo/
Output: data/normalized/sapporo.json

Rules:
- 10 Wards: 中央区(chuo), 北区(kita), 東区(higashi), 白石区(shiroishi),
  厚別区(atsubetsu), 豊平区(toyohira), 清田区(kiyota), 南区(minami),
  西区(nishi), 手稲区(teine)
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
import urllib.parse
from typing import Dict, List, Any, Set, Tuple
from bs4 import BeautifulSoup
import pykakasi

BASE_URL = "https://www.city.sapporo.jp"
INDEX_URL = f"{BASE_URL}/seiso/kaisyu/yomiage/index.html"
TODAY_STR = "2026-09-17"
VALID_DAYS = {"月", "火", "水", "木", "金", "土", "日"}

WARDS = [
    ("01chuo", "中央区", "chuo"),
    ("02kita", "北区", "kita"),
    ("03higashi", "東区", "higashi"),
    ("04shiroishi", "白石区", "shiroishi"),
    ("05atsubetsu", "厚別区", "atsubetsu"),
    ("06toyohira", "豊平区", "toyohira"),
    ("07kiyota", "清田区", "kiyota"),
    ("08minami", "南区", "minami"),
    ("09nishi", "西区", "nishi"),
    ("10teine", "手稲区", "teine"),
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


def parse_clean_days(val: str) -> List[str]:
    """Strictly match ([月火水木金土日])曜."""
    if not val:
        return []
    val_norm = unicodedata.normalize("NFKC", val)
    days = []
    for m in re.finditer(r"([月火水木金土日])曜", val_norm):
        d = m.group(1)
        if d in VALID_DAYS and d not in days:
            days.append(d)
    return days


def fetch_url(url: str, cache_path: str) -> str:
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        with open(cache_path, "r", encoding="utf-8") as f:
            return f.read()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read().decode("utf-8")
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(content)
        return content


def parse_carender_schedule(html: str) -> Dict[str, Any]:
    """Parse waste schedule from yomiage carender page text."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()

    # Look for 令和7年9月 or 令和8年 month descriptions
    types = {}

    m_burn = re.search(r"燃やせるごみは、?毎週(.*?)(?:です|。)", text)
    if m_burn:
        days = parse_clean_days(m_burn.group(1))
        if days:
            types["burnable"] = {
                "label": "燃やせるごみ",
                "days": days,
                "weeks": None,
                "time": "朝8:30まで",
            }

    m_res = re.search(r"びん・缶・ペットボトルは、?毎週(.*?)(?:です|。|、)", text)
    if m_res:
        days = parse_clean_days(m_res.group(1))
        if days:
            types["resource"] = {
                "label": "びん・缶・ペットボトル",
                "days": days,
                "weeks": None,
                "time": "朝8:30まで",
            }

    m_pla = re.search(r"容器包装プラスチックは、?毎週(.*?)(?:です|。|、)", text)
    if m_pla:
        days = parse_clean_days(m_pla.group(1))
        if days:
            types["plastic"] = {
                "label": "容器包装プラスチック",
                "days": days,
                "weeks": None,
                "time": "朝8:30まで",
            }

    m_nonburn = re.search(r"燃やせないごみは.*?([月火水木金土日])曜日", text)
    if m_nonburn:
        types["nonburnable"] = {
            "label": "燃やせないごみ",
            "days": [m_nonburn.group(1)],
            "weeks": None,
            "time": "朝8:30まで",
        }

    m_paper = re.search(r"雑がみは.*?([月火水木金土日])曜日", text)
    if m_paper:
        types["paper_cloth"] = {
            "label": "雑がみ",
            "days": [m_paper.group(1)],
            "weeks": None,
            "time": "朝8:30まで",
        }

    return types


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_dir = os.path.join(base_dir, "data", "raw", "sapporo")
    out_file = os.path.join(base_dir, "data", "normalized", "sapporo.json")

    all_normalized = []
    used_slugs: Set[str] = set()
    carender_cache: Dict[str, Dict[str, Any]] = {}

    for w_code, ward_name, ward_en in WARDS:
        ward_url = f"{BASE_URL}/seiso/kaisyu/yomiage/{w_code}.html"
        cache_file = os.path.join(raw_dir, f"{w_code}.html")
        print(f"[*] Crawling Sapporo {ward_name} ({w_code})...")
        html = fetch_url(ward_url, cache_file)

        soup = BeautifulSoup(html, "html.parser")
        links = soup.find_all("a", href=True)

        for a in links:
            href = a["href"]
            if "carender" not in href:
                continue

            addr_raw = a.get_text().strip()
            if not addr_raw:
                continue

            full_carender_url = urllib.parse.urljoin(ward_url, href)
            carender_id = os.path.splitext(os.path.basename(href))[0]
            carender_cache_file = os.path.join(raw_dir, "carender", f"{carender_id}.html")

            if carender_id not in carender_cache:
                c_html = fetch_url(full_carender_url, carender_cache_file)
                carender_cache[carender_id] = parse_carender_schedule(c_html)

            types = carender_cache[carender_id]

            # Parse town and chome from addr_raw
            # e.g. "北6条～北31条までの全域", "南4条西20丁目～西27丁目", "伏見1丁目～5丁目", "円山"
            addr_norm = unicodedata.normalize("NFKC", addr_raw).strip()
            town = ""
            chome = ""
            sub = ""

            m_ch = re.search(r"(\d+丁目[〜~\d丁目・]*|西\d+丁目[〜~西\d丁目・]*|東\d+丁目[〜~東\d丁目・]*)", addr_norm)
            if m_ch:
                chome = m_ch.group(1).replace("~", "～")
                town = addr_norm[:m_ch.start()].strip()
                sub = addr_norm[m_ch.end():].strip().lstrip("（(").rstrip("）)")
            else:
                town = addr_norm

            if not town:
                town = addr_norm
                chome = ""

            rules = {
                "holiday_collection": "祝日も収集",
                "time_by": "8:30",
                "yearend": "12/31~1/3 休止",
            }

            t_romaji = to_romaji(town)
            chome_num = extract_nums(chome)

            slug_base = f"sapporo/{ward_en}/{t_romaji}"
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
                "pref": "北海道",
                "city": "札幌市",
                "city_en": "sapporo",
                "ward": ward_name,
                "ward_en": ward_en,
                "town": town,
                "romaji": t_romaji,
                "chome": chome,
                "sub": sub,
                "slug": slug,
                "types": types,
                "rules": rules,
                "source": {
                    "url": full_carender_url,
                    "fetched": TODAY_STR,
                    "basis": "official_html_carender",
                },
                "raw": {
                    "address_label": addr_raw,
                    "carender_id": carender_id,
                },
            }
            all_normalized.append(record)

    print(f"[+] Total normalized Sapporo records: {len(all_normalized)}")
    print(f"[+] Unique slugs: {len(used_slugs)}")

    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_normalized, f, ensure_ascii=False, indent=2)

    print(f"[✔] Wrote to {out_file}")


if __name__ == "__main__":
    main()
