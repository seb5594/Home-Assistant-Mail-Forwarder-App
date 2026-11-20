// Talks to the app's JSON API. URLs are relative because Home Assistant ingress serves the page
// below a long, changing path.

export class ApiError extends Error {
  constructor(message, code = '', params = {}) {
    super(message);
    this.code = code;
    this.params = params;
  }
}

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
    throw new ApiError('The app does not answer.', 'unreachable');
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(payload.error || `Request failed (${response.status})`, payload.code, payload.params);
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
