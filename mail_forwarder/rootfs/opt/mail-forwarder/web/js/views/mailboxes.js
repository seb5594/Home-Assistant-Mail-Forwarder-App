// People: every person has one real inbox and one or more addresses on your domains.
import { api } from '../api.js';
import { attempt, closeDialog, confirmDialog, ctx as shared, save, showDialog } from '../context.js';
import { h, initialOf } from '../dom.js';
import { providerOf } from '../format.js';

function addressRow(entry, domains, onRemove) {
  const local = h('input', { type: 'text', value: entry.local, placeholder: 'info', 'aria-label': 'First part of the address',
    autocapitalize: 'none', autocomplete: 'off', spellcheck: 'false', 'data-role': 'local' });
  const domain = h('select', { 'aria-label': 'Domain', 'data-role': 'domain' },
    domains.map((d) => h('option', { value: d.name, selected: d.name === entry.domain }, d.name)));
  return h('div', { class: 'field-row', 'data-role': 'address' }, local, h('span', { class: 'at' }, '@'), domain,
    h('button', { class: 'button button-quiet button-small', type: 'button', onclick: onRemove, 'aria-label': 'Remove this address' }, 'Remove'));
}

function personDialog(person) {
  const { config } = shared.state;
  const isNew = !person;
  const draft = person ? structuredClone(person) : { name: '', target: '', enabled: true, addresses: [{ local: '', domain: config.domains[0].name }] };
  const error = h('p', { class: 'error-text', role: 'alert' });
  const rows = h('div', { class: 'stack' });
  const name = h('input', { type: 'text', value: draft.name, placeholder: 'Uncle Max', maxlength: 60, autocomplete: 'off' });
  const target = h('input', { type: 'email', value: draft.target, placeholder: 'max@gmail.com', autocomplete: 'off',
    autocapitalize: 'none', spellcheck: 'false' });
  const enabled = h('input', { type: 'checkbox', checked: draft.enabled });

  const drawRows = () => {
    rows.replaceChildren(...draft.addresses.map((entry, index) => addressRow(entry, config.domains, () => {
      collect();
      draft.addresses.splice(index, 1);
      drawRows();
    })));
  };
  const collect = () => {
    draft.addresses = [...rows.querySelectorAll('[data-role="address"]')].map((row) => ({
      local: row.querySelector('[data-role="local"]').value.trim().toLowerCase(),
      domain: row.querySelector('[data-role="domain"]').value,
    }));
  };
  drawRows();

  const submit = async (event) => {
    event.preventDefault();
    collect();
    const addresses = draft.addresses.filter((entry) => entry.local);
    if (!addresses.length) {
      error.textContent = 'Add at least one address, for example "info".';
      return;
    }
    const result = { ...draft, name: name.value.trim(), target: target.value.trim(), enabled: enabled.checked, addresses };
    try {
      await save((cfg) => {
        if (isNew) cfg.people.push(result);
        else cfg.people[cfg.people.findIndex((p) => p.id === person.id)] = result;
      });
      closeDialog();
    } catch (problem) {
      error.textContent = problem.message;
    }
  };

  showDialog(h('form', { onsubmit: submit },
    h('h2', null, isNew ? 'Add a person' : `Edit ${person.name}`),
    h('label', { class: 'field' }, 'Name', name, h('span', { class: 'hint' }, 'Only for you, to tell the entries apart.')),
    h('label', { class: 'field' }, 'Forward everything to this inbox', target,
      h('span', { class: 'hint' }, 'The real mailbox of this person, for example at Gmail, Outlook/Hotmail or WEB.DE.')),
    h('div', { class: 'stack' }, h('strong', null, 'Addresses of this person'),
      h('span', { class: 'hint muted small' }, 'Mail to any of these goes to the inbox above. One person can have several, even on different domains.'),
      rows,
      h('div', null, h('button', { class: 'button button-quiet button-small', type: 'button', onclick: () => {
        collect();
        draft.addresses.push({ local: '', domain: config.domains[0].name });
        drawRows();
      } }, '+ Add another address'))),
    isNew ? null : h('label', { class: 'switch' }, enabled, h('span', null, 'Forwarding is switched on')),
    error,
    h('div', { class: 'dialog-actions' },
      h('button', { class: 'button button-quiet', type: 'button', onclick: closeDialog }, 'Cancel'),
      h('button', { class: 'button', type: 'submit' }, 'Save'))));
  name.focus();
}

async function removePerson(person) {
  const sure = await confirmDialog({ title: `Remove ${person.name}?`, confirmLabel: 'Remove', danger: true,
    message: `Mail to ${person.addresses.map((a) => `${a.local}@${a.domain}`).join(', ')} will be refused from now on.` });
  if (sure) await attempt(() => save((cfg) => { cfg.people = cfg.people.filter((p) => p.id !== person.id); }));
}

function personCard(person) {
  const provider = providerOf(person.target);
  const firstAddress = person.addresses[0];
  const first = firstAddress ? `${firstAddress.local}@${firstAddress.domain}` : '';
  return h('section', { class: `card person ${person.enabled ? '' : 'off'}` },
    h('div', { class: 'person-head' }, h('div', { class: 'avatar' }, initialOf(person.name)),
      h('div', null, h('h3', null, person.name),
        h('div', { class: 'muted' }, 'forwards to ', h('strong', null, person.target), provider ? h('span', { class: 'badge badge-info', style: 'margin-left:6px' }, provider) : null)),
      h('span', { class: 'spacer' }),
      person.enabled ? null : h('span', { class: 'badge badge-err' }, 'Switched off')),
    h('div', { class: 'row' }, person.addresses.map((a) => h('span', { class: 'chip' }, `${a.local}@${a.domain}`)),
      person.addresses.length === 0 ? h('span', { class: 'muted' }, 'No address yet') : null),
    h('div', { class: 'row' },
      h('button', { class: 'button button-quiet button-small', type: 'button', disabled: !person.enabled || !first,
        onclick: async () => {
          if (await attempt(() => api.sendTestMail(first), 'Test mail started')) shared.navigate('overview');
        } }, 'Send test mail'),
      h('button', { class: 'button button-quiet button-small', type: 'button', onclick: () => personDialog(person) }, 'Edit'),
      h('button', { class: 'button button-quiet button-small', type: 'button',
        onclick: () => attempt(() => save((cfg) => {
          const entry = cfg.people.find((p) => p.id === person.id);
          entry.enabled = !entry.enabled;
        })) }, person.enabled ? 'Switch off' : 'Switch on'),
      h('button', { class: 'button button-danger button-small', type: 'button', onclick: () => removePerson(person) }, 'Remove')));
}

function intro() {
  return h('section', { class: 'card' },
    h('h2', null, 'How the mailboxes work'),
    h('p', null, 'You do not create real mailboxes here. Each person gets addresses like ', h('code', null, 'max@your-domain.com'),
      ', and everything sent there is passed on to the inbox they already use.'),
    h('ul', { class: 'how' },
      h('li', null, 'Tell the person about their new address, and that the first mail may land in the spam folder until they mark it as "not spam".'),
      h('li', null, 'Replying works: the answer goes to the original sender, but it is sent from the inbox of the person, not from the new address.'),
      h('li', null, 'Only addresses you add here are accepted. Everything else is refused at the door, which keeps spam out.')));
}

export function renderMailboxes(ctx) {
  const { config } = ctx.state;
  if (!config.domains.length) {
    return h('div', { class: 'grid' }, intro(), h('section', { class: 'card' },
      h('h2', null, 'First add a domain'),
      h('p', null, 'Addresses need a domain after the @. Add yours (or a free DuckDNS one) first.'),
      h('button', { class: 'button', type: 'button', onclick: () => ctx.navigate('domains') }, 'Go to Domains')));
  }
  return h('div', { class: 'grid' }, intro(),
    h('div', { class: 'row row-between' }, h('h2', { style: 'margin:0' }, 'People'),
      h('button', { class: 'button', type: 'button', onclick: () => personDialog(null) }, '+ Add a person')),
    config.people.length ? config.people.map(personCard)
      : h('section', { class: 'card' }, h('p', { class: 'muted' }, 'Nobody yet. Add yourself first, then family and friends.')));
}
