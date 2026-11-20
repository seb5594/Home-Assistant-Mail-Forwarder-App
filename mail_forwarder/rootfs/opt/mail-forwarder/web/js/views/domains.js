// Domains: where the addresses live, which DNS records they need, and how to keep them current.
import { api } from '../api.js';
import { attempt, closeDialog, confirmDialog, errorText, save, showDialog } from '../context.js';
import { describeMessage } from '../checkview.js';
import { copyable, h, icon } from '../dom.js';
import { timeAgo } from '../format.js';
import { rich, richList, t } from '../i18n.js';

const KINDS = ['own', 'duckdns'];

function domainStatus(state, domain) {
  const checks = state.checks.items.filter((check) => check.id.startsWith('dns.') && check.id.endsWith(`.${domain.name}`));
  if (!checks.length) return ['pending', 'pending'];
  if (checks.some((check) => check.status === 'error')) return ['error', 'error'];
  if (checks.some((check) => check.status === 'warn')) return ['warn', 'warn'];
  return ['ok', 'ok'];
}

// ---- add a domain ----------------------------------------------------------------------------

function addDomainDialog() {
  let kind = 'own';
  const error = h('p', { class: 'error-text', role: 'alert' });
  const name = h('input', { type: 'text', placeholder: 'example.com', autocapitalize: 'none', autocomplete: 'off', spellcheck: 'false' });
  const mailHost = h('input', { type: 'text', placeholder: 'mail.example.com', autocapitalize: 'none', autocomplete: 'off', spellcheck: 'false' });
  const hostField = h('label', { class: 'field' }, t('domains.mail_host'), mailHost, h('span', { class: 'hint' }, t('domains.mail_host_hint')));
  const choices = h('div', { class: 'choice-grid' });

  const draw = () => {
    choices.replaceChildren(...KINDS.map((id) =>
      h('button', { class: 'choice', type: 'button', 'aria-pressed': String(kind === id), onclick: () => {
        kind = id;
        name.placeholder = id === 'own' ? 'example.com' : 'family.duckdns.org';
        hostField.classList.toggle('hidden', id !== 'own');
        draw();
      } }, h('strong', null, t(`domains.types.${id}.title`)), h('span', null, t(`domains.types.${id}.text`)))));
  };
  draw();

  showDialog(h('form', { onsubmit: async (event) => {
    event.preventDefault();
    try {
      await save((config) => config.domains.push({ name: name.value.trim(), kind, mail_host: kind === 'own' ? mailHost.value.trim() : '' }));
      closeDialog();
    } catch (problem) {
      error.textContent = errorText(problem);
    }
  } },
  h('h2', null, t('domains.dialog_title')), choices,
  h('label', { class: 'field' }, t('domains.domain_name'), name),
  hostField, error,
  h('div', { class: 'dialog-actions' },
    h('button', { class: 'button button-quiet', type: 'button', onclick: closeDialog }, t('common.cancel')),
    h('button', { class: 'button', type: 'submit' }, t('domains.add_button')))));
  name.focus();
}

async function removeDomain(domain, config) {
  const affected = config.people.flatMap((p) => p.addresses.filter((a) => a.domain === domain.name));
  const sure = await confirmDialog({ title: t('domains.remove_title', { name: domain.name }), confirmLabel: t('common.remove'), danger: true,
    message: affected.length ? t('domains.remove_text_with', { count: affected.length }) : t('domains.remove_text') });
  if (!sure) return;
  await attempt(() => save((cfg) => {
    cfg.domains = cfg.domains.filter((d) => d.name !== domain.name);
    for (const person of cfg.people) person.addresses = person.addresses.filter((a) => a.domain !== domain.name);
  }));
}

// ---- DNS instructions ------------------------------------------------------------------------

function relativeName(host, domain) {
  return host === domain ? '@' : host.endsWith(`.${domain}`) ? host.slice(0, -domain.length - 1) : host;
}

function ownDomainGuide(domain, state) {
  const ip = state.public_ip || t('domains.own_guide.your_ip');
  const g = (key) => t(`domains.own_guide.${key}`);
  return h('div', { class: 'stack' },
    h('p', null, rich('domains.own_guide.intro', { domain: domain.name })),
    h('div', { class: 'table-wrap' }, h('table', null,
      h('thead', null, h('tr', null, ['type', 'name', 'value', 'notes'].map((key) => h('th', null, g(key))))),
      h('tbody', null,
        h('tr', null, h('td', null, 'A'), h('td', null, copyable(relativeName(domain.mail_host, domain.name))), h('td', null, copyable(ip)),
          h('td', null, rich('domains.own_guide.a_notes'))),
        h('tr', null, h('td', null, 'MX'), h('td', null, copyable('@')), h('td', null, copyable(domain.mail_host)),
          h('td', null, rich('domains.own_guide.mx_notes'))))),),
    h('div', { class: 'note warn' }, h('p', null, rich('domains.own_guide.routing'))),
    h('p', { class: 'muted small' }, g('wait')));
}

function duckdnsGuide(domain) {
  return h('ol', { class: 'how' }, richList('domains.duck_guide', { sub: domain.name.replace('.duckdns.org', '') }).map((nodes) => h('li', null, nodes)));
}

function domainCard(domain, state) {
  const [status, key] = domainStatus(state, domain);
  return h('section', { class: 'card' },
    h('div', { class: 'card-head' },
      h('div', { class: 'row' }, h('h3', null, domain.name), h('span', { class: 'badge badge-info' }, t(`domains.types.${domain.kind}.title`))),
      h('div', { class: 'row' }, icon(status), h('span', null, t(`domains.status.${key}`)))),
    h('details', { open: status !== 'ok' }, h('summary', null, t('domains.records')),
      h('div', { style: 'margin-top:10px' }, domain.kind === 'own' ? ownDomainGuide(domain, state) : duckdnsGuide(domain))),
    h('div', { class: 'row', style: 'margin-top:12px' },
      h('button', { class: 'button button-danger button-small', type: 'button', onclick: () => removeDomain(domain, state.config) }, t('domains.remove_domain'))));
}

// ---- dynamic DNS -----------------------------------------------------------------------------

function ddnsCard(state) {
  const { dynamic_dns: dynamic, domains } = state.config;
  const hasOwn = domains.some((d) => d.kind === 'own');
  const hasDuck = domains.some((d) => d.kind === 'duckdns');
  if (!hasOwn && !hasDuck) return null;
  const d = (key) => t(`domains.ddns.${key}`);

  const placeholder = (isSet, fallback) => (isSet ? d('saved_placeholder') : fallback);
  const duckToken = h('input', { type: 'password', placeholder: placeholder(dynamic.duckdns.token_set, d('duck_placeholder')), autocomplete: 'off' });
  const cloudToken = h('input', { type: 'password', placeholder: placeholder(dynamic.cloudflare.api_token_set, d('cloud_placeholder')), autocomplete: 'off' });
  const duckOn = h('input', { type: 'checkbox', checked: dynamic.duckdns.enabled });
  const cloudOn = h('input', { type: 'checkbox', checked: dynamic.cloudflare.enabled });

  const forget = (provider, field) => h('button', { class: 'button button-danger button-small', type: 'button', onclick: () => attempt(() => save((cfg) => {
    cfg.dynamic_dns[provider] = { enabled: false, token: '', api_token: '', [`${field}_clear`]: true };
  }), d('forgotten')) }, d('forget'));

  const results = Object.values(state.ddns).map((entry) =>
    h('div', { class: 'row' }, icon(entry.ok ? 'ok' : 'error'), h('span', { class: 'small' }, `${describeMessage('ddns', entry)} (${timeAgo(entry.time)})`)));

  return h('section', { class: 'card' },
    h('div', { class: 'card-head' }, h('h2', null, d('title'))),
    h('p', null, d('intro')),
    h('div', { class: 'note' }, h('p', null, rich('domains.ddns.off_note'))),
    h('div', { class: 'stack' },
      hasDuck ? h('div', { class: 'stack' },
        h('label', { class: 'switch' }, duckOn, h('span', null, h('strong', null, d('duck')), h('br'), d('duck_text'))),
        h('label', { class: 'field' }, d('duck_token'), duckToken),
        dynamic.duckdns.token_set ? h('div', null, forget('duckdns', 'token')) : null) : null,
      hasOwn ? h('div', { class: 'stack' },
        h('label', { class: 'switch' }, cloudOn, h('span', null, h('strong', null, d('cloud')), h('br'), d('cloud_text'))),
        h('label', { class: 'field' }, d('cloud_token'), cloudToken, h('span', { class: 'hint' }, d('cloud_hint'))),
        dynamic.cloudflare.api_token_set ? h('div', null, forget('cloudflare', 'api_token')) : null) : null,
      results,
      h('div', { class: 'row' },
        h('button', { class: 'button', type: 'button', onclick: async () => {
          const saved = await attempt(() => save((cfg) => {
            cfg.dynamic_dns.duckdns = { enabled: duckOn.checked, token: duckToken.value.trim() };
            cfg.dynamic_dns.cloudflare = { enabled: cloudOn.checked, api_token: cloudToken.value.trim() };
          }), d('saved'));
          if (saved) await attempt(() => api.updateDns());
        } }, d('save')))));
}

export function renderDomains(ctx) {
  const { state } = ctx;
  return h('div', { class: 'grid' },
    h('section', { class: 'card' }, h('h2', null, t('domains.title')),
      h('p', null, t('domains.intro')),
      h('p', { class: 'muted small' }, t('domains.intro_more'))),
    h('section', { class: 'banner warn' }, icon('warn'),
      h('div', null, h('h2', null, t('domains.router_ddns_title')), h('p', null, rich('domains.router_ddns_text')))),
    h('div', { class: 'row row-between' }, h('h2', { style: 'margin:0' }, t('domains.list')),
      h('button', { class: 'button', type: 'button', onclick: addDomainDialog }, t('domains.add'))),
    state.config.domains.length ? state.config.domains.map((domain) => domainCard(domain, state))
      : h('section', { class: 'card' }, h('p', { class: 'muted' }, t('domains.none'))),
    ddnsCard(state));
}
