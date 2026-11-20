// Translations: the language is taken from the browser and can be switched in the footer.
// Texts live in i18n/<language>.json. A text may contain {placeholders} and a little markup:
// **bold**, *italic*, `code` and [label](https://link). Everything else is plain text, so
// nothing a user types can become markup.
import { h } from './dom.js';

export const LANGUAGES = { en: 'English', de: 'Deutsch' };
const STORAGE_KEY = 'mail-forwarder-language';

let dictionaries = {};
let current = 'en';

function storedLanguage() {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // storage can be blocked inside the Home Assistant frame
  }
}

function detectLanguage() {
  const stored = storedLanguage();
  if (stored in LANGUAGES) return stored;
  for (const candidate of navigator.languages || [navigator.language]) {
    const code = String(candidate).slice(0, 2).toLowerCase();
    if (code in LANGUAGES) return code;
  }
  return 'en';
}

export async function loadLanguages() {
  const entries = await Promise.all(Object.keys(LANGUAGES).map(async (code) => {
    const response = await fetch(`i18n/${code}.json`);
    return [code, await response.json()];
  }));
  dictionaries = Object.fromEntries(entries);
  setLanguage(detectLanguage(), false);
}

export function language() {
  return current;
}

export function setLanguage(code, remember = true) {
  current = code in LANGUAGES ? code : 'en';
  document.documentElement.lang = current;
  if (remember) {
    try {
      localStorage.setItem(STORAGE_KEY, current);
    } catch {
      // not remembered, the browser language decides next time
    }
  }
}

function lookup(dictionary, key) {
  return key.split('.').reduce((node, part) => (node && typeof node === 'object' ? node[part] : undefined), dictionary);
}

function raw(key) {
  return lookup(dictionaries[current], key) ?? lookup(dictionaries.en, key);
}

export function has(key) {
  return raw(key) !== undefined;
}

function fill(text, params) {
  return text.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match));
}

// Plain text of a translation, with the markup characters removed.
export function t(key, params = {}) {
  const value = raw(key);
  if (typeof value !== 'string') return key;
  return fill(value, params).replace(/\*\*|`/g, '').replace(/\*(.+?)\*/g, '$1').replace(/\[(.+?)\]\(.+?\)/g, '$1');
}

// The same text as DOM nodes: bold, italic, code and links become elements.
const MARKUP = /(\*\*.+?\*\*|`.+?`|\*.+?\*|\[.+?\]\(.+?\))/g;

function renderMarkup(text, params) {
  return text.split(MARKUP).filter(Boolean).map((part) => {
    if (part.startsWith('**')) return h('strong', null, fill(part.slice(2, -2), params));
    if (part.startsWith('`')) return h('code', null, fill(part.slice(1, -1), params));
    if (part.startsWith('*')) return h('em', null, fill(part.slice(1, -1), params));
    const link = part.match(/^\[(.+?)\]\((.+?)\)$/);
    if (link) return h('a', { href: link[2], target: '_blank', rel: 'noopener' }, fill(link[1], params));
    return fill(part, params);
  });
}

// Markup in a text that is not a dictionary key (a value taken from a list).
export function richText(text, params = {}) {
  return renderMarkup(String(text), params);
}

export function rich(key, params = {}) {
  const value = raw(key);
  return typeof value === 'string' ? renderMarkup(value, params) : [key];
}

// A list of texts (steps, tips) as DOM nodes, one entry per item.
export function richList(key, params = {}) {
  const value = raw(key);
  return Array.isArray(value) ? value.map((text) => renderMarkup(String(text), params)) : [];
}

// Plural: key_one / key_other.
export function tn(key, count, params = {}) {
  return t(`${key}_${count === 1 ? 'one' : 'other'}`, { count, ...params });
}

// Pairs such as the glossary: [[term, text], ...]
export function pairs(key) {
  const value = raw(key);
  return Array.isArray(value) ? value : [];
}

// Translates a message that the app sent as {code, params}; falls back to the English text.
export function message(namespace, code, params = {}, fallback = '') {
  const key = `${namespace}.${code}`;
  return has(key) ? t(key, params) : fallback || code;
}
