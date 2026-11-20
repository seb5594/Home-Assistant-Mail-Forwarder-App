// Activity: the queue and the recent events of the app.
import { api } from '../api.js';
import { attempt, confirmDialog, ctx as shared } from '../context.js';
import { describeMessage } from '../checkview.js';
import { h } from '../dom.js';
import { clock, inFuture, timeAgo } from '../format.js';
import { has, t } from '../i18n.js';

let cache = { queue: { queued: [], failed: [] }, events: [] };
let loading = false;

async function load() {
  if (loading) return;
  loading = true;
  try {
    const [queue, activity] = await Promise.all([api.queue(), api.activity()]);
    const next = { queue, events: activity.events };
    if (JSON.stringify(next) !== JSON.stringify(cache)) {
      cache = next;
      shared.render(true);
    }
  } finally {
    loading = false;
  }
}

// The text of an event in the current language; the English text of the app is the fallback.
function eventText(event) {
  const key = `events.${event.code}`;
  if (!event.code || !has(key)) return event.message;
  const params = { ...event.params };
  let text = t(key, params);
  if (params.error_code) text += ` ${describeMessage('delivery', { code: params.error_code, params: params.error_params })}`;
  return text;
}

function problemText(job) {
  return job.error_code ? describeMessage('delivery', { code: job.error_code, params: job.error_params }) : '–';
}

function jobRows(jobs, failed) {
  return jobs.map((job) => h('tr', null,
    h('td', null, h('div', null, job.aliases.join(', ')), h('div', { class: 'muted small' }, t('common.from', { sender: job.sender || t('common.unknown_sender') }))),
    h('td', null, job.target),
    h('td', null, failed ? t('activity.gave_up_when', { when: timeAgo(job.failed_at) })
      : job.attempts ? t('activity.try_n', { n: job.attempts + 1, when: inFuture(job.next_attempt) }) : t('activity.sending_now')),
    h('td', { class: job.needs_attention ? 'log-warning' : 'muted' }, problemText(job)),
    h('td', null, h('div', { class: 'row' },
      h('button', { class: 'button button-quiet button-small', type: 'button',
        onclick: () => attempt(() => api.queueAction(job.id, 'retry'), t('activity.retrying')) }, failed ? t('activity.retry') : t('activity.send_now')),
      h('button', { class: 'button button-danger button-small', type: 'button', onclick: async () => {
        const sure = await confirmDialog({ title: t('activity.delete_title'), message: t('activity.delete_text'), confirmLabel: t('common.delete'), danger: true });
        if (sure) await attempt(() => api.queueAction(job.id, 'delete'), t('activity.deleted'));
      } }, t('common.delete'))))));
}

function queueTable(title, jobs, failed, emptyText) {
  return h('section', { class: 'card' }, h('h2', null, title),
    jobs.length ? h('div', { class: 'table-wrap' }, h('table', null,
      h('thead', null, h('tr', null, ['address', 'goes_to', 'status', 'problem'].map((key) => h('th', null, t(`activity.${key}`))), h('th', null))),
      h('tbody', null, jobRows(jobs, failed)))) : h('p', { class: 'muted' }, emptyText));
}

export function renderActivity() {
  load();
  const { queue, events } = cache;
  return h('div', { class: 'grid' },
    queueTable(t('activity.waiting_title'), queue.queued, false, t('activity.waiting_none')),
    queue.failed.length ? queueTable(t('activity.failed_title'), queue.failed, true, '') : null,
    h('section', { class: 'card' }, h('h2', null, t('activity.events')),
      events.length ? h('div', { class: 'log' }, events.map((event) => h('div', { class: 'log-line' },
        h('span', { class: 'log-time' }, clock(event.time)),
        h('span', { class: `log-${event.level}` }, eventText(event)))))
        : h('p', { class: 'muted' }, t('activity.events_none'))));
}
