// Starts the page: navigation, polling the app's state and drawing the active view.
import { ctx, refresh } from './context.js';
import { clear, h } from './dom.js';
import { renderOverview } from './views/overview.js';
import { renderMailboxes } from './views/mailboxes.js';
import { renderDomains } from './views/domains.js';
import { renderSending } from './views/sending.js';
import { renderNetwork } from './views/network.js';
import { renderActivity } from './views/activity.js';

const TABS = [
  { id: 'overview', label: 'Overview', render: renderOverview },
  { id: 'mailboxes', label: 'Mailboxes', render: renderMailboxes },
  { id: 'domains', label: 'Domains', render: renderDomains },
  { id: 'sending', label: 'Sending', render: renderSending },
  { id: 'network', label: 'Router & network', render: renderNetwork },
  { id: 'activity', label: 'Activity', render: renderActivity },
];

const FAST_POLL_MS = 1500;
const SLOW_POLL_MS = 5000;

let lastDrawn = '';
let pendingDraw = false;

function currentTab() {
  const id = location.hash.replace(/^#\/?/, '');
  return TABS.find((tab) => tab.id === id) || TABS[0];
}

ctx.navigate = (id) => {
  location.hash = `#/${id}`;
};

// A tab gets a red dot when a failing check says that its page explains the fix.
function hasProblem(tabId) {
  const checks = ctx.state?.checks?.items || [];
  return checks.some((check) => check.status === 'error' && check.guide === tabId);
}

function drawNavigation(active) {
  const nav = clear(document.getElementById('nav'));
  for (const tab of TABS) {
    nav.append(h('button', {
      class: 'tab', type: 'button', 'aria-current': tab.id === active.id ? 'page' : null,
      onclick: () => ctx.navigate(tab.id),
    }, tab.label, hasProblem(tab.id) ? h('span', { class: 'dot', title: 'Needs attention' }) : null));
  }
}

function isEditing() {
  const element = document.activeElement;
  return element && ['INPUT', 'SELECT', 'TEXTAREA'].includes(element.tagName) && document.getElementById('view').contains(element);
}

ctx.render = (force = false) => {
  if (!ctx.state) return;
  const tab = currentTab();
  const signature = JSON.stringify([tab.id, ctx.state]);
  if (!force && signature === lastDrawn) return;
  if (!force && isEditing()) {
    pendingDraw = true; // redraw once the user leaves the field
    return;
  }
  lastDrawn = signature;
  pendingDraw = false;
  const scroll = window.scrollY;
  drawNavigation(tab);
  clear(document.getElementById('view')).append(tab.render(ctx));
  document.getElementById('footer-version').textContent = `${ctx.state.version} · Mail Forwarder`;
  window.scrollTo(0, scroll);
};

document.getElementById('view').addEventListener('focusout', () => {
  setTimeout(() => { if (pendingDraw && !isEditing()) ctx.render(); }, 0);
});

window.addEventListener('hashchange', () => {
  window.scrollTo(0, 0);
  ctx.render(true);
});

async function poll() {
  try {
    await refresh();
  } catch (error) {
    clear(document.getElementById('view')).append(h('div', { class: 'banner err' },
      h('div', null, h('h2', null, 'The app does not answer'), h('p', null, error.message))));
    lastDrawn = '';
  }
  if (currentTab().id === 'activity' && !isEditing()) ctx.render(true); // events change without the state changing
  const busy = ctx.state && (ctx.state.checks.running || ctx.state.test_mail?.status === 'running');
  setTimeout(poll, document.hidden ? SLOW_POLL_MS * 3 : busy ? FAST_POLL_MS : SLOW_POLL_MS);
}

poll();
