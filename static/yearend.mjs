export const ORDER = ['burnable', 'resource', 'plastic', 'paper_cloth', 'yard', 'nonburnable', 'bulky'];
export const JDAY = '日月火水木金土';

const dayKey = date => {
  if (typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date)) return date;
  const d = date instanceof Date ? date : new Date(date);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

const asLocalDate = date => {
  if (date instanceof Date) return date;
  const key = dayKey(date);
  const [year, month, day] = key.split('-').map(Number);
  return new Date(year, month - 1, day);
};

function windowMatches(date, window, rule) {
  const d = asLocalDate(date);
  const key = dayKey(d);
  const dateMatches = rule?.repeat_windows
    ? (() => {
        const md = key.slice(5);
        const start = window.start.slice(5);
        const end = window.end.slice(5);
        return start <= end ? start <= md && md <= end : md >= start || md <= end;
      })()
    : window.start <= key && key <= window.end;
  return dateMatches && (!window.weekdays || window.weekdays.includes(JDAY[d.getDay()]));
}

function outsideCurrentSeasonCheck(date, rule) {
  if (!rule?.check_outside_season) return false;
  const d = asLocalDate(date);
  const md = dayKey(d).slice(5);
  if (!(md >= '12-29' || md <= '01-04')) return false;
  const winterYear = d.getMonth() === 11 ? d.getFullYear() : d.getFullYear() - 1;
  return winterYear !== rule.season_year;
}

function matchingWindows(date, type, rule) {
  return (rule?.windows || []).filter(window =>
    windowMatches(date, window, rule) && (!type || !window.types || window.types.includes(type))
  );
}

export function windowState(date, type, rule) {
  const matching = matchingWindows(date, type, rule);
  if (matching.some(window => window.state === 'check')) return 'check';
  if (matching.some(window => window.state === 'closed')) return 'closed';
  return outsideCurrentSeasonCheck(date, rule) ? 'check' : 'normal';
}

export function checkSource(date, rule, type) {
  const check = matchingWindows(date, type, rule).find(window => window.state === 'check');
  return check?.source_url || (outsideCurrentSeasonCheck(date, rule) ? rule?.source_url : '') || rule?.source_url || '';
}

export function regularPickup(type, date) {
  const d = asLocalDate(date);
  const day = JDAY[d.getDay()];
  const nth = Math.ceil(d.getDate() / 7);
  return (type.days || []).includes(day) && (!type.weeks || type.weeks.includes(nth));
}

export function checkTypesOn(types, date, rule) {
  const d = asLocalDate(date);
  const weekday = JDAY[d.getDay()];
  return ORDER.filter(type => types[type] && (types[type].days || []).includes(weekday) && windowState(date, type, rule) === 'check');
}

function checkEventTypesOn(types, date, rule) {
  const d = asLocalDate(date);
  return ORDER.filter(type => {
    if (!types[type] || windowState(date, type, rule) !== 'check') return false;
    const checkWindows = matchingWindows(date, type, rule).filter(window => window.state === 'check');
    if (!checkWindows.length) return outsideCurrentSeasonCheck(date, rule);
    return checkWindows.some(window =>
      !window.weekdays || (types[type].days || []).some(day => window.weekdays.includes(day))
    );
  });
}

export function typesOn(types, date, rule) {
  return ORDER.filter(type => types[type] &&
    windowState(date, type, rule) === 'normal' &&
    regularPickup(types[type], date)
  );
}

export function nextPickup(type, key, from, rule, days = 70) {
  for (let i = 0; i < days; i++) {
    const date = new Date(asLocalDate(from));
    date.setDate(date.getDate() + i);
    if (!regularPickup(type, date)) continue;
    const state = windowState(date, key, rule);
    if (state === 'check') return { date, state, source: checkSource(date, rule, key) };
    if (state === 'normal') return { date, state, source: '' };
  }
  return null;
}

export function calendarEvents(types, rule, from, days = 120) {
  const events = [];
  let reminderAdded = false;

  for (let i = 0; i < days; i++) {
    const date = new Date(asLocalDate(from));
    date.setDate(date.getDate() + i);
    const key = dayKey(date);
    const pickupTypes = typesOn(types, date, rule);
    if (pickupTypes.length) events.push({ date: key, kind: 'pickup', types: pickupTypes });

    if (!reminderAdded) {
      const checkTypes = checkEventTypesOn(types, date, rule);
      if (checkTypes.length) {
        events.push({ date: key, kind: 'check', types: checkTypes, source: checkSource(date, rule, checkTypes[0]) });
        reminderAdded = true;
      }
    }
  }
  return events;
}
