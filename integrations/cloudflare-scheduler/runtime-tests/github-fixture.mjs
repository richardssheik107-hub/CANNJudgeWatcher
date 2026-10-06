const PLACEHOLDER = 'OFFLINE_TEST_PLACEHOLDER_NOT_A_GITHUB_TOKEN';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function fixture(status) {
  let calls = 0;
  return {
    async fetch(request) {
      calls += 1;
      assert(calls === 1, 'Retried request or followed redirect');
      assert(request.url === 'https://api.github.com/repos/richardssheik107-hub/CANNJudgeWatcher/actions/workflows/monitor.yml/dispatches', 'Wrong dispatch destination');
      assert(request.method === 'POST', 'Wrong dispatch method');
      assert(request.headers.get('Authorization') === 'Bearer ' + PLACEHOLDER, 'Wrong offline placeholder');
      assert(request.headers.get('Accept') === 'application/vnd.github+json', 'Wrong response format');
      assert(request.headers.get('Content-Type') === 'application/json', 'Wrong request format');
      assert(request.headers.get('User-Agent') === 'CANNJudgeWatcher-Cloudflare-Cron', 'Wrong user agent');
      assert(request.headers.get('X-GitHub-Api-Version') === '2026-03-10', 'Wrong GitHub API version');
      assert(await request.text() === '{"ref":"main","inputs":{"reset_history":false}}', 'Wrong fixed dispatch inputs');

      // The global outbound route also catches a mistaken attempt to follow this
      // Location. Its next invocation fails before returning another response.
      return new Response(null, {
        status,
        headers: status === 204 ? {} : { Location: 'https://must-not-follow.invalid/' },
      });
    },
  };
}

export const status204 = fixture(204);
export const status301 = fixture(301);
export const status302 = fixture(302);
export const status303 = fixture(303);
export const status307 = fixture(307);
export const status308 = fixture(308);
