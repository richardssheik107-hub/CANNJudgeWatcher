import worker, { EXPECTED_CRON } from './worker.mjs';

// This literal is deliberately not a credential. Never load host environment
// variables or real Worker secrets into these offline runtime tests.
const PLACEHOLDER = 'OFFLINE_TEST_PLACEHOLDER_NOT_A_GITHUB_TOKEN';
const env = Object.freeze({ GITHUB_DISPATCH_TOKEN: PLACEHOLDER });

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

export default {
  async test(_controller, testEnv) {
    const status = Number(testEnv.EXPECTED_STATUS);
    assert([204, 301, 302, 303, 307, 308].includes(status), 'Unknown runtime fixture');
    assert(EXPECTED_CRON === '*/10 * * * *', 'Cron changed');
    assert(Object.keys(worker).join(',') === 'scheduled', 'Unexpected public handler');

    const logs = [];
    let error;
    const originalInfo = console.info;
    console.info = (line) => logs.push(line);
    try {
      // Call the real scheduled handler, including the real native global fetch.
      // config.capnp routes global fetch exclusively to the local fixture Worker.
      await worker.scheduled({ cron: EXPECTED_CRON }, env);
    } catch (caught) {
      error = caught;
    } finally {
      console.info = originalInfo;
    }

    if (status === 204) {
      assert(error === undefined, 'Native scheduled dispatch did not accept 204');
    } else {
      assert(error?.code === 'http-error', 'Redirect was not rejected as an HTTP error');
      assert(error.httpStatus === status, 'Wrong redirect status');
    }

    assert(logs.length === 1, 'Expected one safe dispatch report');
    assert(typeof logs[0] === 'string', 'Report is not structured text');
    assert(!logs[0].includes(PLACEHOLDER), 'Placeholder leaked into report');
    assert(!logs[0].includes('Authorization'), 'Request header leaked into report');
    const entry = JSON.parse(logs[0]);
    const expected = {
      event: 'github-workflow-dispatch',
      outcome: status === 204 ? 'accepted' : 'failed',
      code: status === 204 ? 'dispatch-accepted' : 'http-error',
      repository: 'richardssheik107-hub/CANNJudgeWatcher',
      workflow: 'monitor.yml',
      ref: 'main',
      reset_history: false,
      request_count: 1,
      http_status: status,
    };
    assert(Object.keys(entry).length === Object.keys(expected).length, 'Unexpected report fields');
    for (const [key, value] of Object.entries(expected)) {
      assert(entry[key] === value, 'Wrong report field: ' + key);
    }
    console.log('Native scheduled ' + status + ': PASS; one request, fixed inputs, no redirect following');
  },
};
