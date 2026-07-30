# AgentBoard

**Local agent-development workspace** — use the established terminal workflow
for Story execution and a loopback-only browser workspace for durable
Project, Feature, backlog, Sprint, approval-attention, and report state.

AgentBoard currently has two local interfaces:

- The legacy Textual TUI supports PRD refinement, agent execution, testing, and
  shipping.
- The browser application provides Projects, a ranked future backlog, Current
  Sprint, a five-column Sprint view whose Done column includes merge-ready and
  completed work, Feature
  detail, Approvals, and completed-Sprint Reports. It renders the durable state
  already stored in SQLite.

The browser does not yet derive engineering state from GitHub, synchronize pull
requests, run independent validation, or deliver notifications. Those approved
integrations remain separate future slices in
[the product brief](docs/product-brief.md),
[technical design](docs/architecture-design.md), and
[acceptance evals](docs/acceptance-evals.md).

```
┌─────────────────────────────────────────────────────────────┐
│ AgentBoard  [b]oard [n]ew-story [?]help    ♥ 2min ago OK   │
├──────────────┬───────────────┬─────────────┬────────────────┤
│  DRAFTING    │  ENGINEERING  │   TESTING   │      DONE      │
│              │               │             │                │
│ ┌──────────┐ │ ┌───────────┐ │ ┌─────────┐ │ ┌────────────┐ │
│ │Auth Flow │ │ │ Checkout  │ │ │Dashboard│ │ │ Onboarding │ │
│ │          │ │ │ ████░░ 4/6│ │ │ Testing │ │ │ Shipped ✓  │ │
│ │Refining  │ │ │ BE FE QA  │ │ │ 🐛 1bug │ │ │ LAUNCH.md  │ │
│ │[GTM ⚠]  │ │ │ 📄 launch │ │ │         │ │ │ ready      │ │
│ └──────────┘ │ └───────────┘ │ └─────────┘ │ └────────────┘ │
└──────────────┴───────────────┴─────────────┴────────────────┘
```

## Legacy TUI workflow

1. **Write a PRD** — fill in Problem, Solution, Scope, Acceptance Criteria, and GTM
2. **Refine with PM Agent** — conversational Q&A that sharpens scope and ensures GTM is solid
3. **Finalize** — PM decomposes the PRD into engineering tickets and routes them to specialized agents
4. **Agents execute** — backend, frontend, QA, devops agents run in parallel, commit code, create PRs
5. **Test** — when all tickets are done, you're notified to test; bugs filed here create new tickets automatically
6. **Ship** — mark done, LAUNCH.md is already in your repo

## Install

```bash
pipx install agentboard
```

Or with pip:
```bash
pip install agentboard
```

Python 3.11 or newer is required. The browser application does not require an
LLM CLI. Legacy agent execution requires `claude` or `codex` in your `PATH`; it
uses the corresponding existing subscription and does not require an API key.

```bash
# Install Claude CLI
npm install -g @anthropic-ai/claude-code

# Or Codex CLI
npm install -g @openai/codex
```

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

## Legacy TUI quick start

```bash
# Create default config
agentboard init

# Launch the TUI
agentboard start
```

## Legacy TUI configuration

Config lives at `~/.agentboard/config.yml` (never committed):

```yaml
# Uses CLI auth — no API keys needed
default_provider: claude       # or codex
claude_cli_path: claude        # path to claude binary
codex_cli_path: codex          # path to codex binary

# Optional: GitHub token for PR creation
github_token: ghp_...

# Optional: use your own agent configs (from ai-playbook or custom)
agent_config_path: ~/ai-playbook/agents/

# Behavior
heartbeat_interval_minutes: 30
archive_after_days: 7
```

## Legacy TUI keyboard shortcuts

| Key | Action |
|-----|--------|
| `n` | New story |
| `Enter` | Open story |
| `Tab` | Switch between PM and Growth chat panels |
| `f` | Finalize PM → create tickets, start engineering |
| `g` | Finalize Growth → generate LAUNCH.md |
| `d` | Mark story done |
| `h` | Force heartbeat check |
| `q` / `Esc` | Back / quit |

## Agent Fleet

| Agent | Role | Output |
|-------|------|--------|
| PM | Story refinement, decomposition, bug triage | Tickets |
| Growth | GTM strategy, positioning, launch planning | LAUNCH.md |
| Backend | API, database, server logic | Code PR |
| Frontend | UI, pages, components | Code PR |
| Mobile | iOS/Android features | Code PR |
| DevOps | CI/CD, infra | Code PR |
| QA | Tests | Code PR |
| Fullstack | Cross-cutting changes | Code PR |
| Docs | Documentation | Code PR |

## Agent Config (Optional Customization)

Custom agent configs live in YAML files:

```yaml
# ~/ai-playbook/agents/backend.yml
name: backend
description: API endpoints, database, server logic
preferred_provider: claude
model: claude-sonnet-4-6
tools: [read_file, write_file, bash, github]
system_prompt: |
  You are a senior backend engineer...
```

Point to your custom agents via `agent_config_path` in config.

## $0 Operating Cost

AgentBoard runs entirely locally:

- SQLite database (the platform data-directory default or an explicit `--db`)
- One loopback-only application process while the browser interface is running
- Agent work runs through `claude` or `codex` CLI (your existing subscription)
- No hosted application service, Redis, queue, or frontend build service
- API costs only for actual agent work

## Inspiration

AgentBoard's multi-agent workflow was inspired in part by
[The Multi-Agent Architecture That Actually Ships](https://www.youtube.com/watch?v=ow1we5PzK-o),
a talk by Luke Alvoeiro of Factory published by
[AI Engineer](https://www.youtube.com/@aiDotEngineer).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
