// The start page: is everything working, what is left to do, and a button that proves it.
import { api } from '../api.js';
import { attempt } from '../context.js';
import { h, icon } from '../dom.js';
import { allAddresses, clock, plural, timeAgo } from '../format.js';

const GROUPS = [
  ['app', 'This app'],
  ['internet', 'Internet'],
  ['dns', 'DNS records'],
  ['outbound', 'Sending'],
];

const STATUS_RANK = { error: 0, warn: 1, pending: 2, unknown: 3, todo: 4, ok: 5 };

function checkById(state, id) {
  return state.checks.items.find((check) => check.id === id);
}

function checksOfGroup(state, prefix) {
  return state.checks.items.filter((check) => check.id.startsWith(prefix));
}

function worst(checks) {
  if (!checks.length) return 'todo';
  return checks.map((check) => check.status).sort((a, b) => STATUS_RANK[a] - STATUS_RANK[b])[0];
}

// ---- banner ----------------------------------------------------------------------------------

function banner(state) {
  const failing = state.checks.items.filter((check) => check.status === 'error').length;
  const variants = {
    setup: ['info', 'ok', "Let's set up your mail forwarding",
      'Follow the steps below. Most of the time goes into waiting for DNS changes, the clicking itself is quick.'],
    problem: ['err', 'error', `${plural(failing, 'thing needs', 'things need')} your attention`,
      'Open the failing checks below, each one says what to do.'],
    unverified: ['warn', 'pending', 'Almost there',
      'The setup looks fine, but no mail from the internet has reached this app yet. Send a test mail below.'],
    ready: ['ok', 'ok', 'Mail forwarding is running',
      'Mail sent to your addresses is received here and forwarded to the real mailboxes.'],
    unknown: ['info', 'pending', 'Checking your setup…', 'This takes a few seconds.'],
  };
  const [kind, iconName, title, text] = variants[state.checks.verdict] || variants.unknown;
  return h('div', { class: `banner ${kind}` }, icon(iconName), h('div', null, h('h2', null, title), h('p', null, text)));
}

// ---- setup steps -----------------------------------------------------------------------------

function setupSteps(state, ctx) {
  const test = state.test_mail;
  const dnsChecks = checksOfGroup(state, 'dns.');
  const steps = [
    ['1', 'Add your domain', 'The part after the @ of your new addresses.',
      checkById(state, 'setup.domain')?.status || 'todo', 'domains'],
    ['2', 'Add the people who get mail', 'Each person gets one or more addresses and one real inbox.',
      checkById(state, 'setup.mailbox')?.status || 'todo', 'mailboxes'],
    ['3', 'Choose how mail is sent on', 'A free sending service delivers the forwarded mail reliably.',
      worst([checkById(state, 'setup.sending'), checkById(state, 'out.relay'), checkById(state, 'out.port25')].filter(Boolean)), 'sending'],
    ['4', 'Create the DNS records', 'They tell the internet that this app receives your mail.',
      state.config.domains.length ? worst(dnsChecks) : 'todo', 'domains'],
    ['5', 'Open port 25 in your router', 'Without it, mail cannot reach your Home Assistant.',
      worst([checkById(state, 'app.port'), checkById(state, 'in.traffic')].filter(Boolean)), 'network'],
    ['6', 'Send a test mail', 'Proves the whole way: out, back in and on to the inbox.',
      test?.status === 'ok' ? 'ok' : test?.status === 'running' ? 'pending' : 'todo', null],
  ];
  return h('section', { class: 'card' },
    h('div', { class: 'card-head' }, h('h2', null, 'Setup checklist')),
    h('ol', { class: 'steps' }, steps.map(([number, title, detail, status, tab]) =>
      h('li', { class: `step ${status === 'ok' ? 'done' : ''}` },
        icon(status),
        h('div', { class: 'step-body' }, h('div', { class: 'step-title' }, `${number}. ${title}`),
          h('div', { class: 'step-detail' }, detail)),
        tab ? h('button', { class: 'button button-quiet button-small', type: 'button', onclick: () => ctx.navigate(tab) },
          status === 'ok' ? 'Review' : 'Open') : null))));
}

// ---- checks ----------------------------------------------------------------------------------

function checkRow(check, ctx) {
  const needsHelp = ['error', 'warn', 'pending'].includes(check.status) && (check.fix.length || check.guide);
  return h('div', { class: 'check' },
    h('div', { class: 'check-head' }, icon(check.status),
      h('div', null, h('div', { class: 'check-title' }, check.title),
        check.detail ? h('div', { class: 'check-detail' }, check.detail) : null)),
    needsHelp ? h('details', { open: check.status === 'error' },
      h('summary', null, 'How to fix this'),
      check.fix.length ? h('ol', { class: 'how' }, check.fix.map((step) => h('li', null, step))) : null,
      check.guide ? h('p', null, h('button', { class: 'button button-quiet button-small', type: 'button',
        onclick: () => ctx.navigate(check.guide) }, 'Open the guide')) : null) : null);
}

function checksCard(state, ctx) {
  const { checks } = state;
  const body = GROUPS.map(([group, title]) => {
    const items = checks.items.filter((check) => check.group === group && !check.id.startsWith('setup.'));
    return items.length ? [h('div', { class: 'group-title' }, title), items.map((check) => checkRow(check, ctx))] : null;
  });
  return h('section', { class: 'card' },
    h('div', { class: 'card-head' },
      h('div', null, h('h2', null, 'Health checks'),
        h('span', { class: 'muted small' }, checks.updated ? `Last run ${timeAgo(checks.updated)}` : 'Not run yet')),
      h('button', { class: 'button button-quiet', type: 'button', disabled: checks.running,
        onclick: () => attempt(() => api.runChecks()) }, checks.running ? 'Checking…' : 'Run checks now')),
    checks.items.length ? body : h('p', { class: 'muted' }, 'The first run is under way.'));
}

// ---- test mail -------------------------------------------------------------------------------

const TEST_STEPS = [
  ['sent', 'Handed to the sending service'],
  ['arrived', 'Came back to this app through the internet'],
  ['forwarded', 'Forwarded to the real mailbox'],
];

function testResult(test, state) {
  const person = state.config.people.find((p) => p.addresses.some((a) => `${a.local}@${a.domain}` === test.alias));
  const target = person?.target || 'the mailbox';
  if (test.status === 'ok') {
    return h('div', { class: 'note' }, h('p', null,
      `It works. The test mail travelled the whole way. Look into the inbox of ${target} (and its spam folder, the first mail of a new sender often lands there).`));
  }
  if (test.status === 'failed') {
    return h('div', { class: 'note warn' }, h('p', null, test.error || 'The test failed.'),
      h('p', null, 'Fix the problem named above (usually on the Sending page) and try again.'));
  }
  if (test.status === 'timeout') {
    const sent = Boolean(test.steps.sent);
    const arrived = Boolean(test.steps.arrived);
    return h('div', { class: 'note warn' },
      h('p', null, h('strong', null, !sent ? 'The test mail was never sent.' : !arrived
        ? 'The test mail left, but never came back to this app.' : 'The test mail arrived but could not be forwarded.')),
      h('ul', { class: 'how' }, !sent
        ? [h('li', null, 'Check the Sending page, then press "Save & test login".')]
        : !arrived
          ? [h('li', null, 'The DNS checks above must all be green (MX record and A record).'),
             h('li', null, 'Port 25 must be forwarded in your router, see the Router & network page.'),
             h('li', null, 'Some providers block incoming port 25 or hide your connection behind a shared address (CGNAT, DS-Lite). The Router & network page explains how to find out.')]
          : [h('li', null, 'Open the Activity page: it shows why the forwarding failed and when it is tried again.')]));
  }
  return h('p', { class: 'muted' }, 'This usually takes under a minute. You can leave this page open or come back later.');
}

function testCard(state, ctx) {
  const addresses = allAddresses(state.config).filter((entry) => entry.enabled);
  const test = state.test_mail;
  const running = test?.status === 'running';
  const select = h('select', { id: 'test-address', 'aria-label': 'Address to test' },
    addresses.map((entry) => h('option', { value: entry.address, selected: test?.alias === entry.address }, entry.address)));
  const body = !addresses.length
    ? h('p', { class: 'muted' }, 'Add a person with an address first, then you can test it here.')
    : [h('p', { class: 'muted' }, 'Sends a message to one of your addresses through your sending service. If it arrives in the inbox, everything from DNS to router is right.'),
       h('div', { class: 'row' }, select,
         h('button', { class: 'button', type: 'button', disabled: running,
           onclick: () => attempt(() => api.sendTestMail(select.value)) }, running ? 'Test is running…' : 'Send test mail'))];
  return h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', null, 'Test mail')), body,
    test ? h('div', { class: 'stack', style: 'margin-top:14px' },
      h('ol', { class: 'steps' }, TEST_STEPS.map(([key, label]) => {
        const done = test.steps[key];
        const status = done ? 'ok' : test.status === 'running' ? 'spinner' : 'todo';
        return h('li', { class: 'step' }, icon(status), h('div', { class: 'step-body' }, h('div', { class: 'step-title' }, label),
          done ? h('div', { class: 'step-detail' }, clock(done)) : null));
      })),
      testResult(test, state)) : null);
}

// ---- statistics ------------------------------------------------------------------------------

function tile(value, label, onclick) {
  return h(onclick ? 'button' : 'div', { class: 'tile', type: onclick ? 'button' : null, onclick,
    style: onclick ? 'border:0;text-align:left;color:inherit;font:inherit;cursor:pointer' : null },
  h('div', { class: 'tile-value' }, value), h('div', { class: 'tile-label' }, label));
}

function statsCard(state, ctx) {
  const { stats, queue } = state;
  return h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', null, 'Mail so far')),
    h('div', { class: 'tiles' },
      tile(stats.forwarded || 0, 'forwarded'),
      tile(queue.queued, 'waiting to be sent', () => ctx.navigate('activity')),
      tile(queue.failed, 'given up on', () => ctx.navigate('activity')),
      tile(stats.rejected || 0, 'refused (unknown address)'),
      tile(timeAgo(stats.last_forwarded), 'last forwarded')));
}

export function renderOverview(ctx) {
  const { state } = ctx;
  return h('div', { class: 'grid' },
    banner(state),
    state.checks.verdict === 'setup' || state.checks.verdict === 'unverified' || state.checks.verdict === 'problem'
      ? setupSteps(state, ctx) : null,
    checksCard(state, ctx),
    testCard(state, ctx),
    statsCard(state, ctx));
}
