# AgentBoard — AI-Powered Project Management Board

## Context

Build a SaaS web app — a Kanban board where users create tickets that get automatically triaged by a PM agent and dispatched to specialized AI coding agents (mobile, backend, devops, qa, etc.). Agents execute the work, commit code, create a PR, and notify the user for review.

**Key decisions:** Next.js frontend + Python (FastAPI) backend, both Claude Code and Codex as runtimes (PM agent routes by task type), cloud execution by default with optional local runner.

---

## Architecture

```
Browser (Next.js)
    ↓ HTTPS + SSE
Next.js API Routes (BFF — auth, SSE proxy)
    ↓ HTTP
FastAPI Backend
    ├── REST API (tickets, projects, boards, agents, executions)
    ├── PM Agent Service (Claude Sonnet — triage + routing)
    ├── Agent Executors
    │   ├── Claude Runner (Claude Agent SDK / ClaudeSDKClient)
    │   └── Codex Runner (Codex CLI exec / Cloud Tasks API)
    ├── GitHub Service (branches, commits, PRs)
    ├── Event Bus (Redis pub/sub → SSE)
    └── Task Queue (Arq + Redis)

Data: PostgreSQL + Redis
Auth: GitHub OAuth (NextAuth.js)
```

---

## Monorepo Structure

```
agentboard/
├── apps/
│   ├── web/                    # Next.js (App Router, Tailwind, TypeScript)
│   │   ├── src/app/            # Pages: auth, dashboard, projects, boards, tickets
│   │   ├── src/components/     # board/, agents/, layout/, ui/
│   │   ├── src/hooks/          # useSSE, useBoard, useTickets, useAgentStatus
│   │   └── src/lib/            # api-client, auth config
│   └── api/                    # Python FastAPI
│       ├── src/
│       │   ├── models/         # SQLAlchemy: user, project, board, ticket, execution
│       │   ├── schemas/        # Pydantic request/response
│       │   ├── routers/        # API routes
│       │   ├── services/       # pm_agent, claude_runner, codex_runner, github_service, event_bus
│       │   ├── workers/        # Arq tasks: triage, execute, notify
│       │   ├── agents/         # Prompt templates + custom MCP tools
│       │   └── migrations/     # Alembic
│       └── tests/
├── docker/                     # docker-compose (postgres + redis)
├── turbo.json                  # Turborepo config
└── pnpm-workspace.yaml
```

---

## Data Model (key tables)

| Table | Purpose |
|-------|---------|
| `users` | GitHub OAuth, API keys (encrypted), plan tier |
| `projects` | Linked to GitHub repos, settings |
| `boards` / `board_columns` | Kanban boards with customizable columns |
| `tickets` | Title, description, PM classification (agent_type, runtime, priority, complexity), status, branch, PR link |
| `agent_configs` | Per-project agent settings: system prompt, model, budget, allowed tools |
| `executions` | One per agent run: status, cost, tokens, duration, session_id |
| `execution_logs` | Streaming log entries: assistant messages, tool calls, thinking, errors |
| `notifications` | In-app notifications (triaged, started, PR created, failed) |

**Ticket statuses:** backlog → triaging → ready → in_progress → in_review → done / failed / cancelled
**Agent types:** pm, mobile, backend, frontend, devops, qa, fullstack, docs
**Runtimes:** claude, codex

---

## PM Agent Logic

1. User creates ticket → status moves to `triaging`
2. PM Agent (Claude Sonnet, structured JSON output) receives:
   - Ticket title + description
   - Project repo file tree (cached)
   - Available agent types
3. Outputs: `agent_type`, `runtime`, `priority`, `complexity`, `branch_name`, `refined_description`, `acceptance_criteria`, `context_files`, `reasoning`
4. User can override any field before approving execution

**Routing heuristic:**
- **Claude**: multi-file changes, architectural reasoning, complex refactoring, vague requirements, CI/CD
- **Codex**: single-file fixes, boilerplate, test generation, docs, well-scoped bugs

---

## Agent Execution Flow

```
Ticket created
  → PM triage (Arq task)
  → Classification saved, ticket → "ready"
  → User approves (or auto-approve)
  → Agent execution (Arq task):
      1. Clone repo, create branch
      2. Run Claude (ClaudeSDKClient) or Codex (CLI exec)
         - Stream logs to DB + SSE in real-time
         - Custom MCP tools: update_ticket_status, report_progress
      3. Git add + commit + push
      4. Create PR via GitHub API
      5. Ticket → "in_review", notify user
  → User reviews PR on GitHub
  → PR merged → webhook → ticket → "done"
```

---

## Tech Stack

**Frontend:** Next.js 15, React 19, TypeScript, Tailwind, @tanstack/react-query, next-auth, @dnd-kit (drag-and-drop), zustand, cmdk (command palette), sonner (toasts), zod

**Backend:** FastAPI, SQLAlchemy 2 (async), Alembic, asyncpg, Arq (task queue), Redis, claude-agent-sdk (Python), httpx, sse-starlette, structlog, ruff, pytest

**Infra:** PostgreSQL 16, Redis 7, Docker Compose (local dev), Turborepo + pnpm (monorepo)

**Deploy:** Vercel (frontend), Railway or Render (backend + workers), Neon or Supabase (Postgres), Upstash (Redis)

---

## Key Design Decisions

- **SSE over WebSocket** — board updates are server→client only, SSE auto-reconnects, simpler to proxy
- **Arq over Celery** — native asyncio (matches FastAPI), lightweight, Redis-only
- **ClaudeSDKClient over query()** — supports interrupt, hooks, custom MCP tools, session resumption
- **BYOK (Bring Your Own Key)** for MVP — users provide their own Claude/OpenAI API keys, encrypted at rest
- **Workspace isolation** — each execution gets a fresh git clone in `/tmp/agentboard/workspaces/{execution_id}/`

---

## Implementation Phases

### Phase 0: Foundation (Week 1-2)
- Monorepo setup (Turborepo + pnpm + Docker Compose)
- GitHub OAuth (NextAuth.js ↔ FastAPI token exchange)
- Full database schema + Alembic migrations
- Basic CRUD: users, projects (link GitHub repo)
- **Deliverable:** User logs in, creates a project linked to a repo

### Phase 1: Board UI (Week 3-4)
- Kanban board: columns, ticket cards, drag-and-drop (@dnd-kit)
- Ticket CRUD (create, update, delete, move between columns)
- SSE infrastructure (Redis pub/sub → SSE endpoint → React useSSE hook)
- Real-time sync across browser tabs
- **Deliverable:** Functional Kanban board, no AI yet

### Phase 2: PM Agent (Week 5-6)
- PM Agent service (Claude Sonnet, structured output)
- Arq worker for triage tasks
- Auto-triage on ticket creation
- Triage results displayed in ticket detail (user can override)
- **Deliverable:** Tickets are auto-classified with agent type, runtime, priority

### Phase 3: Claude Agent Execution (Week 7-9)
- Claude runner (ClaudeSDKClient + custom MCP tools)
- Workspace management (clone, branch, cleanup)
- Execution log streaming (agent → DB → SSE → UI)
- GitHub PR creation post-execution
- Cost tracking + budget enforcement
- Retry/cancel flows
- **Deliverable:** End-to-end: ticket → agent codes → PR created → user notified

### Phase 4: Codex Runtime (Week 10-11)
- Codex runner (CLI exec mode)
- Runtime switching (PM routes, user overrides)
- Same execution log format for both runtimes
- **Deliverable:** Simpler tasks route to Codex automatically

### Phase 5: Notifications + Polish (Week 12-13)
- In-app notifications, email (Resend), optional Slack webhook
- GitHub webhook: PR merged → ticket → "done"
- Command palette (Cmd+K for quick ticket creation)
- Dashboard: cost tracking, execution stats
- Mobile-responsive layout
- **Deliverable:** Complete flow with notifications at every step

### Phase 6: Multi-User + Billing (Week 14-16)
- Team/org model, role-based access
- Stripe billing (free + pro tiers, usage-based)
- Execution quotas per plan
- Onboarding flow
- **Deliverable:** SaaS-ready for beta

---

## Critical Path (build in this order)

1. GitHub OAuth + user model
2. Project creation + repo linking
3. Ticket CRUD + board UI
4. SSE infrastructure
5. PM Agent triage
6. Claude runner + execution logging
7. GitHub PR creation
8. Execution log streaming UI

Everything else layers on top.

---

## Progress

- [x] Phase 0: Foundation
- [x] Phase 1: Board UI
- [x] Phase 2: PM Agent
- [x] Phase 3: Claude Agent Execution
- [x] Phase 4: Codex Runtime
- [x] Phase 5: Notifications + Polish
- [x] Phase 6: Multi-User + Billing
