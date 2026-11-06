export const ORDER = ['burnable', 'resource', 'plastic', 'paper_cloth', 'yard', 'nonburnable', 'bulky'];
export const JDAY = '日月火水木金土';

const dayKey = date => {
  if (typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date)) return date;
  const d = date instanceof Date ? date : new Date(date);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

export function windowState(date, type, rule) {
  const key = dayKey(date);
  const matching = (rule?.windows || []).filter(w =>
    w.start <= key && key <= w.end && (!w.types || w.types.includes(type))
  );
  if (matching.some(w => w.state === 'check')) return 'check';
  if (matching.some(w => w.state === 'closed')) return 'closed';
  return 'normal';
}

export function checkSource(date, rule) {
  const key = dayKey(date);
  const check = (rule?.windows || []).find(w =>
    w.state === 'check' && w.start <= key && key <= w.end
  );
  return check?.source_url || rule?.source_url || '';
}

export function regularPickup(type, date) {
  const day = JDAY[date.getDay()];
  const nth = Math.ceil(date.getDate() / 7);
  return (type.days || []).includes(day) && (!type.weeks || type.weeks.includes(nth));
}

export function typesOn(types, date, rule) {
  return ORDER.filter(type => types[type] &&
    windowState(date, type, rule) === 'normal' &&
    regularPickup(types[type], date)
  );
}

export function calendarEvents(types, rule, from, days = 120) {
  const events = [];
  const reminderDate = checkReminderDate(rule);
  const reminderSource = checkSource(reminderDate, rule);

  for (let i = 0; i < days; i++) {
    const date = new Date(from);
    date.setDate(date.getDate() + i);
    const key = dayKey(date);
    const pickupTypes = typesOn(types, date, rule);
    if (pickupTypes.length) events.push({ date: key, kind: 'pickup', types: pickupTypes });
    if (key === reminderDate) events.push({ date: key, kind: 'check', types: [], source: reminderSource });
  }
  return events;
}

export function checkReminderDate(rule) {
  return (rule?.windows || [])
    .filter(w => w.state === 'check')
    .map(w => w.start)
    .sort()[0] || '';
}
