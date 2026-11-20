// People: every person has one real inbox and one or more addresses on your domains.
import { api } from '../api.js';
import { attempt, closeDialog, confirmDialog, ctx as shared, errorText, save, showDialog } from '../context.js';
import { h, initialOf } from '../dom.js';
import { providerOf } from '../format.js';
import { rich, richList, t } from '../i18n.js';

function addressRow(entry, domains, onRemove) {
  const local = h('input', { type: 'text', value: entry.local, placeholder: 'info', 'aria-label': t('mailboxes.local_label'),
    autocapitalize: 'none', autocomplete: 'off', spellcheck: 'false', 'data-role': 'local' });
  const domain = h('select', { 'aria-label': t('mailboxes.domain_label'), 'data-role': 'domain' },
    domains.map((d) => h('option', { value: d.name, selected: d.name === entry.domain }, d.name)));
  return h('div', { class: 'field-row', 'data-role': 'address' }, local, h('span', { class: 'at' }, '@'), domain,
    h('button', { class: 'button button-quiet button-small', type: 'button', onclick: onRemove,
      'aria-label': t('mailboxes.remove_address') }, t('common.remove')));
}

function personDialog(person) {
  const { config } = shared.state;
  const isNew = !person;
  const draft = person ? structuredClone(person) : { name: '', targets: [''], enabled: true, addresses: [{ local: '', domain: config.domains[0].name }] };
  const error = h('p', { class: 'error-text', role: 'alert' });
  const rows = h('div', { class: 'stack' });
  const name = h('input', { type: 'text', value: draft.name, placeholder: t('mailboxes.name_placeholder'), maxlength: 60, autocomplete: 'off' });
  const targetRows = h('div', { class: 'stack' });
  const enabled = h('input', { type: 'checkbox', checked: draft.enabled });

  const collectTargets = () => {
    draft.targets = [...targetRows.querySelectorAll('[data-role="target"]')].map((input) => input.value.trim());
  };
  const drawTargets = () => {
    targetRows.replaceChildren(...draft.targets.map((value, index) => h('div', { class: 'row target-row' },
      h('input', { type: 'email', value, placeholder: 'max@gmail.com', autocomplete: 'off', autocapitalize: 'none',
        spellcheck: 'false', 'data-role': 'target', 'aria-label': t('mailboxes.target_label') }),
      draft.targets.length > 1 ? h('button', { class: 'button button-quiet button-small', type: 'button',
        'aria-label': t('mailboxes.remove_target'), onclick: () => {
          collectTargets();
          draft.targets.splice(index, 1);
          drawTargets();
        } }, t('common.remove')) : null)));
  };
  drawTargets();

  const collect = () => {
    draft.addresses = [...rows.querySelectorAll('[data-role="address"]')].map((row) => ({
      local: row.querySelector('[data-role="local"]').value.trim().toLowerCase(),
      domain: row.querySelector('[data-role="domain"]').value,
    }));
  };
  const drawRows = () => {
    rows.replaceChildren(...draft.addresses.map((entry, index) => addressRow(entry, config.domains, () => {
      collect();
      draft.addresses.splice(index, 1);
      drawRows();
    })));
  };
  drawRows();

  const submit = async (event) => {
    event.preventDefault();
    collect();
    const addresses = draft.addresses.filter((entry) => entry.local);
    if (!addresses.length) {
      error.textContent = t('errors.need_address');
      return;
    }
    collectTargets();
    const result = { ...draft, name: name.value.trim(), targets: draft.targets, enabled: enabled.checked, addresses };
    try {
      await save((cfg) => {
        if (isNew) cfg.people.push(result);
        else cfg.people[cfg.people.findIndex((p) => p.id === person.id)] = result;
      });
      closeDialog();
    } catch (problem) {
      error.textContent = errorText(problem);
    }
  };

  showDialog(h('form', { onsubmit: submit },
    h('h2', null, isNew ? t('mailboxes.dialog_add') : t('mailboxes.dialog_edit', { name: person.name })),
    h('label', { class: 'field' }, t('mailboxes.name'), name, h('span', { class: 'hint' }, t('mailboxes.name_hint'))),
    h('div', { class: 'stack' }, h('strong', null, t('mailboxes.target')),
      h('span', { class: 'hint muted small' }, t('mailboxes.target_hint')),
      targetRows,
      h('div', null, h('button', { class: 'button button-quiet button-small', type: 'button', onclick: () => {
        collectTargets();
        draft.targets.push('');
        drawTargets();
      } }, t('mailboxes.add_target')))),
    h('div', { class: 'stack' }, h('strong', null, t('mailboxes.addresses')),
      h('span', { class: 'hint muted small' }, t('mailboxes.addresses_hint')),
      rows,
      h('div', null, h('button', { class: 'button button-quiet button-small', type: 'button', onclick: () => {
        collect();
        draft.addresses.push({ local: '', domain: config.domains[0].name });
        drawRows();
      } }, t('mailboxes.add_address')))),
    isNew ? null : h('label', { class: 'switch' }, enabled, h('span', null, t('mailboxes.enabled'))),
    error,
    h('div', { class: 'dialog-actions' },
      h('button', { class: 'button button-quiet', type: 'button', onclick: closeDialog }, t('common.cancel')),
      h('button', { class: 'button', type: 'submit' }, t('common.save')))));
  name.focus();
}

async function removePerson(person) {
  const sure = await confirmDialog({ title: t('mailboxes.remove_title', { name: person.name }), confirmLabel: t('common.remove'), danger: true,
    message: t('mailboxes.remove_text', { addresses: person.addresses.map((a) => `${a.local}@${a.domain}`).join(', ') }) });
  if (sure) await attempt(() => save((cfg) => { cfg.people = cfg.people.filter((p) => p.id !== person.id); }));
}

function personCard(person) {
  const firstAddress = person.addresses[0];
  const first = firstAddress ? `${firstAddress.local}@${firstAddress.domain}` : '';
  return h('section', { class: `card person ${person.enabled ? '' : 'off'}` },
    h('div', { class: 'person-head' }, h('div', { class: 'avatar' }, initialOf(person.name)),
      h('div', null, h('h3', null, person.name),
        h('div', { class: 'muted' }, `${t('mailboxes.forwards_to')} `, person.targets.map((target, index) => {
          const provider = providerOf(target);
          return h('span', { class: 'target' }, index ? ', ' : '', h('strong', null, target),
            provider ? h('span', { class: 'badge badge-info', style: 'margin-left:6px' }, provider) : null);
        }))),
      h('span', { class: 'spacer' }),
      person.enabled ? null : h('span', { class: 'badge badge-err' }, t('mailboxes.switched_off'))),
    h('div', { class: 'row' }, person.addresses.map((a) => h('span', { class: 'chip' }, `${a.local}@${a.domain}`)),
      person.addresses.length === 0 ? h('span', { class: 'muted' }, t('mailboxes.no_address')) : null),
    h('div', { class: 'row' },
      h('button', { class: 'button button-quiet button-small', type: 'button', disabled: !person.enabled || !first,
        onclick: async () => {
          if (await attempt(() => api.sendTestMail(first), t('overview.test.started'))) shared.navigate('overview');
        } }, t('mailboxes.send_test')),
      h('button', { class: 'button button-quiet button-small', type: 'button', onclick: () => personDialog(person) }, t('common.edit')),
      h('button', { class: 'button button-quiet button-small', type: 'button',
        onclick: () => attempt(() => save((cfg) => {
          const entry = cfg.people.find((p) => p.id === person.id);
          entry.enabled = !entry.enabled;
        })) }, person.enabled ? t('mailboxes.switch_off') : t('mailboxes.switch_on')),
      h('button', { class: 'button button-danger button-small', type: 'button', onclick: () => removePerson(person) }, t('common.remove'))));
}

function intro() {
  return h('section', { class: 'card' },
    h('h2', null, t('mailboxes.intro_title')),
    h('p', null, rich('mailboxes.intro_text')),
    h('ul', { class: 'how' }, richList('mailboxes.intro_tips').map((nodes) => h('li', null, nodes))));
}

export function renderMailboxes(ctx) {
  const { config } = ctx.state;
  if (!config.domains.length) {
    return h('div', { class: 'grid' }, intro(), h('section', { class: 'card' },
      h('h2', null, t('mailboxes.first_domain_title')),
      h('p', null, t('mailboxes.first_domain_text')),
      h('button', { class: 'button', type: 'button', onclick: () => ctx.navigate('domains') }, t('mailboxes.go_domains'))));
  }
  return h('div', { class: 'grid' }, intro(),
    h('div', { class: 'row row-between' }, h('h2', { style: 'margin:0' }, t('mailboxes.people')),
      h('button', { class: 'button', type: 'button', onclick: () => personDialog(null) }, t('mailboxes.add_person'))),
    config.people.length ? config.people.map(personCard)
      : h('section', { class: 'card' }, h('p', { class: 'muted' }, t('mailboxes.nobody'))));
}
