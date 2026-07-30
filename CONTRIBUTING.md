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

## How the Codebase Is Organized

```
agentboard/
├── application/    # Use cases and persistence ports
├── domain/         # Project, Feature, and Sprint rules
├── infrastructure/ # SQLite adapters and migrations
├── migrations/     # Alembic migration environment
├── web/            # FastAPI routes, templates, and local assets
└── cli.py          # Browser, demo, and Project commands
```

## Principles

- No hosted services — everything runs locally
- Projects own their Backlog, Sprint, and Feature state
- Browser access is loopback-only and login-free
- Mutations remain durable, atomic, and project-isolated
- Integrations must not fabricate repository or validation evidence

## Submitting a PR

1. Fork and create a branch: `git checkout -b feat/my-feature`
2. Write tests for your change
3. Run `pytest` and `ruff check` — both must pass
4. Submit PR with a clear description of what and why

## Code of Conduct

Be kind. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
