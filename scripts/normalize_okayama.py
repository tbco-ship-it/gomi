#!/usr/bin/env python3
"""
Normalize Okayama City (岡山市) Garbage Collection Schedule
----------------------------------------------------------
Official Source: 岡山市役所 収集曜日一覧表 (kintone API / official JSON)
URL: https://f5d44204.viewer.kintoneapp.com/public/bba750ccc0622ed0ea1ee9803b60537753367b11af275de1ad0d1507c414d779
Raw cache: data/raw/okayama/okayama_raw.json
Output: data/wip/okayama.json -> data/normalized/okayama.json
"""

import json
import os
import re
import sys
import unicodedata
import collections
import pykakasi

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_PATH = os.path.join(BASE_DIR, "data", "raw", "okayama", "okayama_raw.json")
WIP_DIR = os.path.join(BASE_DIR, "data", "wip")
NORM_DIR = os.path.join(BASE_DIR, "data", "normalized")

os.makedirs(WIP_DIR, exist_ok=True)
os.makedirs(NORM_DIR, exist_ok=True)

SOURCE_URL = "https://f5d44204.viewer.kintoneapp.com/public/bba750ccc0622ed0ea1ee9803b60537753367b11af275de1ad0d1507c414d779"
TODAY_STR = "2026-09-17"

WARD_EN = {
    "北区": "kita",
    "中区": "naka",
    "東区": "higashi",
    "南区": "minami",
}

EXTRA_SCHOOLS = {
    "高田": "中区",
    "太伯": "東区",
    "東畦": "南区",
    "朝日": "東区",
    "福谷": "北区",
    "大宮": "北区",
    "大井": "北区",
    "幸島": "東区",
}

kakasi = pykakasi.kakasi()


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return re.sub(r"[^a-z0-9]+", "-", romaji).strip("-")


def parse_schedule_str(sched_raw: str):
    """Parses Okayama schedule string like '１水', '１．３木', '月・木', '１月・３木' into (days, weeks)"""
    if not sched_raw:
        return [], None

    s = unicodedata.normalize("NFKC", str(sched_raw)).strip()

    # Extract weeks
    week_nums = []
    for m in re.finditer(r"([1-5])", s):
        w = int(m.group(1))
        if w not in week_nums:
            week_nums.append(w)
    weeks = sorted(week_nums) if week_nums else None

    # Extract days
    days = []
    for m in re.finditer(r"([月火水木金土日])", s):
        d = m.group(1)
        if d in "月火水木金土日" and d not in days:
            days.append(d)

    return days, weeks


def split_town_name(raw_town: str):
    s = unicodedata.normalize("NFKC", raw_town).strip()
    sub = ""
    m_paren = re.search(r"[\(（](.*?)[\)）]", s)
    if m_paren:
        sub = m_paren.group(1).strip()
        s = re.sub(r"[\(（].*?[\)）]", "", s).strip()

    m_chome = re.search(r"([0-9０-９一二三四五六七八九十]+(?:[~～\-]+[0-9０-９一二三四五六七八九十]+)?(?:丁目))", s)
    chome = ""
    if m_chome:
        chome = m_chome.group(1)
        town = s[:m_chome.start()].strip()
        rem = s[m_chome.end():].strip()
        if rem:
            sub = f"{rem} {sub}".strip()
    else:
        town = s

    return town, chome if chome else None, sub if sub else None


def get_ward_mapping():
    school_to_ward = {
        "岡山中央": "北区", "清輝": "北区", "伊島": "北区", "津島": "北区", "石井": "北区",
        "鹿田": "北区", "大元": "北区", "御野": "北区", "岡南": "北区", "牧石": "北区",
        "御津": "北区", "御津南": "北区", "五城": "北区", "建部": "北区", "竹枝": "北区",
        "福渡": "北区", "足守": "北区", "福谷": "北区", "高松": "北区", "加茂": "北区",
        "庄内": "北区", "鯉山": "北区", "生石": "北区", "吉備": "北区", "陵南": "北区",
        "御南": "北区", "西": "北区", "三門": "北区", "大野": "北区", "大井": "北区",
        "大宮": "北区", "馬屋上": "北区", "馬屋下": "北区", "桃丘": "北区", "平津": "北区",
        "野谷": "北区", "横井": "北区", "中山": "北区",
        "三勲": "中区", "宇野": "中区", "平井": "中区", "操南": "中区", "操明": "中区",
        "富山": "中区", "財田": "中区", "幡多": "中区", "高島": "中区", "竜之口": "中区",
        "旭東": "中区", "旭操": "中区", "高田": "中区",
        "西大寺": "東区", "西大寺南": "東区", "雄神": "東区", "可知": "東区", "古都": "東区",
        "芥子山": "東区", "政田": "東区", "開成": "東区", "幸島": "東区", "朝日": "東区",
        "太伯": "東区", "幸島": "東区", "邑久": "東区", "上道": "東区", "城東": "東区",
        "浮田": "東区", "平島": "東区", "御休": "東区", "角山": "東区",
        "芳泉": "南区", "芳田": "南区", "芳明": "南区", "福浜": "南区", "平福": "南区",
        "福島": "南区", "南輝": "南区", "甲浦": "南区", "小串": "南区", "東畦": "南区",
        "興除": "南区", "妹尾": "南区", "箕島": "南区", "第一藤田": "南区", "第二藤田": "南区",
        "第三藤田": "南区", "灘崎": "南区", "彦崎": "南区", "七区": "南区", "浦安": "南区"
    }
    school_to_ward.update(EXTRA_SCHOOLS)
    return school_to_ward


def resolve_ward(school_name: str, school_map: dict) -> str:
    if not school_name:
        return "北区"
    if school_name in school_map:
        return school_map[school_name]
    parts = school_name.replace("･", "・").split("・")
    for p in parts:
        if p in school_map:
            return school_map[p]
    return "北区"


def clean_note(note_str: str):
    if not note_str:
        return "", None
    s = unicodedata.normalize("NFKC", str(note_str)).strip()
    time_by = None
    if "7時30分" in s:
        time_by = "7:30"
        s = re.sub(r"[\(（]朝?7時30分までにお出しください[。]?[\)）]", "", s).strip()
    s = s.strip("「」").strip()
    return s, time_by


def main():
    if not os.path.exists(RAW_PATH):
        print(f"[!] Error: {RAW_PATH} not found", file=sys.stderr)
        sys.exit(1)

    with open(RAW_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    school_map = get_ward_mapping()

    # Pre-process records to group and resolve ambiguous subdivisions
    intermediate = []
    for r in data:
        raw_town = (r.get("文字列__1行__0", {}).get("value") or "").strip()
        if not raw_town:
            continue

        school = (r.get("ドロップダウン_1", {}).get("value") or "").strip()
        burn_val = r.get("ドロップダウン_3", {}).get("value") or ""
        nonburn_val = r.get("ドロップダウン_4", {}).get("value") or ""
        res_val = r.get("ドロップダウン_6", {}).get("value") or ""
        pla_val = r.get("ドロップダウン_7", {}).get("value") or ""
        raw_note = (r.get("文字列__1行__1", {}).get("value") or "").strip()

        ward_ja = resolve_ward(school, school_map)
        ward_en = WARD_EN.get(ward_ja, "kita")

        town, chome, sub_raw = split_town_name(raw_town)
        note_clean, time_by = clean_note(raw_note)

        intermediate.append({
            "ward_ja": ward_ja,
            "ward_en": ward_en,
            "town": town,
            "chome": chome,
            "sub_raw": sub_raw,
            "school": school,
            "note_clean": note_clean,
            "raw_note": raw_note,
            "time_by": time_by or "8:00",
            "raw_town": raw_town,
            "burn_val": burn_val,
            "nonburn_val": nonburn_val,
            "res_val": res_val,
            "pla_val": pla_val,
        })

    # Group by (ward_ja, town, chome) to assign distinctive sub
    groups = collections.defaultdict(list)
    for item in intermediate:
        groups[(item["ward_ja"], item["town"], item["chome"])].append(item)

    for key, glist in groups.items():
        if len(glist) == 1:
            g = glist[0]
            g["sub"] = g["sub_raw"] or (g["note_clean"] if g["note_clean"] else None)
        else:
            for g in glist:
                parts = []
                if g["sub_raw"]:
                    parts.append(g["sub_raw"])
                if g["note_clean"]:
                    parts.append(g["note_clean"])
                elif g["school"]:
                    parts.append(g["school"] + "学区")
                g["sub"] = " ".join(parts) if parts else None

    records = []
    slug_counts = {}

    for item in intermediate:
        types = {}

        # 1. 可燃ごみ (burnable)
        b_days, b_weeks = parse_schedule_str(item["burn_val"])
        if b_days:
            types["burnable"] = {"label": "可燃ごみ", "days": b_days, "weeks": b_weeks, "time": None}

        # 2. 不燃ごみ (nonburnable)
        nb_days, nb_weeks = parse_schedule_str(item["nonburn_val"])
        if nb_days:
            types["nonburnable"] = {"label": "不燃ごみ", "days": nb_days, "weeks": nb_weeks, "time": None}

        # 3. 資源化物 (resource)
        r_days, r_weeks = parse_schedule_str(item["res_val"])
        if r_days:
            types["resource"] = {"label": "資源化物", "days": r_days, "weeks": r_weeks, "time": None}

        # 4. プラスチック資源 (plastic)
        p_days, p_weeks = parse_schedule_str(item["pla_val"])
        if p_days:
            types["plastic"] = {"label": "プラスチック資源", "days": p_days, "weeks": p_weeks, "time": None}

        town = item["town"]
        chome = item["chome"]
        sub = item["sub"]
        ward_en = item["ward_en"]

        town_romaji = to_romaji(town) or "town"
        slug_parts = ["okayama", ward_en, town_romaji]
        if chome:
            nums = "".join(re.findall(r"\d+", unicodedata.normalize("NFKC", chome)))
            slug_parts.append(f"{nums}chome" if nums else to_romaji(chome))
        if sub:
            sub_r = to_romaji(sub)
            if sub_r:
                slug_parts.append(sub_r[:25])

        base_slug = "/".join(slug_parts)
        base_slug = re.sub(r"-+", "-", base_slug).strip("-")
        base_slug = re.sub(r"/+", "/", base_slug).lower()

        cnt = slug_counts.get(base_slug, 0) + 1
        slug_counts[base_slug] = cnt
        slug = base_slug if cnt == 1 else f"{base_slug}-{cnt}"

        rec = {
            "pref": "岡山県",
            "city": "岡山市",
            "city_en": "okayama",
            "ward": item["ward_ja"],
            "ward_en": ward_en,
            "town": town,
            "chome": chome,
            "sub": sub,
            "romaji": town_romaji,
            "slug": slug,
            "types": types,
            "rules": {
                "holiday_collection": "祝日も収集（年末年始除く）",
                "time_by": item["time_by"],
                "yearend": "12/31~1/3 休止",
                "elementary_school": item["school"] if item["school"] else None,
                "note": item["raw_note"] if item["raw_note"] else None,
            },
            "source": {
                "url": SOURCE_URL,
                "fetched": TODAY_STR,
                "basis": "official_html",
            },
            "raw": {
                "town": item["raw_town"],
                "school": item["school"],
                "burnable": item["burn_val"],
                "nonburnable": item["nonburn_val"],
                "resource": item["res_val"],
                "plastic": item["pla_val"],
                "note": item["raw_note"],
            },
        }
        records.append(rec)

    wip_file = os.path.join(WIP_DIR, "okayama.json")
    with open(wip_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"[✔] Generated {len(records)} records for Okayama -> {wip_file}")


if __name__ == "__main__":
    main()
