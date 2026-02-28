# Contributing to AgentBoard

Thanks for contributing! AgentBoard is MIT-licensed and welcomes PRs.

## Setup

```bash
# Clone
git clone https://github.com/agentboard/agentboard
cd agentboard

# Install in dev mode with test deps
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest
```

## Linting

```bash
ruff check agentboard tests
ruff format agentboard tests
```

## Adding a New Agent Type

1. Create `agentboard/agents/defaults/<type>.yml`:
```yaml
name: myagent
description: What it does
preferred_provider: claude
model: claude-sonnet-4-6
tools: [read_file, write_file, bash]
system_prompt: |
  You are a...
```

2. Add the enum value to `AgentType` in `agentboard/core/models.py`
3. Add a badge abbreviation in `agentboard/tui/widgets/story_card.py`
4. Add tests in `tests/`

## How the Codebase Is Organized

```
agentboard/
├── cli.py          # Typer entry point
├── core/           # DB, models, config, agent registry
├── llm/            # CLI subprocess clients (claude, codex)
├── agents/         # PM, Growth, Engineering Runner; default YAML configs
├── workers/        # asyncio orchestrator + heartbeat
└── tui/            # Textual app, screens, widgets
```

## Principles

- No hosted services — everything runs locally
- Agent agnostic — no vendor lock-in
- PRD ↔ ticket live link — tickets are derived from PRDs, not independent
- Heartbeat — periodic health checks, never silent failures
- GTM mandatory — the PM agent refuses to finalize without a launch plan

## Submitting a PR

1. Fork and create a branch: `git checkout -b feat/my-feature`
2. Write tests for your change
3. Run `pytest` and `ruff check` — both must pass
4. Submit PR with a clear description of what and why

## Code of Conduct

Be kind. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
