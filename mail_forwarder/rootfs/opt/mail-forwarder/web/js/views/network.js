// Router & network: everything between the internet and port 25 of this app.
import { api } from '../api.js';
import { attempt } from '../context.js';
import { describeCheck } from '../checkview.js';
import { copyable, h, icon } from '../dom.js';
import { pairs, rich, richText, t } from '../i18n.js';

let selectedRouter = 'opnsense';

const ROUTERS = ['opnsense', 'fritzbox', 'other'];
const OPNSENSE_ROWS = ['interface', 'version', 'protocol', 'src_invert', 'src_address', 'src_port', 'dst_invert',
  'dst_address', 'dst_port', 'redirect_ip', 'redirect_port', 'log', 'rule'];

function step(title, text) {
  return h('li', null, h('strong', null, title), h('div', { class: 'muted' }, text));
}

function settingsTable(rows) {
  return h('div', { class: 'table-wrap' }, h('table', null,
    h('thead', null, h('tr', null, h('th', null, t('network.setting')), h('th', null, t('network.value')))),
    h('tbody', null, rows.map(([name, value]) => h('tr', null, h('td', null, name), h('td', null, value))))));
}

function opnsense(values) {
  const p = { ha: values.haHost, port: values.hostPort };
  const rows = OPNSENSE_ROWS.map((key) => {
    const [name, value] = pairs(`network.opn.rows.${key}`);
    const content = key === 'redirect_ip' ? [richText(value, p), ' ', copyable(values.haHost)] : richText(value, p);
    return [name, content];
  });
  const text = (key) => rich(`network.opn.${key}`, p);
  return h('div', { class: 'stack' },
    h('p', null, text('intro')),
    h('ol', { class: 'how' },
      step(t('network.opn.s1_title'), text('s1_text')),
      step(t('network.opn.s2_title'), [text('s2_text'), values.hostPort !== 25 ? [' ', text('s2_port')] : null]),
      step(t('network.opn.s3_title'), text('s3_text')),
    ),
    settingsTable(rows),
    h('ol', { class: 'how', start: 4 },
      step(t('network.opn.s4_title'), text('s4_text')),
      step(t('network.opn.s5_title'), text('s5_text')),
      step(t('network.opn.s6_title'), text('s6_text')),
      step(t('network.opn.s7_title'), text('s7_text')),
      step(t('network.opn.s8_title'), text('s8_text'))),
    h('div', { class: 'note' }, h('p', null, text('ddns'))),
    h('div', { class: 'note' }, h('p', null, text('reflection'))));
}

function fritzbox(values) {
  const p = { ha: values.haHost, port: values.hostPort };
  const text = (key) => rich(`network.fritz.${key}`, p);
  return h('div', { class: 'stack' },
    h('p', null, text('intro')),
    h('ol', { class: 'how' },
      step(t('network.fritz.s1_title'), text('s1_text')),
      step(t('network.fritz.s2_title'), text('s2_text'))),
    settingsTable(pairs('network.fritz.rows').map(([name, value]) => [name, richText(value, p)])),
    h('ol', { class: 'how', start: 3 }, step(t('network.fritz.s3_title'), text('s3_text'))));
}

function other(values) {
  const p = { ha: values.haHost, port: values.hostPort };
  return h('div', { class: 'stack' },
    h('p', null, rich('network.other.intro')),
    settingsTable(pairs('network.other.rows').map(([name, value]) =>
      [name, value.includes('{') ? copyable(richText(value, p).join('')) : value])),
    h('p', { class: 'muted small' }, rich('network.other.note')));
}

function connectionCard() {
  return h('section', { class: 'card' },
    h('h2', null, t('network.conn.title')),
    h('p', null, t('network.conn.intro')),
    h('ul', { class: 'how' }, [0, 1, 2].map((index) => h('li', null, richTextAt(`network.conn.items.${index}`)))),
    h('div', { class: 'note' }, h('p', null, rich('network.conn.cloudflare'))));
}

function richTextAt(key) {
  return rich(key);
}

function healthRows(state) {
  const ids = ['app.listener', 'app.port', 'net.ip', 'in.traffic'];
  return ids.map((id) => state.checks.items.find((check) => check.id === id)).filter(Boolean);
}

export function renderNetwork(ctx) {
  const { state } = ctx;
  const values = {
    haHost: state.host_addresses[0] || location.hostname || t('network.ha_placeholder'),
    hostPort: state.host_port || state.smtp_port,
    publicIp: state.public_ip || t('network.unknown_ip'),
  };
  const portMissing = state.host_port === null && state.checks.items.find((check) => check.id === 'app.port')?.status === 'error';
  const tabs = h('div', { class: 'subtabs' }, ROUTERS.map((id) =>
    h('button', { class: 'subtab', type: 'button', 'aria-pressed': String(selectedRouter === id),
      onclick: () => { selectedRouter = id; ctx.render(true); } }, t(`network.routers.${id}`))));
  const guides = { opnsense, fritzbox, other };

  return h('div', { class: 'grid' },
    h('section', { class: 'card' }, h('h2', null, t('network.flow_title')),
      h('p', null, t('network.flow_text')),
      h('div', { class: 'tiles' },
        h('div', { class: 'tile' }, h('div', { class: 'tile-value mono' }, values.publicIp), h('div', { class: 'tile-label' }, t('network.tile_ip'))),
        h('div', { class: 'tile' }, h('div', { class: 'tile-value mono' }, values.haHost), h('div', { class: 'tile-label' }, t('network.tile_ha'))),
        h('div', { class: 'tile' }, h('div', { class: 'tile-value mono' }, `25 → ${values.hostPort}`), h('div', { class: 'tile-label' }, t('network.tile_port')))),
    ),
    h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', null, t('network.state_title')),
      h('button', { class: 'button button-quiet', type: 'button', disabled: state.checks.running,
        onclick: () => attempt(() => api.runChecks()) }, state.checks.running ? t('common.checking') : t('common.run_checks'))),
    healthRows(state).map((check) => {
      const { title, detail } = describeCheck(check);
      return h('div', { class: 'check' }, h('div', { class: 'check-head' }, icon(check.status),
        h('div', null, h('div', { class: 'check-title' }, title), detail ? h('div', { class: 'check-detail' }, detail) : null)));
    })),
    portMissing ? h('section', { class: 'card' }, h('h2', null, t('network.publish.title')),
      h('p', null, t('network.publish.intro')),
      h('ol', { class: 'how' }, [0, 1, 2].map((index) => h('li', null, rich(`network.publish.steps.${index}`))))) : null,
    connectionCard(),
    h('section', { class: 'card' }, h('h2', null, t('network.router_title')), tabs, guides[selectedRouter](values)),
    h('section', { class: 'card' }, h('h2', null, t('network.verify_title')),
      h('p', null, t('network.verify_text')),
      h('button', { class: 'button', type: 'button', onclick: () => ctx.navigate('overview') }, t('common.go_overview'))));
}
