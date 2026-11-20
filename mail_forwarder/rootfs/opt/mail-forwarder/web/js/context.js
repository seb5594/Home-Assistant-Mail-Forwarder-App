// State and actions that every view shares. app.js fills in `render` and `navigate`.
import { api } from './api.js';
import { h, toast } from './dom.js';
import { message, t } from './i18n.js';

export const ctx = {
  state: null,
  render: () => {},
  navigate: () => {},
};

export async function refresh() {
  ctx.state = await api.state();
  ctx.render();
}

// Applies a change to a copy of the stored configuration and saves it. The server validates
// everything and answers with a readable error that the caller shows.
export async function save(mutator) {
  const config = structuredClone(ctx.state.config);
  mutator(config);
  ctx.state.config = await api.saveConfig(config);
  await refresh();
}

// The text of an error in the language of the page. Errors from the app carry a code.
export function errorText(error) {
  if (error.code === 'unreachable') return t('app.unreachable_text');
  return error.code ? message('errors', error.code, error.params || {}, error.message) : error.message;
}

// Runs an async action, shows the error as a toast, and tells the caller whether it worked.
export async function attempt(action, success) {
  try {
    const result = await action();
    await refresh();
    if (success) toast(success);
    return result ?? true;
  } catch (error) {
    toast(errorText(error), 'error');
    return false;
  }
}

// ---- dialogs -----------------------------------------------------------------------------------

const dialog = () => document.getElementById('dialog');

export function closeDialog() {
  const element = dialog();
  if (element.open) element.close();
}

export function showDialog(content) {
  const element = dialog();
  element.replaceChildren(content);
  if (!element.open) element.showModal();
}

export function confirmDialog({ title, message: body, confirmLabel, danger = false }) {
  return new Promise((resolve) => {
    const finish = (answer) => {
      closeDialog();
      resolve(answer);
    };
    showDialog(h('form', { onsubmit: (event) => { event.preventDefault(); finish(true); } },
      h('h2', null, title),
      h('p', null, body),
      h('div', { class: 'dialog-actions' },
        h('button', { class: 'button button-quiet', type: 'button', onclick: () => finish(false) }, t('common.cancel')),
        h('button', { class: `button ${danger ? 'button-danger' : ''}`, type: 'submit' }, confirmLabel || t('common.save')))));
    dialog().addEventListener('close', () => resolve(false), { once: true });
  });
}
