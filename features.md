# AgentBoard CLI — Features

Source of truth for all features. AgentBoard is a terminal-native personal productivity system for developers combining AI agent delegation with personal time intelligence.

**Status key:** `planned` | `in-progress` | `done` | `deprecated`

---

## Core Concept

Personal productivity OS for developers, built around three pillars:

1. **Time Intelligence** — understand where your time actually goes vs where you think it goes
2. **Agent Delegation** — offload implementation work to AI coding agents
3. **Habit Building** — track patterns, maintain streaks, close the gap between intention and action

---

## Data Sources

| Source | What it captures | Integration | Status |
|--------|-----------------|-------------|--------|
| Location (mobile app) | Physical location — gym, office, home, commute | GPS + geofencing, syncs to local DB | planned |
| Google Calendar | Scheduled activities — what you planned to do | OAuth + Calendar API polling | planned |
| Computer activity | What you're actually doing on your machine | Active window tracking, categorized by activity type | planned |

---

## Time Intelligence

| Feature | Status | Details |
|---------|--------|---------|
| Planned vs actual comparison | planned | Calendar events compared against location + computer activity to show what you actually did |
| Location-aware context | planned | Automatic context detection — "at gym" vs "at desk" vs "commuting" — from mobile location data |
| Intensity scoring | planned | How focused was the work session — derived from app switching frequency, break patterns |
| Daily honesty report | planned | End-of-day summary: what you planned, what you did, where you were, focus score |
| Weekly honesty report | planned | Aggregated weekly view with trends and comparisons to previous weeks |
| Pattern detection | planned | Identify recurring patterns over time — best focus hours, most productive locations, schedule drift |

---

## Agent Delegation

| Feature | Status | Details |
|---------|--------|---------|
| Ticket creation | done | Create tickets with title and description |
| PM agent planning conversation | done | Interactive chat with PM agent to refine requirements — priority, size, risks, dependencies, validation criteria |
| PM streaming replies | done | Claude Sonnet streaming via SSE for real-time typing effect |
| Finalize plan | done | PM outputs structured triage classification after conversation |
| Triage classification | done | agent_type, runtime, priority, complexity, branch_name, refined_description, acceptance_criteria, context_files, reasoning |
| Ticket dependency graph | planned | Visual relationship view showing ticket dependencies and blockers |
| Claude agent execution | done | ClaudeSDKClient with isolated workspace, branch/commit/push/PR |
| Codex agent execution | done | CLI exec mode, same flow as Claude runner |
| Workspace isolation | done | Fresh git clone in /tmp/agentboard/workspaces/{execution_id}/ |
| Execution log streaming | done | Log types: assistant, tool_call, tool_result, thinking, error, system |
| Auto PR creation | done | Agent creates PR via GitHub API after completing work, tags creator for review |
| Agent self-validation | planned | Agent runs tests/linter before creating PR, reports confidence score |
| Execution metrics | done | total_tokens, total_cost, duration_seconds per execution |
| Retry / cancel execution | planned | Ability to retry failed executions or cancel in-progress ones |

**Agent types:** backend, frontend, mobile, devops, qa, fullstack, docs
**Runtimes:** claude (complex/multi-file), codex (simple/single-file)

---

## TUI Board

| Feature | Status | Details |
|---------|--------|---------|
| Terminal kanban board | planned | Color-coded columns rendered with ANSI colors in the terminal |
| Column color scheme | planned | Backlog (gray), Planning (yellow), Ready (blue), In Progress (cyan), In Review (magenta), Done (green), Failed (red), Cancelled (dim) |
| Keyboard navigation | planned | Arrow keys to move between tickets/columns, Enter to open detail, single-key shortcuts for actions |
| Ticket detail view | planned | Full-screen overlay showing ticket metadata, planning chat history, execution logs |
| Planning chat in TUI | planned | Interactive chat with PM agent directly in the terminal |
| Execution log viewer | planned | Real-time streaming logs from agent execution in terminal |

---

## Habit Tracking

| Feature | Status | Details |
|---------|--------|---------|
| Velocity tracking | planned | Tickets completed per sprint/week, trend over time |
| Time allocation trends | planned | Where time is spent across categories — coding, meetings, gym, commute, etc. |
| Streak tracking | planned | Consecutive days hitting targets — gym visits, focus hours, tickets shipped |
| Planned vs actual gap trending | planned | Track how the gap between intention and reality changes over weeks/months |
| Focus score history | planned | Daily focus scores plotted over time to identify improvement or regression |

---

## Customization

| Feature | Status | Details |
|---------|--------|---------|
| Config file (`.agentboard/config.yml`) | planned | Agent model, cost limits, PR template, branch naming convention |
| Custom prompts (`.agentboard/prompts/`) | planned | Override default PM agent and validation prompts per project |
| Custom workflows (`.agentboard/workflows/`) | planned | Define ticket lifecycle, status transitions, auto-approve rules |
| Custom templates (`.agentboard/templates/`) | planned | PR body format, commit message format, ticket templates |
| Git-native config | planned | All config lives in the repo, versioned alongside the project |

---

## Infrastructure

| Feature | Status | Details |
|---------|--------|---------|
| No hosted services required | planned | $0/day operating cost — everything runs locally |
| Local SQLite storage | planned | Tickets, time data, execution history stored in local SQLite DB |
| File-based ticket storage | planned | Optional: tickets as markdown files in the repo (git-native) |
| Anthropic API (BYOK) | done | Users provide their own API key for PM agent + execution |
| GitHub integration | done | Branches, PRs, repo file tree, webhooks |
| Redis + PostgreSQL (legacy web) | deprecated | Web version infra — being replaced by local SQLite |
| Arq background workers (legacy web) | deprecated | Web version task queue — being replaced by local async execution |
