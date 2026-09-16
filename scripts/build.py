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

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
SITE = "ゴミの日ナビ"
JDAY = "月火水木金土日"
TYPE_ORDER = ["burnable", "resource", "plastic", "paper_cloth", "nonburnable", "bulky"]
TYPE_COLOR = {"burnable": "#ff7a00", "resource": "#3182f6", "plastic": "#00b06f", "paper_cloth": "#8b5cf6", "nonburnable": "#6b7684", "bulky": "#f04452"}


def nfkc(s):
    return unicodedata.normalize("NFKC", s or "")


def split_addr(r):
    """(town, chome, sub) — Osaka towns without 丁目 carry the 番地 in `chome` ("1番"); that is a sub-area, not a page."""
    town, chome, sub = nfkc(r["town"]), nfkc(r.get("chome")), r.get("sub") or ""
    if re.fullmatch(r"\d+番.*", chome):
        sub, chome = (chome + (" " + sub if sub else "")), ""
    return town, chome, sub


def group_key(r):
    town, chome, _ = split_addr(r)
    return (r["city_en"], r["ward_en"], town, chome)


def sched_sig(r):
    return json.dumps({t: [v.get("days"), v.get("weeks")] for t, v in r["types"].items()}, ensure_ascii=False, sort_keys=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="/")
    ap.add_argument("--origin", default="https://tbco-ship-it.github.io")
    ap.add_argument("--cname", default="")
    ap.add_argument("--adsense-pub", default="pub-8425563704095379")
    args = ap.parse_args()
    base = args.base if args.base.endswith("/") else args.base + "/"
    origin = args.origin.rstrip("/")
    today = dt.date.today()

    cities = {}
    groups = {}
    for f in [ROOT / "data/normalized" / f"{c}.json" for c in ("osaka", "yokohama", "kitakyushu")]:
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
                slug = f"{r['city_en']}/{r['ward_en']}/{r['romaji']}" + ("-" + "-".join(nums) if nums else "")
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
                       JDAY=JDAY, TYPE_ORDER=TYPE_ORDER, TYPE_COLOR=TYPE_COLOR, cities=cities,
                       n_towns=len(groups), n_records=sum(len(g["records"]) for g in groups.values()))

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    shutil.copytree(ROOT / "static", DIST / "static")
    # search index: one entry per town-group (small fields only)
    index = [{"c": g["city_en"], "cn": g["city"], "w": g["ward"], "we": g["ward_en"], "t": g["town"], "ch": g["chome"], "r": g["romaji"], "s": g["slug"],
              "ty": {t: {"d": v.get("days") or [], "w": v.get("weeks"), "l": v.get("label"), "tm": v.get("time")} for t, v in g["main"]["types"].items()}}
             for g in groups.values()]
    (DIST / "static/index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")))

    urls = []

    def write(path, template, **ctx):
        out = DIST / path
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(env.get_template(template).render(path=path, **ctx))
        urls.append(path)

    write("", "index.html")
    for page in ("about", "methodology", "privacy", "contact"):
        write(f"{page}/", f"{page}.html")
    write("guide/nenmatsu/", "guide_nenmatsu.html")
    for ce, c in cities.items():
        write(f"{ce}/", "city.html", c=c)
        for we, w in c["wards"].items():
            write(f"{ce}/{we}/", "ward.html", c=c, w=w)
            for g in w["towns"].values():
                write(f"{g['slug']}/", "town.html", c=c, w=w, g=g)

    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sm.append(f"<url><loc>{origin}{base}{u}</loc><lastmod>{today.isoformat()}</lastmod></url>")
    sm.append("</urlset>")
    (DIST / "sitemap.xml").write_text("\n".join(sm))
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
