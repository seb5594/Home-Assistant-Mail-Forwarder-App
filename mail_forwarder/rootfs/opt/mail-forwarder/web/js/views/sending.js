// Sending: how a forwarded message leaves this app and reaches the real inbox.
import { api } from '../api.js';
import { attempt, save } from '../context.js';
import { h, icon } from '../dom.js';
import { allAddresses, timeAgo } from '../format.js';

// The form is kept outside the page so that a refresh of the page never wipes what is typed.
let draft = null;
let draftSource = '';
let dirty = false;

function ensureDraft(delivery) {
  const source = JSON.stringify(delivery);
  if (!draft || (!dirty && source !== draftSource)) {
    draft = structuredClone(delivery);
    draft.relay.password = '';
    draftSource = source;
    dirty = false;
  }
}

function field(label, input, hint) {
  return h('label', { class: 'field' }, label, input, hint ? h('span', { class: 'hint' }, hint) : null);
}

function bound(type, key, target, extra = {}) {
  return h('input', { type, value: target[key] ?? '', autocomplete: 'off', autocapitalize: 'none', spellcheck: 'false',
    oninput: (event) => { target[key] = type === 'number' ? Number(event.target.value) : event.target.value; dirty = true; }, ...extra });
}

function modeChoice(ctx) {
  const options = [
    ['relay', 'Through a sending service', 'Recommended. Reliable, free for private use, works from any home connection.'],
    ['direct', 'Directly from here', 'Advanced. Big providers like Gmail and Outlook usually reject or hide mail that comes from a home connection.'],
  ];
  return h('div', { class: 'choice-grid' }, options.map(([id, title, text]) =>
    h('button', { class: 'choice', type: 'button', 'aria-pressed': String(draft.mode === id), onclick: () => {
      draft.mode = id;
      dirty = true;
      ctx.render(true);
    } }, h('strong', null, title), h('span', null, text))));
}

function relaySection(state, ctx) {
  const preset = state.presets.find((item) => item.id === draft.relay.preset) || state.presets[state.presets.length - 1];
  const onlyDuck = !state.config.domains.some((d) => d.kind === 'own');
  const chips = h('div', { class: 'subtabs' }, state.presets.map((item) =>
    h('button', { class: 'subtab', type: 'button', 'aria-pressed': String(item.id === preset.id), onclick: () => {
      draft.relay = { ...draft.relay, preset: item.id, host: item.host, port: item.port, security: item.security };
      dirty = true;
      ctx.render(true);
    } }, item.name, item.recommended ? ' ★' : '')));

  const security = h('select', { onchange: (event) => { draft.relay.security = event.target.value; dirty = true; } },
    [['starttls', 'STARTTLS (port 587)'], ['ssl', 'SSL/TLS (port 465)'], ['none', 'None (not recommended)']]
      .map(([value, label]) => h('option', { value, selected: draft.relay.security === value }, label)));

  const sender = bound('email', 'sender_address', draft, { placeholder: 'forwarder@your-domain.com' });
  const suggestions = [];
  const firstOwn = state.config.domains.find((d) => d.kind === 'own');
  if (firstOwn) suggestions.push(`forwarder@${firstOwn.name}`);
  if (draft.relay.username.includes('@')) suggestions.push(draft.relay.username);

  return h('div', { class: 'stack' },
    h('h3', null, 'Which service?'), chips,
    h('div', { class: 'note' }, h('p', null, h('strong', null, preset.name), ': ', preset.summary),
      preset.needs_own_domain && onlyDuck
        ? h('p', null, h('strong', null, 'You only have a DuckDNS domain. '), 'This service needs a domain of your own, pick Gmail or WEB.DE instead, or add a domain first.') : null),
    h('ol', { class: 'how' }, preset.steps.map((step) => h('li', null, step))),
    preset.website ? h('p', null, h('a', { href: preset.website, target: '_blank', rel: 'noopener' }, `Open ${preset.name}`)) : null,
    h('div', { class: 'grid grid-2' },
      field('Server', bound('text', 'host', draft.relay, { placeholder: 'smtp.example.com' })),
      field('Port', bound('number', 'port', draft.relay)),
      field('Connection security', security),
      field(preset.username_label, bound('text', 'username', draft.relay)),
      field(preset.password_label, bound('password', 'password', draft.relay, {
        placeholder: state.config.delivery.relay.password_set ? 'Saved, type to replace' : '' }))),
    field('Sender address', sender, 'Forwarded mail is sent from this address. The sending service must allow it, see the steps above.'),
    suggestions.length ? h('div', { class: 'row' }, h('span', { class: 'muted small' }, 'Use:'),
      [...new Set(suggestions)].map((value) => h('button', { class: 'chip', type: 'button', style: 'border:0;cursor:pointer',
        onclick: () => { draft.sender_address = value; dirty = true; ctx.render(true); } }, value))) : null);
}

function directSection(state) {
  const check = state.checks.items.find((item) => item.id === 'out.port25');
  return h('div', { class: 'stack' },
    h('div', { class: 'note warn' },
      h('p', null, h('strong', null, 'Think twice before using this. '), 'Direct delivery only works when:'),
      h('ul', { class: 'how' },
        h('li', null, 'your internet provider does not block outgoing port 25 (many do),'),
        h('li', null, 'your IP address has a reverse DNS name that matches your mail server name (home connections rarely have one),'),
        h('li', null, 'the receiving provider does not distrust home IP addresses. Outlook/Hotmail and Gmail often do.'))),
    check ? h('div', { class: 'row' }, icon(check.status), h('span', null, check.title), h('span', { class: 'muted small' }, check.detail)) : null);
}

function rewriteOption() {
  const input = h('input', { type: 'checkbox', checked: draft.rewrite_from,
    onchange: (event) => { draft.rewrite_from = event.target.checked; dirty = true; } });
  return h('label', { class: 'switch' }, input, h('span', null, h('strong', null, 'Show the original sender in the name'), h('br'),
    'Recommended. A forwarded mail cannot truthfully claim to come from the original sender, so strict providers sort it away. With this on, it comes from your sender address as "Anna (anna@example.org)", and Reply still goes to Anna.'));
}

function loginResult(state) {
  const login = state.checks.login;
  if (!login) return null;
  return h('div', { class: 'row' }, icon(login.ok ? 'ok' : 'error'), h('span', null, login.detail), h('span', { class: 'muted small' }, timeAgo(login.time)));
}

export function renderSending(ctx) {
  const { state } = ctx;
  ensureDraft(state.config.delivery);
  const hasAddresses = allAddresses(state.config).length > 0;

  const persist = async () => {
    const saved = await attempt(() => save((cfg) => {
      cfg.delivery = {
        mode: draft.mode, sender_address: draft.sender_address, rewrite_from: draft.rewrite_from,
        relay: { ...draft.relay, port: Number(draft.relay.port) || 587 },
      };
    }), 'Saved');
    if (saved) dirty = false;
    return saved;
  };

  return h('div', { class: 'grid' },
    h('section', { class: 'card' }, h('h2', null, 'How should forwarded mail be sent?'),
      h('p', null, 'This app receives mail for your domain and then has to hand it to the inbox of the person. Gmail, Outlook and WEB.DE accept mail from a trusted sending service far more readily than from a home internet connection.'),
      modeChoice(ctx)),
    h('section', { class: 'card' },
      draft.mode === 'relay' ? relaySection(state, ctx) : directSection(state),
      h('div', { class: 'stack', style: 'margin-top:14px' }, rewriteOption())),
    h('section', { class: 'card stack' },
      h('div', { class: 'row' },
        h('button', { class: 'button', type: 'button', onclick: persist }, 'Save'),
        draft.mode === 'relay' ? h('button', { class: 'button button-quiet', type: 'button', onclick: async () => {
          if (await persist()) await attempt(() => api.testLogin());
        } }, 'Save & test login') : null,
        hasAddresses ? h('button', { class: 'button button-quiet', type: 'button', onclick: () => ctx.navigate('overview') }, 'Go and send a test mail') : null),
      loginResult(state)));
}
