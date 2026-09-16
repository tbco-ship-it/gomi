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
- Resolves ditto mark (〃) with preceding 町名 prefix (冠称: 紫野, 紫竹, 大宮, etc.)
- 6 standard keys: burnable, resource, plastic, paper_cloth, nonburnable, bulky
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
    ("10", "右京区", "ukyo"),  # keihoku
    ("11", "西京区", "nishikyo"),
    ("13", "伏見区", "fushimi"),
]

# Official Kyoto kansho (prefix) mapping by ward
KYOTO_PREFIXES = {
    "北区": [
        "出雲路", "大北山", "大宮", "上賀茂", "小野", "衣笠", "小山",
        "紫竹", "紫野", "鷹峯", "鷹峰", "西賀茂", "中川", "雲ケ畑",
        "雲ヶ畑", "真弓", "杉阪", "杉坂", "北野", "大将軍", "等持院", "平野"
    ],
    "上京区": [],
    "左京区": [
        "粟田口", "岩倉", "大原", "北白川", "鞍馬", "久多", "鹿ヶ谷",
        "鹿ケ谷", "静市", "下鴨", "修学院", "聖護院", "浄土寺", "高野",
        "上高野", "田中", "南禅寺", "花背", "広河原", "松ヶ崎", "八瀬",
        "山端", "吉田", "一乗寺", "岡崎"
    ],
    "中京区": ["三条", "三坊", "聚楽廻", "西ノ京", "壬生", "六角"],
    "東山区": ["粟田口", "今熊野", "清閑寺", "泉涌寺", "福稲", "本町", "蛭子町", "一橋", "祇園町"],
    "山科区": [
        "安朱", "上野", "大塚", "大宅", "音羽", "小野", "上花山", "川田",
        "勧修寺", "北花山", "栗栖野", "小山", "四ノ宮", "厨子奥", "竹鼻",
        "椥辻", "西野", "西野山", "東野", "髭茶屋", "日ノ岡", "御陵"
    ],
    "下京区": ["梅小路", "中堂寺", "西七条", "西新屋敷", "東塩小路", "七条御所ノ内", "朱雀", "西綾小路", "立売", "仏光寺"],
    "南区": ["上鳥羽", "唐橋", "吉祥院", "久世", "西九条", "八条", "東九条"],
    "右京区": [
        "太秦安井", "太秦", "宇多野", "梅ケ畑", "梅ヶ畑", "梅津", "御室",
        "北嵯峨", "西院", "嵯峨野", "嵯峨", "谷口", "常盤", "鳴滝",
        "西京極郡", "西京極", "花園", "山越", "山ノ内", "龍安寺", "京北"
    ],
    "西京区": [
        "嵐山", "牛ケ瀬", "大枝", "大原野", "樫原", "上桂", "桂",
        "川島", "御陵", "下津林", "松尾", "松室", "山田", "北福西町"
    ],
    "伏見区": [
        "石田", "小栗栖", "京町", "下鳥羽", "醍醐", "竹田", "中島",
        "納所", "羽束師", "日野", "深草", "向島", "桃山町", "桃山",
        "横大路", "葭島", "淀", "久我"
    ],
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
    if not val:
        return []
    val_norm = unicodedata.normalize("NFKC", val)
    clean = re.sub(r"曜日?", "", val_norm)
    days = []
    for ch in clean:
        if ch in VALID_DAYS and ch not in days:
            days.append(ch)
    return days


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
        m = re.search(r"/(\d+)", zname)
        if m:
            pdf_entries[m.group(1)] = zname

    all_normalized = []
    used_slugs: Set[str] = set()
    seen_dedupe_keys: Set[Tuple] = set()

    for p_id, ward_name, ward_en in PDF_WARD_MAP:
        zname = pdf_entries.get(p_id)
        if not zname:
            print(f"[!] PDF entry for id {p_id} not found!", file=sys.stderr)
            continue

        print(f"[*] Parsing Kyoto {ward_name} ({p_id})...")
        pdf_bytes = zf.read(zname)

        if p_id == "10":
            # Keihoku special table
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
                        "burnable": {"label": "燃やすごみ", "days": burn_days, "weeks": None, "time": "朝8:00까지"},
                        "resource": {"label": "缶・びん・ペットボトル", "days": res_days, "weeks": None, "time": "朝8:00까지"},
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

        prefixes = sorted(KYOTO_PREFIXES.get(ward_name, []), key=len, reverse=True)
        current_prefix = ""
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
                    c0 = unicodedata.normalize("NFKC", row[0]).strip()
                    if c0.startswith("町") or c0.startswith("種類") or c0.startswith("【") or c0 == "収集日":
                        continue

                    # Extract reading kana if present in parentheses
                    kana = ""
                    m_kana = re.search(r"[\(（](.*?)[\)）]", c0)
                    if m_kana:
                        kana = m_kana.group(1).strip()
                    name_clean = re.sub(r"[\(（].*?[\)）]", "", c0).strip()

                    town = ""
                    chome = ""

                    # Resolve ditto marks (〃) with prefix
                    if name_clean == "〃" or not name_clean.strip("〃 "):
                        town = last_town
                        chome = last_chome
                    elif name_clean.startswith("〃"):
                        rest = re.sub(r"^〃\s*", "", name_clean).strip()
                        m_ch = re.match(r"^(\d+|[一二三四五六七八九十]+)丁目$", rest)
                        if m_ch:
                            town = last_town
                            chome = rest
                        else:
                            m_ch2 = re.search(r"(\d+丁目|[一二三四五六七八九十]+丁目)", rest)
                            if m_ch2:
                                chome = m_ch2.group(1)
                                rest = rest.replace(chome, "").strip()
                            town = current_prefix + rest
                            last_town = town
                            last_chome = chome
                    else:
                        # Non-ditto row defines or resets prefix
                        matched_p = ""
                        for pfx in prefixes:
                            if name_clean.startswith(pfx):
                                matched_p = pfx
                                break
                        current_prefix = matched_p

                        m_ch = re.search(r"(\d+丁目|[一二三四五六七八九十]+丁目)", name_clean)
                        if m_ch:
                            chome = m_ch.group(1)
                            name_clean = name_clean.replace(chome, "").strip()
                        town = name_clean
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

                    sub_clean = unicodedata.normalize("NFKC", note_raw).strip()

                    # Deduplication: exactly duplicate raw rows within the same town/chome/sub
                    dedupe_key = (ward_name, town, chome, sub_clean, tuple(row[1:]))
                    if dedupe_key in seen_dedupe_keys:
                        continue
                    seen_dedupe_keys.add(dedupe_key)

                    types: Dict[str, Any] = {}
                    rules = {
                        "holiday_collection": "祝日も収集",
                        "time_by": "8:00",
                        "yearend": "12/31~1/3 休止",
                    }

                    if "収集していません" in burn_raw:
                        rules["note"] = "収集していません"
                    else:
                        burn_days = parse_clean_days(burn_raw)
                        res_days = parse_clean_days(res_raw)
                        pla_days = parse_clean_days(pla_raw)

                        met_weeks = None
                        met_days = []
                        if met_raw:
                            nums = re.findall(r"\d+", unicodedata.normalize("NFKC", met_raw))
                            if nums:
                                met_weeks = [int(x) for x in nums]
                                met_days = ["水"]

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
                        "rules": rules,
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
