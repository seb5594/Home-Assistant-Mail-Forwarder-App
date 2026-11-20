// Tiny DOM helpers. All text goes in as text nodes, so nothing a user types can become markup.

export function h(tag, props, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key.startsWith('on') && typeof value === 'function') {
      element.addEventListener(key.slice(2), value);
    } else if (key === 'class') {
      element.className = value;
    } else if (key === 'value' || key === 'checked' || key === 'disabled' || key === 'selected') {
      element[key] = value;
    } else {
      element.setAttribute(key, value === true ? '' : value);
    }
  }
  append(element, children);
  return element;
}

function append(parent, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    parent.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function clear(element) {
  element.replaceChildren();
  return element;
}

// Icons are static markup defined in this file, never built from user input.
const ICONS = {
  ok: '<circle cx="12" cy="12" r="10" fill="currentColor" opacity=".15"/><path d="M7.5 12.5l3 3 6-6.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
  warn: '<path d="M12 3l10 18H2z" fill="currentColor" opacity=".15"/><path d="M12 9v5m0 3v.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>',
  error: '<circle cx="12" cy="12" r="10" fill="currentColor" opacity=".15"/><path d="M8.5 8.5l7 7m0-7l-7 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>',
  todo: '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="3 3"/>',
  pending: '<circle cx="12" cy="12" r="10" fill="currentColor" opacity=".12"/><path d="M12 7v5l3 2" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
  unknown: '<circle cx="12" cy="12" r="10" fill="currentColor" opacity=".12"/><path d="M9.5 9.5a2.5 2.5 0 114 2c-.9.6-1.5 1-1.5 2m0 3v.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>',
  spinner: '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="3" opacity=".2"/><path d="M21 12a9 9 0 00-9-9" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>',
};

export function icon(name, className = '') {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('class', `status status-${name} ${name === 'spinner' ? 'spin' : ''} ${className}`.trim());
  svg.innerHTML = ICONS[name] || ICONS.unknown;
  return svg;
}

export function toast(message, kind = '') {
  const holder = document.getElementById('toasts');
  const item = h('div', { class: `toast ${kind}` }, message);
  holder.append(item);
  setTimeout(() => item.remove(), kind === 'error' ? 7000 : 3500);
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast('Copied');
  } catch {
    // Clipboard access can be blocked inside the Home Assistant frame; fall back to selecting.
    const field = h('textarea', { style: 'position:fixed;opacity:0' }, text);
    document.body.append(field);
    field.select();
    const copied = document.execCommand('copy');
    field.remove();
    toast(copied ? 'Copied' : 'Select the text and copy it by hand', copied ? '' : 'error');
  }
}

// A value with a copy button, used for DNS records and router settings.
export function copyable(text) {
  return h('span', null,
    h('span', { class: 'value' }, text),
    h('button', { class: 'copy', type: 'button', onclick: () => copyText(text), 'aria-label': `Copy ${text}` }, 'Copy'));
}

export function initialOf(name) {
  return (name || '?').trim().charAt(0).toUpperCase() || '?';
}
