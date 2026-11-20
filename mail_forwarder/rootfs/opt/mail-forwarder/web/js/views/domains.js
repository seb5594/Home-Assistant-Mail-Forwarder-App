// Domains: where the addresses live, which DNS records they need, and how to keep them current.
import { api } from '../api.js';
import { attempt, closeDialog, confirmDialog, save, showDialog } from '../context.js';
import { copyable, h, icon } from '../dom.js';
import { timeAgo } from '../format.js';

const TYPES = {
  own: {
    title: 'My own domain',
    text: 'A domain you bought, for example at Cloudflare, with an address like name@your-domain.com.',
  },
  duckdns: {
    title: 'Free DuckDNS domain',
    text: 'A free name like family.duckdns.org. No purchase needed, addresses look like name@family.duckdns.org.',
  },
};

function domainStatus(state, domain) {
  const checks = state.checks.items.filter((check) => check.id.startsWith('dns.') && check.id.endsWith(`.${domain.name}`));
  if (!checks.length) return ['pending', 'Not checked yet'];
  if (checks.some((check) => check.status === 'error')) return ['error', 'DNS needs attention'];
  if (checks.some((check) => check.status === 'warn')) return ['warn', 'Works, with a warning'];
  return ['ok', 'DNS is correct'];
}

// ---- add a domain ----------------------------------------------------------------------------

function addDomainDialog() {
  let kind = 'own';
  const error = h('p', { class: 'error-text', role: 'alert' });
  const name = h('input', { type: 'text', placeholder: 'example.com', autocapitalize: 'none', autocomplete: 'off', spellcheck: 'false' });
  const mailHost = h('input', { type: 'text', placeholder: 'mail.example.com', autocapitalize: 'none', autocomplete: 'off', spellcheck: 'false' });
  const hostField = h('label', { class: 'field' }, 'Mail server name', mailHost,
    h('span', { class: 'hint' }, 'The name your MX record will point to. "mail." plus your domain is the usual choice, leave it empty for that.'));
  const choices = h('div', { class: 'choice-grid' });

  const draw = () => {
    choices.replaceChildren(...Object.entries(TYPES).map(([id, type]) =>
      h('button', { class: 'choice', type: 'button', 'aria-pressed': String(kind === id), onclick: () => {
        kind = id;
        name.placeholder = id === 'own' ? 'example.com' : 'family.duckdns.org';
        hostField.classList.toggle('hidden', id !== 'own');
        draw();
      } }, h('strong', null, type.title), h('span', null, type.text))));
  };
  draw();

  showDialog(h('form', { onsubmit: async (event) => {
    event.preventDefault();
    try {
      await save((config) => config.domains.push({ name: name.value.trim(), kind, mail_host: kind === 'own' ? mailHost.value.trim() : '' }));
      closeDialog();
    } catch (problem) {
      error.textContent = problem.message;
    }
  } },
  h('h2', null, 'Add a domain'), choices,
  h('label', { class: 'field' }, 'Domain name', name),
  hostField, error,
  h('div', { class: 'dialog-actions' },
    h('button', { class: 'button button-quiet', type: 'button', onclick: closeDialog }, 'Cancel'),
    h('button', { class: 'button', type: 'submit' }, 'Add domain'))));
  name.focus();
}

async function removeDomain(domain, config) {
  const affected = config.people.flatMap((p) => p.addresses.filter((a) => a.domain === domain.name));
  const sure = await confirmDialog({ title: `Remove ${domain.name}?`, confirmLabel: 'Remove', danger: true,
    message: affected.length ? `${affected.length} address(es) on this domain are removed as well. Your DNS records stay untouched.`
      : 'Your DNS records stay untouched.' });
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
  const ip = state.public_ip || 'your public IP address';
  return h('div', { class: 'stack' },
    h('p', null, 'Open the DNS settings of ', h('strong', null, domain.name), ' (at Cloudflare: your domain, then ', h('em', null, 'DNS'), ', then ', h('em', null, 'Records'),
      ') and create these two records:'),
    h('div', { class: 'table-wrap' }, h('table', null,
      h('thead', null, h('tr', null, ['Type', 'Name', 'Value', 'Notes'].map((title) => h('th', null, title)))),
      h('tbody', null,
        h('tr', null, h('td', null, 'A'), h('td', null, copyable(relativeName(domain.mail_host, domain.name))), h('td', null, copyable(ip)),
          h('td', null, 'Proxy status: ', h('strong', null, 'DNS only'), ' (grey cloud). Skip this record if you switch on dynamic DNS below, the app creates it for you.')),
        h('tr', null, h('td', null, 'MX'), h('td', null, copyable('@')), h('td', null, copyable(domain.mail_host)),
          h('td', null, 'Priority ', h('strong', null, '10'), '. Delete other MX records of this domain.'))))),
    h('div', { class: 'note warn' }, h('p', null,
      h('strong', null, 'Cloudflare Email Routing: '), 'if you switched it on for this domain, it owns the MX records. Remove them first, the two cannot be used together.')),
    h('p', { class: 'muted small' }, 'DNS changes need a few minutes to spread. The status above turns green by itself, or press "Run checks now" on the Overview.'));
}

function duckdnsGuide(domain) {
  return h('ol', { class: 'how' },
    h('li', null, 'Log in at ', h('a', { href: 'https://www.duckdns.org', target: '_blank', rel: 'noopener' }, 'duckdns.org'),
      ' and create the subdomain ', h('span', { class: 'value' }, domain.name.replace('.duckdns.org', '')), '.'),
    h('li', null, 'Copy your DuckDNS token from that page into "Keep DNS up to date" below, so that the name follows your IP address.'),
    h('li', null, 'No MX record is needed. Senders fall back to the IP address of the name, which is what you want.'));
}

function domainCard(domain, state) {
  const [status, text] = domainStatus(state, domain);
  return h('section', { class: 'card' },
    h('div', { class: 'card-head' },
      h('div', { class: 'row' }, h('h3', null, domain.name), h('span', { class: 'badge badge-info' }, TYPES[domain.kind].title)),
      h('div', { class: 'row' }, icon(status), h('span', null, text))),
    h('details', { open: status !== 'ok' }, h('summary', null, 'DNS records for this domain'),
      h('div', { style: 'margin-top:10px' }, domain.kind === 'own' ? ownDomainGuide(domain, state) : duckdnsGuide(domain))),
    h('div', { class: 'row', style: 'margin-top:12px' },
      h('button', { class: 'button button-danger button-small', type: 'button', onclick: () => removeDomain(domain, state.config) }, 'Remove domain')));
}

// ---- dynamic DNS -----------------------------------------------------------------------------

function ddnsCard(state) {
  const { dynamic_dns: dynamic, domains } = state.config;
  const hasOwn = domains.some((d) => d.kind === 'own');
  const hasDuck = domains.some((d) => d.kind === 'duckdns');
  if (!hasOwn && !hasDuck) return null;

  const duckToken = h('input', { type: 'password', placeholder: dynamic.duckdns.token_set ? 'Saved, type to replace' : 'Your DuckDNS token', autocomplete: 'off' });
  const cloudToken = h('input', { type: 'password', placeholder: dynamic.cloudflare.api_token_set ? 'Saved, type to replace' : 'Cloudflare API token', autocomplete: 'off' });
  const duckOn = h('input', { type: 'checkbox', checked: dynamic.duckdns.enabled });
  const cloudOn = h('input', { type: 'checkbox', checked: dynamic.cloudflare.enabled });

  const results = Object.entries(state.ddns).map(([key, entry]) =>
    h('div', { class: 'row' }, icon(entry.ok ? 'ok' : 'error'), h('span', { class: 'small' }, `${entry.detail} (${timeAgo(entry.time)})`)));

  return h('section', { class: 'card' },
    h('div', { class: 'card-head' }, h('h2', null, 'Keep DNS up to date')),
    h('p', null, 'Your internet provider changes your public IP address from time to time. These switches let the app update your DNS records automatically, so that mail keeps finding you.'),
    h('div', { class: 'stack' },
      hasDuck ? h('div', { class: 'stack' },
        h('label', { class: 'switch' }, duckOn, h('span', null, h('strong', null, 'DuckDNS'), h('br'), 'Updates your duckdns.org names.')),
        h('label', { class: 'field' }, 'DuckDNS token', duckToken)) : null,
      hasOwn ? h('div', { class: 'stack' },
        h('label', { class: 'switch' }, cloudOn, h('span', null, h('strong', null, 'Cloudflare'), h('br'), 'Creates and updates the A record of your mail server name (DNS only, never proxied).')),
        h('label', { class: 'field' }, 'Cloudflare API token', cloudToken,
          h('span', { class: 'hint' }, 'Cloudflare dashboard, My Profile, API Tokens, Create Token, template "Edit zone DNS", pick your domain. It needs Zone: Read and DNS: Edit for that one zone only.'))) : null,
      results,
      h('div', { class: 'row' },
        h('button', { class: 'button', type: 'button', onclick: async () => {
          const saved = await attempt(() => save((cfg) => {
            cfg.dynamic_dns.duckdns = { enabled: duckOn.checked, token: duckToken.value.trim() };
            cfg.dynamic_dns.cloudflare = { enabled: cloudOn.checked, api_token: cloudToken.value.trim() };
          }), 'Saved. The app updates your DNS records now.');
          if (saved) await attempt(() => api.updateDns());
        } }, 'Save and update now'))));
}

export function renderDomains(ctx) {
  const { state } = ctx;
  return h('div', { class: 'grid' },
    h('section', { class: 'card' }, h('h2', null, 'Your domains'),
      h('p', null, 'A domain is the part after the @ in an address. Mail for it is delivered to this app, so the internet must know where this app lives: that is what the DNS records do.'),
      h('p', { class: 'muted small' }, 'You can use several domains at once, for example your own domain plus a free DuckDNS name, and give one person addresses on both.')),
    h('div', { class: 'row row-between' }, h('h2', { style: 'margin:0' }, 'Domains'),
      h('button', { class: 'button', type: 'button', onclick: addDomainDialog }, '+ Add a domain')),
    state.config.domains.length ? state.config.domains.map((domain) => domainCard(domain, state))
      : h('section', { class: 'card' }, h('p', { class: 'muted' }, 'No domain yet.')),
    ddnsCard(state));
}
