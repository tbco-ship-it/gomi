#!/usr/bin/env python3
"""
Normalize Sakai City (堺市) Garbage Collection Schedule
-------------------------------------------------------
Official Source: 堺市役所 町名別の収集曜日一覧 (HTML tables)
- 7 Wards: 堺区(sakai), 中区(naka), 東区(higashi), 西区(nishi),
           南区(minami), 北区(kita), 美原区(mihara)
Output: data/wip/sakai.json -> data/normalized/sakai.json
"""

import json
import os
import re
import sys
import unicodedata
import urllib.parse
import bs4
import pykakasi
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw", "sakai")
WIP_DIR = os.path.join(BASE_DIR, "data", "wip")
NORM_DIR = os.path.join(BASE_DIR, "data", "normalized")

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(WIP_DIR, exist_ok=True)
os.makedirs(NORM_DIR, exist_ok=True)

BASE_URL = "https://www.city.sakai.lg.jp/kurashi/gomi/gomi_recy/bunbetsu/chomeiichiran/"
TODAY_STR = "2026-09-17"

WARDS = [
    ("堺区", "sakai", "youbiichirannsakaikubann.html"),
    ("中区", "naka", "nakakkushuushuuyoubi.html"),
    ("東区", "higashi", "youbiichirannhigashikubann.html"),
    ("西区", "nishi", "nishi.html"),
    ("南区", "minami", "youbiichirannminami.html"),
    ("北区", "kita", "youbiichirannkita.html"),
    ("美原区", "mihara", "youbiichirannmihara.html"),
]

kakasi = pykakasi.kakasi()


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return re.sub(r"[^a-z0-9]+", "-", romaji).strip("-")


def parse_schedule_cell(val: str):
    """Parses '月曜日・木曜日', '2･4回目水曜日', '2回目木曜日' into (days, weeks)"""
    if not val or val == "-" or "※" in val:
        return [], None

    s = unicodedata.normalize("NFKC", val).strip()

    weeks = None
    if "1・3" in s or "1･3" in s:
        weeks = [1, 3]
    elif "2・4" in s or "2･4" in s:
        weeks = [2, 4]
    else:
        m_single = re.search(r"([1-5])回目", s)
        if m_single:
            weeks = [int(m_single.group(1))]

    days = []
    for m in re.finditer(r"([月火水木金土日])曜", s):
        d = m.group(1)
        if d not in days:
            days.append(d)

    return days, weeks


def split_town_name(raw_town: str):
    s = unicodedata.normalize("NFKC", raw_town).strip()
    sub_paren = ""
    m_paren = re.search(r"[\(（](.*?)[\)）]", s)
    if m_paren:
        sub_paren = m_paren.group(1).strip()
        s_clean = re.sub(r"[\(（].*?[\)）]", "", s).strip()
    else:
        s_clean = s

    # Split town name from digit-based chome or banchi ranges
    m_digit = re.search(r"\d", s_clean)
    if m_digit:
        town = s_clean[:m_digit.start()].strip()
        rest = s_clean[m_digit.start():].strip()
    else:
        town = s_clean
        rest = ""

    chome = None
    sub_parts = []

    if rest:
        # Check if rest starts with chome pattern (e.g. 1から8丁, 9丁..., 1から5街区)
        m_cho = re.match(r"^(\d+(?:から\d+|[~～\-]\d+)?(?:丁|丁目|街区))(.*)$", rest)
        if m_cho:
            chome = m_cho.group(1)
            rem = m_cho.group(2).strip()
            if rem:
                sub_parts.append(rem.lstrip("、").strip())
        else:
            sub_parts.append(rest)

    if sub_paren:
        sub_parts.append(sub_paren)

    sub = " ".join(sub_parts).strip() if sub_parts else None
    return town, chome, sub


def fetch_html(url: str, fname: str) -> str:
    path = os.path.join(RAW_DIR, fname)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    text = resp.text
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return text


def main():
    records = []
    slug_counts = {}

    for w_ja, w_en, page in WARDS:
        url = urllib.parse.urljoin(BASE_URL, page)
        html_text = fetch_html(url, f"{w_en}.html")
        soup = bs4.BeautifulSoup(html_text, "html.parser")

        for t in soup.find_all("table"):
            for tr in t.find_all("tr"):
                tds = [unicodedata.normalize("NFKC", td.text.strip().replace("\n", " ")) for td in tr.find_all(["th", "td"])]
                if len(tds) < 6 or tds[0] == "町名" or "生活ごみ" in tds:
                    continue

                if len(tds) == 7:
                    raw_town = tds[1]
                    scheds = tds[2:]
                elif len(tds) == 6:
                    raw_town = tds[0]
                    scheds = tds[1:]
                else:
                    continue

                # scheds: [生活ごみ, 缶・びん, ペットボトル, プラ容器包装, 小型金属]
                town, chome, sub = split_town_name(raw_town)
                town_romaji = to_romaji(town) or "town"

                types = {}

                # 1. 生活ごみ (burnable)
                if len(scheds) > 0:
                    b_days, b_weeks = parse_schedule_cell(scheds[0])
                    if b_days:
                        types["burnable"] = {"label": "生活ごみ", "days": b_days, "weeks": b_weeks, "time": None}

                # 2. 缶・びん (resource)
                if len(scheds) > 1:
                    r_days, r_weeks = parse_schedule_cell(scheds[1])
                    if r_days:
                        types["resource"] = {"label": "缶・びん", "days": r_days, "weeks": r_weeks, "time": None}

                # 3. プラ容器包装 (plastic)
                if len(scheds) > 3:
                    p_days, p_weeks = parse_schedule_cell(scheds[3])
                    if p_days:
                        types["plastic"] = {"label": "プラ容器包装", "days": p_days, "weeks": p_weeks, "time": None}

                # 4. 小型金属 (nonburnable)
                if len(scheds) > 4:
                    nb_days, nb_weeks = parse_schedule_cell(scheds[4])
                    if nb_days:
                        types["nonburnable"] = {"label": "小型金属", "days": nb_days, "weeks": nb_weeks, "time": None}

                slug_parts = ["sakai", w_en, town_romaji]
                if chome:
                    nums = "".join(re.findall(r"\d+", chome))
                    slug_parts.append(f"{nums}cho" if nums else to_romaji(chome))
                if sub:
                    sub_r = to_romaji(sub)
                    if sub_r:
                        slug_parts.append(sub_r[:20])

                base_slug = "/".join(slug_parts)
                base_slug = re.sub(r"-+", "-", base_slug).strip("-")
                base_slug = re.sub(r"/+", "/", base_slug).lower()

                cnt = slug_counts.get(base_slug, 0) + 1
                slug_counts[base_slug] = cnt
                slug = base_slug if cnt == 1 else f"{base_slug}-{cnt}"

                rec = {
                    "pref": "大阪府",
                    "city": "堺市",
                    "city_en": "sakai",
                    "ward": w_ja,
                    "ward_en": w_en,
                    "town": town,
                    "chome": chome,
                    "sub": sub,
                    "romaji": town_romaji,
                    "slug": slug,
                    "types": types,
                    "rules": {
                        "holiday_collection": "祝日も収集（年末年始除く）",
                        "time_by": "朝",
                        "yearend": "12/31~1/3 休止",
                        "pet_bottle_schedule": scheds[2] if len(scheds) > 2 else None,
                    },
                    "source": {
                        "url": url,
                        "fetched": TODAY_STR,
                        "basis": "official_html",
                    },
                    "raw": {
                        "raw_town": raw_town,
                        "burnable": scheds[0] if len(scheds) > 0 else "",
                        "can_bin": scheds[1] if len(scheds) > 1 else "",
                        "pet_bottle": scheds[2] if len(scheds) > 2 else "",
                        "plastic": scheds[3] if len(scheds) > 3 else "",
                        "metal": scheds[4] if len(scheds) > 4 else "",
                    },
                }
                records.append(rec)

    wip_file = os.path.join(WIP_DIR, "sakai.json")
    with open(wip_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"[✔] Generated {len(records)} records for Sakai -> {wip_file}")


if __name__ == "__main__":
    main()
