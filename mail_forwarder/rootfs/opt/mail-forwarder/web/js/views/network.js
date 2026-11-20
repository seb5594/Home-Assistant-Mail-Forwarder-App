// Router & network: everything between the internet and port 25 of this app.
import { api } from '../api.js';
import { attempt } from '../context.js';
import { copyable, h, icon } from '../dom.js';

let selectedRouter = 'opnsense';

const ROUTERS = [
  ['opnsense', 'OPNsense'],
  ['fritzbox', 'FRITZ!Box'],
  ['other', 'Other router'],
];

function step(title, ...details) {
  return h('li', null, h('strong', null, title), details.length ? h('div', { class: 'muted' }, details) : null);
}

function settingsTable(rows) {
  return h('div', { class: 'table-wrap' }, h('table', null,
    h('thead', null, h('tr', null, h('th', null, 'Setting'), h('th', null, 'Value'))),
    h('tbody', null, rows.map(([name, value]) => h('tr', null, h('td', null, name), h('td', null, value))))));
}

function opnsense(values) {
  return h('div', { class: 'stack' },
    h('p', null, 'OPNsense does not open anything by default, which is good. You need one port forward (NAT rule) and, on its way in, one matching firewall rule that OPNsense creates for you.'),
    h('ol', { class: 'how' },
      step('Give Home Assistant a fixed address',
        'Services, then DHCPv4, then your LAN, then "Static mappings": add the MAC address of the Home Assistant computer with the address ', copyable(values.haHost),
        '. Otherwise the forward points to the wrong device after a restart.'),
      step('Create the port forward',
        'Firewall, then NAT, then "Port Forward" (called "Destination NAT" in newer versions). Click "+" and fill in:'),
      settingsTable([
        ['Interface', 'WAN'],
        ['TCP/IP Version', 'IPv4'],
        ['Protocol', 'TCP'],
        ['Source', 'any'],
        ['Destination', 'WAN address'],
        ['Destination port range', 'from SMTP to SMTP (that is port 25)'],
        ['Redirect target IP', copyable(values.haHost)],
        ['Redirect target port', copyable(String(values.hostPort))],
        ['Description', 'Mail Forwarder (Home Assistant)'],
        ['NAT reflection', 'Enable'],
        ['Filter rule association', 'Add associated filter rule'],
      ]),
      step('Save and apply', 'Press "Save", then "Apply changes" on top of the list. Without applying, nothing happens.'),
      step('Look at the filter rules that guard WAN',
        'Mail servers all over the world connect to you. If you use country blocking (GeoIP), CrowdSec, Zenarmor or an IP block list in front of WAN, make sure they do not drop the big mail providers, which mostly sit in the USA.'),
      step('Allow Home Assistant to go out',
        'If you restrict outgoing traffic of the Home Assistant network, allow TCP to your sending service (usually port 587) and HTTPS (443). Home Assistant needs 443 anyway, the app uses it for DNS checks and to find your public IP.'),
      step('Look at the live log while you test',
        'Open Firewall, then "Log Files", then "Live View", and filter for destination port 25. Send the test mail from the Overview. A green "pass" line from an outside address means that the router did its part. A red "block" line shows which rule to fix. Nothing at all means that the traffic never reaches you, which points to your provider (see above).')),
    h('div', { class: 'note' }, h('p', null, h('strong', null, 'Dynamic DNS: '),
      'let either this app (Domains page) or the OPNsense plugin "os-ddclient" update your DNS records, not both.')),
    h('div', { class: 'note' }, h('p', null, h('strong', null, 'Optional, for tests from inside your network: '),
      'Services, then Unbound DNS, then "Overrides": add your mail server name ', h('em', null, '(for example mail.your-domain.com)'),
      ' pointing to ', copyable(values.haHost), ' so that your own devices reach the app directly.')));
}

function fritzbox(values) {
  return h('div', { class: 'stack' },
    h('p', null, 'The menu names below are the German ones of the FRITZ!Box with the English meaning in brackets.'),
    h('ol', { class: 'how' },
      step('Keep the address of Home Assistant fixed',
        'Heimnetz, then Netzwerk (Home network, Network): open the Home Assistant entry and tick "Diesem Netzwerkgerät immer die gleiche IPv4-Adresse zuweisen" (always assign the same address).'),
      step('Create the port sharing',
        'Internet, then Freigaben (Permit access), then Portfreigaben (Port sharing). Click "Gerät für Freigaben hinzufügen", pick the Home Assistant device, then "Neue Freigabe":'),
      settingsTable([
        ['Freigabe (Type)', 'Portfreigabe'],
        ['Anwendung (Application)', 'Andere Anwendung'],
        ['Bezeichnung (Name)', 'Mail Forwarder'],
        ['Protokoll (Protocol)', 'TCP'],
        ['Port an Gerät (Port on the device)', `${values.hostPort} bis ${values.hostPort}`],
        ['Port extern gewünscht (External port)', '25 bis 25'],
        ['Freigabe aktivieren', 'ticked'],
      ]),
      step('Check that your connection is allowed to do this',
        'If the FRITZ!Box says that the connection is "DS-Lite" or shows no public IPv4 address, incoming mail cannot reach you. See "Can your connection receive mail?" above.')));
}

function other(values) {
  return h('div', { class: 'stack' },
    h('p', null, 'Every router calls it differently: "Port forwarding", "Virtual server", "NAT" or "Applications and gaming". The rule you need:'),
    settingsTable([
      ['Protocol', 'TCP'],
      ['External / WAN port', '25'],
      ['Internal IP address', copyable(values.haHost)],
      ['Internal port', copyable(String(values.hostPort))],
    ]),
    h('p', { class: 'muted small' }, 'Also give the Home Assistant computer a fixed address in the router (DHCP reservation), so that the rule keeps pointing at it.'));
}

function connectionCard() {
  return h('section', { class: 'card' },
    h('h2', null, 'Can your connection receive mail?'),
    h('p', null, 'Most problems are not about your router but about the internet connection itself. Check these three things before you spend an evening on firewall rules:'),
    h('ul', { class: 'how' },
      h('li', null, h('strong', null, 'A real public IPv4 address. '),
        'Compare the "WAN address" in your router with the public IP shown above. If they differ, or the WAN address starts with 100.64 to 100.127, 10., 172.16 to 172.31 or 192.168, your provider shares one address between many customers (CGNAT or DS-Lite). Nothing can reach you from outside then. Many providers lift this for free or a small fee, ask for a "public IPv4 address" or a "Dual Stack" tariff.'),
      h('li', null, h('strong', null, 'Incoming port 25 is not blocked by the provider. '),
        'Some providers block it on private contracts. A quick sign: the router log shows nothing when the test mail is sent. Ask the provider to unblock port 25 for incoming connections, or use a business tariff.'),
      h('li', null, h('strong', null, 'Outgoing connections work. '),
        'The sending service is reached on port 587, which is almost never blocked. This is the reason why the app sends through a service and not directly.')),
    h('div', { class: 'note' }, h('p', null, h('strong', null, 'Cannot get port 25? '),
      'If your domain is on Cloudflare, its free "Email Routing" forwards mail to your inbox without any home server. It needs no port and no router settings, but only works with domains at Cloudflare (not DuckDNS), and the forwarding addresses must be verified one by one.')));
}

function healthRows(state) {
  const ids = ['app.listener', 'app.port', 'net.ip', 'in.traffic'];
  return ids.map((id) => state.checks.items.find((check) => check.id === id)).filter(Boolean);
}

export function renderNetwork(ctx) {
  const { state } = ctx;
  const values = {
    haHost: state.host_addresses[0] || location.hostname || '<address of Home Assistant>',
    hostPort: state.host_port || state.smtp_port,
    publicIp: state.public_ip || 'unknown',
  };
  const portMissing = state.host_port === null && state.checks.items.find((check) => check.id === 'app.port')?.status === 'error';
  const tabs = h('div', { class: 'subtabs' }, ROUTERS.map(([id, label]) =>
    h('button', { class: 'subtab', type: 'button', 'aria-pressed': String(selectedRouter === id),
      onclick: () => { selectedRouter = id; ctx.render(true); } }, label)));
  const guides = { opnsense, fritzbox, other };

  return h('div', { class: 'grid' },
    h('section', { class: 'card' }, h('h2', null, 'How mail finds its way to this app'),
      h('p', null, 'A sender looks up the MX record of your domain, connects to your public IP address on port 25, your router forwards that connection to Home Assistant, and Home Assistant hands it to this app.'),
      h('div', { class: 'tiles' },
        h('div', { class: 'tile' }, h('div', { class: 'tile-value mono' }, values.publicIp), h('div', { class: 'tile-label' }, 'your public IP')),
        h('div', { class: 'tile' }, h('div', { class: 'tile-value mono' }, values.haHost), h('div', { class: 'tile-label' }, 'Home Assistant address (check it, it may differ)')),
        h('div', { class: 'tile' }, h('div', { class: 'tile-value mono' }, `25 → ${values.hostPort}`), h('div', { class: 'tile-label' }, 'router port → Home Assistant port')))),
    h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', null, 'Where things stand'),
      h('button', { class: 'button button-quiet', type: 'button', disabled: state.checks.running,
        onclick: () => attempt(() => api.runChecks()) }, state.checks.running ? 'Checking…' : 'Run checks now')),
    healthRows(state).map((check) => h('div', { class: 'check' }, h('div', { class: 'check-head' }, icon(check.status),
      h('div', null, h('div', { class: 'check-title' }, check.title), check.detail ? h('div', { class: 'check-detail' }, check.detail) : null),
    )))),
    portMissing ? h('section', { class: 'card' }, h('h2', null, 'Step 1: publish the port in Home Assistant'),
      h('p', null, 'Home Assistant keeps app ports closed until you open them:'),
      h('ol', { class: 'how' },
        h('li', null, 'Open this app in Home Assistant (Settings, Apps, Mail Forwarder) and go to the tab ', h('strong', null, 'Configuration'), '.'),
        h('li', null, 'Under ', h('strong', null, 'Network'), ' enter ', h('code', null, '25'), ' next to ', h('code', null, '25/tcp'), '. If port 25 is taken on your Home Assistant, pick another one, for example 2525, and use that in the router.'),
        h('li', null, 'Save and restart the app.'))) : null,
    connectionCard(),
    h('section', { class: 'card' }, h('h2', null, 'Open port 25 in your router'), tabs, guides[selectedRouter](values)),
    h('section', { class: 'card' }, h('h2', null, 'Then prove it works'),
      h('p', null, 'Press "Send test mail" on the Overview. The app sends a message through your sending service to your own address. If it comes back in through the internet, DNS, router and port are all right.'),
      h('button', { class: 'button', type: 'button', onclick: () => ctx.navigate('overview') }, 'Go to the Overview')));
}
