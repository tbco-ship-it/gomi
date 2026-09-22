#!/usr/bin/env python3
"""Generate the static ゴミ収集日 site into dist/ from data/normalized/*.json.
Pages are at 町丁目 level; 番地/建物 variants become an exceptions table on the same page."""
import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import unicodedata
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

from jinja2 import Environment, FileSystemLoader, select_autoescape
import pykakasi

KKS = pykakasi.kakasi()
_READ = {}


def reading(text):
    """(hiragana, hepburn) for a 町名/区名 via pykakasi — machine reading, good enough for search matching."""
    if text not in _READ:
        parts = KKS.convert(text)
        _READ[text] = ("".join(x["hira"] for x in parts), "".join(x["hepburn"] for x in parts))
    return _READ[text]


def raw_kana(r):
    """Readings the source itself provides (京都 '町名 （かな）', 神戸 reading column)."""
    raw = r.get("raw") or {}
    row = raw.get("row") if isinstance(raw, dict) else None
    out = []
    if isinstance(row, list):
        for cell in row[:4]:
            if isinstance(cell, str):
                out += re.findall(r"[ぁ-ゖー]{2,}", cell)
    return "".join(dict.fromkeys(out))

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
SITE = "ゴミの日ナビ"
JDAY = "月火水木金土日"
DAY_EN = dict(zip("月火水木金土日", ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]))
ORD_EN = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th"}


def en_schedule(types):
    """English one-liner for the foreign-resident lane: 'Burnable Mon & Thu · Plastic Sat · Non-burnable 2nd & 4th Fri'."""
    parts = []
    for t in TYPE_ORDER:
        v = types.get(t)
        if not v or not v.get("days"):
            continue
        wk = (" & ".join(ORD_EN.get(w, str(w)) for w in v["weeks"]) + " ") if v.get("weeks") else ""
        parts.append(f"{TYPE_EN[t].replace(' · ', '/')} {wk}{' & '.join(DAY_EN.get(d, d) for d in v['days'])}")
    return " · ".join(parts)
TYPE_ORDER = ["burnable", "resource", "plastic", "paper_cloth", "yard", "nonburnable", "bulky"]
TYPE_EN = {"burnable": "Burnable", "resource": "Cans · bottles · PET", "plastic": "Plastic", "paper_cloth": "Paper & cloth", "yard": "Branches · grass · leaves", "nonburnable": "Non-burnable", "bulky": "Bulky (reservation)"}
TYPE_COLOR = {"burnable": "#ff7a00", "resource": "#3182f6", "plastic": "#00b06f", "paper_cloth": "#8b5cf6", "yard": "#65a30d", "nonburnable": "#6b7684", "bulky": "#f04452"}


KANJI_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def kanji_to_digits(s):
    """一丁目→1丁目, 十二丁目→12丁目 (名古屋 uses kanji numerals in the source table)."""
    def conv(m):
        t = m.group(0); n = 0
        if "十" in t:
            a, b = t.split("十"); n = (KANJI_NUM[a] if a else 1) * 10 + (KANJI_NUM[b] if b else 0)
        else:
            n = KANJI_NUM[t]
        return str(n)
    return re.sub(r"[一二三四五六七八九]?十[一二三四五六七八九]?|[一二三四五六七八九]", conv, s) if re.search(r"[一二三四五六七八九十]丁目", s) else s


def nfkc(s):
    s = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s or "")).strip()
    return kanji_to_digits(s)


def split_addr(r):
    """(town, chome, sub) — Osaka towns without 丁目 carry the 番地 in `chome` ("1番"); that is a sub-area, not a page."""
    town, chome, sub = nfkc(r["town"]), nfkc(r.get("chome")), nfkc(r.get("sub"))
    sub = re.sub(r"[「」]|\(?朝?\d{1,2}時(\d{1,2}分)?までにお出しください。?\)?", "", sub).strip(" 、,")  # 岡山: stray quotes / time notes in sub
    if re.fullmatch(r"\d+番.*", chome):
        sub, chome = (chome + (" " + sub if sub else "")), ""
    return town, chome, sub


def group_key(r):
    town, chome, _ = split_addr(r)
    return (r["city_en"], r["ward_en"], town, chome)


def sched_sig(r):
    return json.dumps({t: [v.get("days"), v.get("weeks")] for t, v in r["types"].items()}, ensure_ascii=False, sort_keys=True)



def write_sitemaps(urls, origin, base, lastmod=None, limit=5000):
    """One sitemap index plus a file per section, so Search Console reports coverage per section
    instead of one opaque pile. urls is a list of (shard, path)."""
    shards = defaultdict(list)
    for shard, u in urls:
        shards[shard].append(u)
    for k in [k for k, v in shards.items() if len(v) < 10 and k != "core"]:
        shards["core"] += shards.pop(k)
    out = DIST / "sitemaps"
    out.mkdir(parents=True, exist_ok=True)
    names = []
    for shard in sorted(shards):
        rows = shards[shard]
        parts = [rows[i:i + limit] for i in range(0, len(rows), limit)] or [[]]
        for n, part in enumerate(parts, 1):
            fn = f"{shard}.xml" if len(parts) == 1 else f"{shard}-{n}.xml"
            lm = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
            body = "\n".join(f"<url><loc>{escape(origin + base + u)}</loc>{lm}</url>" for u in part)
            (out / fn).write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                  + body + "\n</urlset>")
            names.append(fn)
    idx = "".join(f"<sitemap><loc>{origin}{base}sitemaps/{n}</loc></sitemap>" for n in names)
    (DIST / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                      '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                      + idx + "</sitemapindex>")
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="/")
    ap.add_argument("--origin", default="https://gomiday.com")
    ap.add_argument("--cname", default="gomiday.com")
    ap.add_argument("--adsense-pub", default="pub-8425563704095379")
    args = ap.parse_args()
    base = args.base if args.base.endswith("/") else args.base + "/"
    origin = args.origin.rstrip("/")
    today = dt.date.today()

    cities = {}
    groups = {}
    ndir = ROOT / "data/normalized"
    first = ["osaka", "yokohama", "kitakyushu"]  # nav order; new cities append alphabetically
    files = [ndir / f"{c}.json" for c in first if (ndir / f"{c}.json").exists()] + sorted(f for f in ndir.glob("*.json") if f.stem not in first)
    for f in files:
        recs = json.loads(f.read_text())
        for r in recs:
            if not r["types"]:
                continue  # e.g. 横浜 南区平楽: "事務所にお問合せください" — nothing to show
            cities.setdefault(r["city_en"], {"city": r["city"], "pref": r["pref"], "city_en": r["city_en"], "wards": {}, "source": r["source"]["url"].split("/")[2], "fetched": r["source"]["fetched"], "rules": r.get("rules", {})})
            c = cities[r["city_en"]]
            c["wards"].setdefault(r["ward_en"], {"ward": r["ward"], "ward_en": r["ward_en"], "towns": {}})
            k = group_key(r)
            town, chome, sub = split_addr(r)
            r["sub"] = sub
            if k not in groups:
                # town-level slug from romaji + the digits of 丁目 (record slugs carry 番地/sub suffixes)
                nums = [x.lower() for x in re.findall(r"\d+|[A-Za-z]+", chome)]
                head = f"{r['city_en']}/{r['ward_en']}" if r["ward_en"] else r["city_en"]  # 23区: the ward is the city
                slug = f"{head}/{r['romaji']}" + ("-" + "-".join(nums) if nums else "")
                groups[k] = {"city_en": r["city_en"], "city": r["city"], "pref": r["pref"], "ward": r["ward"], "ward_en": r["ward_en"],
                             "town": town, "chome": chome, "romaji": r.get("romaji", ""), "slug": slug,
                             "records": [], "rules": r.get("rules", {}), "source": r["source"]}
            groups[k]["records"].append(r)
    # resolve slug collisions across groups (different chome parsed to same slug)
    seen = {}
    for k, g in groups.items():
        s = g["slug"]
        if s in seen:
            n = 2
            while f"{s}-v{n}" in seen: n += 1
            g["slug"] = f"{s}-v{n}"
        seen[g["slug"]] = 1
    for g in groups.values():
        sigs = defaultdict(list)
        for r in g["records"]:
            sigs[sched_sig(r)].append(r)
        main_sig = max(sigs, key=lambda s: len(sigs[s]))
        g["main"] = sigs[main_sig][0]
        g["exceptions"] = [r for s, rs in sigs.items() if s != main_sig for r in rs]
        g["uniform"] = len(sigs) == 1
        g["primary"] = "burnable" if "burnable" in g["main"]["types"] else next(iter(g["main"]["types"]))
        cities[g["city_en"]]["wards"][g["ward_en"]]["towns"][g["slug"]] = g

    h = hashlib.md5()
    for f in sorted((ROOT / "static").glob("*")):
        h.update(f.read_bytes())
    v = h.hexdigest()[:8]
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
    env.globals.update(site=SITE, base=base, origin=origin, today=today.isoformat(), v=v, adsense_pub=args.adsense_pub,
                       JDAY=JDAY, TYPE_ORDER=TYPE_ORDER, TYPE_COLOR=TYPE_COLOR, TYPE_EN=TYPE_EN, cities=cities,
                       n_towns=len(groups), n_records=sum(len(g["records"]) for g in groups.values()))

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    shutil.copytree(ROOT / "static", DIST / "static")
    # search index: one entry per town-group (small fields only)
    for g in groups.values():
        wk, wr = reading(g["ward"] or g["city"])  # 23区: the city name is what people type
        tk, tr = reading(g["town"])
        g["kana"] = " ".join(x for x in (wk, tk, raw_kana(g["main"])) if x)
        g["romaji_full"] = " ".join(x for x in (wr, tr, g["romaji"]) if x)
        nums = re.findall(r"\d+", g["chome"])
        g["en"] = ", ".join(x for x in ((g["ward_en"] or g["city_en"]).title(), g["romaji"].title() + (" " + "-".join(nums) if nums else "")) if x)
        rm = re.match(r"(.*?)(\d+)$", g["romaji"])  # '曙1,2丁目' romanises as akebono1 + chome ',2丁目': put the digit back with the chome numbers
        en_town, en_nums = (rm.group(1), [rm.group(2)] + nums) if rm else (g["romaji"], nums)
        g["en_place"] = ", ".join(x for x in (en_town.title() + (" " + "-".join(en_nums) + "-chome" if en_nums else ""), (g["ward_en"].title() + "-ku" if g["ward_en"] else ""), g["city_en"].title() + ("-ku" if not g["ward_en"] else "")) if x)
        g["en_sched"] = en_schedule(g["main"]["types"])
        tb = (g.get("rules") or {}).get("time_by") or ""
        g["en_time"] = tb if re.fullmatch(r"\d{1,2}:\d{2}", tb) else ""  # '日没から夜12時まで' style rules stay Japanese-only
    # compact search index: per-city label dictionary + one small entry per town group
    labels = {}
    for g in groups.values():
        for t, v in g["main"]["types"].items():
            labels.setdefault(g["city_en"], {}).setdefault(t, v.get("label"))
    items = [[g["city_en"], g["ward"], g["ward_en"], g["town"], g["chome"], g["romaji_full"], g["kana"], g["slug"], g["en"],
              {t: [v.get("days") or [], v.get("weeks"), v.get("time")] for t, v in g["main"]["types"].items()}] for g in groups.values()]
    # GPS lookup: GSI reverse-geocoder muniCd (JIS 5-digit) -> [city_en, ward] for covered wards only.
    # data/muni_codes.json is GSI's own table (https://maps.gsi.go.jp/js/muni.js), vendored 2026-09-17.
    muni_all = json.loads((ROOT / "data/muni_codes.json").read_text())
    muni = {}
    for ce, c in cities.items():
        for w in c["wards"].values():
            wn = re.sub(r"区.*$", "区", w["ward"])  # 名古屋 '緑区大高町' rows share 緑区's code
            want = f"{c['city']} {wn}" if w["ward"] else c["city"]
            for code, (_pref, name) in muni_all.items():
                if name == want and code not in muni:
                    muni[code] = [ce, wn]
    index = {"cities": {ce: c["city"] for ce, c in cities.items()}, "labels": labels, "items": items, "muni": muni}
    (DIST / "static/index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")))

    urls = []

    def write(path, template, sm=None, **ctx):
        out = DIST / path
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(env.get_template(template).render(path=path, **ctx))
        urls.append((sm or path.split("/")[0] or "core", path))

    write("", "index.html")
    for page in ("about", "methodology", "privacy", "contact"):
        write(f"{page}/", f"{page}.html")
    write("guide/nenmatsu/", "guide_nenmatsu.html")
    write("guide/hikkoshi/", "guide_hikkoshi.html")
    write("cities/", "cities.html")
    for ce, c in cities.items():
        write(f"{ce}/", "city.html", c=c)
        for we, w in c["wards"].items():
            if we:
                write(f"{ce}/{we}/", "ward.html", c=c, w=w)
            for g in w["towns"].values():
                write(f"{g['slug']}/", "town.html", c=c, w=w, g=g)

    write_sitemaps(urls, origin, base, today.isoformat())
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {origin}{base}sitemap.xml\n")
    (DIST / "404.html").write_text(env.get_template("404.html").render(path="404"))
    (DIST / ".nojekyll").write_text("")
    key = (ROOT / "static/indexnow-key.txt").read_text().strip()
    (DIST / f"{key}.txt").write_text(key + "\n")
    if args.adsense_pub:
        (DIST / "ads.txt").write_text(f"google.com, {args.adsense_pub}, DIRECT, f08c47fec0942fa0\n")
    if args.cname:
        (DIST / "CNAME").write_text(args.cname + "\n")
    print(f"built {len(urls)} pages ({len(groups)} towns, {sum(len(g['records']) for g in groups.values())} records) -> {DIST}")


if __name__ == "__main__":
    main()
