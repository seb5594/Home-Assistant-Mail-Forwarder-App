// Activity: the queue and the recent events of the app.
import { api } from '../api.js';
import { attempt, confirmDialog, ctx as shared } from '../context.js';
import { h } from '../dom.js';
import { clock, inFuture, timeAgo } from '../format.js';

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

function jobRows(jobs, failed) {
  return jobs.map((job) => h('tr', null,
    h('td', null, h('div', null, job.aliases.join(', ')), h('div', { class: 'muted small' }, `from ${job.sender || 'unknown'}`)),
    h('td', null, job.target),
    h('td', null, failed ? `gave up ${timeAgo(job.failed_at)}` : job.attempts ? `try ${job.attempts + 1} ${inFuture(job.next_attempt)}` : 'sending now'),
    h('td', { class: job.needs_attention ? 'log-warning' : 'muted' }, job.last_error || '–'),
    h('td', null, h('div', { class: 'row' },
      h('button', { class: 'button button-quiet button-small', type: 'button',
        onclick: () => attempt(() => api.queueAction(job.id, 'retry'), 'Trying again') }, failed ? 'Try again' : 'Send now'),
      h('button', { class: 'button button-danger button-small', type: 'button', onclick: async () => {
        const sure = await confirmDialog({ title: 'Delete this message?', message: 'It is removed for good and never delivered.', confirmLabel: 'Delete', danger: true });
        if (sure) await attempt(() => api.queueAction(job.id, 'delete'), 'Deleted');
      } }, 'Delete')))));
}

function queueTable(title, jobs, failed, emptyText) {
  return h('section', { class: 'card' }, h('h2', null, title),
    jobs.length ? h('div', { class: 'table-wrap' }, h('table', null,
      h('thead', null, h('tr', null, ['Address', 'Goes to', 'Status', 'Last problem', ''].map((name) => h('th', null, name)))),
      h('tbody', null, jobRows(jobs, failed)))) : h('p', { class: 'muted' }, emptyText));
}

export function renderActivity() {
  load();
  const { queue, events } = cache;
  return h('div', { class: 'grid' },
    queueTable('Waiting to be sent', queue.queued, false, 'Nothing is waiting. Messages normally leave within seconds.'),
    queue.failed.length ? queueTable('Given up on', queue.failed, true, '') : null,
    h('section', { class: 'card' }, h('h2', null, 'Recent events'),
      events.length ? h('div', { class: 'log' }, events.map((event) => h('div', { class: 'log-line' },
        h('span', { class: 'log-time' }, clock(event.time)),
        h('span', { class: `log-${event.level}` }, event.message))))
        : h('p', { class: 'muted' }, 'Nothing has happened since the app started.')));
}
