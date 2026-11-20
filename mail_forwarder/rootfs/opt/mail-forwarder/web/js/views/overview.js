// The start page: is everything working, what is left to do, and a button that proves it.
import { api } from '../api.js';
import { attempt } from '../context.js';
import { describeCheck, describeMessage } from '../checkview.js';
import { h, icon } from '../dom.js';
import { allAddresses, clock, timeAgo } from '../format.js';
import { richList, t } from '../i18n.js';

const GROUPS = ['app', 'internet', 'dns', 'outbound'];
const STATUS_RANK = { error: 0, warn: 1, pending: 2, unknown: 3, todo: 4, ok: 5 };
const TEST_STEPS = ['sent', 'arrived', 'forwarded'];

const checkById = (state, id) => state.checks.items.find((check) => check.id === id);
const checksStartingWith = (state, prefix) => state.checks.items.filter((check) => check.id.startsWith(prefix));

function worst(checks) {
  if (!checks.length) return 'todo';
  return checks.map((check) => check.status).sort((a, b) => STATUS_RANK[a] - STATUS_RANK[b])[0];
}

// ---- banner ----------------------------------------------------------------------------------

function banner(state) {
  const failing = state.checks.items.filter((check) => check.status === 'error').length;
  const verdict = state.checks.verdict;
  const look = { setup: ['info', 'ok'], problem: ['err', 'error'], unverified: ['warn', 'pending'], ready: ['ok', 'ok'], unknown: ['info', 'pending'] };
  const [kind, iconName] = look[verdict] || look.unknown;
  const base = verdict === 'problem' ? `overview.banner.problem_${failing === 1 ? 'one' : 'other'}` : `overview.banner.${look[verdict] ? verdict : 'unknown'}`;
  return h('div', { class: `banner ${kind}` }, icon(iconName),
    h('div', null, h('h2', null, t(`${base}.title`, { count: failing })), h('p', null, t(`${base}.text`))));
}

// ---- setup steps -----------------------------------------------------------------------------

function setupSteps(state, ctx) {
  const test = state.test_mail;
  const dnsChecks = checksStartingWith(state, 'dns.');
  const steps = [
    ['domain', checkById(state, 'setup.domain')?.status || 'todo', 'domains'],
    ['mailbox', checkById(state, 'setup.mailbox')?.status || 'todo', 'mailboxes'],
    ['sending', worst([checkById(state, 'setup.sending'), checkById(state, 'out.relay'), checkById(state, 'out.port25')].filter(Boolean)), 'sending'],
    ['dns', state.config.domains.length ? worst(dnsChecks) : 'todo', 'domains'],
    ['port', worst([checkById(state, 'app.port'), checkById(state, 'in.traffic')].filter(Boolean)), 'network'],
    ['test', test?.status === 'ok' ? 'ok' : test?.status === 'running' ? 'pending' : 'todo', null],
  ];
  return h('section', { class: 'card' },
    h('div', { class: 'card-head' }, h('h2', null, t('overview.checklist'))),
    h('ol', { class: 'steps' }, steps.map(([key, status, tab]) =>
      h('li', { class: `step ${status === 'ok' ? 'done' : ''}` },
        icon(status),
        h('div', { class: 'step-body' }, h('div', { class: 'step-title' }, t(`overview.steps.${key}.title`)),
          h('div', { class: 'step-detail' }, t(`overview.steps.${key}.detail`))),
        tab ? h('button', { class: 'button button-quiet button-small', type: 'button', onclick: () => ctx.navigate(tab) },
          status === 'ok' ? t('common.review') : t('common.open')) : null))));
}

// ---- checks ----------------------------------------------------------------------------------

function checkRow(check, ctx) {
  const { title, detail, fix } = describeCheck(check);
  const needsHelp = ['error', 'warn', 'pending'].includes(check.status) && (fix.length || check.guide);
  return h('div', { class: 'check' },
    h('div', { class: 'check-head' }, icon(check.status),
      h('div', null, h('div', { class: 'check-title' }, title), detail ? h('div', { class: 'check-detail' }, detail) : null)),
    needsHelp ? h('details', { open: check.status === 'error' },
      h('summary', null, t('common.how_to_fix')),
      fix.length ? h('ol', { class: 'how' }, fix.map((nodes) => h('li', null, nodes))) : null,
      check.guide ? h('p', null, h('button', { class: 'button button-quiet button-small', type: 'button',
        onclick: () => ctx.navigate(check.guide) }, t('common.open_guide'))) : null) : null);
}

function checksCard(state, ctx) {
  const { checks } = state;
  const body = GROUPS.map((group) => {
    const items = checks.items.filter((check) => check.group === group && !check.id.startsWith('setup.'));
    return items.length ? [h('div', { class: 'group-title' }, t(`overview.groups.${group}`)), items.map((check) => checkRow(check, ctx))] : null;
  });
  return h('section', { class: 'card' },
    h('div', { class: 'card-head' },
      h('div', null, h('h2', null, t('overview.health')),
        h('span', { class: 'muted small' }, checks.updated ? t('common.last_run', { when: timeAgo(checks.updated) }) : t('common.not_run'))),
      h('button', { class: 'button button-quiet', type: 'button', disabled: checks.running,
        onclick: () => attempt(() => api.runChecks()) }, checks.running ? t('common.checking') : t('common.run_checks'))),
    checks.items.length ? body : h('p', { class: 'muted' }, t('overview.first_run')));
}

// ---- test mail -------------------------------------------------------------------------------

function testResult(test, state) {
  const person = state.config.people.find((p) => p.addresses.some((a) => `${a.local}@${a.domain}` === test.alias));
  if (test.status === 'ok') {
    return h('div', { class: 'note' }, h('p', null, t('overview.test.ok', { target: person?.target || t('overview.test.the_mailbox') })));
  }
  if (test.status === 'failed') {
    return h('div', { class: 'note warn' },
      h('p', null, test.error ? describeMessage('delivery', test.error) || test.error.text : t('overview.test.failed_generic')),
      h('p', null, t('overview.test.failed_hint')));
  }
  if (test.status === 'timeout') {
    const stage = !test.steps.sent ? 'not_sent' : !test.steps.arrived ? 'not_arrived' : 'not_forwarded';
    return h('div', { class: 'note warn' }, h('p', null, h('strong', null, t(`overview.test.timeout_${stage}`))),
      h('ul', { class: 'how' }, richList(`overview.test.tips_${stage}`).map((nodes) => h('li', null, nodes))));
  }
  return h('p', { class: 'muted' }, t('overview.test.waiting'));
}

function testCard(state) {
  const addresses = allAddresses(state.config).filter((entry) => entry.enabled);
  const test = state.test_mail;
  const running = test?.status === 'running';
  const select = h('select', { id: 'test-address', 'aria-label': t('overview.test.address') },
    addresses.map((entry) => h('option', { value: entry.address, selected: test?.alias === entry.address }, entry.address)));
  const body = !addresses.length
    ? h('p', { class: 'muted' }, t('overview.test.no_addresses'))
    : [h('p', { class: 'muted' }, t('overview.test.intro')),
       h('div', { class: 'row' }, select,
         h('button', { class: 'button', type: 'button', disabled: running,
           onclick: () => attempt(() => api.sendTestMail(select.value)) }, running ? t('overview.test.running') : t('overview.test.send')))];
  return h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', null, t('overview.test.title'))), body,
    test ? h('div', { class: 'stack', style: 'margin-top:14px' },
      h('ol', { class: 'steps' }, TEST_STEPS.map((key) => {
        const done = test.steps[key];
        return h('li', { class: 'step' }, icon(done ? 'ok' : test.status === 'running' ? 'spinner' : 'todo'),
          h('div', { class: 'step-body' }, h('div', { class: 'step-title' }, t(`overview.test.steps.${key}`)),
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
  return h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', null, t('overview.stats.title'))),
    h('div', { class: 'tiles' },
      tile(stats.forwarded || 0, t('overview.stats.forwarded')),
      tile(queue.queued, t('overview.stats.waiting'), () => ctx.navigate('activity')),
      tile(queue.failed, t('overview.stats.failed'), () => ctx.navigate('activity')),
      tile(stats.rejected || 0, t('overview.stats.rejected')),
      tile(timeAgo(stats.last_forwarded), t('overview.stats.last'))));
}

export function renderOverview(ctx) {
  const { state } = ctx;
  const unfinished = ['setup', 'unverified', 'problem'].includes(state.checks.verdict);
  return h('div', { class: 'grid' },
    banner(state),
    unfinished ? setupSteps(state, ctx) : null,
    checksCard(state, ctx),
    testCard(state),
    statsCard(state, ctx));
}
