// Small formatting helpers shared by the views.
import { t } from './i18n.js';

export function timeAgo(seconds) {
  if (!seconds) return t('common.never');
  const delta = Math.max(0, Date.now() / 1000 - seconds);
  if (delta < 45) return t('common.just_now');
  if (delta < 3600) return t('common.min_ago', { n: Math.round(delta / 60) });
  if (delta < 86400) return t('common.h_ago', { n: Math.round(delta / 3600) });
  return t('common.d_ago', { n: Math.round(delta / 86400) });
}

export function inFuture(seconds) {
  const delta = seconds - Date.now() / 1000;
  if (delta <= 0) return t('common.now');
  if (delta < 3600) return t('common.in_min', { n: Math.ceil(delta / 60) });
  return t('common.in_h', { n: Math.round(delta / 3600) });
}

export function clock(seconds) {
  return new Date(seconds * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
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
