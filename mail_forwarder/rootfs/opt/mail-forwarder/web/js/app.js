// Starts the page: navigation, polling the app's state and drawing the active view.
import { ctx, errorText, refresh } from './context.js';
import { clear, h } from './dom.js';
import { LANGUAGES, language, loadLanguages, rich, setLanguage, t } from './i18n.js';
import { renderOverview } from './views/overview.js';
import { renderMailboxes } from './views/mailboxes.js';
import { renderDomains } from './views/domains.js';
import { renderSending } from './views/sending.js';
import { renderNetwork } from './views/network.js';
import { renderActivity } from './views/activity.js';
import { renderHelp } from './views/help.js';

const TABS = [
  { id: 'overview', render: renderOverview },
  { id: 'mailboxes', render: renderMailboxes },
  { id: 'domains', render: renderDomains },
  { id: 'sending', render: renderSending },
  { id: 'network', render: renderNetwork },
  { id: 'activity', render: renderActivity },
  { id: 'help', render: renderHelp },
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
    }, t(`tab.${tab.id}`), hasProblem(tab.id) ? h('span', { class: 'dot', title: t('tab.attention') }) : null));
  }
}

// The footer shows the version, the language switch and the author's credit with the two links.
function drawFooter() {
  document.getElementById('badge-experimental').textContent = t('app.experimental');
  document.getElementById('badge-experimental').title = t('app.experimental_hint');
  document.getElementById('footer-version').textContent = `${ctx.state.version} · Mail Forwarder`;
  clear(document.getElementById('language-switch')).append(...Object.entries(LANGUAGES).map(([code, name]) =>
    h('button', { type: 'button', 'aria-pressed': String(code === language()), title: name, onclick: () => {
      setLanguage(code);
      ctx.render(true);
    } }, code.toUpperCase())));
  clear(document.getElementById('footer-credit')).append(
    ...rich('footer.developed'), h('br'), t('footer.made_before'), ' ', h('span', { class: 'heart', 'aria-label': 'love' }, '♥'), ' ', t('footer.made_after'));
  clear(document.getElementById('footer-buttons')).append(
    h('a', { class: 'button button-outline', href: 'https://github.com/seb5594/Home-Assistant-Apps', target: '_blank', rel: 'noopener' }, t('footer.more')),
    h('a', { class: 'button button-outline', href: 'https://buymeacoffee.com/seb5594', target: '_blank', rel: 'noopener' }, t('footer.support')));
}

function isEditing() {
  const element = document.activeElement;
  return element && ['INPUT', 'SELECT', 'TEXTAREA'].includes(element.tagName) && document.getElementById('view').contains(element);
}

ctx.render = (force = false) => {
  if (!ctx.state) return;
  const tab = currentTab();
  const signature = JSON.stringify([tab.id, language(), ctx.state]);
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
  drawFooter();
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
      h('div', null, h('h2', null, t('app.unreachable')), h('p', null, errorText(error)))));
    lastDrawn = '';
  }
  if (currentTab().id === 'activity' && !isEditing()) ctx.render(true); // events change without the state changing
  const busy = ctx.state && (ctx.state.checks.running || ctx.state.test_mail?.status === 'running');
  setTimeout(poll, document.hidden ? SLOW_POLL_MS * 3 : busy ? FAST_POLL_MS : SLOW_POLL_MS);
}

loadLanguages().then(poll);
