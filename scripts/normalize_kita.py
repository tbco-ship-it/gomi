#!/usr/bin/env python3
"""Normalize Kita Ward (北区) Garbage Collection Schedule
Source: Official HTML (kita.html)
Output: data/normalized/kita.json
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
    if not val or "集積所" in val:
        return None
    val_norm = unicodedata.normalize("NFKC", str(val))

    weeks = None
    w_nums = re.findall(r"第?([0-9]+)", val_norm)
    if ("第" in val_norm or "回" in val_norm) and w_nums:
        weeks = [int(w) for w in w_nums if int(w) <= 5]
        if not weeks:
            weeks = None

    days = []
    for m in re.finditer(r"([月火水木金土日])曜", val_norm):
        d = m.group(1)
        if d in VALID_DAYS and d not in days:
            days.append(d)
    if not days:
        for ch in val_norm:
            if ch in VALID_DAYS and ch not in days:
                days.append(ch)

    if not days:
        return None

    res_obj = {
        "label": label,
        "days": days,
        "weeks": weeks,
        "time": "朝8:00まで",
    }
    if "集団回収" in val:
        res_obj["note"] = val
    return res_obj


def split_kita_town_chome(name: str):
    name_norm = unicodedata.normalize("NFKC", name).strip()
    m = re.match(r"^(.*?)([一二三四五六七八九十]+丁目)$", name_norm)
    if m:
        t = m.group(1)
        ch_str = m.group(2)
        c_num = ch_str[:-2]
        c_arabic = "".join([KANJI_MAP.get(k, k) for k in c_num]) + "丁目"
        return t, c_arabic
    m2 = re.match(r"^(.*?)(\d+丁目)$", name_norm)
    if m2:
        return m2.group(1), m2.group(2)
    return name_norm, ""


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(base_dir, "data", "raw", "kita", "kita.html")
    out_path = os.path.join(base_dir, "data", "normalized", "kita.json")

    with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f, "html.parser")

    tables = soup.find_all("table")
    records = []
    used_slugs: Set[str] = set()

    for t in tables:
        rows = t.find_all("tr")
        if not rows:
            continue
        for tr in rows[1:]:
            tds = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
            if len(tds) < 6:
                continue

            raw_name = tds[0]
            raw_sub = tds[1]
            sub = raw_sub if raw_sub != "全域" else ""

            town, chome = split_kita_town_chome(raw_name)
            romaji_town = to_romaji(town)

            chome_slug = to_romaji(chome) if chome else ""
            sub_slug = to_romaji(sub) if sub else ""

            slug_parts = ["kita", romaji_town]
            if chome_slug:
                slug_parts.append(chome_slug)
            if sub_slug:
                slug_parts.append(sub_slug)

            base_slug = "-".join([s for s in slug_parts if s])
            base_slug = re.sub(r"[^a-z0-9\-]+", "-", base_slug).strip("-")
            base_slug = re.sub(r"-+", "-", base_slug)
            if base_slug.startswith("kita-"):
                base_slug = "kita/" + base_slug[len("kita-") :]
            elif base_slug == "kita":
                base_slug = "kita/area"

            slug = base_slug
            idx = 2
            while slug in used_slugs:
                slug = f"{base_slug}-{idx}"
                idx += 1
            used_slugs.add(slug)

            types = {}
            # tds[2]: 可燃ごみ
            c_burn = parse_schedule_cell(tds[2], "可燃ごみ")
            if c_burn:
                types["burnable"] = c_burn
            # tds[3]: 不燃ごみ
            c_non = parse_schedule_cell(tds[3], "不燃ごみ")
            if c_non:
                types["nonburnable"] = c_non
            # tds[4]: 古紙・プラスチック
            c_pla = parse_schedule_cell(tds[4], "古紙・プラスチック")
            if c_pla:
                types["plastic"] = c_pla
            # tds[5]: びん・缶・ペットボトル
            c_res = parse_schedule_cell(tds[5], "びん・缶・ペットボトル")
            if c_res:
                types["resource"] = c_res

            rules = {
                "holiday_collection": "祝日も収集（年末年始を除く）",
                "time_by": "朝8:00まで",
                "yearend": "12/31~1/3 休止",
            }
            if "集積所の表示板に記載" in tds[2] or "集積所の表示板に記載" in tds[3]:
                rules["note"] = "集積所の表示板に記載"

            raw_dict = {
                "町名": tds[0],
                "地区": tds[1],
                "可燃ごみ": tds[2],
                "不燃ごみ": tds[3],
                "古紙・プラスチック": tds[4],
                "びん・缶・ペットボトル": tds[5],
            }

            record = {
                "pref": "東京都",
                "city": "北区",
                "city_en": "kita",
                "ward": "",
                "ward_en": "",
                "town": town,
                "chome": chome,
                "sub": sub,
                "romaji": romaji_town,
                "slug": slug,
                "types": types,
                "rules": rules,
                "source": {
                    "url": "https://www.city.kita.tokyo.jp/kankyo/gomi/shushu/ichiran.html",
                    "fetched": TODAY_STR,
                    "basis": "official_html",
                },
                "raw": raw_dict,
            }
            records.append(record)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"kita: {len(records)} records written -> {out_path}")


if __name__ == "__main__":
    main()
