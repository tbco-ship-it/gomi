#!/usr/bin/env python3
"""
Normalize Niigata City (新潟市) Garbage Collection Schedule
----------------------------------------------------------
Official Source: 新潟市 家庭ごみ収集カレンダー / Webスケジュール
- 8 Wards: 北区(kita), 東区(higashi), 中央区(chuo), 江南区(konan),
           秋葉区(akiha), 南区(minami), 西区(nishi), 西蒲区(nishikan)
Output: data/wip/niigata.json -> data/normalized/niigata.json
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
RAW_DIR = os.path.join(BASE_DIR, "data", "raw", "niigata")
WIP_DIR = os.path.join(BASE_DIR, "data", "wip")
NORM_DIR = os.path.join(BASE_DIR, "data", "normalized")

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(WIP_DIR, exist_ok=True)
os.makedirs(NORM_DIR, exist_ok=True)

BASE_URL = "https://www.city.niigata.lg.jp/kurashi/gomi/gomishigen/gomidasi/gomi_calemder/"
TODAY_STR = "2026-09-17"

WARDS = [
    ("北区", "kita", "kita.html"),
    ("東区", "higashi", "higasi.html"),
    ("中央区", "chuo", "tyuou.html"),
    ("江南区", "konan", "kounan.html"),
    ("秋葉区", "akiha", "akiha.html"),
    ("南区", "minami", "minami.html"),
    ("西区", "nishi", "nisi.html"),
    ("西蒲区", "nishikan", "nisikan.html"),
]

kakasi = pykakasi.kakasi()


def to_romaji(text: str) -> str:
    res = kakasi.convert(text)
    romaji = "".join([x.get("passport") or x.get("hepburn", "") for x in res]).lower()
    return re.sub(r"[^a-z0-9]+", "-", romaji).strip("-")


def parse_schedule_str(sched_text: str):
    """Parses '毎週 火曜・木曜・土曜' or '毎月 第2・第4金曜' into (days, weeks)"""
    if not sched_text:
        return [], None

    weeks = None
    week_nums = []
    for m in re.finditer(r"第([1-5])", sched_text):
        week_nums.append(int(m.group(1)))
    if week_nums:
        weeks = sorted(list(set(week_nums)))

    days = []
    for m in re.finditer(r"([月火水木金土日])曜", sched_text):
        d = m.group(1)
        if d in "月火水木金土日" and d not in days:
            days.append(d)

    return days, weeks


def fetch_cached(url: str, fname: str) -> str:
    path = os.path.join(RAW_DIR, fname)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    resp.encoding = "utf-8"
    text = resp.text
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return text


def parse_schedule_page(url: str, fname: str) -> dict:
    """Parses schedule page and extracts standard waste types"""
    html_text = fetch_cached(url, fname)
    soup = bs4.BeautifulSoup(html_text, "html.parser")

    res = {}
    for tr in soup.find_all("tr"):
        tds = [td.text.strip().replace("\n", " ") for td in tr.find_all(["th", "td"])]
        if len(tds) != 2 or tds[0] == "分類":
            continue

        item_name = unicodedata.normalize("NFKC", tds[0])
        sched_text = unicodedata.normalize("NFKC", tds[1])

        days, weeks = parse_schedule_str(sched_text)

        if "燃やすごみ" in item_name:
            if days:
                res["burnable"] = {"label": "燃やすごみ", "days": days, "weeks": weeks, "time": None}
        elif "燃やさないごみ" in item_name:
            if days:
                res["nonburnable"] = {"label": "燃やさないごみ", "days": days, "weeks": weeks, "time": None}
        elif "プラマーク容器包装" in item_name:
            if days:
                res["plastic"] = {"label": "プラマーク容器包装", "days": days, "weeks": weeks, "time": None}
        elif "古紙" in item_name:
            if days:
                res["paper_cloth"] = {"label": "古紙", "days": days, "weeks": weeks, "time": None}
        elif "びん" in item_name or "缶" in item_name:
            if days and "resource" not in res:
                res["resource"] = {"label": "びん・缶", "days": days, "weeks": weeks, "time": None}
        elif "粗大ごみ" in item_name:
            res["bulky"] = {"label": "粗大ごみ", "days": [], "weeks": None, "time": None, "note": "事前申込制"}

    return res


def split_raw_town(raw_town: str):
    """
    Splits complex raw_town strings into individual town items:
    - Splits by comma '、' and middle dot '・' when not inside parentheses
    - Resolves pure numbers in Kameda ward into '亀田X区'
    - Separates chome (e.g. 1～3丁目) and sub-regions
    """
    s = unicodedata.normalize("NFKC", raw_town).strip()

    if "広域農道" in s and "西側" in s:
        return [("巻", None, s)]
    if "旧国道116号線" in s and "東側" in s:
        return [("巻", None, s)]

    items = []
    current = []
    paren_depth = 0
    for char in s:
        if char in "（(":
            paren_depth += 1
            current.append(char)
        elif char in "）)":
            paren_depth = max(0, paren_depth - 1)
            current.append(char)
        elif (char in "、・") and paren_depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
        else:
            current.append(char)
    last_item = "".join(current).strip()
    if last_item:
        items.append(last_item)

    results = []
    for item in items:
        # Check pure digits
        if re.match(r"^\d+$", item):
            results.append((f"亀田{item}区", None, None))
            continue

        sub = None
        m_paren = re.search(r"[\(（](.*?)[\)）]", item)
        if m_paren:
            sub = m_paren.group(1).strip()
            item = re.sub(r"[\(（].*?[\)）]", "", item).strip()

        m_chome = re.search(r"([0-9０-９一二三四五六七八九十]+(?:[~～\-][0-9０-９一二三四五六七八九十]+)?(?:丁目|番町))", item)
        chome = None
        if m_chome:
            chome = m_chome.group(1)
            town = item[:m_chome.start()].strip()
            rem = item[m_chome.end():].strip()
            if rem:
                sub = f"{rem} {sub}".strip() if sub else rem
        else:
            town = item

        if not town and chome:
            town = chome
            chome = None

        results.append((town, chome, sub))
    return results


def main():
    records = []
    slug_counts = {}

    for w_ja, w_en, page in WARDS:
        ward_url = urllib.parse.urljoin(BASE_URL, page)
        html_text = fetch_cached(ward_url, f"ward_{w_en}.html")
        soup = bs4.BeautifulSoup(html_text, "html.parser")

        for t in soup.find_all("table"):
            for tr in t.find_all("tr"):
                cells = tr.find_all(["th", "td"])
                if not cells:
                    continue

                texts = [unicodedata.normalize("NFKC", c.text.strip().replace("\n", " ")) for c in cells]

                # Distinguish 4-column tables vs 3-column tables
                if len(cells) == 4:
                    raw_town = texts[1]
                    link_cell = cells[3]
                elif len(cells) == 3:
                    raw_town = texts[0]
                    link_cell = cells[2]
                else:
                    continue

                # Skip header rows
                if any(h in raw_town for h in ["町名", "自治会名", "自治町内会区分", "地域", "分類"]):
                    continue
                if not raw_town:
                    continue

                sched_links = []
                for a in link_cell.find_all("a"):
                    href = a.get("href", "")
                    if "schedule" in href or "haitai" in href or ".html" in href:
                        cal_no = a.text.strip()
                        full_url = urllib.parse.urljoin(ward_url, href)
                        sched_links.append((cal_no, full_url))

                # If no schedule links found in link_cell, fallback to whole tr
                if not sched_links:
                    for a in tr.find_all("a"):
                        href = a.get("href", "")
                        if "schedule" in href:
                            cal_no = a.text.strip()
                            full_url = urllib.parse.urljoin(ward_url, href)
                            sched_links.append((cal_no, full_url))

                if not sched_links:
                    continue

                town_items = split_raw_town(raw_town)

                for town, chome, sub in town_items:
                    if not town:
                        continue

                    town_romaji = to_romaji(town) or "town"

                    for cal_no, sched_url in sched_links:
                        cal_fname = f"sched_{re.sub(r'[^a-zA-Z0-9]', '_', sched_url.split('/')[-1])}"
                        types = parse_schedule_page(sched_url, cal_fname)

                        sub_parts = []
                        if sub:
                            sub_parts.append(sub)
                        if len(sched_links) > 1 and cal_no:
                            sub_parts.append(f"カレンダー{cal_no}")
                        entry_sub = " ".join(sub_parts) if sub_parts else None

                        slug_parts = ["niigata", w_en, town_romaji]
                        if chome:
                            nums = "".join(re.findall(r"\d+", unicodedata.normalize("NFKC", chome)))
                            slug_parts.append(f"{nums}chome" if nums else to_romaji(chome))
                        if entry_sub:
                            s_r = to_romaji(entry_sub)
                            if s_r:
                                slug_parts.append(s_r[:20])

                        base_slug = "/".join(slug_parts)
                        base_slug = re.sub(r"-+", "-", base_slug).strip("-")
                        base_slug = re.sub(r"/+", "/", base_slug).lower()

                        cnt = slug_counts.get(base_slug, 0) + 1
                        slug_counts[base_slug] = cnt
                        slug = base_slug if cnt == 1 else f"{base_slug}-{cnt}"

                        rec = {
                            "pref": "新潟県",
                            "city": "新潟市",
                            "city_en": "niigata",
                            "ward": w_ja,
                            "ward_en": w_en,
                            "town": town,
                            "chome": chome,
                            "sub": entry_sub,
                            "romaji": town_romaji,
                            "slug": slug,
                            "types": types,
                            "rules": {
                                "holiday_collection": "祝日も収集（年末年始除く）",
                                "time_by": "8:00",
                                "yearend": "12/31~1/3 休止",
                                "calendar_no": cal_no,
                            },
                            "source": {
                                "url": sched_url,
                                "fetched": TODAY_STR,
                                "basis": "official_html",
                            },
                            "raw": {
                                "raw_town": raw_town,
                                "calendar_no": cal_no,
                                "schedule_url": sched_url,
                            },
                        }
                        records.append(rec)

    wip_file = os.path.join(WIP_DIR, "niigata.json")
    with open(wip_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"[✔] Generated {len(records)} records for Niigata -> {wip_file}")


if __name__ == "__main__":
    main()
