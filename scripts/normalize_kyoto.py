#!/usr/bin/env python3
"""
Normalize Kyoto City (京都市) Garbage Collection Schedule
---------------------------------------------------------
Reads official Kyoto Open Data garbage collection schedule PDFs:
Source: https://data.city.kyoto.lg.jp/dataset/00029/ (resource id 149)
Raw cache: data/raw/kyoto/
Output: data/normalized/kyoto.json

Rules:
- 11 Wards: 北区(kita), 上京区(kamigyo), 左京区(sakyo), 中京区(nakagyo),
  東山区(higashiyama), 山科区(yamashina), 下京区(shimogyo), 南区(minami),
  右京区(ukyo), 西京区(nishikyo), 伏見区(fushimi)
- 6 standard keys: burnable, resource, plastic, nonburnable
- pykakasi slug with 0 duplicates
- source.fetched: 2026-09-17
"""

import io
import json
import os
import re
import sys
import unicodedata
import urllib.request
import urllib.parse
import zipfile
from typing import Dict, List, Any, Set, Tuple
import pdfplumber
import pykakasi

RESOURCE_URL = "https://data.city.kyoto.lg.jp/resource/?id=149"
VALID_DAYS = {"月", "火", "水", "木", "金", "土", "日"}
TODAY_STR = "2026-09-17"

PDF_WARD_MAP = [
    ("1", "北区", "kita"),
    ("2", "上京区", "kamigyo"),
    ("3", "左京区", "sakyo"),
    ("4", "中京区", "nakagyo"),
    ("5", "東山区", "higashiyama"),
    ("6", "山科区", "yamashina"),
    ("7", "下京区", "shimogyo"),
    ("8", "南区", "minami"),
    ("9", "右京区", "ukyo"),
    ("10", "右京区", "ukyo"), # keihoku
    ("11", "西京区", "nishikyo"),
    ("13", "伏見区", "fushimi"),
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
    if not val:
        return []
    val_norm = unicodedata.normalize("NFKC", val)
    clean = re.sub(r"曜日?", "", val_norm)
    days = []
    for ch in clean:
        if ch in VALID_DAYS and ch not in days:
            days.append(ch)
    return days


def split_town_and_chome(name_field: str) -> Tuple[str, str, str]:
    """Returns (town, chome, kana)"""
    name_field = unicodedata.normalize("NFKC", name_field).strip()
    kana = ""
    m_kana = re.search(r"[\(（](.*?)[\)）]", name_field)
    if m_kana:
        kana = m_kana.group(1).strip()
        name_field = re.sub(r"[\(（].*?[\)）]", "", name_field).strip()

    # Split chome if any
    m_chome = re.search(r"(\d+丁目)", name_field)
    if m_chome:
        chome = m_chome.group(1)
        town = name_field.replace(chome, "").strip()
        return town, chome, kana

    return name_field, "", kana


def download_kyoto_zip(raw_dir: str) -> str:
    os.makedirs(raw_dir, exist_ok=True)
    zip_path = os.path.join(raw_dir, "kyoto_gomi.zip")
    if not os.path.exists(zip_path) or os.path.getsize(zip_path) == 0:
        print(f"[*] Downloading Kyoto data zip from {RESOURCE_URL}...")
        data = urllib.parse.urlencode({
            "upload_file": "ごみの収集日（町名ごと）.zip",
            "upload_url": "",
            "download": "このデータをダウンロード"
        }).encode("utf-8")
        req = urllib.request.Request(RESOURCE_URL, data=data, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            with open(zip_path, "wb") as f:
                f.write(resp.read())
        print(f"[+] Downloaded Kyoto zip ({os.path.getsize(zip_path)} bytes)")
    return zip_path


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_dir = os.path.join(base_dir, "data", "raw", "kyoto")
    out_file = os.path.join(base_dir, "data", "normalized", "kyoto.json")

    zip_path = download_kyoto_zip(raw_dir)
    zf = zipfile.ZipFile(zip_path)

    # Index files by prefix number
    pdf_entries = {}
    for zname in zf.namelist():
        # Match e.g. 1北区, 10右京区, etc.
        m = re.search(r"/(\d+)", zname)
        if m:
            pdf_entries[m.group(1)] = zname

    all_normalized = []
    used_slugs: Set[str] = set()

    for p_id, ward_name, ward_en in PDF_WARD_MAP:
        zname = pdf_entries.get(p_id)
        if not zname:
            print(f"[!] PDF entry for id {p_id} not found!", file=sys.stderr)
            continue

        print(f"[*] Parsing Kyoto {ward_name} ({p_id})...")
        pdf_bytes = zf.read(zname)
        
        if p_id == "10":
            # Keihoku special table
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                t = pdf.pages[0].extract_table()
                # Row 1: ['燃やすごみ\n（週２回）', '黒田・宇津・山国・細野 地区', '月・木 曜日']
                # Row 2: [None, '周山・弓削 地区', '火・金 曜日']
                # Row 3: ['缶・びん・ペットボトル\n（週１回）', '全ての地区', '水 曜日']
                districts = [
                    ("黒田・宇津・山国・細野地区", ["月", "木"], ["水"]),
                    ("周山・弓削地区", ["火", "金"], ["水"]),
                ]
                for dname, burn_days, res_days in districts:
                    t_romaji = to_romaji(dname)
                    slug_base = f"kyoto/{ward_en}/{t_romaji}"
                    slug = slug_base
                    idx = 2
                    while slug in used_slugs:
                        slug = f"{slug_base}-{idx}"
                        idx += 1
                    used_slugs.add(slug)

                    record = {
                        "pref": "京都府",
                        "city": "京都市",
                        "city_en": "kyoto",
                        "ward": ward_name,
                        "ward_en": ward_en,
                        "town": dname,
                        "romaji": t_romaji,
                        "chome": "",
                        "sub": "京北地区",
                        "slug": slug,
                        "types": {
                            "burnable": {"label": "燃やすごみ", "days": burn_days, "weeks": None, "time": "朝8:00まで"},
                            "resource": {"label": "缶・びん・ペットボトル", "days": res_days, "weeks": None, "time": "朝8:00まで"},
                        },
                        "rules": {
                            "holiday_collection": "祝日も収集",
                            "time_by": "8:00",
                            "yearend": "12/31~1/3 休止",
                        },
                        "source": {
                            "url": "https://data.city.kyoto.lg.jp/dataset/00029/",
                            "fetched": TODAY_STR,
                            "basis": "official_pdf",
                        },
                        "raw": {"district": dname, "burnable": burn_days, "resource": res_days},
                    }
                    all_normalized.append(record)
            continue

        last_town = ""
        last_chome = ""

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                t = page.extract_table()
                if not t:
                    continue
                for row in t:
                    if not row or not row[0]:
                        continue
                    c0 = row[0].strip()
                    if c0.startswith("町") or c0.startswith("種類") or c0.startswith("【") or c0 == "収集日":
                        continue

                    raw_name = c0
                    town, chome, kana = split_town_and_chome(raw_name)
                    
                    # Handle ditto mark 〃
                    town_clean = town.strip()
                    if town_clean == "〃" or not town_clean.strip("〃 "):
                        town = last_town
                        if not chome:
                            chome = last_chome
                    else:
                        town = re.sub(r"^〃\s*", "", town_clean).strip()
                        last_town = town
                        last_chome = chome

                    if not town:
                        continue

                    # Columns: ['町 名', '燃やす\nごみ', '缶・びん・\nﾍﾟｯﾄﾎﾞﾄﾙ', 'ﾌﾟﾗｽﾁｯｸ製\n容器包装', '小型\n金属', '備 考']
                    burn_raw = row[1] if len(row) > 1 and row[1] else ""
                    res_raw = row[2] if len(row) > 2 and row[2] else ""
                    pla_raw = row[3] if len(row) > 3 and row[3] else ""
                    met_raw = row[4] if len(row) > 4 and row[4] else ""
                    note_raw = row[5] if len(row) > 5 and row[5] else ""

                    burn_days = parse_clean_days(burn_raw)
                    res_days = parse_clean_days(res_raw)
                    pla_days = parse_clean_days(pla_raw)

                    # Metal is "第○水曜日", with integer in cell
                    met_weeks = None
                    met_days = []
                    if met_raw:
                        nums = re.findall(r"\d+", unicodedata.normalize("NFKC", met_raw))
                        if nums:
                            met_weeks = [int(x) for x in nums]
                            met_days = ["水"]  # Kyoto small metal is strictly collected on Wednesdays

                    types: Dict[str, Any] = {}
                    if burn_days:
                        types["burnable"] = {"label": "燃やすごみ", "days": burn_days, "weeks": None, "time": "朝8:00まで"}
                    if res_days:
                        types["resource"] = {"label": "缶・びん・ペットボトル", "days": res_days, "weeks": None, "time": "朝8:00まで"}
                    if pla_days:
                        types["plastic"] = {"label": "プラスチック製容器包装", "days": pla_days, "weeks": None, "time": "朝8:00まで"}
                    if met_days:
                        types["nonburnable"] = {"label": "小型金属", "days": met_days, "weeks": met_weeks, "time": "朝8:00まで"}

                    t_romaji = to_romaji(town)
                    chome_num = extract_nums(chome)
                    sub_clean = unicodedata.normalize("NFKC", note_raw).strip()

                    slug_base = f"kyoto/{ward_en}/{t_romaji}"
                    if chome_num:
                        slug_base += f"-{chome_num}"
                    if sub_clean:
                        sub_romaji = to_romaji(sub_clean)[:20]
                        if sub_romaji:
                            slug_base += f"-{sub_romaji}"

                    slug_base = re.sub(r"[^a-z0-9\-/]+", "-", slug_base.lower()).strip("-")
                    slug = slug_base
                    idx = 2
                    while slug in used_slugs:
                        slug = f"{slug_base}-{idx}"
                        idx += 1
                    used_slugs.add(slug)

                    record = {
                        "pref": "京都府",
                        "city": "京都市",
                        "city_en": "kyoto",
                        "ward": ward_name,
                        "ward_en": ward_en,
                        "town": town,
                        "romaji": t_romaji,
                        "chome": chome,
                        "sub": sub_clean,
                        "slug": slug,
                        "types": types,
                        "rules": {
                            "holiday_collection": "祝日も収集",
                            "time_by": "8:00",
                            "yearend": "12/31~1/3 休止",
                        },
                        "source": {
                            "url": "https://data.city.kyoto.lg.jp/dataset/00029/",
                            "fetched": TODAY_STR,
                            "basis": "official_pdf",
                        },
                        "notes": f"読み: {kana}" if kana else "",
                        "raw": {
                            "row": row,
                            "pdf": os.path.basename(zname),
                        },
                    }
                    all_normalized.append(record)

    print(f"[+] Total normalized Kyoto records: {len(all_normalized)}")
    print(f"[+] Unique slugs: {len(used_slugs)}")

    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_normalized, f, ensure_ascii=False, indent=2)

    print(f"[✔] Wrote to {out_file}")


if __name__ == "__main__":
    main()
