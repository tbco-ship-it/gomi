#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  calendarEvents, nextPickup, ORDER, typesOn, windowState,
} from '../static/yearend.mjs';

process.env.TZ ||= 'Asia/Tokyo';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const index = JSON.parse(fs.readFileSync(path.join(ROOT, 'dist/static/index.json'), 'utf8'));
const targets = [
  {
    label: '名古屋市 東区 相生町',
    city: 'nagoya',
    match: row => row[1] === '東区' && row[3] === '相生町' && row[4] === '',
  },
  {
    label: '名古屋市 東区 赤塚町 1〜3（住居表示地区・水曜資源）',
    city: 'nagoya',
    match: row => row[1] === '東区' && row[3] === '赤塚町 1〜3(住居表示地区)'
      && (row[9].resource?.[0] || []).includes('水'),
  },
  {
    label: '名古屋市 千種区 今池五丁目（不燃・金曜）',
    city: 'nagoya',
    match: row => row[1] === '千種区' && row[3] === '今池' && row[4] === '5丁目'
      && (row[9].nonburnable?.[0] || []).includes('金'),
  },
  {
    label: '名古屋市 名東区 猪高台二丁目（粗大・第4金曜）',
    city: 'nagoya',
    match: row => row[1] === '名東区' && row[3] === '猪高台' && row[4] === '2丁目'
      && (row[9].bulky?.[0] || []).includes('金') && (row[9].bulky?.[1] || []).includes(4),
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
    label: '新潟市 北区 上町（豊栄1）',
    city: 'niigata',
    match: row => row[1] === '北区' && row[3] === '上町',
  },
  {
    label: '広島市 中区 江波東2丁目',
    city: 'hiroshima',
    match: row => row[1] === '中区' && row[3] === '江波東' && row[4] === '2丁目',
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

const fail = message => { throw new Error(message); };
const assert = (condition, message) => { if (!condition) fail(message); };
const parseKey = key => {
  assert(/^\d{4}-\d{2}-\d{2}$/.test(key), 'NOW must use YYYY-MM-DD: ' + key);
  const [year, month, day] = key.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  assert(date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day, 'Invalid date: ' + key);
  return date;
};
const dateKey = date => String(date.getFullYear()).padStart(4, '0') + '-'
  + String(date.getMonth() + 1).padStart(2, '0') + '-'
  + String(date.getDate()).padStart(2, '0');
const addDays = (date, count) => {
  const out = new Date(date);
  out.setDate(out.getDate() + count);
  return out;
};
const nowKey = process.env.NOW || dateKey(new Date());
const now = parseKey(nowKey);
const seasonStart = parseKey('2026-12-26');
const seasonEnd = parseKey('2027-01-31');
const withinSeason = key => key >= dateKey(seasonStart) && key <= dateKey(seasonEnd);

const expanded = row => Object.fromEntries(Object.entries(row[9]).map(([key, [days, weeks, time]]) => [
  key,
  { days, weeks, time, label: index.labels[row[0]][key] },
]));
const resolved = targets.map(target => {
  const row = index.items.find(item => item[0] === target.city && target.match(item));
  assert(row, 'Address not found in built search index: ' + target.label);
  return { ...target, row, types: expanded(row), yearend: row[11] };
});
const byLabel = label => {
  const target = resolved.find(item => item.label === label);
  assert(target, 'Missing diagnostic target: ' + label);
  return target;
};
const typeList = (target, date) => typesOn(target.types, date, target.yearend);
const isPickup = (target, key, type) => typeList(target, parseKey(key)).includes(type);
const state = (target, key, type) => windowState(parseKey(key), type, target.yearend);
const assertState = (target, key, expected) => {
  for (const type of Object.keys(target.types)) {
    assert(state(target, key, type) === expected,
      target.label + ' ' + key + ' ' + type + ' must be ' + expected);
  }
  assert(typeList(target, parseKey(key)).length === 0, target.label + ' ' + key + ' must have no pickup chips');
};
const seasonEvents = target => calendarEvents(target.types, target.yearend, seasonStart, 120);
const checkEvents = events => events.filter(event => event.kind === 'check');
const checkEventsForSeason = target => seasonEvents(target).filter(event => event.kind === 'check' && withinSeason(event.date));

const aioi = byLabel('名古屋市 東区 相生町');
const akatsuka = byLabel('名古屋市 東区 赤塚町 1〜3（住居表示地区・水曜資源）');
const imaike = byLabel('名古屋市 千種区 今池五丁目（不燃・金曜）');
const inoshishitakadai = byLabel('名古屋市 名東区 猪高台二丁目（粗大・第4金曜）');

assert(akatsuka.row[3] === '赤塚町 1〜3(住居表示地区)' && akatsuka.types.resource.days.includes('水'),
  '赤塚町 check must use the 1〜3 (住居表示地区) Wednesday-resource row');
assert(isPickup(aioi, '2026-12-30', 'plastic'), '相生町 must retain 12/30 plastic pickup');
assert(state(aioi, '2026-12-30', 'burnable') === 'closed', '相生町 12/30 burnable must be closed');
assert(isPickup(akatsuka, '2026-12-30', 'resource'), '赤塚町 1〜3 must retain 12/30 Wednesday resource pickup');
assert(state(aioi, '2027-01-04', 'resource') === 'closed' && !isPickup(aioi, '2027-01-04', 'resource'),
  '相生町 1/4 resource must be closed with no pickup chip');
assert(isPickup(aioi, '2027-01-04', 'burnable'), '相生町 must have 1/4 burnable pickup');
assert(isPickup(aioi, '2027-01-11', 'resource'), '相生町 must have 1/11 resource pickup');
assert(isPickup(aioi, '2027-01-13', 'nonburnable'), '相生町 must have 1/13 nonburnable pickup');
assert(isPickup(aioi, '2027-01-27', 'bulky'), '相生町 must have 1/27 bulky pickup');
assert(checkEventsForSeason(aioi).length === 0, '相生町 must have no address-specific check ICS event');
assert(state(imaike, '2027-01-22', 'nonburnable') === 'check' && !isPickup(imaike, '2027-01-22', 'nonburnable'),
  '今池五丁目 1/22 nonburnable must be check with no pickup chip');
const imaikeJanNext = nextPickup(imaike.types.nonburnable, 'nonburnable', parseKey('2027-01-10'), imaike.yearend);
assert(imaikeJanNext?.state === 'check' && dateKey(imaikeJanNext.date) === '2027-01-22',
  'NOW=2027-01-10 next nonburnable must return 1/22 as check, never skip to 2/26');
assert(imaikeJanNext.source === imaike.yearend.source_url, '今池 next check must include its official source URL');
assert(isPickup(inoshishitakadai, '2027-01-08', 'burnable') && isPickup(inoshishitakadai, '2027-01-22', 'burnable'),
  '猪高台二丁目 must retain 1/8 and 1/22 burnable pickups');
assert(state(inoshishitakadai, '2027-01-22', 'bulky') === 'check' && !isPickup(inoshishitakadai, '2027-01-22', 'bulky'),
  '猪高台二丁目 1/22 bulky fourth-Friday pickup must be check and hidden');
assert(isPickup(inoshishitakadai, '2027-01-20', 'nonburnable'), '猪高台二丁目 must retain 1/20 nonburnable pickup');
const imaikeCheck = checkEventsForSeason(imaike);
assert(imaikeCheck.length === 1 && imaikeCheck[0].date === '2027-01-08'
  && imaikeCheck[0].source === imaike.yearend.source_url,
  '今池 ICS check reminder must occur once on 2027-01-08 and include the official URL');

const kumamoto = byLabel('熊本市 中央区 内坪井町');
const kawasaki = byLabel('川崎市 川崎区 浅田');
const koto = byLabel('江東区 青海');
const hiroshima = byLabel('広島市 中区 江波東2丁目');
const kobe = byLabel('神戸市 東灘区 魚崎南町1丁目');
const itabashi = byLabel('板橋区 相生町');
const niigata = byLabel('新潟市 北区 上町（豊栄1）');
for (const target of [kumamoto, koto]) {
  for (const key of ['2026-12-29', '2026-12-30', '2026-12-31', '2027-01-01', '2027-01-02', '2027-01-03', '2027-01-04']) {
    assertState(target, key, 'check');
  }
  const reminders = checkEventsForSeason(target);
  assert(reminders.length === 1 && reminders[0].date === '2026-12-29'
    && reminders[0].source === target.yearend.source_url,
    target.label + ' check ICS reminder must be on 2026-12-29 and include the official URL');
}
assert(state(kobe, '2026-12-29', 'burnable') === 'check' && !isPickup(kobe, '2026-12-29', 'burnable'),
  '神戸 12/29 must be check with no pickup chip');
for (const key of ['2027-01-01', '2027-01-02', '2027-01-03']) assertState(kobe, key, 'closed');
assert(isPickup(kobe, '2027-01-04', 'burnable'), '神戸 1/4 must retain its normal burnable pickup');
const kobeReminders = checkEventsForSeason(kobe);
assert(kobeReminders.length === 1 && kobeReminders[0].date === '2026-12-29'
  && kobeReminders[0].source === kobe.yearend.source_url,
  '神戸 check ICS reminder must be on 2026-12-29 and include the official URL');
assert(state(itabashi, '2026-12-31', 'burnable') === 'check' && !isPickup(itabashi, '2026-12-31', 'burnable'),
  '板橋 12/31 must be check with no pickup chip');
for (const key of ['2027-01-01', '2027-01-02', '2027-01-03']) assertState(itabashi, key, 'closed');
assert(state(niigata, '2026-12-31', 'burnable') === 'check' && !isPickup(niigata, '2026-12-31', 'burnable'),
  '新潟 12/31 must be check with no regular burnable pickup chip');
for (const key of ['2027-01-01', '2027-01-02', '2027-01-03']) assertState(niigata, key, 'closed');
assert(isPickup(niigata, '2027-01-04', 'burnable'), '新潟 1/4 must return to its normal burnable pickup');
assert(isPickup(kawasaki, '2026-12-31', 'burnable'), '川崎 must retain 12/31 burnable pickup');
for (const key of ['2027-01-01', '2027-01-02', '2027-01-03']) assertState(kawasaki, key, 'closed');
for (const target of [kumamoto, kawasaki, hiroshima]) {
  assert(typeList(target, parseKey('2028-01-01')).length === 0,
    target.label + ' must have no 2028-01-01 pickup');
}
assert(state(hiroshima, '2028-01-01', 'burnable') === 'check',
  '広島 2028-01-01 must be check outside the confirmed 2026-27 season');
assert(state(kawasaki, '2028-01-01', 'burnable') === 'closed',
  '川崎 annual closed rule must recur on 2028-01-01');
assert(state(kumamoto, '2028-01-01', 'burnable') === 'check',
  '熊本 unconfirmed schedule must be check on 2028-01-01');
assert(state(hiroshima, '2026-12-31', 'burnable') === 'closed'
  && state(hiroshima, '2027-01-04', 'burnable') === 'normal',
  '広島 current-season closure must cover 12/31–1/3 and return to normal on 1/4');
for (const key of ['2027-01-01', '2027-01-02', '2027-01-03']) assertState(hiroshima, key, 'closed');

console.log('# check_yearend.mjs');
console.log('NOW=' + nowKey + ' (TZ=' + (process.env.TZ || 'system') + ')');
console.log('Assertions: PASS (Nagoya windows and weekday filter, local check ICS dates/URLs, next pickup, seasonal and annual 2028 rules)');
console.log('相生町 12/30: plastic=' + (isPickup(aioi, '2026-12-30', 'plastic') ? 'pickup' : '—')
  + ', burnable=' + state(aioi, '2026-12-30', 'burnable')
  + '; 1/4 resource=' + state(aioi, '2027-01-04', 'resource')
  + ', burnable=' + (isPickup(aioi, '2027-01-04', 'burnable') ? 'pickup' : '—')
  + '; 1/11 resource=' + (isPickup(aioi, '2027-01-11', 'resource') ? 'pickup' : '—')
  + '; 1/13 nonburnable=' + (isPickup(aioi, '2027-01-13', 'nonburnable') ? 'pickup' : '—')
  + '; 1/27 bulky=' + (isPickup(aioi, '2027-01-27', 'bulky') ? 'pickup' : '—')
  + '; check ICS=' + checkEventsForSeason(aioi).length);
console.log('今池五丁目 NOW=2027-01-10 next nonburnable: ' + dateKey(imaikeJanNext.date)
  + ' state=' + imaikeJanNext.state + ' URL=' + imaikeJanNext.source);
console.log('今池五丁目 check ICS: ' + imaikeCheck[0].date + ' URL=' + imaikeCheck[0].source);
console.log('熊本・江東 check ICS: ' + checkEventsForSeason(kumamoto)[0].date + ' / '
  + checkEventsForSeason(koto)[0].date + '; 神戸: ' + kobeReminders[0].date);
console.log('NOW=2027-12-01 pickup chips on 2028-01-01: 熊本=0, 川崎=0, 広島=0; 広島 state='
  + state(hiroshima, '2028-01-01', 'burnable'));
for (const target of resolved) {
  const events = seasonEvents(target);
  console.log('\n## ' + target.label);
  console.log('source=' + (target.yearend.source_url || '(なし)'));
  console.log('| date | state by type | pickup chips | ICS |');
  console.log('|---|---|---|---|');
  for (let date = new Date(seasonStart); date <= seasonEnd; date = addDays(date, 1)) {
    const key = dateKey(date);
    const states = ORDER.filter(type => target.types[type])
      .map(type => type + '=' + windowState(date, type, target.yearend)).join(' ');
    const pickups = typeList(target, date).join(',') || '—';
    const dayEvents = events.filter(event => event.date === key);
    const ics = dayEvents.map(event => event.kind === 'check'
      ? '確認案内(' + (event.source || 'URLなし') + ')'
      : '収集:' + event.types.join(',')).join(' / ') || '—';
    console.log('| ' + key + ' | ' + states + ' | ' + pickups + ' | ' + ics + ' |');
  }
  const seasonal = events.filter(event => withinSeason(event.date));
  console.log('ICS dates: ' + (seasonal.map(event =>
    event.date + ':' + (event.kind === 'check' ? 'check(URL=' + event.source + ')' : event.types.join('+'))
  ).join(', ') || '—'));
  const dynamic = calendarEvents(target.types, target.yearend, now, 120);
  console.log('NOW=' + nowKey + ' ICS check: ' + (checkEvents(dynamic).map(event =>
    event.date + ' URL=' + event.source
  ).join(', ') || '—'));
}
