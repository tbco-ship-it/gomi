#!/usr/bin/env python3
"""
Normalize Nagoya City (名古屋市) Garbage Collection Schedule
-----------------------------------------------------------
Reads official Nagoya City collection schedule HTML:
Source: https://www.city.nagoya.jp/kurashi/gomi/1012183/1037098.html
Raw cache: data/raw/nagoya/gomi.html
Output: data/normalized/nagoya.json

Rules:
- 16 Wards: 千種区(chikusa), 東区(higashi), 北区(kita), 西区(nishi),
  中村区(nakamura), 中区(naka), 昭和区(showa), 瑞穂区(mizuho),
  熱田区(atsuta), 中川区(nakagawa), 港区(minato), 南区(minami),
  守山区(moriyama), 緑区(midori), 名東区(meito), 天白区(tempaku)
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

PAGE_URL = "https://www.city.nagoya.jp/kurashi/gomi/1012183/1037098.html"
TODAY_STR = "2026-09-17"
VALID_DAYS = {"月", "火", "水", "木", "金", "土", "日"}

WARD_EN_MAP = {
    "千種区": "chikusa",
    "東区": "higashi",
    "北区": "kita",
    "西区": "nishi",
    "中村区": "nakamura",
    "中区": "naka",
    "昭和区": "showa",
    "瑞穂区": "mizuho",
    "熱田区": "atsuta",
    "中川区": "nakagawa",
    "港区": "minato",
    "南区": "minami",
    "守山区": "moriyama",
    "緑区": "midori",
    "名東区": "meito",
    "天白区": "tempaku",
}

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
    """Parse days strictly matching ([月火水木金土日])曜 to avoid matching '日' from '曜日'."""
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
    """Parse string like '第2水曜日' into ([2], ['水'])."""
    if not val:
        return [], []
    val_norm = unicodedata.normalize("NFKC", val)
    days = []
    for m in re.finditer(r"([月火水木金土日])曜", val_norm):
        d = m.group(1)
        if d in VALID_DAYS and d not in days:
            days.append(d)

    weeks = []
    m_w = re.findall(r"第(\d+)", val_norm)
    if m_w:
        weeks = [int(x) for x in m_w]
    return weeks, days


def download_nagoya_html(raw_dir: str) -> str:
    os.makedirs(raw_dir, exist_ok=True)
    html_path = os.path.join(raw_dir, "gomi.html")
    if not os.path.exists(html_path) or os.path.getsize(html_path) == 0:
        print(f"[*] Downloading Nagoya HTML from {PAGE_URL}...")
        req = urllib.request.Request(PAGE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            with open(html_path, "wb") as f:
                f.write(data)
        print(f"[+] Downloaded Nagoya HTML ({os.path.getsize(html_path)} bytes)")
    return html_path


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_dir = os.path.join(base_dir, "data", "raw", "nagoya")
    out_file = os.path.join(base_dir, "data", "normalized", "nagoya.json")

    html_path = download_nagoya_html(raw_dir)

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")
    table_all = soup.find("div", class_="table-all")
    if not table_all:
        print("[!] table-all div not found in Nagoya HTML!", file=sys.stderr)
        sys.exit(1)

    trs = table_all.find_all("tr")
    print(f"[*] Total table rows found: {len(trs)}")

    all_normalized = []
    used_slugs: Set[str] = set()

    # trs[0] is table header
    for r_idx, tr in enumerate(trs[1:], start=1):
        tds = [td.get_text().strip() for td in tr.find_all(["th", "td"])]
        if len(tds) < 6 or tds[0] == "地区名":
            continue

        area_raw = tds[0]
        burn_raw = tds[1]
        nonburn_raw = tds[2]
        bulky_raw = tds[3]
        pla_raw = tds[4]
        res_raw = tds[5]

        # Parse ward and town: e.g. "東区　相生町" or "天白区　相川一丁目、二丁目"
        parts = re.split(r"[\s\u3000]+", area_raw.strip(), maxsplit=1)
        ward = parts[0]
        town_full = parts[1] if len(parts) > 1 else ""

        ward_en = WARD_EN_MAP.get(ward, to_romaji(ward))

        # Split chome and sub from town_full
        town_norm = unicodedata.normalize("NFKC", town_full).strip()
        chome = ""
        sub = ""

        # Check for trailing note / exceptions in town_norm
        # e.g. "上飯田東町1丁目 201〜205" or "相川一丁目、二丁目"
        m_ch = re.search(r"(\d+丁目[、\d丁目]*|[一二三四五六七八九十]+丁目[、一二三四五六七八九十丁目]*)", town_norm)
        if m_ch:
            chome = m_ch.group(1)
            # Town is prefix before chome
            town = town_norm[:m_ch.start()].strip()
            rest = town_norm[m_ch.end():].strip()
            if rest:
                sub = rest
        else:
            town = town_norm

        types: Dict[str, Any] = {}

        # Burnable
        # Handle "8/3からは..." note: if present, since 2026-09-17 is after 8/3, use new schedule
        burn_days = []
        if "8/3からは" in burn_raw:
            m_after = re.search(r"8/3からは(.*?)詳しく", burn_raw)
            if m_after:
                burn_days = parse_clean_days(m_after.group(1))
        if not burn_days:
            burn_days = parse_clean_days(burn_raw)

        if burn_days:
            types["burnable"] = {
                "label": "可燃ごみ",
                "days": burn_days,
                "weeks": None,
                "time": "朝8:00まで",
            }

        # Non-burnable
        nb_weeks, nb_days = parse_week_and_days(nonburn_raw)
        if nb_days:
            types["nonburnable"] = {
                "label": "不燃ごみ",
                "days": nb_days,
                "weeks": nb_weeks if nb_weeks else None,
                "time": "朝8:00まで",
            }

        # Bulky
        bk_weeks, bk_days = parse_week_and_days(bulky_raw)
        if bk_days:
            types["bulky"] = {
                "label": "粗大ごみ",
                "days": bk_days,
                "weeks": bk_weeks if bk_weeks else None,
                "time": "朝8:00まで",
            }

        # Plastic
        pla_days = parse_clean_days(pla_raw)
        if pla_days:
            types["plastic"] = {
                "label": "プラスチック資源",
                "days": pla_days,
                "weeks": None,
                "time": "朝8:00まで",
            }

        # Resource (paper, cloth, cans, bottles, PET)
        res_days = parse_clean_days(res_raw)
        if res_days:
            types["resource"] = {
                "label": "資源（紙・缶・びん・ペットボトル）",
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

        slug_base = f"nagoya/{ward_en}/{t_romaji}"
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
            "pref": "愛知県",
            "city": "名古屋市",
            "city_en": "nagoya",
            "ward": ward,
            "ward_en": ward_en,
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
                "nonburnable": nonburn_raw,
                "bulky": bulky_raw,
                "plastic": pla_raw,
                "resource": res_raw,
            },
        }
        all_normalized.append(record)

    print(f"[+] Total normalized Nagoya records: {len(all_normalized)}")
    print(f"[+] Unique slugs: {len(used_slugs)}")

    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_normalized, f, ensure_ascii=False, indent=2)

    print(f"[✔] Wrote to {out_file}")


if __name__ == "__main__":
    main()
