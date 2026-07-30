# AgentBoard

**Local browser workspace** for durable Project, Feature, backlog, Sprint,
approval-attention, and report state.

AgentBoard provides Projects, a ranked future backlog, Current Sprint, a
five-column Sprint view whose Done column includes merge-ready and completed
work, Feature detail, Approvals, and completed-Sprint Reports. All durable
workspace state is stored in local SQLite.

AgentBoard does not yet derive engineering state from a Git provider,
synchronize pull requests, run independent validation, or deliver
notifications. Those approved integrations remain separate future slices in
[the product brief](docs/product-brief.md),
[technical design](docs/architecture-design.md), and
[acceptance evals](docs/acceptance-evals.md).

## Install

```bash
pipx install agentboard
```

Or with pip:
```bash
pip install agentboard
```

Python 3.11 or newer is required. AgentBoard does not require an LLM CLI.

## Browser quick start

The browser binds to loopback and has no login or password authentication. These
commands create a representative demo workspace in an explicit SQLite database
and start the app:

```bash
export AGENTBOARD_DB_PATH="$PWD/agentboard-demo.db"

agentboard seed-demo --db "$AGENTBOARD_DB_PATH"
agentboard web --db "$AGENTBOARD_DB_PATH"
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) and select `DEMO`.
The demo includes an active Sprint across every durable engineering state, a
combined Done column, three reorderable future-backlog items, Feature history,
design and Human Review attention, and a completed-Sprint report. Seeding is
atomic and refuses to alter an existing `DEMO` Project; choose a new database
path for a fresh copy.

To create an empty Project instead, select the **+** control on the Projects
page, then enter a stable URL-safe key, display name, repository URL, and
default branch. AgentBoard opens the new Project's independent empty Backlog
after creation. Each Project keeps its own Backlog and Sprint. A Project can be
permanently removed from its catalog card through the explicit two-step delete
confirmation without changing any other Project.
The equivalent CLI command is:

```bash
agentboard create-project \
  AB \
  "AgentBoard" \
  https://github.com/owner/repository \
  --db "$AGENTBOARD_DB_PATH"
```

When no session secret is configured, AgentBoard generates an in-memory secret
for that process. The signed `SameSite=Strict` session cookie binds CSRF tokens
to one browser; it does not authenticate a user or restrict access.

Direct non-loopback binding is intentionally rejected. To use a browser on
another machine, keep AgentBoard bound to loopback and use an SSH tunnel or a
trusted private HTTPS proxy. For example, from the browser machine:

```bash
ssh -L 8000:127.0.0.1:8000 user@agentboard-host
```

Use `--secure-cookies` only when the browser reaches AgentBoard through HTTPS.
Public internet hosting is outside browser v0.

## Test the browser behavior locally

From a source checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"

# Full Python suite with the repository's 100% coverage requirement.
python3 -m pytest

# Dependency-free browser JavaScript tests.
npm test
```

The focused browser suite is:

```bash
python3 -m pytest \
  tests/test_browser_views.py \
  tests/test_browser_web.py \
  tests/test_browser_web_edges.py \
  tests/test_web_security.py \
  tests/test_browser_cli.py
```

It verifies login-free local access, absent authentication routes, atomic demo
seeding, project isolation, exact page content, security headers and CSRF, five
ordered Sprint columns ending in combined Done, Feature
details, non-actionable approval attention when an immutable revision is
unavailable, completed-Sprint Reports, durable/idempotent backlog reordering,
stale-version conflicts, and empty/error states.

## Local operation

AgentBoard runs entirely locally:

- SQLite database (the platform data-directory default or an explicit `--db`)
- One loopback-only application process while the browser interface is running
- No hosted application service, Redis, queue, or frontend build service

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
