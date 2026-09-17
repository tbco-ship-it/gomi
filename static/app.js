(async function () {
  const cssHref = document.querySelector('link[href*="static/style.css"]').getAttribute('href');
  const v = (cssHref.match(/\?v=([^&]+)/) || [])[1] || '';
  const base = cssHref.replace(/static\/style\.css.*$/, '');
  const $ = id => document.getElementById(id);
  const JDAY = '日月火水木金土';
  const ORDER = ['burnable', 'resource', 'plastic', 'paper_cloth', 'nonburnable', 'bulky'];
  const COLOR = { burnable: '#ff7a00', resource: '#3182f6', plastic: '#00b06f', paper_cloth: '#8b5cf6', nonburnable: '#6b7684', bulky: '#f04452' };
  const TAG = { ...COLOR, burnable: '#d95d00', plastic: '#00885a' }; // white text needs ≥3:1
  const SHORT = { resource: '資源', plastic: 'プラ', paper_cloth: '古紙', nonburnable: '不燃', bulky: '粗大' };
  const short = (k, l) => SHORT[k] || l.replace(/ごみ$/, '');
  const TYPE_EN = { burnable: 'Burnable', resource: 'Cans · bottles · PET', plastic: 'Plastic', paper_cloth: 'Paper & cloth', nonburnable: 'Non-burnable', bulky: 'Bulky' };
  const SHORT_EN = { burnable: 'Burn', resource: 'Cans', plastic: 'Plastic', paper_cloth: 'Paper', nonburnable: 'Non-burn', bulky: 'Bulky' };
  const I18N = {
    nav_search: 'Search by address', nav_cities: 'Covered cities', nav_nenmatsu: 'Year-end', hero_h1: 'Garbage day lookup', hero_sub: 'Type your town name to see what goes out today and tomorrow, plus this week\u2019s pickup days. Official city data.',
    pick_title: 'Pick your address', pick_label: 'Town / chome', pick_hint: 'Kanji, hiragana or romaji all work. Your last address is remembered.',
    cities_h2: 'Covered cities', cities_all: 'All', today_tomorrow: 'Today & tomorrow', ics: 'Add to calendar (.ics)', remember: 'Remember this address',
    types_h2: 'Collection day by type', exc_h2: 'Differences by block', near_h2: 'Nearby areas', placeholder: 'e.g. Oyodonaka, おおよどなか, 大淀中',
    geo_btn: 'Use my location', geo_wait: 'Finding your location\u2026', geo_denied: 'Location access was denied. Type your town name instead.', geo_fail: 'Could not resolve your location. Type your town name instead.',
    geo_nocity: 'This city is not covered yet. See the city list below.', geo_pick: 'Close match \u2014 pick your block:', geo_notown: 'Town not found. Try another spelling:', geo_ok: 'Location: ',
  };
  const JAS = { geo_wait: '現在地を取得中…', geo_denied: '位置情報が許可されていません。町名を入力してください。', geo_fail: '現在地を判定できませんでした。町名を入力してください。', geo_nocity: 'この場所の市区はまだ対応していません(下の対応市をご覧ください)。', geo_pick: '近い候補です。丁目を選んでください。', geo_notown: '町名を特定できませんでした。表記を変えてみてください。', geo_ok: '現在地: ' };
  const T = k => EN() ? I18N[k] : JAS[k];
  const JA = {}; // filled from the DOM on first toggle
  let lang = localStorage.getItem('gomi.lang') || 'ja';
  const EN = () => lang === 'en';
  const DOW_EN = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  function applyLang() {
    document.documentElement.lang = lang;
    document.querySelectorAll('[data-i18n]').forEach(el => { const k = el.dataset.i18n; if (!(k in JA)) JA[k] = el.textContent; el.textContent = EN() ? (I18N[k] || JA[k]) : JA[k]; });
    const ph = document.getElementById('addr'); if (ph) { if (!JA.placeholder) JA.placeholder = ph.placeholder; ph.placeholder = EN() ? I18N.placeholder : JA.placeholder; }
    const b = document.getElementById('lang'); if (b) b.textContent = EN() ? '日本語' : 'EN';
  }
  applyLang();
  const langBtn = document.getElementById('lang');
  if (langBtn) langBtn.addEventListener('click', () => { lang = EN() ? 'ja' : 'en'; localStorage.setItem('gomi.lang', lang); applyLang(); if (window.__rerender) window.__rerender(); });
  const now = new Date(); now.setHours(0, 0, 0, 0);
  const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const md = d => EN() ? `${DOW_EN[d.getDay()]} ${d.getMonth() + 1}/${d.getDate()}` : `${d.getMonth() + 1}/${d.getDate()}(${JDAY[d.getDay()]})`;
  const yearend = d => (d.getMonth() === 11 && d.getDate() === 31) || (d.getMonth() === 0 && d.getDate() <= 3);
  const nth = d => Math.ceil(d.getDate() / 7);
  // t: {days:[..], weeks:[..]|null}
  const on = (t, d) => !yearend(d) && (t.days || []).includes(JDAY[d.getDay()]) && (!t.weeks || t.weeks.includes(nth(d)));
  const typesOn = (types, d) => ORDER.filter(k => types[k] && on(types[k], d));
  const nextOf = (t, from) => { for (let i = 0; i < 70; i++) { const d = addDays(from, i); if (on(t, d)) return d; } return null; };
  const rel = d => { const n = Math.round((d - now) / 864e5); return EN() ? (n === 0 ? 'Today' : n === 1 ? 'Tomorrow' : md(d)) : (n === 0 ? '今日' : n === 1 ? '明日' : n === 2 ? '明後日' : md(d)); };

  function render(types, name, slug, root) {
    const today = typesOn(types, now), tomorrow = typesOn(types, addDays(now, 1));
    const lbl = k => EN() ? TYPE_EN[k] : types[k].label;
    const sep = EN() ? ' + ' : '・';
    let head, sub, cls;
    if (tomorrow.length) { head = EN() ? 'Tomorrow: ' + tomorrow.map(lbl).join(sep) : '明日は ' + tomorrow.map(lbl).join(sep); cls = 'balanced'; }
    else { const nx = ORDER.filter(k => types[k]).map(k => [k, nextOf(types[k], addDays(now, 1))]).filter(x => x[1]).sort((a, b) => a[1] - b[1])[0]; head = nx ? (EN() ? `Next: ${lbl(nx[0])} ${rel(nx[1])}` : `次は ${rel(nx[1])} ${lbl(nx[0])}`) : (EN() ? 'No collection scheduled' : '収集予定なし'); cls = 'quiet'; }
    sub = EN() ? (today.length ? `Today (${md(now)}): ${today.map(lbl).join(sep)}.` : `Today (${md(now)}): no collection.`) : (today.length ? `今日 ${md(now)} は${today.map(lbl).join('・')}の日です。` : `今日 ${md(now)} の収集はありません。`);
    const t0 = ORDER.filter(k => types[k]).map(k => [k, nextOf(types[k], now)]).filter(x => x[1]).sort((a, b) => a[1] - b[1]);
    const upcoming = t0.map(([k, d]) => `<div class="item"><span class="dot" style="background:${COLOR[k]}"></span><span class="txt"><b>${lbl(k)}</b>${EN() ? `<span class="tsub">${types[k].label}</span>` : ''}${types[k].time ? `<span class="tsub">${types[k].time}</span>` : ''}</span><span class="when">${rel(d)}</span></div>`).join('');
    const week = Array.from({ length: 7 }, (_, i) => { const d = addDays(now, i); const ks = typesOn(types, d); return `<div class="day${i === 0 ? ' today' : ''}"><span class="dow">${i === 0 ? (EN() ? 'Today' : '今日') : (EN() ? DOW_EN[d.getDay()] : JDAY[d.getDay()])}</span><span class="dnum">${d.getDate()}</span><span class="dots">${ks.map(k => `<span class="tag" style="background:${TAG[k]}">${EN() ? SHORT_EN[k] : short(k, types[k].label)}</span>`).join('')}</span></div>`; }).join('');
    if (root) {
      root.innerHTML = `<section class="sheet ${cls}"><p class="sheet-label">${name}</p><div class="sheet-num"><span class="num small-num">${head}</span></div><p class="sheet-title">${sub}</p><div class="stack">${upcoming}</div><p class="sheet-actions"><a class="next" href="${base}${slug}/">${EN() ? 'Open this address (block differences · .ics)' : 'この住所のページ(番地の違い・.ics)'}</a></p></section><div class="week">${week}</div>`;
    } else {
      const sheet = $('today'); sheet.classList.remove('balanced', 'quiet'); sheet.classList.add(cls);
      $('headline').textContent = head; $('sub').textContent = sub; $('upcoming').innerHTML = upcoming; $('week').innerHTML = week;
    }
    return { today, tomorrow };
  }

  function ics(types, name) {
    const lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//ごみの日ナビ//JP', 'CALSCALE:GREGORIAN', `X-WR-CALNAME:${name} ごみ収集日`];
    for (let i = 0; i < 120; i++) {
      const d = addDays(now, i); const ks = typesOn(types, d); if (!ks.length) continue;
      const ymd = iso(d).replace(/-/g, ''), nxt = iso(addDays(d, 1)).replace(/-/g, '');
      lines.push('BEGIN:VEVENT', `UID:${ymd}-${ks.join('-')}@gomi`, `DTSTAMP:${ymd}T000000Z`, `DTSTART;VALUE=DATE:${ymd}`, `DTEND;VALUE=DATE:${nxt}`, `SUMMARY:🗑 ${ks.map(k => types[k].label).join('・')}`, `DESCRIPTION:${name}${ks.map(k => types[k].time ? ` ${types[k].label} ${types[k].time}` : '').join('')}`, 'END:VEVENT');
    }
    lines.push('END:VCALENDAR');
    return 'data:text/calendar;charset=utf-8,' + encodeURIComponent(lines.join('\r\n'));
  }

  // town page
  const sched = $('sched');
  if (sched) {
    const S = JSON.parse(sched.textContent);
    render(S.types, S.name, S.slug, null);
    window.__rerender = () => render(S.types, S.name, S.slug, null);
    $('ics').href = ics(S.types, S.name);
    $('remember').addEventListener('click', () => localStorage.setItem('gomi.slug', S.slug));
    return;
  }

  // home: typeahead
  const input = $('addr'); if (!input) return;
  const out = $('result'), menu = $('addr-menu');
  const RAW = await (await fetch(base + 'static/index.json?v=' + v)).json();
  const D = RAW.items.map(([c, w, we, t, ch, r, k, s, en, ty]) => ({ c, cn: RAW.cities[c], w, we, t, ch, r, kana: k, s, en, ty: Object.fromEntries(Object.entries(ty).map(([tk, [d, wk, tm]]) => [tk, { l: RAW.labels[c][tk], d, w: wk, tm }])) }));
  const kata2hira = s => s.replace(/[ァ-ヶ]/g, c => String.fromCharCode(c.charCodeAt(0) - 0x60));
  const norm = s => kata2hira(s.toLowerCase()).replace(/[\s　]+/g, '').replace(/ヶ/g, 'ケ').replace(/丁目|ちょうめ/g, '');
  D.forEach(e => { e.k = norm(e.cn + e.w + e.t + e.ch); e.k2 = norm(e.w + e.t + e.ch); e.rk = e.r.toLowerCase().replace(/\s+/g, ''); e.kn = kata2hira(e.kana || '').replace(/\s+/g, ''); e.name = e.w + e.t + e.ch; });
  let items = [], active = -1;
  function open(q) {
    const toks = q.split(/[\s　、,]+/).map(norm).filter(Boolean); const nq = toks.join('');
    if (!nq) { items = []; menu.innerHTML = `<li class="empty">${EN() ? 'Type a town name (e.g. Oyodonaka) or a ward.' : '町名(例: 大淀中)や区名を入れてください。'}</li>`; menu.hidden = false; return; }
    const score = e => { let s = 0; for (const t of toks) { if (e.k2.startsWith(t)) s += 3; else if (e.kn.startsWith(t)) s += 2; else if (e.k.includes(t) || e.rk.includes(t) || e.kn.includes(t)) s += 1; else return -1; } return s; };
    showItems(D.map(e => [score(e), e]).filter(x => x[0] > 0).sort((a, b) => b[0] - a[0] || a[1].k.localeCompare(b[1].k, 'ja')).slice(0, 10).map(x => x[1]));
  }
  function showItems(list) {
    items = list;
    menu.innerHTML = items.length ? items.map((e, i) => `<li role="option" data-i="${i}" ${i === active ? 'aria-selected="true"' : ''}>${e.name}<small class="muted"> ${e.cn}</small><span class="ro">${e.en} · ${e.c[0].toUpperCase() + e.c.slice(1)}</span></li>`).join('') : `<li class="empty">${EN() ? 'No match. Try the ward name or another spelling.' : '見つかりません。区名や漢字表記を変えてみてください。'}</li>`;
    menu.hidden = false; input.setAttribute('aria-expanded', 'true');
  }
  function close() { menu.hidden = true; active = -1; input.setAttribute('aria-expanded', 'false'); }
  function choose(e) {
    input.value = e.name; close();
    const types = {}; for (const k in e.ty) types[k] = { label: e.ty[k].l, days: e.ty[k].d, weeks: e.ty[k].w, time: e.ty[k].tm };
    render(types, e.cn + e.name + (EN() ? ` — ${e.en}` : ''), e.s, out); localStorage.setItem('gomi.slug', e.s); window.__rerender = () => choose(e);
  }
  input.addEventListener('focus', () => { setTimeout(() => input.select(), 0); open(input.value); });
  input.addEventListener('input', () => { active = -1; open(input.value); });
  input.addEventListener('keydown', ev => {
    if (menu.hidden) return;
    if (ev.key === 'ArrowDown') { active = Math.min(active + 1, items.length - 1); open(input.value); ev.preventDefault(); }
    else if (ev.key === 'ArrowUp') { active = Math.max(active - 1, 0); open(input.value); ev.preventDefault(); }
    else if (ev.key === 'Enter') { const it = items[active >= 0 ? active : 0]; if (it) choose(it); ev.preventDefault(); }
    else if (ev.key === 'Escape') close();
  });
  menu.addEventListener('mousedown', ev => { const li = ev.target.closest('li[data-i]'); if (li) { choose(items[+li.dataset.i]); ev.preventDefault(); } });
  input.addEventListener('blur', () => setTimeout(close, 120));
  const remembered = D.find(e => e.s === localStorage.getItem('gomi.slug')) || D.find(e => e.s === 'osaka/kita/oyodonaka-2');
  if (remembered) choose(remembered);

  // GPS: browser position → GSI reverse geocoder (muniCd + 町丁目) → index entry in that ward.
  const geoBtn = $('geo'), geoMsg = $('geo-msg');
  if (!geoBtn) return;
  if (!('geolocation' in navigator)) { geoBtn.hidden = true; return; }
  const KN = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9 };
  // 西新宿二丁目 → 西新宿2丁目 (only when a 丁目 follows, so 一番町 etc. stay as written)
  const kanji2num = s => /[一二三四五六七八九十]丁目/.test(s) ? s.replace(/[一二三四五六七八九]?十[一二三四五六七八九]?|[一二三四五六七八九]/g, t => { if (t.includes('十')) { const [a, b] = t.split('十'); return String((a ? KN[a] : 1) * 10 + (b ? KN[b] : 0)); } return String(KN[t]); }) : s;
  const nums = s => (s.match(/\d+/g) || []).map(Number);
  // "1~4丁目" → [1,2,3,4]; "2・3丁目" / "1丁目、2丁目" → [2,3]; "西1丁目~西9丁目" → [1..9]
  const chomeSet = ch => ch.split(/[、・,]/).flatMap(tok => { const n = nums(tok); if (n.length === 2 && /[~〜～から]/.test(tok)) { const r = []; for (let i = n[0]; i <= n[1]; i++) r.push(i); return r; } return n; });
  const letters = s => s.replace(/[\d丁目~〜～から・、,の\s]/g, '');
  function locate(muniCd, lv01) {
    const cw = RAW.muni[muniCd]; if (!cw) return { status: 'nocity' };
    const [ce, w] = cw;
    const q = norm(kanji2num(lv01)); // 西新宿2 / 北1条西2 / 手取本町
    const cands = D.filter(e => e.c === ce && (!w || e.w.startsWith(w)));
    const exact = cands.filter(e => norm(e.t + e.ch) === q);
    if (exact.length === 1) return { status: 'ok', e: exact[0] };
    const towns = cands.filter(e => q.startsWith(norm(e.t)));
    if (!towns.length) return { status: 'notown' };
    const L = Math.max(...towns.map(e => norm(e.t).length));
    const same = towns.filter(e => norm(e.t).length === L);
    const rest = q.slice(L), n = nums(rest)[0], lt = letters(rest);
    const hit = same.filter(e => e.ch && n !== undefined && chomeSet(e.ch).includes(n) && [...lt].every(c => letters(e.ch).includes(c)));
    if (hit.length === 1) return { status: 'ok', e: hit[0] };
    if (hit.length > 1) return { status: 'pick', list: hit };
    const whole = same.filter(e => !e.ch);
    if (whole.length === 1 && same.length === 1) return { status: 'ok', e: whole[0] };
    return { status: 'pick', list: same.slice(0, 10) };
  }
  const say = (k, extra, err) => { geoMsg.textContent = (k ? T(k) : '') + (extra || ''); geoMsg.classList.toggle('err', !!err); };
  geoBtn.addEventListener('click', () => {
    geoBtn.disabled = true; say('geo_wait');
    navigator.geolocation.getCurrentPosition(async pos => {
      try {
        const { latitude: lat, longitude: lon } = pos.coords;
        const r = (await (await fetch(`https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress?lat=${lat}&lon=${lon}`)).json()).results || {};
        if (!r.muniCd) { say('geo_fail', '', true); return; }
        const res = locate(r.muniCd, r.lv01Nm || '');
        if (res.status === 'ok') { choose(res.e); say('geo_ok', r.lv01Nm); }
        else if (res.status === 'pick') { input.value = r.lv01Nm; input.focus(); showItems(res.list); say('geo_pick'); }
        else if (res.status === 'notown') { input.value = r.lv01Nm; input.focus(); say('geo_notown', '', true); }
        else say('geo_nocity', '', true);
      } catch (e) { say('geo_fail', '', true); }
      finally { geoBtn.disabled = false; }
    }, err => { geoBtn.disabled = false; say(err.code === 1 ? 'geo_denied' : 'geo_fail', '', true); }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 });
  });
})();
