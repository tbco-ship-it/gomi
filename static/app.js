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
  const now = new Date(); now.setHours(0, 0, 0, 0);
  const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const md = d => `${d.getMonth() + 1}/${d.getDate()}(${JDAY[d.getDay()]})`;
  const yearend = d => (d.getMonth() === 11 && d.getDate() === 31) || (d.getMonth() === 0 && d.getDate() <= 3);
  const nth = d => Math.ceil(d.getDate() / 7);
  // t: {days:[..], weeks:[..]|null}
  const on = (t, d) => !yearend(d) && (t.days || []).includes(JDAY[d.getDay()]) && (!t.weeks || t.weeks.includes(nth(d)));
  const typesOn = (types, d) => ORDER.filter(k => types[k] && on(types[k], d));
  const nextOf = (t, from) => { for (let i = 0; i < 70; i++) { const d = addDays(from, i); if (on(t, d)) return d; } return null; };
  const rel = d => { const n = Math.round((d - now) / 864e5); return n === 0 ? '今日' : n === 1 ? '明日' : n === 2 ? '明後日' : md(d); };

  function render(types, name, slug, root) {
    const today = typesOn(types, now), tomorrow = typesOn(types, addDays(now, 1));
    const lbl = k => types[k].label;
    let head, sub, cls;
    if (tomorrow.length) { head = '明日は ' + tomorrow.map(lbl).join('・'); cls = 'balanced'; }
    else { const nx = ORDER.filter(k => types[k]).map(k => [k, nextOf(types[k], addDays(now, 1))]).filter(x => x[1]).sort((a, b) => a[1] - b[1])[0]; head = nx ? `次は ${rel(nx[1])} ${lbl(nx[0])}` : '収集予定なし'; cls = 'quiet'; }
    sub = today.length ? `今日 ${md(now)} は${today.map(lbl).join('・')}の日です。` : `今日 ${md(now)} の収集はありません。`;
    const t0 = ORDER.filter(k => types[k]).map(k => [k, nextOf(types[k], now)]).filter(x => x[1]).sort((a, b) => a[1] - b[1]);
    const upcoming = t0.map(([k, d]) => `<div class="item"><span class="dot" style="background:${COLOR[k]}"></span><b>${lbl(k)}</b>${types[k].time ? `<span class="tsub"> ${types[k].time}</span>` : ''}<span class="when">${rel(d)}</span></div>`).join('');
    const week = Array.from({ length: 7 }, (_, i) => { const d = addDays(now, i); const ks = typesOn(types, d); return `<div class="day${i === 0 ? ' today' : ''}"><span class="dow">${i === 0 ? '今日' : JDAY[d.getDay()]}</span><span class="dnum">${d.getDate()}</span><span class="dots">${ks.map(k => `<span class="tag" style="background:${TAG[k]}">${short(k, lbl(k))}</span>`).join('')}</span></div>`; }).join('');
    if (root) {
      root.innerHTML = `<section class="sheet ${cls}"><p class="sheet-label">${name}</p><div class="sheet-num"><span class="num small-num">${head}</span></div><p class="sheet-title">${sub}</p><div class="stack">${upcoming}</div><p class="sheet-actions"><a class="next" href="${base}${slug}/">この住所のページ(番地の違い・.ics)</a></p></section><div class="week">${week}</div>`;
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
    $('ics').href = ics(S.types, S.name);
    $('remember').addEventListener('click', () => localStorage.setItem('gomi.slug', S.slug));
    return;
  }

  // home: typeahead
  const input = $('addr'); if (!input) return;
  const out = $('result'), menu = $('addr-menu');
  const D = await (await fetch(base + 'static/index.json?v=' + v)).json();
  const norm = s => s.toLowerCase().replace(/[\s　]+/g, '').replace(/ヶ/g, 'ケ').replace(/丁目|ちょうめ/g, '');
  D.forEach(e => { e.k = norm(e.cn + e.w + e.t + e.ch); e.k2 = norm(e.w + e.t + e.ch); e.rk = e.r.toLowerCase(); e.name = e.w + e.t + e.ch; });
  let items = [], active = -1;
  function open(q) {
    const nq = norm(q);
    if (!nq) { items = []; menu.innerHTML = '<li class="empty">町名(例: 大淀中)や区名を入れてください。</li>'; menu.hidden = false; return; }
    const toks = nq.split(/[、,]/).filter(Boolean);
    const score = e => { let s = 0; for (const t of toks) { if (e.k2.startsWith(t)) s += 3; else if (e.k.includes(t) || e.rk.includes(t)) s += 1; else return -1; } return s; };
    items = D.map(e => [score(e), e]).filter(x => x[0] > 0).sort((a, b) => b[0] - a[0] || a[1].k.localeCompare(b[1].k, 'ja')).slice(0, 10).map(x => x[1]);
    menu.innerHTML = items.length ? items.map((e, i) => `<li role="option" data-i="${i}" ${i === active ? 'aria-selected="true"' : ''}>${e.name}<small class="muted"> ${e.cn}</small></li>`).join('') : '<li class="empty">見つかりません。区名や漢字表記を変えてみてください。</li>';
    menu.hidden = false; input.setAttribute('aria-expanded', 'true');
  }
  function close() { menu.hidden = true; active = -1; input.setAttribute('aria-expanded', 'false'); }
  function choose(e) {
    input.value = e.name; close();
    const types = {}; for (const k in e.ty) types[k] = { label: e.ty[k].l, days: e.ty[k].d, weeks: e.ty[k].w, time: e.ty[k].tm };
    render(types, e.cn + e.name, e.s, out); localStorage.setItem('gomi.slug', e.s);
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
})();
