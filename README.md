# AgentBoard

**Story-driven multi-agent development TUI** — write a PRD in your terminal, let AI agents handle all engineering and GTM work.

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

## How it works

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

**Requirements:** `claude` CLI or `codex` CLI must be in your PATH. No API keys needed — uses your existing subscription.

```bash
# Install Claude CLI
npm install -g @anthropic-ai/claude-code

# Or Codex CLI
npm install -g @openai/codex
```

## Quick Start

```bash
# Create default config
agentboard init

# Launch the TUI
agentboard start
```

## Configuration

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

## Keyboard Shortcuts

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
- SQLite database (`~/.agentboard/agentboard.db`)
- Agent work runs through `claude` or `codex` CLI (your existing subscription)
- No servers, no Redis, no hosted services
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
