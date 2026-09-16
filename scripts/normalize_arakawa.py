#!/usr/bin/env python3
"""Normalize Arakawa Ward (荒川区) Garbage Collection Schedule
Source: Official HTML (arakawa.html)
Output: data/normalized/arakawa.json
"""
import json
import os
import re
import unicodedata
from typing import Dict, List, Any, Set
from bs4 import BeautifulSoup
import pykakasi

kakasi = pykakasi.kakasi()
VALID_DAYS = {"月", "火", "水", "木", "金", "土", "日"}
TODAY_STR = "2026-09-17"
KANJI_MAP = {
    "一": "1",
    "二": "2",
    "三": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
    "十": "10",
}


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return re.sub(r"[^a-z0-9]+", "-", romaji).strip("-")


def parse_schedule_cell(val: str, label: str) -> Dict[str, Any]:
    if not val:
        return None
    val_norm = unicodedata.normalize("NFKC", str(val))

    weeks = None
    w_nums = re.findall(r"([0-9]+)", val_norm.split()[0] if "回目" in val_norm else "")
    if "回目" in val_norm and w_nums:
        weeks = [int(w) for w in w_nums if int(w) <= 5]

    days = []
    for m in re.finditer(r"([月火水木金土日])曜", val_norm):
        d = m.group(1)
        if d in VALID_DAYS and d not in days:
            days.append(d)

    if not days:
        return None

    return {
        "label": label,
        "days": days,
        "weeks": weeks,
        "time": "朝8:00まで",
    }


def split_area(raw_area: str):
    s = unicodedata.normalize("NFKC", raw_area).replace("※注釈", "").strip()
    m = re.match(r"^([^\d一二三四五六七八九]+)(.+?丁目)(.*)$", s)
    if m:
        town = m.group(1)
        chome = m.group(2)
        sub = m.group(3).strip()
        for k, v in KANJI_MAP.items():
            chome = chome.replace(k, v)
        return town, chome, sub
    m2 = re.match(r"^([^\d]+)(\d+丁目)(.*)$", s)
    if m2:
        return m2.group(1), m2.group(2), m2.group(3).strip()
    return s, "", ""


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(base_dir, "data", "raw", "arakawa", "arakawa.html")
    out_path = os.path.join(base_dir, "data", "normalized", "arakawa.json")

    with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f, "html.parser")

    tables = soup.find_all("table")
    records = []
    used_slugs: Set[str] = set()

    for idx_table, t in enumerate(tables):
        rows = t.find_all("tr")
        if not rows:
            continue
        header = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]

        # Context heading for apartment tables (Table 1~4)
        apt_context = None
        if idx_table > 0:
            prev = t.find_previous(["h2", "h3", "h4", "p"])
            if prev:
                apt_context = prev.get_text(strip=True)

        for tr in rows[1:]:
            tds = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
            if len(tds) < 4:
                continue

            raw_name = tds[0]
            if idx_table == 0:
                town, chome, sub = split_area(raw_name)
            else:
                # Apartment complex
                town = "南千住"
                chome_m = re.search(r"([一二三四五六七八九\d]+丁目)", apt_context or "")
                if chome_m:
                    ch_str = chome_m.group(1)
                    for k, v in KANJI_MAP.items():
                        ch_str = ch_str.replace(k, v)
                    chome = ch_str
                else:
                    chome = ""
                sub = raw_name

            romaji_town = to_romaji(town)
            chome_slug = to_romaji(chome) if chome else ""
            sub_slug = to_romaji(sub) if sub else ""

            slug_parts = ["arakawa", romaji_town]
            if chome_slug:
                slug_parts.append(chome_slug)
            if sub_slug:
                slug_parts.append(sub_slug)

            base_slug = "-".join([s for s in slug_parts if s])
            base_slug = re.sub(r"[^a-z0-9\-]+", "-", base_slug).strip("-")
            base_slug = re.sub(r"-+", "-", base_slug)
            if base_slug.startswith("arakawa-"):
                base_slug = "arakawa/" + base_slug[len("arakawa-") :]
            elif base_slug == "arakawa":
                base_slug = "arakawa/area"

            slug = base_slug
            idx = 2
            while slug in used_slugs:
                slug = f"{base_slug}-{idx}"
                idx += 1
            used_slugs.add(slug)

            types = {}
            # tds[1]: 燃やすごみ
            c_burn = parse_schedule_cell(tds[1], "燃やすごみ")
            if c_burn:
                types["burnable"] = c_burn
            # tds[2]: 燃やさないごみ
            c_non = parse_schedule_cell(tds[2], "燃やさないごみ")
            if c_non:
                types["nonburnable"] = c_non
            # tds[3]: プラスチック
            c_pla = parse_schedule_cell(tds[3], "プラスチック")
            if c_pla:
                types["plastic"] = c_pla

            raw_dict = {
                "地域_物件名": tds[0],
                "燃やすごみの収集日": tds[1],
                "燃やさないごみの収集日": tds[2],
                "プラスチックの回収日": tds[3],
            }
            if apt_context:
                raw_dict["context"] = apt_context

            record = {
                "pref": "東京都",
                "city": "荒川区",
                "city_en": "arakawa",
                "ward": "",
                "ward_en": "",
                "town": town,
                "chome": chome,
                "sub": sub,
                "romaji": romaji_town,
                "slug": slug,
                "types": types,
                "rules": {
                    "holiday_collection": "祝日も収集（年末年始を除く）",
                    "time_by": "朝8:00まで",
                    "yearend": "12/31~1/3 休止",
                    "note": "資源回収（びん・缶・紙）は町会集団回収方式で実施",
                },
                "source": {
                    "url": "https://www.city.arakawa.tokyo.jp/a025/recycle/shuushuubi/ichiran.html",
                    "fetched": TODAY_STR,
                    "basis": "official_html",
                },
                "raw": raw_dict,
            }
            records.append(record)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"arakawa: {len(records)} records written -> {out_path}")


if __name__ == "__main__":
    main()
