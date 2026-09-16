#!/usr/bin/env python3
"""
Normalize Kobe City (神戸市) Garbage Collection Schedule
--------------------------------------------------------
Reads official Kobe City Open Data CSV:
Source: https://www.city.kobe.lg.jp/documents/25079/gomi.csv
Raw cache: data/raw/kobe/gomi.csv
Output: data/normalized/kobe.json

Rules:
- 9 Wards: 東灘区(higashinada), 灘区(nada), 兵庫区(hyogo), 長田区(nagata),
  須磨区(suma), 垂水区(tarumi), 北区(kita), 中央区(chuo), 西区(nishi)
- 6 standard keys: burnable, resource, plastic, paper_cloth, nonburnable, bulky
- pykakasi slug with 0 duplicates
- source.fetched: 2026-09-17
"""

import csv
import io
import json
import os
import re
import sys
import unicodedata
import urllib.request
from typing import Dict, List, Any, Set, Tuple
import pykakasi

CSV_URL = "https://www.city.kobe.lg.jp/documents/25079/gomi.csv"
TODAY_STR = "2026-09-17"
VALID_DAYS = {"月", "火", "水", "木", "金", "土", "日"}

WARD_EN_MAP = {
    "東灘区": "higashinada",
    "灘区": "nada",
    "兵庫区": "hyogo",
    "長田区": "nagata",
    "須磨区": "suma",
    "垂水区": "tarumi",
    "北区": "kita",
    "中央区": "chuo",
    "西区": "nishi",
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


def download_kobe_csv(raw_dir: str) -> str:
    os.makedirs(raw_dir, exist_ok=True)
    csv_path = os.path.join(raw_dir, "gomi.csv")
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        print(f"[*] Downloading Kobe CSV from {CSV_URL}...")
        req = urllib.request.Request(CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            with open(csv_path, "wb") as f:
                f.write(data)
        print(f"[+] Downloaded Kobe CSV ({os.path.getsize(csv_path)} bytes)")
    return csv_path


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_dir = os.path.join(base_dir, "data", "raw", "kobe")
    out_file = os.path.join(base_dir, "data", "normalized", "kobe.json")

    csv_path = download_kobe_csv(raw_dir)

    with open(csv_path, "rb") as f:
        raw_bytes = f.read()

    text = ""
    for enc in ["cp932", "shift-jis", "utf-8"]:
        try:
            text = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            pass

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    # rows[0] is header 1, rows[1] is header 2
    # Data starts at row 2
    all_normalized = []
    used_slugs: Set[str] = set()

    for idx, r in enumerate(rows[2:], start=3):
        if not r or len(r) < 5 or not r[0]:
            continue

        ward = r[0].strip()
        town = r[1].strip()
        kana = r[2].strip() if len(r) > 2 else ""
        block_raw = r[3].strip() if len(r) > 3 else ""
        burn_raw = r[4].strip() if len(r) > 4 else ""
        nonburn_weeks_raw = r[5].strip() if len(r) > 5 else ""
        nonburn_day_raw = r[6].strip() if len(r) > 6 else ""
        pla_day_raw = r[8].strip() if len(r) > 8 else ""
        can_day_raw = r[10].strip() if len(r) > 10 else ""
        note_raw = r[11].strip() if len(r) > 11 else ""

        ward_en = WARD_EN_MAP.get(ward, to_romaji(ward))

        # Split chome from block_raw
        block_norm = unicodedata.normalize("NFKC", block_raw).strip()
        chome = ""
        sub = ""

        m_ch = re.search(r"(\d+丁目)", block_norm)
        if m_ch:
            chome = m_ch.group(1)
            sub = block_norm.replace(chome, "").strip()
        else:
            if block_norm and block_norm != "全域":
                sub = block_norm

        # Waste schedule
        types: Dict[str, Any] = {}

        # Burnable: "月木" -> ["月", "木"], "火金" -> ["火", "金"]
        burn_days = [ch for ch in burn_raw if ch in VALID_DAYS]
        if burn_days:
            types["burnable"] = {"label": "燃えるごみ", "days": burn_days, "weeks": None, "time": "朝8:00まで"}

        # Non-burnable: weeks "13" -> [1, 3], "24" -> [2, 4]
        if nonburn_day_raw in VALID_DAYS:
            nb_weeks = None
            if nonburn_weeks_raw == "13":
                nb_weeks = [1, 3]
            elif nonburn_weeks_raw == "24":
                nb_weeks = [2, 4]
            types["nonburnable"] = {
                "label": "燃えないごみ",
                "days": [nonburn_day_raw],
                "weeks": nb_weeks,
                "time": "朝8:00まで",
            }

        # Plastic: "水", "木" etc.
        if pla_day_raw in VALID_DAYS:
            types["plastic"] = {
                "label": "容器包装プラスチック",
                "days": [pla_day_raw],
                "weeks": None,
                "time": "朝8:00まで",
            }

        # Resource (cans, bottles, PET): "水" etc.
        if can_day_raw in VALID_DAYS:
            types["resource"] = {
                "label": "缶・びん・ペットボトル",
                "days": [can_day_raw],
                "weeks": None,
                "time": "朝8:00까지",
            }

        rules = {
            "holiday_collection": "祝日も収集",
            "time_by": "8:00",
            "yearend": "12/31~1/3 休止",
        }
        if note_raw:
            rules["note"] = note_raw

        t_romaji = to_romaji(town)
        chome_num = extract_nums(chome)
        sub_num = extract_nums(sub)

        slug_base = f"kobe/{ward_en}/{t_romaji}"
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
            "pref": "兵庫県",
            "city": "神戸市",
            "city_en": "kobe",
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
                "url": "https://www.city.kobe.lg.jp/a04164/kurashi/recycle/gomi/dashikata/shigen/index.html",
                "fetched": TODAY_STR,
                "basis": "official_csv",
            },
            "notes": f"読み: {kana}" if kana else "",
            "raw": {
                "row": r,
                "line": idx,
            },
        }
        all_normalized.append(record)

    print(f"[+] Total normalized Kobe records: {len(all_normalized)}")
    print(f"[+] Unique slugs: {len(used_slugs)}")

    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_normalized, f, ensure_ascii=False, indent=2)

    print(f"[✔] Wrote to {out_file}")


if __name__ == "__main__":
    main()
