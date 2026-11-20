// State and actions that every view shares. app.js fills in `render` and `navigate`.
import { api } from './api.js';
import { h, toast } from './dom.js';

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

// Runs an async action, shows the error as a toast, and tells the caller whether it worked.
export async function attempt(action, success) {
  try {
    const result = await action();
    await refresh();
    if (success) toast(success);
    return result ?? true;
  } catch (error) {
    toast(error.message, 'error');
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

export function confirmDialog({ title, message, confirmLabel = 'Confirm', danger = false }) {
  return new Promise((resolve) => {
    const finish = (answer) => {
      closeDialog();
      resolve(answer);
    };
    showDialog(h('form', { onsubmit: (event) => { event.preventDefault(); finish(true); } },
      h('h2', null, title),
      h('p', null, message),
      h('div', { class: 'dialog-actions' },
        h('button', { class: 'button button-quiet', type: 'button', onclick: () => finish(false) }, 'Cancel'),
        h('button', { class: `button ${danger ? 'button-danger' : ''}`, type: 'submit' }, confirmLabel))));
    dialog().addEventListener('close', () => resolve(false), { once: true });
  });
}
