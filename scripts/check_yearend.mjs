#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { calendarEvents, typesOn, windowState, ORDER } from '../static/yearend.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const index = JSON.parse(fs.readFileSync(path.join(ROOT, 'dist/static/index.json'), 'utf8'));
const targets = [
  {
    label: '名古屋市 東区 相生町',
    city: 'nagoya',
    match: row => row[1] === '東区' && row[3] === '相生町' && row[4] === '',
  },
  {
    label: '名古屋市 千種区 今池五丁目（不燃・金曜）',
    city: 'nagoya',
    match: row => row[1] === '千種区' && row[3] === '今池' && row[4] === '5丁目'
      && (row[9].nonburnable?.[0] || []).includes('金'),
  },
  {
    label: '名古屋市 名東区 猪高台二丁目（粗大・金曜）',
    city: 'nagoya',
    match: row => row[1] === '名東区' && row[3] === '猪高台' && row[4] === '2丁目'
      && (row[9].bulky?.[0] || []).includes('金'),
  },
  {
    label: '神戸市 東灘区 魚崎南町1丁目',
    city: 'kobe',
    match: row => row[1] === '東灘区' && row[3] === '魚崎南町' && row[4] === '1丁目',
  },
  {
    label: '板橋区 相生町',
    city: 'itabashi',
    match: row => row[3] === '相生町' && row[4] === '',
  },
  {
    label: '熊本市 中央区 内坪井町',
    city: 'kumamoto',
    match: row => row[1] === '中央区' && row[3] === '内坪井町',
  },
  {
    label: '川崎市 川崎区 浅田',
    city: 'kawasaki',
    match: row => row[1] === '川崎区' && row[3] === '浅田',
  },
  {
    label: '江東区 青海',
    city: 'koto',
    match: row => row[3] === '青海',
  },
];

const dateKey = date => String(date.getFullYear()).padStart(4, '0') + '-'
  + String(date.getMonth() + 1).padStart(2, '0') + '-'
  + String(date.getDate()).padStart(2, '0');
const addDays = (date, count) => {
  const out = new Date(date);
  out.setDate(out.getDate() + count);
  return out;
};
const start = new Date(2026, 11, 26);
const end = new Date(2027, 0, 31);
const now = new Date();
now.setHours(0, 0, 0, 0);

for (const target of targets) {
  const row = index.items.find(item => item[0] === target.city && target.match(item));
  if (!row) throw new Error('Address not found in built search index: ' + target.label);
  const [city, ward, , town, chome, , , , , compactTypes, , yearend] = row;
  const types = Object.fromEntries(Object.entries(compactTypes).map(([key, [days, weeks, time]]) => [
    key,
    { days, weeks, time, label: index.labels[city][key] },
  ]));
  const name = index.cities[city] + ward + town + chome;
  const events = calendarEvents(types, yearend, now, 120);
  console.log('\n## ' + target.label);
  console.log('source=' + (yearend.source_url || '(なし)'));
  for (let date = new Date(start); date <= end; date = addDays(date, 1)) {
    const key = dateKey(date);
    const states = ORDER.filter(type => types[type])
      .map(type => type + '=' + windowState(date, type, yearend)).join(' ');
    const pickups = typesOn(types, date, yearend);
    const dayEvents = events.filter(event => event.date === key);
    const ics = dayEvents.map(event => event.kind === 'check'
      ? '確認案内' + (event.source ? '(' + event.source + ')' : '')
      : '収集:' + event.types.join(',')).join(' / ') || '—';
    console.log(key + ' | ' + states + ' | pickup=' + (pickups.join(',') || '—') + ' | ics=' + ics);
  }
  const visibleEvents = events.filter(event => event.date >= dateKey(start) && event.date <= dateKey(end));
  console.log('ICS dates (' + dateKey(start) + '–' + dateKey(end) + '): ' + (visibleEvents.map(event =>
    event.date + ':' + (event.kind === 'check' ? 'check' : event.types.join('+'))
  ).join(', ') || '—'));
}
