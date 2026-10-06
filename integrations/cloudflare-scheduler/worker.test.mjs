import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import worker, {
  DISPATCH_BODY,
  DISPATCH_URL,
  DispatchError,
  EXPECTED_CRON,
  dispatchMonitor,
} from './worker.mjs';

// Deliberately not a credential; never use environment variables in these tests.
const PLACEHOLDER = 'OFFLINE_TEST_PLACEHOLDER_NOT_A_GITHUB_TOKEN';
const REMOTE_TEXT = 'UNTRUSTED_RESPONSE_MUST_NEVER_APPEAR_IN_LOGS';
const env = Object.freeze({ GITHUB_DISPATCH_TOKEN: PLACEHOLDER });

function unreadableResponse(status) {
  return {
    status,
    get headers() { throw new Error(REMOTE_TEXT); },
    get body() { throw new Error(REMOTE_TEXT); },
    async json() { throw new Error(REMOTE_TEXT); },
    async text() { throw new Error(REMOTE_TEXT); },
  };
}

function offlineTransport(response) {
  const calls = [];
  return {
    calls,
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return response;
    },
  };
}

function verifySafeLog(logs, outcome, code, status, requestCount) {
  assert.equal(logs.length, 1);
  assert.ok(!logs[0].includes(PLACEHOLDER));
  assert.ok(!logs[0].includes(REMOTE_TEXT));
  assert.ok(!logs[0].includes('Authorization'));
  const entry = JSON.parse(logs[0]);
  assert.deepEqual(entry, {
    event: 'github-workflow-dispatch',
    outcome,
    code,
    repository: 'richardssheik107-hub/CANNJudgeWatcher',
    workflow: 'monitor.yml',
    ref: 'main',
    reset_history: false,
    request_count: requestCount,
    ...(status === undefined ? {} : { http_status: status }),
  });
}

for (const status of [200, 204]) {
  test('offline dispatch accepts ' + status + ' with fixed safe request', async () => {
    const transport = offlineTransport(unreadableResponse(status));
    const logs = [];
    const result = await dispatchMonitor({
      ...env,
      owner: 'must-not-override',
      repo: 'must-not-override',
      ref: 'must-not-override',
      workflow: 'must-not-override',
      reset_history: true,
      DISPATCH_URL: 'https://must-not-override.invalid/',
    }, { fetchImpl: transport.fetchImpl, report: (line) => logs.push(line) });
    assert.deepEqual(result, { accepted: true, httpStatus: status });
    assert.equal(transport.calls.length, 1);
    const { url, options } = transport.calls[0];
    assert.equal(url, 'https://api.github.com/repos/richardssheik107-hub/CANNJudgeWatcher/actions/workflows/monitor.yml/dispatches');
    assert.equal(url, DISPATCH_URL);
    assert.equal(options.method, 'POST');
    assert.equal(options.redirect, 'error');
    assert.ok(options.signal instanceof AbortSignal);
    assert.equal(options.signal.aborted, false);
    assert.deepEqual(options.headers, {
      Accept: 'application/vnd.github+json',
      Authorization: 'Bearer ' + PLACEHOLDER,
      'Content-Type': 'application/json',
      'User-Agent': 'CANNJudgeWatcher-Cloudflare-Cron',
      'X-GitHub-Api-Version': '2026-03-10',
    });
    assert.equal(options.body, DISPATCH_BODY);
    assert.deepEqual(JSON.parse(options.body), { ref: 'main', inputs: { reset_history: false } });
    verifySafeLog(logs, 'accepted', 'dispatch-accepted', status, 1);
  });
}

for (const status of [401, 403, 404, 429, 500, 503]) {
  test('offline HTTP ' + status + ' fails once without retry or response disclosure', async () => {
    const transport = offlineTransport(unreadableResponse(status));
    const logs = [];
    await assert.rejects(dispatchMonitor(env, {
      fetchImpl: transport.fetchImpl,
      report: (line) => logs.push(line),
    }), (error) => error instanceof DispatchError && error.code === 'http-error' && error.httpStatus === status);
    assert.equal(transport.calls.length, 1);
    verifySafeLog(logs, 'failed', 'http-error', status, 1);
  });
}

test('offline unexpected 2xx does not claim accepted', async () => {
  const transport = offlineTransport(unreadableResponse(202));
  const logs = [];
  await assert.rejects(dispatchMonitor(env, {
    fetchImpl: transport.fetchImpl,
    report: (line) => logs.push(line),
  }), (error) => error.code === 'unexpected-success-status');
  assert.equal(transport.calls.length, 1);
  verifySafeLog(logs, 'failed', 'unexpected-success-status', 202, 1);
});

for (const absentEnv of [undefined, {}, { GITHUB_DISPATCH_TOKEN: '' }, { GITHUB_DISPATCH_TOKEN: '  ' }]) {
  test('offline missing secret rejects before any network request', async () => {
    const transport = offlineTransport(unreadableResponse(200));
    const logs = [];
    await assert.rejects(dispatchMonitor(absentEnv, {
      fetchImpl: transport.fetchImpl,
      report: (line) => logs.push(line),
    }), (error) => error.code === 'missing-secret');
    assert.equal(transport.calls.length, 0);
    verifySafeLog(logs, 'failed', 'missing-secret', undefined, 0);
  });
}

test('offline malformed secret rejects before any network request', async () => {
  const transport = offlineTransport(unreadableResponse(200));
  const logs = [];
  await assert.rejects(dispatchMonitor({ GITHUB_DISPATCH_TOKEN: PLACEHOLDER + '\n' }, {
    fetchImpl: transport.fetchImpl,
    report: (line) => logs.push(line),
  }), (error) => error.code === 'invalid-secret');
  assert.equal(transport.calls.length, 0);
  verifySafeLog(logs, 'failed', 'invalid-secret', undefined, 0);
});

test('offline network exception message is replaced with a safe error', async () => {
  const logs = [];
  let calls = 0;
  await assert.rejects(dispatchMonitor(env, {
    fetchImpl: async () => {
      calls += 1;
      throw new Error(PLACEHOLDER + ' ' + REMOTE_TEXT);
    },
    report: (line) => logs.push(line),
  }), (error) => error instanceof DispatchError && error.code === 'network-error' && !String(error).includes(PLACEHOLDER));
  assert.equal(calls, 1);
  verifySafeLog(logs, 'failed', 'network-error', undefined, 1);
});

test('offline timeout aborts exactly one request and rejects even if transport ignores abort', async () => {
  const logs = [];
  let calls = 0;
  let signal;
  await assert.rejects(dispatchMonitor(env, {
    fetchImpl: async (_, options) => {
      calls += 1;
      signal = options.signal;
      return new Promise(() => {});
    },
    report: (line) => logs.push(line),
    timeoutMs: 10,
  }), (error) => error instanceof DispatchError && error.code === 'timeout');
  assert.equal(calls, 1);
  assert.equal(signal.aborted, true);
  verifySafeLog(logs, 'failed', 'timeout', undefined, 1);
});

test('offline scheduled handler only runs the configured Cron and has no HTTP endpoint', async (t) => {
  const logs = [];
  const transport = offlineTransport(unreadableResponse(200));
  t.mock.method(globalThis, 'fetch', transport.fetchImpl);
  t.mock.method(console, 'info', (line) => logs.push(line));
  assert.deepEqual(Object.keys(worker), ['scheduled']);
  assert.equal(worker.fetch, undefined);
  assert.equal(EXPECTED_CRON, '*/10 * * * *');
  await worker.scheduled({ cron: EXPECTED_CRON }, env);
  assert.equal(transport.calls.length, 1);
  verifySafeLog(logs, 'accepted', 'dispatch-accepted', 200, 1);
  logs.length = 0;
  await assert.rejects(worker.scheduled({ cron: '* * * * *' }, env), (error) => error.code === 'unexpected-schedule');
  assert.equal(transport.calls.length, 1);
  verifySafeLog(logs, 'failed', 'unexpected-schedule', undefined, 0);
});

test('offline deployment configuration disables every HTTP route and requires only a Secret', async () => {
  const config = JSON.parse(await readFile(new URL('./wrangler.jsonc', import.meta.url), 'utf8'));
  assert.equal(config.main, 'worker.mjs');
  assert.equal(config.workers_dev, false);
  assert.equal(config.preview_urls, false);
  assert.deepEqual(config.routes, []);
  assert.deepEqual(config.triggers.crons, [EXPECTED_CRON]);
  assert.deepEqual(config.secrets, { required: ['GITHUB_DISPATCH_TOKEN'] });
  assert.equal(config.vars, undefined);
  assert.ok(!JSON.stringify(config).includes(PLACEHOLDER));
});
