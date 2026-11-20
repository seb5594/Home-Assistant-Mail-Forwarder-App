// Sending: how a forwarded message leaves this app and reaches the real inbox.
import { api } from '../api.js';
import { attempt, save } from '../context.js';
import { describeMessage } from '../checkview.js';
import { h, icon } from '../dom.js';
import { allAddresses, timeAgo } from '../format.js';
import { has, rich, richList, t } from '../i18n.js';

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

const field = (label, input, hint) => h('label', { class: 'field' }, label, input, hint ? h('span', { class: 'hint' }, hint) : null);

function bound(type, key, target, extra = {}) {
  return h('input', { type, value: target[key] ?? '', autocomplete: 'off', autocapitalize: 'none', spellcheck: 'false',
    oninput: (event) => { target[key] = type === 'number' ? Number(event.target.value) : event.target.value; dirty = true; }, ...extra });
}

function modeChoice(ctx) {
  return h('div', { class: 'choice-grid' }, ['relay', 'direct'].map((id) =>
    h('button', { class: 'choice', type: 'button', 'aria-pressed': String(draft.mode === id), onclick: () => {
      draft.mode = id;
      dirty = true;
      ctx.render(true);
    } }, h('strong', null, t(`sending.${id}.title`)), h('span', null, t(`sending.${id}.text`)))));
}

function presetName(preset) {
  return preset.name || t(`presets.${preset.id}.name`);
}

function relaySection(state, ctx) {
  const preset = state.presets.find((item) => item.id === draft.relay.preset) || state.presets[state.presets.length - 1];
  const onlyDuck = !state.config.domains.some((d) => d.kind === 'own');
  const chips = h('div', { class: 'subtabs' }, state.presets.map((item) =>
    h('button', { class: 'subtab', type: 'button', 'aria-pressed': String(item.id === preset.id), onclick: () => {
      draft.relay = { ...draft.relay, preset: item.id, host: item.host, port: item.port, security: item.security };
      dirty = true;
      ctx.render(true);
    } }, presetName(item), item.recommended ? ' ★' : '')));

  const security = h('select', { onchange: (event) => { draft.relay.security = event.target.value; dirty = true; } },
    ['starttls', 'ssl', 'none'].map((value) => h('option', { value, selected: draft.relay.security === value }, t(`sending.sec.${value}`))));

  const suggestions = [];
  const firstOwn = state.config.domains.find((d) => d.kind === 'own');
  if (firstOwn) suggestions.push(`forwarder@${firstOwn.name}`);
  if (draft.relay.username.includes('@')) suggestions.push(draft.relay.username);

  return h('div', { class: 'stack' },
    h('h3', null, t('sending.which')), chips,
    h('div', { class: 'note' }, h('p', null, h('strong', null, presetName(preset)), ': ', t(`presets.${preset.id}.summary`)),
      preset.needs_own_domain && onlyDuck ? h('p', null, rich('sending.needs_domain')) : null),
    h('ol', { class: 'how' }, richList(`presets.${preset.id}.steps`).map((nodes) => h('li', null, nodes))),
    preset.website ? h('p', null, h('a', { href: preset.website, target: '_blank', rel: 'noopener' }, t('sending.open_service', { name: presetName(preset) }))) : null,
    h('div', { class: 'grid grid-2' },
      field(t('sending.server'), bound('text', 'host', draft.relay, { placeholder: 'smtp.example.com' })),
      field(t('sending.port'), bound('number', 'port', draft.relay)),
      field(t('sending.security'), security),
      field(t(`presets.${preset.id}.username`), bound('text', 'username', draft.relay)),
      field(t(`presets.${preset.id}.password`), bound('password', 'password', draft.relay, {
        placeholder: state.config.delivery.relay.password_set ? t('sending.password_saved') : '' }))),
    field(t('sending.sender'), bound('email', 'sender_address', draft, { placeholder: 'forwarder@your-domain.com' }), t('sending.sender_hint')),
    suggestions.length ? h('div', { class: 'row' }, h('span', { class: 'muted small' }, t('sending.use')),
      [...new Set(suggestions)].map((value) => h('button', { class: 'chip', type: 'button', style: 'border:0;cursor:pointer',
        onclick: () => { draft.sender_address = value; dirty = true; ctx.render(true); } }, value))) : null);
}

function directSection(state) {
  const check = state.checks.items.find((item) => item.id === 'out.port25');
  return h('div', { class: 'stack' },
    h('div', { class: 'note warn' },
      h('p', null, h('strong', null, t('sending.direct_warn_title')), ' ', t('sending.direct_warn_intro')),
      h('ul', { class: 'how' }, richList('sending.direct_warn').map((nodes) => h('li', null, nodes)))),
    check ? h('div', { class: 'row' }, icon(check.status), h('span', { class: 'muted small' },
      has(`probe.${check.params.probe}`) ? t(`probe.${check.params.probe}`, check.params) : '')) : null);
}

function rewriteOption() {
  const input = h('input', { type: 'checkbox', checked: draft.rewrite_from,
    onchange: (event) => { draft.rewrite_from = event.target.checked; dirty = true; } });
  return h('label', { class: 'switch' }, input, h('span', null, h('strong', null, t('sending.rewrite_title')), h('br'), t('sending.rewrite_text')));
}

function loginResult(state) {
  const login = state.checks.login;
  if (!login) return null;
  return h('div', { class: 'row' }, icon(login.ok ? 'ok' : 'error'), h('span', null, describeMessage('delivery', login)),
    h('span', { class: 'muted small' }, timeAgo(login.time)));
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
    }), t('common.saved'));
    if (saved) dirty = false;
    return saved;
  };

  return h('div', { class: 'grid' },
    h('section', { class: 'card' }, h('h2', null, t('sending.mode_title')),
      h('p', null, t('sending.mode_intro')),
      modeChoice(ctx)),
    h('section', { class: 'card' },
      draft.mode === 'relay' ? relaySection(state, ctx) : directSection(state),
      h('div', { class: 'stack', style: 'margin-top:14px' }, rewriteOption())),
    h('section', { class: 'card stack' },
      h('div', { class: 'row' },
        h('button', { class: 'button', type: 'button', onclick: persist }, t('sending.save')),
        draft.mode === 'relay' ? h('button', { class: 'button button-quiet', type: 'button', onclick: async () => {
          if (await persist()) await attempt(() => api.testLogin());
        } }, t('sending.save_test')) : null,
        hasAddresses ? h('button', { class: 'button button-quiet', type: 'button', onclick: () => ctx.navigate('overview') }, t('sending.go_test')) : null),
      loginResult(state)));
}
