#!/usr/bin/env python3
"""
Comprehensive Validation Script for Normalized Garbage Collection Data
----------------------------------------------------------------------
Verifies:
1. Pure JSON array at root
2. Zero duplicate slugs per city
3. Slug formatting (ASCII, lowercase, hyphens, slashes)
4. Standard waste type keys only (burnable, resource, plastic, paper_cloth, nonburnable, bulky)
5. Valid Japanese day characters (月火水木金土日)
6. Weeks format (null or list of integers)
7. Source metadata (source.fetched == '2026-09-17')
8. Romaji field presence
9. Raw field preservation
"""

import json
import os
import re
import sys

VALID_KEYS = {"burnable", "resource", "plastic", "paper_cloth", "nonburnable", "bulky"}
VALID_DAYS = {"月", "火", "水", "木", "金", "土", "日"}
TODAY_STR = "2026-09-17"


def verify_file(file_path: str) -> dict:
    city_en = os.path.basename(file_path).replace(".json", "")
    print(f"\n==========================================")
    print(f"[*] Verifying {city_en} ({file_path})...")

    if not os.path.exists(file_path):
        print(f"[!] File does not exist: {file_path}", file=sys.stderr)
        return {"city": city_en, "status": "FAIL", "error": "File not found"}

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Pure list check
    assert isinstance(data, list), "Root is not a pure JSON array!"

    total_records = len(data)
    used_slugs = set()
    slug_dupes = []
    invalid_slug_chars = []
    invalid_type_keys = []
    invalid_days = []
    invalid_weeks = []
    invalid_fetched_dates = []
    missing_romaji = 0
    missing_raw = 0

    type_counts = {k: 0 for k in VALID_KEYS}

    for i, r in enumerate(data):
        slug = r.get("slug", "")
        if slug in used_slugs:
            slug_dupes.append(slug)
        used_slugs.add(slug)

        if not re.match(r"^[a-z0-9\-/]+$", slug):
            invalid_slug_chars.append(slug)

        if not r.get("romaji"):
            missing_romaji += 1

        if not r.get("raw"):
            missing_raw += 1

        for req_field in ["pref", "city", "city_en", "ward", "ward_en", "town", "slug", "types", "source", "raw", "romaji"]:
            if req_field not in r:
                errors.append(f"Missing required field '{req_field}' in record slug={slug}")

        fetched = r.get("source", {}).get("fetched")
        if fetched != TODAY_STR:
            invalid_fetched_dates.append((slug, fetched))

        types = r.get("types", {})
        for t_k, t_v in types.items():
            if t_k not in VALID_KEYS:
                invalid_type_keys.append((slug, t_k))
            else:
                type_counts[t_k] += 1

            days = t_v.get("days", [])
            for d in days:
                if d not in VALID_DAYS:
                    invalid_days.append((slug, t_k, d))

            weeks = t_v.get("weeks")
            if weeks is not None:
                if not isinstance(weeks, list) or not all(isinstance(w, int) for w in weeks):
                    invalid_weeks.append((slug, t_k, weeks))

    status = "PASS"
    errors = []

    if slug_dupes:
        status = "FAIL"
        errors.append(f"Slug duplicates: {len(slug_dupes)}")
    if invalid_slug_chars:
        status = "FAIL"
        errors.append(f"Invalid slug chars: {len(invalid_slug_chars)}")
    if invalid_type_keys:
        status = "FAIL"
        errors.append(f"Invalid type keys: {len(invalid_type_keys)}")
    if invalid_days:
        status = "FAIL"
        errors.append(f"Invalid day characters: {len(invalid_days)}")
    if invalid_weeks:
        status = "FAIL"
        errors.append(f"Invalid weeks: {len(invalid_weeks)}")
    if invalid_fetched_dates:
        status = "FAIL"
        errors.append(f"Invalid fetched dates: {len(invalid_fetched_dates)}")
    if missing_romaji > 0:
        status = "FAIL"
        errors.append(f"Missing romaji: {missing_romaji}")
    if missing_raw > 0:
        status = "FAIL"
        errors.append(f"Missing raw: {missing_raw}")

    print(f"[+] Total records: {total_records}")
    print(f"[+] Unique slugs: {len(used_slugs)} (Duplicates: {len(slug_dupes)})")
    print(f"[+] Type keys distribution: {type_counts}")
    print(f"[+] Result: {status}")

    return {
        "city": city_en,
        "total_records": total_records,
        "unique_slugs": len(used_slugs),
        "slug_duplicates": len(slug_dupes),
        "type_counts": type_counts,
        "status": status,
        "errors": errors,
    }


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    norm_dir = os.path.join(base_dir, "data", "normalized")

    if len(sys.argv) > 1:
        cities = sys.argv[1:]
    else:
        cities = [f[:-5] for f in sorted(os.listdir(norm_dir)) if f.endswith(".json") and not f.startswith(".")]

    summary = []

    for city in cities:
        file_path = os.path.join(norm_dir, f"{city}.json")
        res = verify_file(file_path)
        summary.append(res)

    print("\n" + "=" * 50)
    print("ALL CITIES VALIDATION SUMMARY:")
    print("=" * 50)
    all_pass = True
    for s in summary:
        print(f"City: {s['city']:12} | Records: {s['total_records']:6} | Unique Slugs: {s['unique_slugs']:6} | Status: {s['status']}")
        if s["status"] != "PASS":
            all_pass = False
            for err in s["errors"]:
                print(f"   [!] {err}")

    if not all_pass:
        print("\n[❌] SOME VALIDATIONS FAILED!")
        sys.exit(1)
    else:
        print(f"\n[✔] ALL {len(summary)} CITIES PASSED 100% OF SCHEMA VERIFICATIONS!")


if __name__ == "__main__":
    main()
