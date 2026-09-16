#!/usr/bin/env python3
"""
Normalize Ota Ward (大田区) Garbage Collection Schedule
------------------------------------------------------
Reads official Ota City collection schedule PDF:
Source: https://www.city.ota.tokyo.jp/seikatsu/gomi/shigentogomi/gomishigen.files/shuushuuyoubi.pdf
Raw cache: data/raw/ota/shuushuuyoubi.pdf
Output: data/normalized/ota.json

Rules:
- Tokyo 23 Ward: pref: 東京都, city: 大田区, city_en: ota, ward: ""
- 6 standard keys: burnable, resource, plastic, paper_cloth, nonburnable, bulky
- pykakasi slug with 0 duplicates
- source.fetched: 2026-09-17
"""

import json
import os
import re
import sys
import unicodedata
import urllib.request
from typing import Dict, List, Any, Set, Tuple
import pdfplumber
import pykakasi

PDF_URL = "https://www.city.ota.tokyo.jp/seikatsu/gomi/shigentogomi/gomishigen.files/shuushuuyoubi.pdf"
TODAY_STR = "2026-09-17"
VALID_DAYS = {"月", "火", "水", "木", "金", "土", "日"}

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
    """Parse days from text like '月・木' or '火'."""
    if not val:
        return []
    val_norm = unicodedata.normalize("NFKC", val)
    days = []
    for ch in val_norm:
        if ch in VALID_DAYS and ch not in days:
            days.append(ch)
    return days


def parse_nonburn(val: str) -> Tuple[List[int], List[str]]:
    """Parse nonburn text like '2・4 金' into ([2, 4], ['金'])."""
    if not val:
        return [], []
    val_norm = unicodedata.normalize("NFKC", val)
    days = [ch for ch in val_norm if ch in VALID_DAYS]
    nums = re.findall(r"\d+", val_norm)
    weeks = [int(x) for x in nums if int(x) in [1, 2, 3, 4, 5]]
    return weeks, days


def download_ota_pdf(raw_dir: str) -> str:
    os.makedirs(raw_dir, exist_ok=True)
    pdf_path = os.path.join(raw_dir, "shuushuuyoubi.pdf")
    if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) == 0:
        print(f"[*] Downloading Ota PDF from {PDF_URL}...")
        req = urllib.request.Request(PDF_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            with open(pdf_path, "wb") as f:
                f.write(data)
        print(f"[+] Downloaded Ota PDF ({os.path.getsize(pdf_path)} bytes)")
    return pdf_path


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_dir = os.path.join(base_dir, "data", "raw", "ota")
    out_file = os.path.join(base_dir, "data", "normalized", "ota.json")

    pdf_path = download_ota_pdf(raw_dir)

    all_normalized = []
    used_slugs: Set[str] = set()

    with pdfplumber.open(pdf_path) as pdf:
        last_town = ""
        last_pla = ""
        last_res = ""
        last_burn = ""
        last_nonburn = ""
        last_office = ""

        for p_idx, page in enumerate(pdf.pages):
            table = page.extract_table()
            if not table:
                continue

            for r_idx, r in enumerate(table):
                r_norm = [unicodedata.normalize("NFKC", x).strip() if x else "" for x in r]
                if not r_norm or "集積所" in r_norm[0]:
                    continue

                raw_town = (r_norm[1] + r_norm[2]).replace(" ", "")
                if raw_town:
                    last_town = raw_town
                    # Reset nonburn when new town appears, unless row provides it
                    last_nonburn = ""
                town = last_town

                chome_raw = r_norm[3]
                pla = r_norm[4]
                res = r_norm[5] or (r_norm[6] if len(r_norm) > 6 else "")
                burn = r_norm[7] if len(r_norm) > 7 else ""
                nonburn = (r_norm[8] if len(r_norm) > 8 else "") or (r_norm[9] if len(r_norm) > 9 else "")
                office = (r_norm[10] if len(r_norm) > 10 else "") + (r_norm[11] if len(r_norm) > 11 else "")
                office = office.replace(" ", "")

                if pla:
                    last_pla = pla
                else:
                    pla = last_pla

                if res:
                    last_res = res
                else:
                    res = last_res

                if burn:
                    last_burn = burn
                else:
                    burn = last_burn

                if nonburn:
                    last_nonburn = nonburn
                else:
                    nonburn = last_nonburn

                if office:
                    last_office = office
                else:
                    office = last_office

                # Split chome and sub
                chome_norm = unicodedata.normalize("NFKC", chome_raw).replace("\n", " ").strip()
                chome = ""
                sub = ""

                m_ch = re.search(r"(\d+丁目[〜~\d丁目・]*|[一二三四五六七八九十]+丁目[〜~一二三四五六七八九十丁目・]*)", chome_norm)
                if m_ch:
                    chome = m_ch.group(1).replace("~", "～")
                    sub = chome_norm[m_ch.end():].strip().lstrip("〔(").rstrip("〕)")
                else:
                    if chome_norm and chome_norm != "全域":
                        sub = chome_norm

                types: Dict[str, Any] = {}

                # Burnable
                burn_days = parse_clean_days(burn)
                if burn_days:
                    types["burnable"] = {
                        "label": "可燃ごみ",
                        "days": burn_days,
                        "weeks": None,
                        "time": "朝8:00まで",
                    }

                # Plastic
                pla_days = parse_clean_days(pla)
                if pla_days:
                    types["plastic"] = {
                        "label": "プラ",
                        "days": pla_days,
                        "weeks": None,
                        "time": "朝8:00まで",
                    }

                # Nonburnable
                nb_weeks, nb_days = parse_nonburn(nonburn)
                if nb_days:
                    types["nonburnable"] = {
                        "label": "不燃ごみ",
                        "days": nb_days,
                        "weeks": nb_weeks if nb_weeks else None,
                        "time": "朝8:00まで",
                    }

                # Resource
                res_days = parse_clean_days(res)
                if res_days:
                    types["resource"] = {
                        "label": "資源",
                        "days": res_days,
                        "weeks": None,
                        "time": "朝8:00まで",
                    }

                rules = {
                    "holiday_collection": "祝日も収集",
                    "time_by": "8:00",
                    "yearend": "12/31~1/3 休止",
                }
                if office:
                    rules["office"] = f"{office}特別出張所／清掃事務所"

                t_romaji = to_romaji(town)
                chome_num = extract_nums(chome)

                slug_base = f"ota/{t_romaji}"
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
                    "pref": "東京都",
                    "city": "大田区",
                    "city_en": "ota",
                    "ward": "",
                    "ward_en": "",
                    "town": town,
                    "romaji": t_romaji,
                    "chome": chome,
                    "sub": sub,
                    "slug": slug,
                    "types": types,
                    "rules": rules,
                    "source": {
                        "url": PDF_URL,
                        "fetched": TODAY_STR,
                        "basis": "official_pdf",
                    },
                    "raw": {
                        "row": r,
                        "page": p_idx,
                        "office": office,
                    },
                }
                all_normalized.append(record)

    print(f"[+] Total normalized Ota records: {len(all_normalized)}")
    print(f"[+] Unique slugs: {len(used_slugs)}")

    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_normalized, f, ensure_ascii=False, indent=2)

    print(f"[✔] Wrote to {out_file}")


if __name__ == "__main__":
    main()
