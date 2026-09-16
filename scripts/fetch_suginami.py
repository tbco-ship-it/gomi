#!/usr/bin/env python3
"""Fetch Suginami Ward garbage collection schedule from threeR web calendar
"""
import urllib.request
import json
import time
from bs4 import BeautifulSoup

areas = [
    ('158647', '阿佐谷北'),
    ('158648', '阿佐谷南'),
    ('158649', '天沼'),
    ('158650', '井草'),
    ('158652', '和泉'),
    ('158654', '今川'),
    ('158656', '梅里'),
    ('158658', '永福'),
    ('158659', '大宮'),
    ('158660', '荻窪'),
    ('158661', '上井草'),
    ('158663', '上荻'),
    ('158665', '上高井戸'),
    ('158666', '久我山'),
    ('158668', '高円寺北'),
    ('158670', '高円寺南'),
    ('158672', '清水'),
    ('158674', '下井草'),
    ('158676', '下高井戸'),
    ('158678', '松庵'),
    ('158679', '善福寺'),
    ('158680', '高井戸西'),
    ('158682', '高井戸東'),
    ('158683', '成田西'),
    ('158685', '成田東'),
    ('158686', '西荻北'),
    ('158688', '西荻南'),
    ('158689', '浜田山'),
    ('158690', '方南'),
    ('158691', '堀ノ内'),
    ('158692', '本天沼'),
    ('158693', '松ノ木'),
    ('158694', '南荻窪'),
    ('158695', '宮前'),
    ('158697', '桃井'),
    ('158698', '和田'),
]

leaves = []
for aid, town in areas:
    url = f'https://manage.delight-system.com/threeR/web/calendar?menu=calendar&jichitaiId=suginamiku&areaId={aid}&lang=ja'
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
    url = f'https://manage.delight-system.com/threeR/web/calendar?menu=calendar&jichitaiId=suginamiku&areaId={aid}&year=2026&month=09&lang=ja'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        soup = BeautifulSoup(resp.read(), 'html.parser')
        t = soup.find_all('table')[-1]
        sched = {
            "burnable": set(),
            "nonburnable": set(),
            "binkan": set(),
            "pet": set(),
            "plastic": set(),
            "paper": set(),
        }
        nonburnable_dates = []

        rows = t.find_all('tr')
        for week_idx, tr in enumerate(rows[1:], 1):
            tds = tr.find_all(['th', 'td'])
            for d_idx, td in enumerate(tds):
                txt = td.get_text(separator=' ', strip=True)
                if not txt:
                    continue
                d_name = day_names[d_idx]
                if '可燃ごみ' in txt:
                    sched['burnable'].add(d_name)
                if '不燃ごみ' in txt:
                    sched['nonburnable'].add(d_name)
                    nonburnable_dates.append((week_idx, d_name))
                if 'びん・かん' in txt:
                    sched['binkan'].add(d_name)
                if 'ペットボトル' in txt:
                    sched['pet'].add(d_name)
                if 'プラ' in txt:
                    sched['plastic'].add(d_name)
                if '古紙' in txt:
                    sched['paper'].add(d_name)

        results.append({
            "town": town,
            "chome": chome,
            "areaId": aid,
            "burnable": sorted(list(sched['burnable'])),
            "nonburnable": sorted(list(sched['nonburnable'])),
            "nonburnable_weeks": sorted(list(set(w[0] for w in nonburnable_dates))),
            "binkan": sorted(list(sched['binkan'])),
            "pet": sorted(list(sched['pet'])),
            "plastic": sorted(list(sched['plastic'])),
            "paper": sorted(list(sched['paper'])),
        })
    time.sleep(0.1)

with open('data/raw/suginami/suginami_raw.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"Fetched {len(results)} areas for Suginami!")
