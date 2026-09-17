#!/usr/bin/env python3
"""
Normalize Kawasaki City (川崎市) Garbage Collection Schedule
------------------------------------------------------------
Official Source: 川崎市役所 環境局 資源物とごみの分け方・出し方 (地域別収集日一覧)
- 4 HTML pages, 7 Wards:
  1. 川崎区 (kawasaki): https://www.city.kawasaki.jp/300/page/0000012570.html
  2. 幸区 (saiwai) & 中原区 (nakahara): https://www.city.kawasaki.jp/300/page/0000012568.html
  3. 高津区 (takatsu) & 宮前区 (miyamae): https://www.city.kawasaki.jp/300/page/0000012561.html
  4. 多摩区 (tama) & 麻生区 (asao): https://www.city.kawasaki.jp/300/page/0000012577.html
Total: 255 町名 records across 7 wards
Output: data/wip/kawasaki.json
"""

import json
import os
import re
import sys
import unicodedata
import urllib.request
from bs4 import BeautifulSoup
import pykakasi

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw", "kawasaki")
WIP_DIR = os.path.join(BASE_DIR, "data", "wip")

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(WIP_DIR, exist_ok=True)

TODAY_STR = "2026-09-17"

PAGE_CONFIGS = [
    {
        "file": "kawasaki_ku.html",
        "url": "https://www.city.kawasaki.jp/300/page/0000012570.html",
        "wards": [("川崎区", "kawasaki", 0)],
    },
    {
        "file": "saiwai_nakahara_ku.html",
        "url": "https://www.city.kawasaki.jp/300/page/0000012568.html",
        "wards": [("幸区", "saiwai", 0), ("中原区", "nakahara", 1)],
    },
    {
        "file": "takatsu_miyamae_ku.html",
        "url": "https://www.city.kawasaki.jp/300/page/0000012561.html",
        "wards": [("高津区", "takatsu", 0), ("宮前区", "miyamae", 1)],
    },
    {
        "file": "tama_asao_ku.html",
        "url": "https://www.city.kawasaki.jp/300/page/0000012577.html",
        "wards": [("多摩区", "tama", 0), ("麻生区", "asao", 1)],
    },
]

kakasi = pykakasi.kakasi()


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return re.sub(r"[^a-z0-9]+", "-", romaji).strip("-")


def parse_schedule_cell(val: str):
    """
    Parses day characters and week numbers.
    e.g. '月曜・木曜' -> (['月', '木'], None)
         '第1・3回目 水曜' -> (['水'], [1, 3])
         '第2・4回目 木曜' -> (['木'], [2, 4])
    """
    if not val or val == "-":
        return [], None

    s = unicodedata.normalize("NFKC", val).strip()

    weeks = None
    if "1・3" in s or "1,3" in s:
        weeks = [1, 3]
    elif "2・4" in s or "2,4" in s:
        weeks = [2, 4]

    days = []
    for m in re.finditer(r"([月火水木金土日])曜", s):
        d = m.group(1)
        if d not in days:
            days.append(d)

    return days, weeks


def fetch_page_html(cfg: dict) -> str:
    path = os.path.join(RAW_DIR, cfg["file"])
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    req = urllib.request.Request(cfg["url"], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        content = resp.read()
        with open(path, "wb") as f:
            f.write(content)
        return content.decode("utf-8")


def normalize():
    records = []
    seen_slugs = set()

    for page in PAGE_CONFIGS:
        html = fetch_page_html(page)
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")

        for ward_name, ward_en, table_idx in page["wards"]:
            if table_idx >= len(tables):
                print(f"[!] Warning: table index {table_idx} out of range for {ward_name}")
                continue

            table = tables[table_idx]
            rows = table.find_all("tr")
            if not rows:
                continue

            # Header row check
            header_tds = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]

            for r_idx, row in enumerate(rows[1:], 1):
                tds = [unicodedata.normalize("NFKC", td.get_text(strip=True)) for td in row.find_all(["th", "td"])]
                if len(tds) < 7:
                    continue

                kana = tds[0]
                raw_town = tds[1]
                burn_val = tds[2]
                res_val = tds[3]
                paper_val = tds[4]
                plastic_val = tds[5]
                nonburn_val = tds[6]

                town = raw_town
                chome = None
                sub = None

                # Address splitting & sub-designation for Saiwai-ku edge cases
                if ward_en == "saiwai":
                    if raw_town == "小倉":
                        town = "小倉"
                        sub = "1~5丁目除く"
                    elif raw_town == "小倉1~5丁目":
                        town = "小倉"
                        chome = "1~5丁目"
                        sub = None
                    elif raw_town == "河原町":
                        town = "河原町"
                        sub = "団地除く"
                    elif raw_town == "河原町団地1~3号棟":
                        town = "河原町"
                        sub = "団地1~3号棟"
                    elif raw_town == "河原町団地4~9号棟":
                        town = "河原町"
                        sub = "団地4~9号棟"
                    elif raw_town == "河原町団地12~15号棟":
                        town = "河原町"
                        sub = "団地12~15号棟"
                    elif raw_town == "古市場":
                        town = "古市場"
                        sub = "1・2丁目除く"
                    elif raw_town == "古市場1・2丁目":
                        town = "古市場"
                        chome = "1・2丁目"
                        sub = None

                town_romaji = to_romaji(town) or "town"
                slug_parts = ["kawasaki", ward_en, town_romaji]

                if chome:
                    nums = "".join(re.findall(r"\d+", unicodedata.normalize("NFKC", chome)))
                    slug_parts.append(f"{nums}chome" if nums else to_romaji(chome))
                if sub and sub not in ["1~5丁目除く", "団地除く", "1・2丁目除く"]:
                    sub_r = to_romaji(sub)
                    if sub_r:
                        slug_parts.append(sub_r)

                slug = "/".join(slug_parts)
                slug = re.sub(r"-+", "-", slug).strip("-").lower()

                # Ensure slug uniqueness
                base_slug = slug
                cnt = 2
                while slug in seen_slugs:
                    slug = f"{base_slug}-{cnt}"
                    cnt += 1
                seen_slugs.add(slug)

                # Standard 6 waste types
                types = {}

                # 1. burnable (普通ごみ)
                b_days, b_weeks = parse_schedule_cell(burn_val)
                if b_days:
                    types["burnable"] = {
                        "label": "普通ごみ",
                        "days": b_days,
                        "weeks": b_weeks,
                        "time": None,
                    }

                # 2. resource (空き缶ペットボトル空きびん使用済み乾電池)
                r_days, r_weeks = parse_schedule_cell(res_val)
                if r_days:
                    types["resource"] = {
                        "label": "空き缶・ペットボトル・空きびん・使用済み乾電池",
                        "days": r_days,
                        "weeks": r_weeks,
                        "time": None,
                    }

                # 3. paper_cloth (ミックスペーパー)
                p_days, p_weeks = parse_schedule_cell(paper_val)
                if p_days:
                    types["paper_cloth"] = {
                        "label": "ミックスペーパー",
                        "days": p_days,
                        "weeks": p_weeks,
                        "time": None,
                    }

                # 4. plastic (プラスチック資源)
                pl_days, pl_weeks = parse_schedule_cell(plastic_val)
                if pl_days:
                    types["plastic"] = {
                        "label": "プラスチック資源",
                        "days": pl_days,
                        "weeks": pl_weeks,
                        "time": None,
                    }

                # 5. nonburnable (粗大ごみ小物金属)
                nb_days, nb_weeks = parse_schedule_cell(nonburn_val)
                if nb_days:
                    types["nonburnable"] = {
                        "label": "粗大ごみ小物金属",
                        "days": nb_days,
                        "weeks": nb_weeks,
                        "time": None,
                    }

                # 6. bulky (粗大ごみ - 申込制)
                types["bulky"] = {
                    "label": "粗大ごみ",
                    "days": [],
                    "weeks": None,
                    "time": None,
                    "note": "申込制",
                }

                rec = {
                    "pref": "神奈川県",
                    "city": "川崎市",
                    "city_en": "kawasaki",
                    "ward": ward_name,
                    "ward_en": ward_en,
                    "town": town,
                    "chome": chome,
                    "sub": sub,
                    "romaji": town_romaji,
                    "slug": slug,
                    "types": types,
                    "rules": {
                        "holiday_collection": "祝日も通常どおり収集（日曜日除く）",
                        "time_by": "8:00",
                        "yearend": "1/1~1/3 休止",
                    },
                    "source": {
                        "url": page["url"],
                        "fetched": TODAY_STR,
                        "basis": "official_html",
                    },
                    "raw": {
                        "区": ward_name,
                        "50音": kana,
                        "町名": raw_town,
                        "普通ごみ": burn_val,
                        "空き缶ペットボトル空きびん使用済み乾電池": res_val,
                        "ミックスペーパー": paper_val,
                        "プラスチック資源": plastic_val,
                        "粗大ごみ小物金属": nonburn_val,
                    },
                }
                records.append(rec)

    wip_file = os.path.join(WIP_DIR, "kawasaki.json")
    with open(wip_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"[✔] Successfully normalized {len(records)} records for Kawasaki -> {wip_file}")
    return wip_file


if __name__ == "__main__":
    wip_path = normalize()
    # Verification
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from verify_normalized import verify_file
    res = verify_file(wip_path)
    if res["status"] != "PASS":
        print(f"[❌] Validation FAILED: {res['errors']}")
        sys.exit(1)
    else:
        print("[✔] Validation PASSED 100%!")
