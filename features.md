# AgentBoard — Feature Tracker

Story-driven multi-agent development TUI. Write a PRD in your terminal; AI agents handle engineering and GTM.

**Status key:** `planned` | `in-progress` | `done` | `deprecated`

---

## Story Board (Kanban)

| Feature | Status | Details |
|---------|--------|---------|
| 4-column Kanban (DRAFTING / ENGINEERING / TESTING / DONE) | done | Textual TUI with full keyboard navigation |
| Story cards with progress bars and agent badges | done | Shows N/M tickets done, agent type abbreviations (BE FE QA), GTM warning, bug count |
| Keyboard navigation | done | [n] new, [enter] open, [tab] switch chat, [f] finalize PM, [g] finalize growth, [d] done, [h] heartbeat |

---

## PRD Editing

| Feature | Status | Details |
|---------|--------|---------|
| 5-section PRD editor (Problem / Solution / Scope / Acceptance / GTM) | done | Editable while DRAFTING/REFINING; read-only after finalize |
| GTM mandatory gate | done | PM refuses to suggest finalization without GTM; warns on card with [GTM ⚠] badge |
| PRD deletion (safe stage) | done | User can delete PRD with confirmation while DRAFTING/REFINING |

---

## PM Agent

| Feature | Status | Details |
|---------|--------|---------|
| Conversational refinement | done | Streaming chat in TUI; asks 2-3 questions per response |
| GTM prompting | done | Always asks about growth lever, channels, monetization if GTM missing |
| PM finalize guard | done | Requires at least one PM user/assistant exchange and allows PM finalize only once per story |
| Decomposition on finalize | done | Outputs structured JSON with engineering tickets + marketing ticket |
| prd_anchor linking | done | Each ticket tagged with the PRD section it was sliced from |
| PRD diff analysis | done | Detects changed sections, marks affected tickets as stale |
| Bug triage | done | Creates focused bug-fix tickets from user bug reports |

---

## Growth Agent

| Feature | Status | Details |
|---------|--------|---------|
| Parallel conversational agent | done | Runs alongside PM chat from story creation; tab-switchable |
| GTM questions | done | Covers ICP, discovery, growth lever, pricing, launch sequence |
| Independent finalize | done | [g] generates LAUNCH.md independently from PM finalize |
| LAUNCH.md generation | done | Positioning, audience, channels, launch copy, pricing, 30-day sequence |

---

## Engineering Execution

| Feature | Status | Details |
|---------|--------|---------|
| Dependency-aware orchestration | done | asyncio — independent tickets start in parallel; dependent tickets wait |
| Claude CLI runner | done | Subprocess claude --dangerously-skip-permissions in workspace dir |
| Codex CLI runner | done | Subprocess codex --full-auto in workspace dir |
| Workspace isolation | done | Fresh git clone per execution in /tmp/agentboard/workspaces/{id}/ |
| Automatic commit + push | done | Runner commits changes and pushes branch after agent completes |
| GitHub PR creation | done | Uses gh CLI if github_token is configured |
| Agent type routing | done | PM assigns backend/frontend/mobile/devops/qa/fullstack/docs/marketing |

---

## Testing Loop

| Feature | Status | Details |
|---------|--------|---------|
| Auto-transition to TESTING | done | Story moves to TESTING when all tickets are terminal |
| TUI notification on ready for testing | done | Textual notify() + desktop notification (macOS/Linux) |
| Bug report chat panel | done | PM agent creates bug-fix ticket from user description |
| Story flip back to ENGINEERING | done | Story returns to ENGINEERING when bug ticket is created |
| Mark done | done | [d] transitions story to DONE |

---

## Heartbeat

| Feature | Status | Details |
|---------|--------|---------|
| 30-minute asyncio loop | done | asyncio.sleep(1800), no external scheduler |
| Board state checks | done | Empty pipeline, stale drafts (>24h), stuck executions (>3h), missing GTM, stale tickets |
| LLM-powered alerts | done | Claude CLI generates 1-2 sentence alerts; local fallback if CLI unavailable |
| Status bar display | done | Footer shows "♥ 2min ago OK" or alert text |
| Desktop notifications | done | macOS osascript + Linux notify-send |
| Force heartbeat | done | [h] triggers immediate check |

---

## Data Model

| Feature | Status | Details |
|---------|--------|---------|
| Story with 5 PRD sections | done | prd_problem/solution/scope/acceptance/gtm columns |
| StoryMessage (PM chat history) | done | Full conversation persisted; replayed on each CLI call |
| GrowthMessage (Growth chat history) | done | Independent conversation for growth agent |
| Ticket with prd_anchor | done | Links ticket to PRD section; is_stale flag for drift detection |
| Execution + ExecutionLog | done | Per-agent-run records with stdout/stderr streaming |
| SQLite via SQLAlchemy async | done | aiosqlite + asyncio, zero config, zero hosting cost |

---

## Infrastructure & Distribution

| Feature | Status | Details |
|---------|--------|---------|
| Local SQLite (no hosted DB) | done | ~/.agentboard/agentboard.db |
| CLI subprocess (no API keys) | done | Uses claude/codex CLI with user's existing subscription |
| $0 operating cost | done | Only API costs for actual agent work via CLI |
| PyPI package | done | pipx install agentboard / pip install agentboard |
| MIT license | done | No restrictions on commercial use |
| Agent YAML configs (bundled defaults) | done | backend, frontend, mobile, devops, qa, fullstack, docs, growth, marketing |
| ai-playbook override path | done | agent_config_path in config for custom agent YAMLs |
| GitHub Actions CI | done | ruff + pytest on Python 3.11/3.12/3.13 |
| GitHub Actions release | done | PyPI publish + GitHub release on tag push |
| No vendor lock-in | done | Works with claude-only or codex-only; GitHub integration optional |
