# AgentBoard Features

Source of truth for all features in the project. Each feature is marked with its current status.

**Status key:** `done` | `partial` | `planned`

---

## Authentication & Users

| Feature | Status | Details |
|---------|--------|---------|
| GitHub OAuth sign-in | done | NextAuth.js frontend + FastAPI token exchange |
| User profile (login, name, email, avatar) | done | Auto-populated from GitHub |
| API key management (BYOK) | done | Anthropic + OpenAI keys, Fernet-encrypted at rest |
| API key status check | done | Users can verify which keys are configured |

---

## Projects

| Feature | Status | Details |
|---------|--------|---------|
| Project CRUD | done | Create, list, get, update, delete |
| GitHub repo linking | done | Each project stores repo_full_name, repo_url, default_branch |
| Auto-create default board on project creation | done | 6 columns: Backlog, Triaging, Ready, In Progress, In Review, Done |
| Project-level settings (JSON blob) | partial | DB field exists, no API or UI |

---

## Kanban Board

| Feature | Status | Details |
|---------|--------|---------|
| Board with customizable columns | done | Each column maps to a ticket status |
| Drag-and-drop ticket movement | done | @dnd-kit, updates position + status on server |
| Real-time board sync (SSE) | done | Redis pub/sub -> SSE endpoint -> React useSSE hook |
| Multi-tab / multi-user live updates | done | All connected clients see changes instantly |

---

## Tickets

| Feature | Status | Details |
|---------|--------|---------|
| Ticket CRUD | done | Create, list, get, update, delete |
| Ticket move between columns | done | Updates column_id, position, and status |
| Ticket detail side panel | done | Shows all metadata, triage results, planning chat, executions, PR link |
| Ticket status workflow | done | backlog -> planning -> triaging -> ready -> in_progress -> in_review -> done / failed / cancelled |
| Approve & Execute action | done | From "ready" status, creates execution and enqueues agent |
| Cancel ticket | done | Moves ticket to "cancelled" status |
| Manual status transition from detail panel | done | Dropdown in ticket detail panel to move between any of the 9 statuses; auto-moves to matching column when one exists |

---

## PM Agent & Planning

| Feature | Status | Details |
|---------|--------|---------|
| Interactive planning conversation | done | On ticket creation, PM agent starts a chat to refine requirements |
| PM streaming replies | done | Claude Sonnet streaming via SSE deltas for real-time typing effect |
| Finalize plan | done | User clicks "Finalize Plan", PM outputs structured triage classification |
| Reopen planning | done | Move ticket from "ready" back to "planning", conversation preserved |
| Auto-triage (single-shot, legacy) | done | PM classifies ticket in one pass without conversation; still available |
| Triage classification fields | done | agent_type, runtime, priority, complexity, branch_name, refined_description, acceptance_criteria, context_files, reasoning |

**Agent types:** backend, frontend, mobile, devops, qa, fullstack, docs
**Runtimes:** claude (complex/multi-file), codex (simple/single-file)
**Priority:** critical, high, medium, low
**Complexity:** trivial, simple, medium, complex

---

## Agent Execution

| Feature | Status | Details |
|---------|--------|---------|
| Claude agent runner | done | ClaudeSDKClient, isolated workspace, branch/commit/push/PR |
| Codex agent runner | done | CLI exec mode, same flow as Claude |
| Workspace isolation | done | Fresh git clone in /tmp/agentboard/workspaces/{execution_id}/ |
| Execution log streaming | done | Log types: assistant, tool_call, tool_result, thinking, error, system |
| Execution metrics | done | total_tokens, total_cost, duration_seconds per execution |
| PR auto-creation post-execution | done | Agent creates PR via GitHub API after completing work |
| Retry / cancel execution | planned | Mentioned in architecture, no endpoints yet |
| Session resumption | planned | Mentioned in architecture, not implemented |

---

## GitHub Integration

| Feature | Status | Details |
|---------|--------|---------|
| Create branches | done | GitHub API, feature branch from default branch |
| Create pull requests | done | Auto-generated PR with ticket context |
| List repo file tree | done | Used as PM agent context during triage |
| Webhook: PR merged -> ticket done | done | GitHub webhook handler moves ticket to "done" column |

---

## Notifications

| Feature | Status | Details |
|---------|--------|---------|
| In-app notification system | done | Types: triaged, execution_started, pr_created, execution_failed, pr_merged |
| Notification bell with unread count | done | Header icon, badge, dropdown list; polls every 15s |
| Mark as read (single / all) | done | PATCH single, POST read-all |
| Email notifications (Resend) | planned | Not implemented |
| Slack webhook notifications | planned | Not implemented |

---

## Dashboard

| Feature | Status | Details |
|---------|--------|---------|
| Dashboard stats | done | Active projects, open tickets, PRs created |
| Recent projects grid | done | Quick links to project boards |

---

## Command Palette

| Feature | Status | Details |
|---------|--------|---------|
| Cmd/Ctrl+K command palette | done | Navigate to dashboard, projects, settings; open specific boards |

---

## Teams & Collaboration

| Feature | Status | Details |
|---------|--------|---------|
| Team CRUD | done | Create team, get team, list user's teams |
| Invite / remove members | done | Owner/admin can manage members |
| Role-based access | done | Roles: owner, admin, member; enforced on backend |
| Teams UI | planned | Backend complete, no frontend pages yet |
| Team-level project ownership | planned | Projects still tied to individual users |
| Audit logs | planned | Mentioned in Team plan tier, not implemented |

---

## Billing & Subscription

| Feature | Status | Details |
|---------|--------|---------|
| Plan tiers | done | Free (50 exec/mo, 5 projects), Pro ($29/mo, 500 exec), Team ($79/mo, 2000 exec) |
| Usage tracking | done | execution_quota + executions_used on User/Team models |
| Stripe checkout | done | Create checkout session, handle webhook to activate plan |
| Execution quota enforcement | planned | Tracking exists but no hard limits enforced at execution time |
| Onboarding flow | planned | Not implemented |

---

## Agent Configuration

| Feature | Status | Details |
|---------|--------|---------|
| Per-project agent config model | partial | DB schema: system_prompt, model, max_tokens, cost_limit, allowed_tools |
| Agent config API / UI | planned | No endpoints or frontend |
| Custom MCP tools | planned | agents/ directory exists as placeholder |

---

## Infrastructure

| Feature | Status | Details |
|---------|--------|---------|
| Monorepo (Turborepo + pnpm) | done | apps/web + apps/api |
| PostgreSQL 16 + async SQLAlchemy 2 | done | Full schema with Alembic migrations |
| Redis 7 (pub/sub + task queue) | done | Event bus + Arq worker backend |
| Arq background workers | done | 4 tasks: triage, execute, start_planning, generate_pm_reply |
| Docker Compose (local dev) | done | Postgres + Redis containers |
| Fernet encryption service | done | For API key storage |

---

## UI/UX

| Feature | Status | Details |
|---------|--------|---------|
| Dark theme via CSS variables | done | Full variable-based theming |
| Responsive / mobile layout | done | Sidebar, header, board all responsive |
| Toast notifications (Sonner) | done | Success/error feedback on all actions |
| Loading states & spinners | done | Across all pages and async actions |
