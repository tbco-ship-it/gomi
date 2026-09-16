#!/usr/bin/env python3
"""Fetch Toshima Ward garbage collection schedule from threeR web calendar
"""
import urllib.request
import json
import time
import re
from bs4 import BeautifulSoup

areas = [
    ('149860', '池袋'),
    ('149878', '池袋本町'),
    ('149879', '要町'),
    ('144905', '上池袋'),
    ('149885', '北大塚'),
    ('149894', '駒込'),
    ('149895', '巣鴨'),
    ('149897', '千川'),
    ('144916', '雑司が谷'),
    ('149898', '高田'),
    ('144919', '高松'),
    ('144920', '千早'),
    ('149900', '長崎'),
    ('149902', '西池袋'),
    ('149919', '西巣鴨'),
    ('149920', '東池袋'),
    ('149935', '南池袋'),
    ('149943', '南大塚'),
    ('149947', '南長崎'),
    ('149949', '目白'),
]

leaves = []
for aid, town in areas:
    url = f'https://manage.delight-system.com/threeR/web/calendar?menu=calendar&jichitaiId=toshimaku&areaId={aid}&lang=ja'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        soup = BeautifulSoup(resp.read(), 'html.parser')
        selects = soup.find_all('select')
        sub_opts = []
        if len(selects) > 1:
            for opt in selects[1].find_all('option'):
                v = opt.get('value')
                txt = opt.get_text(strip=True)
                if v and v != '-':
                    sub_opts.append((v, txt))
        if sub_opts:
            for v, chome in sub_opts:
                leaves.append((town, chome, v))
        else:
            leaves.append((town, '', aid))

results = []
day_names = ["日", "月", "火", "水", "木", "金", "土"]

for town, chome, aid in leaves:
    # September 2026 calendar
    url = f'https://manage.delight-system.com/threeR/web/calendar?menu=calendar&jichitaiId=toshimaku&areaId={aid}&year=2026&month=09&lang=ja'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        soup = BeautifulSoup(resp.read(), 'html.parser')
        t = soup.find_all('table')[-1]
        sched = {
            "burnable": set(),
            "nonburnable": set(),
            "resource": set(),
            "plastic": set(),
            "paper_cloth": set(),
        }
        # To find weeks for nonburnable
        nonburnable_dates = []

        rows = t.find_all('tr')
        # Skip header row
        for week_idx, tr in enumerate(rows[1:], 1):
            tds = tr.find_all(['th', 'td'])
            for d_idx, td in enumerate(tds):
                txt = td.get_text(separator=' ', strip=True)
                if not txt:
                    continue
                d_name = day_names[d_idx]
                if '燃やすごみ' in txt:
                    sched['burnable'].add(d_name)
                if '金属・陶器・ガラスごみ' in txt:
                    sched['nonburnable'].add(d_name)
                    nonburnable_dates.append((week_idx, d_name))
                if '資源（びん・かん・ペットボトル）' in txt:
                    sched['resource'].add(d_name)
                if '資源（プラスチック）' in txt:
                    sched['plastic'].add(d_name)
                if '資源（段ボール・紙・布類）' in txt:
                    sched['paper_cloth'].add(d_name)

        results.append({
            "town": town,
            "chome": chome,
            "areaId": aid,
            "burnable": sorted(list(sched['burnable'])),
            "nonburnable": sorted(list(sched['nonburnable'])),
            "nonburnable_weeks": sorted(list(set(w[0] for w in nonburnable_dates))),
            "resource": sorted(list(sched['resource'])),
            "plastic": sorted(list(sched['plastic'])),
            "paper_cloth": sorted(list(sched['paper_cloth'])),
        })
    time.sleep(0.1)

with open('data/raw/toshima/toshima_raw.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"Fetched {len(results)} areas for Toshima!")
