# AgentBoard — Codex Agent Instructions

> **Mirror of `CLAUDE.md`** — same rules adapted for Codex CLI.
> This file guides Codex when operating in the agentboard workspace, whether as:
> - **PM Agent** — conversational story refinement, PRD decomposition, bug triage
> - **Engineering Agent** — headless code execution on a ticket
> - **Developer** — working on agentboard itself

---

## Project Context

AgentBoard is a CLI/TUI multi-agent development tool. Users write a PRD in the terminal; AI agents handle engineering and GTM. It runs locally with zero hosting cost — SQLite for persistence, Claude/Codex CLI subprocesses for agent execution.

**Stack:** Python 3.11+, Textual (TUI), SQLAlchemy async (aiosqlite), ruff, pytest

**Key paths:**
```
agentboard/
├── agents/
│   ├── defaults/           # YAML configs for engineering agent types
│   ├── pm_agent.py         # PM agent: refinement, decomposition, diff analysis, bug triage
│   ├── growth_agent.py     # Growth agent: GTM conversation + LAUNCH.md generation
│   └── engineering_runner.py  # Headless ticket execution (Claude or Codex CLI)
├── core/
│   ├── models.py           # SQLAlchemy models: Story, Ticket, Execution, etc.
│   ├── config.py           # Config loading from ~/.agentboard/config.yml
│   └── agent_registry.py  # Loads agent YAML definitions
├── llm/
│   ├── claude_cli.py       # Claude CLI subprocess client
│   └── codex_cli.py        # Codex CLI subprocess client
├── tui/                    # Textual TUI screens and widgets
└── workers/                # Async execution workers
tests/                      # pytest test suite
```

**Data model key entities:**
- `Story` — a feature with 5 PRD sections (problem, solution, scope, acceptance, gtm)
- `Ticket` — engineering work item with agent_type, runtime, prd_anchor, branch_name
- `Execution` — one per agent run, with stdout/stderr logs
- `StoryMessage` / `GrowthMessage` — conversation history (persisted, replayed)

**Story flow:** DRAFTING → ENGINEERING → TESTING → DONE

**Agent routing:**
- **Claude**: multi-file changes, architectural reasoning, complex refactoring, vague requirements, CI/CD
- **Codex**: single-file fixes, boilerplate, test generation, docs, well-scoped bugs

---

## As PM Agent

When acting as PM during story refinement (DRAFTING phase):

1. Ask 2–3 sharp clarifying questions per response — deepen understanding, don't just acknowledge
2. **Always** ask about GTM if not addressed: growth lever, discovery channels, monetization
3. Push for specificity on scope — what's explicitly in and what's out
4. Identify risks and ambiguities early
5. Refuse to suggest finalization until all 5 PRD sections have substance:
   - **Problem** — what pain, for whom
   - **Solution** — what we're building and why this approach
   - **Scope** — in / out of scope (be specific)
   - **Acceptance Criteria** — how we know it works
   - **GTM** — growth lever, channels, monetization (mandatory — no finalize without it)
6. Keep responses conversational and under 200 words

When decomposing a finalized PRD (output ONLY valid JSON):
- `engineering_tickets[]` — each with: index, title, prd_anchor, agent_type, runtime, priority, complexity, branch_name, refined_description, acceptance_criteria, context_files, depends_on, reasoning
- `marketing_ticket` — title, prd_anchor, gtm_context, output_file
- Maximum 8 engineering tickets per story — keep them small and independently deployable
- `prd_anchor` format: `section.feature` (e.g. `checkout.payment-methods`, `bug.login-crash`)

When triaging a bug (output ONLY valid JSON):
- Title: `Fix: [specific bug]`
- Include steps to reproduce, expected vs actual, and fix approach in refined_description
- `prd_anchor` format: `bug.[area]`

---

## As Engineering Agent

When executing a ticket in a workspace:

1. Read the task prompt and acceptance criteria carefully before touching any file
2. Read the relevant existing files — understand conventions before writing new code
3. Follow the project's existing patterns — do not invent new abstractions
4. Run the project's linter (`ruff check .` for Python) and fix all errors before finishing
5. Write tests for all new code
6. Make atomic commits with clear messages
7. Do NOT modify files unrelated to the ticket
8. Implement the minimal version that satisfies the acceptance criteria
9. Print `TASK_COMPLETE` on the last line when done

---

## Development Standards

### Workflow

1. Run the linter before committing — fix all errors (warnings OK)
2. Run tests and ensure they pass before committing
3. Commit and push automatically after tests pass — do not ask for permission

### Code Organization

- Each function does one thing — max ~30 lines; break longer ones into named steps
- Files have a single responsibility
- Prefer composition over inheritance
- **UI layer**: rendering and user interaction only — no business logic
- **Business logic layer**: domain rules, orchestration — no UI or infrastructure
- **Data layer**: persistence, external integrations — abstracted behind interfaces
- Use explicit state (enums, discriminated unions) over multiple boolean flags
- One source of truth per piece of state — no duplicated or derived state that can drift
- Dependencies flow inward: UI → Business Logic → Data
- Depend on abstractions at layer boundaries, not concrete implementations

### Error Handling

- Never silently catch errors
- Define domain-specific error types with user-facing descriptions
- Validate inputs at system boundaries (user input, external APIs)
- Prefer graceful degradation over crashing — return valid empty states for "no data"

### Security

- Never hardcode secrets or credentials
- Sanitize user inputs (SQL injection, command injection, XSS)
- Validate all external data before processing
- Principle of least privilege

### Performance

- Never block the main/UI thread with heavy computation
- Run expensive work on background threads/asyncio tasks
- UI updates must happen on the main/UI thread only

### Testing

**Every code change must include corresponding unit tests.** Aim for complete coverage of business logic.

- New code: tests for all new functions and types
- Modified code: update existing tests; add tests for new behavior
- Bug fixes: add a regression test that would have caught the bug
- Follow Arrange-Act-Assert (AAA) consistently
- One logical assertion per test
- Descriptive test names: what scenario, what outcome
- Each test is independent — no shared mutable state
- Mock external dependencies consistently
- No reliance on timing, network, or randomness

**Edge cases to always cover:**
- Empty collections, zero, maximum values, off-by-one
- Null/None and missing data
- Invalid state transitions, interrupted operations
- Malformed input and unexpected types

### Documentation

- Document the "why", not the "what" — code should be self-explanatory
- Add comments only where logic isn't self-evident
- Document complex algorithms, thresholds, non-obvious configuration
- Don't add docstrings or comments to code you didn't change

---

## Skills

Use reusable Codex skills for targeted work across projects:

| Skill | When to use |
|-------|-------------|
| `architecture-reviewer` | **Before** implementing significant changes — validates design early |
| `senior-code-reviewer` | **After** completing a feature — reviews for bugs, security, performance |
| `senior-qa-engineer` | Test coverage analysis, TDD, flaky test debugging |
| `code-simplification-architect` | When code works but is messy — simplify and reduce duplication |
| `github-actions-engineer` | CI/CD workflow creation, debugging, optimization |
| `red-team-analyst` | **After** security-sensitive features — adversarial review |

**Pattern:** Plan → Implement → Review → Attack → Test → Simplify
