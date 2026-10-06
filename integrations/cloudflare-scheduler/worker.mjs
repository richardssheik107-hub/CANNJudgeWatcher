// Credentials belong only in a Cloudflare Worker Secret.
export const EXPECTED_CRON = '*/10 * * * *';
export const REQUEST_TIMEOUT_MS = 10_000;
export const DISPATCH_URL = 'https://api.github.com/repos/richardssheik107-hub/CANNJudgeWatcher/actions/workflows/monitor.yml/dispatches';
export const DISPATCH_BODY = '{"ref":"main","inputs":{"reset_history":false}}';

export class DispatchError extends Error {
  constructor(code, httpStatus) {
    super('GitHub workflow dispatch failed: ' + code);
    this.name = 'DispatchError';
    this.code = code;
    if (Number.isInteger(httpStatus)) this.httpStatus = httpStatus;
  }
}

function safeReport(report, outcome, code, httpStatus, requestCount) {
  const entry = {
    event: 'github-workflow-dispatch',
    outcome,
    code,
    repository: 'richardssheik107-hub/CANNJudgeWatcher',
    workflow: 'monitor.yml',
    ref: 'main',
    reset_history: false,
    request_count: requestCount,
  };
  if (Number.isInteger(httpStatus)) entry.http_status = httpStatus;
  report(JSON.stringify(entry));
}

function rejectDispatch(report, code, httpStatus, requestCount) {
  safeReport(report, 'failed', code, httpStatus, requestCount);
  return new DispatchError(code, httpStatus);
}

// Injectable transport/reporter/timeout allow fully offline tests. None of these
// options can change the repository, branch, workflow, or dispatch inputs.
export async function dispatchMonitor(env, {
  fetchImpl = globalThis.fetch,
  report = (line) => console.info(line),
  timeoutMs = REQUEST_TIMEOUT_MS,
} = {}) {
  const token = env?.GITHUB_DISPATCH_TOKEN;
  if (typeof token !== 'string' || !token.trim()) {
    throw rejectDispatch(report, 'missing-secret', undefined, 0);
  }
  if (/\s/.test(token)) {
    throw rejectDispatch(report, 'invalid-secret', undefined, 0);
  }
  if (!Number.isInteger(timeoutMs) || timeoutMs <= 0) {
    throw rejectDispatch(report, 'invalid-timeout', undefined, 0);
  }

  const controller = new AbortController();
  let timedOut = false;
  let timer;
  let response;
  try {
    const deadline = new Promise((_, reject) => {
      timer = setTimeout(() => {
        timedOut = true;
        controller.abort();
        reject(new DispatchError('timeout'));
      }, timeoutMs);
    });
    const request = Promise.resolve().then(() => fetchImpl(DISPATCH_URL, {
      method: 'POST',
      headers: {
        Accept: 'application/vnd.github+json',
        Authorization: 'Bearer ' + token,
        'Content-Type': 'application/json',
        'User-Agent': 'CANNJudgeWatcher-Cloudflare-Cron',
        'X-GitHub-Api-Version': '2026-03-10',
      },
      body: DISPATCH_BODY,
      // Workers supports manual/follow only. Never follow a redirect with credentials;
      // every 3xx response is rejected below before a second request can be sent.
      redirect: 'manual',
      signal: controller.signal,
    }));
    response = await Promise.race([request, deadline]);
  } catch {
    // Do not expose transport errors; a thrown message can include credentials.
    throw rejectDispatch(report, timedOut ? 'timeout' : 'network-error', undefined, 1);
  } finally {
    clearTimeout(timer);
  }

  // Never read or log the response body, headers, request, or secret.
  const status = response?.status;
  if (!Number.isInteger(status) || status < 100 || status > 599) {
    throw rejectDispatch(report, 'invalid-response', undefined, 1);
  }
  if (status < 200 || status >= 300) {
    throw rejectDispatch(report, 'http-error', status, 1);
  }
  if (status !== 200 && status !== 204) {
    throw rejectDispatch(report, 'unexpected-success-status', status, 1);
  }

  // Accepted means GitHub accepted the dispatch, not that collection/deploy passed.
  safeReport(report, 'accepted', 'dispatch-accepted', status, 1);
  return Object.freeze({ accepted: true, httpStatus: status });
}

export default {
  async scheduled(controller, env) {
    if (controller?.cron !== EXPECTED_CRON) {
      throw rejectDispatch((line) => console.info(line), 'unexpected-schedule', undefined, 0);
    }
    await dispatchMonitor(env);
  },
  // Deliberately no fetch handler and no public HTTP dispatch endpoint.
};
