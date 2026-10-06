# Run with the pinned official runtime:
# npx --yes workerd@1.20261001.1 test integrations/cloudflare-scheduler/runtime-tests/config.capnp
# No sockets, storage, or credentials; the internet service explicitly denies all.
using Workerd = import "/workerd/workerd.capnp";

const config :Workerd.Config = (
  services = [
    (name = "scheduled204", worker = (
      modules = [
        (name = "scheduled.test.mjs", esModule = embed "scheduled.test.mjs"),
        (name = "worker.mjs", esModule = embed "../worker.mjs")
      ],
      compatibilityDate = "2026-10-06",
      globalOutbound = (name = "github-fixture", entrypoint = "status204"),
      bindings = [(name = "EXPECTED_STATUS", text = "204")]
    )),
    (name = "scheduled301", worker = (
      modules = [
        (name = "scheduled.test.mjs", esModule = embed "scheduled.test.mjs"),
        (name = "worker.mjs", esModule = embed "../worker.mjs")
      ],
      compatibilityDate = "2026-10-06",
      globalOutbound = (name = "github-fixture", entrypoint = "status301"),
      bindings = [(name = "EXPECTED_STATUS", text = "301")]
    )),
    (name = "scheduled302", worker = (
      modules = [
        (name = "scheduled.test.mjs", esModule = embed "scheduled.test.mjs"),
        (name = "worker.mjs", esModule = embed "../worker.mjs")
      ],
      compatibilityDate = "2026-10-06",
      globalOutbound = (name = "github-fixture", entrypoint = "status302"),
      bindings = [(name = "EXPECTED_STATUS", text = "302")]
    )),
    (name = "scheduled303", worker = (
      modules = [
        (name = "scheduled.test.mjs", esModule = embed "scheduled.test.mjs"),
        (name = "worker.mjs", esModule = embed "../worker.mjs")
      ],
      compatibilityDate = "2026-10-06",
      globalOutbound = (name = "github-fixture", entrypoint = "status303"),
      bindings = [(name = "EXPECTED_STATUS", text = "303")]
    )),
    (name = "scheduled307", worker = (
      modules = [
        (name = "scheduled.test.mjs", esModule = embed "scheduled.test.mjs"),
        (name = "worker.mjs", esModule = embed "../worker.mjs")
      ],
      compatibilityDate = "2026-10-06",
      globalOutbound = (name = "github-fixture", entrypoint = "status307"),
      bindings = [(name = "EXPECTED_STATUS", text = "307")]
    )),
    (name = "scheduled308", worker = (
      modules = [
        (name = "scheduled.test.mjs", esModule = embed "scheduled.test.mjs"),
        (name = "worker.mjs", esModule = embed "../worker.mjs")
      ],
      compatibilityDate = "2026-10-06",
      globalOutbound = (name = "github-fixture", entrypoint = "status308"),
      bindings = [(name = "EXPECTED_STATUS", text = "308")]
    )),
    (name = "github-fixture", worker = (
      modules = [(name = "github-fixture.mjs", esModule = embed "github-fixture.mjs")],
      compatibilityDate = "2026-10-06"
    )),
    (name = "internet", network = (allow = []))
  ]
);
