#!/usr/bin/env python3
"""
Normalize Saitama City (さいたま市) Garbage Collection Schedule
--------------------------------------------------------------
Reads official Saitama gomisuke system data:
Sources:
- https://admin.gomisuke.jp/app/0017/api/jsonp.php?file=area
- https://admin.gomisuke.jp/app/0017/api/jsonp.php?file=type
- https://admin.gomisuke.jp/app/0017/api/jsonp.php?file=calendar
Raw cache: data/raw/saitama/
Output: data/normalized/saitama.json

Rules:
- 10 Wards: 西区(nishi), 北区(kita), 大宮区(omiya), 見沼区(minuma),
  中央区(chuo), 桜区(sakura), 浦和区(urawa), 南区(minami),
  緑区(midori), 岩槻区(iwatsuki)
- 6 standard keys: burnable, resource, plastic, paper_cloth, nonburnable
- Zero duplicate slugs via pykakasi
- source.fetched: 2026-09-17
"""

import datetime
import json
import os
import re
import sys
import unicodedata
import urllib.request
from typing import Dict, List, Any, Set, Tuple
import pykakasi

AREA_URL = "https://admin.gomisuke.jp/app/0017/api/jsonp.php?file=area"
CALENDAR_URL = "https://admin.gomisuke.jp/app/0017/api/jsonp.php?file=calendar"
TYPE_URL = "https://admin.gomisuke.jp/app/0017/api/jsonp.php?file=type"

VALID_DAYS = {"月", "火", "水", "木", "金", "土", "日"}
TODAY_STR = "2026-09-17"

WARD_ROMAJI = {
    "西区": "nishi",
    "北区": "kita",
    "大宮区": "omiya",
    "見沼区": "minuma",
    "中央区": "chuo",
    "桜区": "sakura",
    "浦和区": "urawa",
    "南区": "minami",
    "緑区": "midori",
    "岩槻区": "iwatsuki",
}

DAYS_MAP = {0: "月", 1: "火", 2: "水", 3: "木", 4: "金", 5: "土", 6: "日"}

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


def parse_jsonp(text: str) -> Any:
    m = re.search(r"gomisukeGetData\([^\,]+,\s*(.*)\);?$", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    return None


def fetch_or_cache(url: str, cache_file: str) -> str:
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 0:
        with open(cache_file, "r", encoding="utf-8") as f:
            return f.read()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        content = resp.read().decode("utf-8")
    with open(cache_file, "w", encoding="utf-8") as f:
        f.write(content)
    return content


def split_town_string(raw_town: str) -> Tuple[str, str, str]:
    """Splits raw town into (town, chome, sub)"""
    s = unicodedata.normalize("NFKC", raw_town).strip()
    s = re.sub(r"^★", "", s) # remove marker

    sub = ""
    m_paren = re.search(r"[\(（](.*?)[\)）]", s)
    if m_paren:
        sub = m_paren.group(1).strip()
        s = re.sub(r"[\(（].*?[\)）]", "", s).strip()

    # Split chome or range: e.g. "内野本郷", "三橋6丁目", "大戸1~6丁目", "加倉1564-1~1596-3"
    m_chome = re.search(r"([0-9～~・\-]+丁目)", s)
    if m_chome:
        chome = m_chome.group(1)
        town = s.replace(chome, "").strip()
        return town, chome, sub

    # If range without 丁目, e.g. "加倉1564-1～1596-3"
    m_range = re.search(r"(\d+.*)$", s)
    if m_range and not s.endswith("町") and not s.endswith("村"):
        # has number suffix
        num_part = m_range.group(1)
        town = s[:m_range.start()].strip()
        return town, "", f"{num_part} {sub}".strip()

    return s, "", sub


def compute_area_schedules(cal_data: dict) -> Dict[str, Dict[str, List[str]]]:
    """Calculates weekly collection days for each type per area."""
    area_sched: Dict[str, Dict[str, Set[str]]] = {}
    
    # We examine dates in 202605 (May 2026, regular standard schedule)
    for ym_item in cal_data["array"]["dict"]:
        if ym_item["string"] == "202605":
            year, month = 2026, 5
            for a in ym_item["array"]["dict"]:
                area_id = a["string"]
                d_dict = a["dict"]
                for day_str, type_str in zip(d_dict["key"], d_dict["string"]):
                    dt = datetime.date(year, month, int(day_str))
                    dow = DAYS_MAP[dt.weekday()]
                    for t_id in type_str.split(","):
                        if t_id != "15": # 15 = closed
                            area_sched.setdefault(area_id, {}).setdefault(t_id, set()).add(dow)
            break

    # Convert sets to sorted lists
    # Standard Saitama weekday order: 月, 火, 水, 木, 金, 土
    dow_order = {"月": 1, "火": 2, "水": 3, "木": 4, "金": 5, "土": 6, "日": 7}
    res = {}
    for a_id, t_dict in area_sched.items():
        res[a_id] = {}
        for t_id, d_set in t_dict.items():
            res[a_id][t_id] = sorted(list(d_set), key=lambda d: dow_order.get(d, 99))
    return res


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_dir = os.path.join(base_dir, "data", "raw", "saitama")
    out_file = os.path.join(base_dir, "data", "normalized", "saitama.json")
    os.makedirs(raw_dir, exist_ok=True)

    area_raw = fetch_or_cache(AREA_URL, os.path.join(raw_dir, "area.jsonp"))
    cal_raw = fetch_or_cache(CALENDAR_URL, os.path.join(raw_dir, "calendar.jsonp"))

    area_data = parse_jsonp(area_raw)
    cal_data = parse_jsonp(cal_raw)

    area_schedules = compute_area_schedules(cal_data)

    all_normalized = []
    used_slugs: Set[str] = set()

    for item_dict in area_data["array"]["dict"]:
        item = dict(zip(item_dict["key"], item_dict["string"]))
        area_id = item["areaID"]
        full_name = item["name"]

        m_ward = re.match(r"【(.*?)】::(.*)", full_name)
        if not m_ward:
            continue

        ward_name = m_ward.group(1)
        ward_en = WARD_ROMAJI.get(ward_name, to_romaji(ward_name))
        towns_str = m_ward.group(2)

        town_entries = [t.strip() for t in towns_str.split("、") if t.strip()]
        a_sched = area_schedules.get(area_id, {})

        # Build waste types for this area
        types: Dict[str, Any] = {}
        # 1: もえるごみ -> burnable
        if "1" in a_sched:
            types["burnable"] = {
                "label": "もえるごみ",
                "days": a_sched["1"],
                "weeks": None,
                "time": "朝8:30まで",
            }
        # 2: もえないごみ -> nonburnable
        if "2" in a_sched:
            types["nonburnable"] = {
                "label": "もえないごみ",
                "days": a_sched["2"],
                "weeks": None,
                "time": "朝8:30まで",
            }
        # 6, 7: びん, かん -> resource
        res_days = set()
        if "6" in a_sched: res_days.update(a_sched["6"])
        if "7" in a_sched: res_days.update(a_sched["7"])
        if res_days:
            dow_order = {"月": 1, "火": 2, "水": 3, "木": 4, "金": 5, "土": 6, "日": 7}
            types["resource"] = {
                "label": "びん・かん",
                "days": sorted(list(res_days), key=lambda d: dow_order.get(d, 99)),
                "weeks": None,
                "time": "朝8:30まで",
            }
        # 8, 9: ペットボトル, 容器包装プラスチック -> plastic
        pla_days = set()
        if "8" in a_sched: pla_days.update(a_sched["8"])
        if "9" in a_sched: pla_days.update(a_sched["9"])
        if pla_days:
            dow_order = {"月": 1, "火": 2, "水": 3, "木": 4, "金": 5, "土": 6, "日": 7}
            types["plastic"] = {
                "label": "ペットボトル・容器包装プラスチック",
                "days": sorted(list(pla_days), key=lambda d: dow_order.get(d, 99)),
                "weeks": None,
                "time": "朝8:30まで",
            }
        # 4, 5: 古紙類, 繊維 -> paper_cloth
        pap_days = set()
        if "4" in a_sched: pap_days.update(a_sched["4"])
        if "5" in a_sched: pap_days.update(a_sched["5"])
        if pap_days:
            dow_order = {"月": 1, "火": 2, "水": 3, "木": 4, "金": 5, "土": 6, "日": 7}
            types["paper_cloth"] = {
                "label": "古紙類・繊維",
                "days": sorted(list(pap_days), key=lambda d: dow_order.get(d, 99)),
                "weeks": None,
                "time": "朝8:30まで",
            }

        for raw_t in town_entries:
            town, chome, sub = split_town_string(raw_t)
            t_romaji = to_romaji(town)
            if not t_romaji:
                t_romaji = "town"

            chome_num = extract_nums(chome)
            sub_clean = unicodedata.normalize("NFKC", sub).strip()

            slug_base = f"saitama/{ward_en}/{t_romaji}"
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
                "pref": "埼玉県",
                "city": "さいたま市",
                "city_en": "saitama",
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
                    "time_by": "8:30",
                    "yearend": "12/31~1/3 休止",
                },
                "source": {
                    "url": "https://www.city.saitama.lg.jp/001/006/010/003/p042612.html",
                    "fetched": TODAY_STR,
                    "basis": "official_html",
                },
                "notes": f"地区パターン: {area_id}",
                "raw": {
                    "areaID": area_id,
                    "raw_entry": raw_t,
                    "area_name": full_name,
                },
            }
            all_normalized.append(record)

    print(f"[+] Total normalized Saitama records: {len(all_normalized)}")
    print(f"[+] Unique slugs: {len(used_slugs)}")

    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_normalized, f, ensure_ascii=False, indent=2)

    print(f"[✔] Wrote to {out_file}")


if __name__ == "__main__":
    main()
