// Turns a health check from the app (kind, code, params) into text in the current language.
import { has, richList, t } from './i18n.js';

export function describeCheck(check) {
  const params = check.params || {};
  const base = `checks.${check.kind}`;
  const key = `${base}.${check.code}`;
  let detail = '';
  if (has(`${key}.detail`)) detail = t(`${key}.detail`, params);
  else if (params.probe) detail = t(`probe.${params.probe}`, params);
  return { title: t(`${base}.title`, params), detail, fix: richList(`${key}.fix`, params) };
}

// A message with {code, params} from the app (delivery problem, DNS update result) as text.
export function describeMessage(namespace, entry) {
  if (!entry || !entry.code) return '';
  const key = `${namespace}.${entry.code}`;
  const params = { ...(entry.params || {}) };
  if (namespace === 'ddns' && params.outcome) params.outcome = t(`ddns.outcome.${params.outcome}`);
  return has(key) ? t(key, params) : entry.code;
}
