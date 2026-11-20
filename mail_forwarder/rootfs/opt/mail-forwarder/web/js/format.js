// Small formatting helpers shared by the views.

export function timeAgo(seconds) {
  if (!seconds) return 'never';
  const delta = Math.max(0, Date.now() / 1000 - seconds);
  if (delta < 45) return 'just now';
  if (delta < 3600) return `${Math.round(delta / 60)} min ago`;
  if (delta < 86400) return `${Math.round(delta / 3600)} h ago`;
  return `${Math.round(delta / 86400)} d ago`;
}

export function inFuture(seconds) {
  const delta = seconds - Date.now() / 1000;
  if (delta <= 0) return 'now';
  if (delta < 3600) return `in ${Math.ceil(delta / 60)} min`;
  return `in ${Math.round(delta / 3600)} h`;
}

export function clock(seconds) {
  return new Date(seconds * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function plural(count, one, many) {
  return `${count} ${count === 1 ? one : many}`;
}

// A friendly name for well-known mailbox providers.
export function providerOf(address) {
  const domain = (address.split('@')[1] || '').toLowerCase();
  if (['gmail.com', 'googlemail.com'].includes(domain)) return 'Gmail';
  if (/^(hotmail|outlook|live|msn)\./.test(domain)) return 'Outlook';
  if (domain === 'web.de') return 'WEB.DE';
  if (/^gmx\./.test(domain)) return 'GMX';
  if (['icloud.com', 'me.com'].includes(domain)) return 'iCloud';
  return '';
}

export function allAddresses(config) {
  const list = [];
  for (const person of config.people) {
    for (const entry of person.addresses) {
      list.push({ address: `${entry.local}@${entry.domain}`, person, enabled: person.enabled });
    }
  }
  return list;
}
