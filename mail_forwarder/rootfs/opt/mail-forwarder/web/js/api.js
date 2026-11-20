// Talks to the app's JSON API. URLs are relative because Home Assistant ingress serves the page
// below a long, changing path.

async function request(method, path, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  } else if (method !== 'GET') {
    options.headers['Content-Type'] = 'application/json';
    options.body = '{}';
  }
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new Error('The app does not answer. Is it still running?');
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

export const api = {
  state: () => request('GET', 'api/state'),
  queue: () => request('GET', 'api/queue'),
  activity: () => request('GET', 'api/activity'),
  saveConfig: (config) => request('PUT', 'api/config', config),
  runChecks: () => request('POST', 'api/checks/run'),
  testLogin: () => request('POST', 'api/relay/test'),
  sendTestMail: (address) => request('POST', 'api/test-mail', { address }),
  updateDns: () => request('POST', 'api/ddns/run'),
  queueAction: (id, action) => request('POST', `api/queue/${encodeURIComponent(id)}/${action}`),
};
