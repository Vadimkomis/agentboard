# AgentBoard v0 Technical Design

Status: Draft for owner approval

## Simplicity rule

AgentBoard v0 is a modular monolith. It stays that way until measured behavior
proves otherwise.

```text
Browser
    │ local or private connection
AgentBoard host (macOS or Linux)
    ├── FastAPI + server-rendered HTML
    ├── domain rules
    ├── GitHub synchronization
    └── SQLite
```

No SPA, Redis, PostgreSQL, message broker, microservice, or plugin framework is
required.

## Stack

- Python 3.12
- FastAPI
- Jinja2 and HTMX
- SQLAlchemy 2 async
- SQLite in WAL mode
- Alembic
- Native process supervision (`launchd` on macOS or `systemd` on Linux)

The existing Python repository remains the base. Rust is deferred unless a
measured security or performance need justifies a separate worker component.

## Layers

### Domain

Plain Python contains:

- backlog ranking rules;
- sprint rules;
- engineering state derivation;
- approval invalidation;
- serial execution guard.

It imports neither FastAPI nor SQLAlchemy.

### Application

Small command handlers coordinate use cases such as:

- create Feature;
- reorder backlog;
- start or complete sprint;
- approve design;
- start engineering;
- ingest PR facts;
- approve PR;
- record merge.

### Infrastructure

Adapters handle SQLite, GitHub, filesystem paths, and later the engineering
worker. Browser handlers never mutate database models directly.

## Minimal data model

### Project

`id`, `key`, `name`, `repository_url`, `default_branch`, timestamps

### Feature

`id`, `project_id`, `number`, `title`, `description`, `rank`, `planning_stage`,
`engineering_state`, `priority`, `estimate`, `owner`, `approved_design_hash`,
`completed_at`, timestamps

### Sprint

`id`, `project_id`, `number`, `name`, `goal`, `state`, `starts_at`, `ends_at`

Only one Sprint may be active per Project.

### SprintFeature

`sprint_id`, `feature_id`, `sprint_rank`

### PullRequest

`id`, `feature_id`, `number`, `url`, `head_revision`, `draft`, `state`,
`checks_state`, `review_state`, `mergeable_state`, `provider_updated_at`,
`merge_commit`, `merged_at`, `last_reconciled_at`

One active primary PR may belong to a Feature.

### Approval

`id`, `feature_id`, `kind`, `subject_revision`, `decision`, `comment`,
`created_at`

Kinds are `design` and `pull_request`.

### AuditEvent

`id`, `project_id`, `feature_id`, `type`, `payload`, `created_at`

This is a small audit table, not an event-sourcing framework.

## State rules

Planning remains in Backlog:

```text
Inbox → Clarifying → Spec → Evals → Design → Design Review
```

The engineering board is:

```text
Ready for Engineering → Working → In Review → Human Review → Ready to Merge
```

The engineering state is derived:

- **Ready for Engineering:** approved design, active sprint, no PR.
- **Working:** draft PR, active implementation, new commits, requested changes,
  or failed checks requiring rework.
- **In Review:** implementation finished; checks or validation running.
- **Human Review:** checks and validation pass for the exact PR head.
- **Ready to Merge:** exact head approved and currently mergeable.
- **Done:** GitHub confirms merge; shown in the active sprint's compact
  completed section until the sprint closes.

Done is terminal. It is not a sixth work-in-progress column.

Closing a sprint:

1. requires an explicit destination for every incomplete Feature;
2. marks the Sprint completed;
3. removes its Done Features from standard active sprint and backlog queries;
4. preserves Feature, Sprint, PR, merge, approval, and audit records;
5. makes those records available to completed-sprint project reports.

Reports are read models over preserved SQLite records, not copied archive data.

UI drag-and-drop cannot set engineering state.

## GitHub synchronization

GitHub webhooks provide fast updates. A periodic reconciliation query repairs
missed events.

For each delivery:

1. Verify the webhook signature.
2. Store the provider delivery ID idempotently.
3. Ignore facts older than the current provider revision.
4. Update the PullRequest row.
5. Recompute the Feature's engineering state.
6. Commit the change and audit event together.

## Browser

Each selected Project has three primary pages:

1. **Backlog** — Current Sprint followed by future ranked Features.
2. **Board** — five engineering columns for the Current Sprint.
3. **Approvals** — design and PR decisions waiting for the owner.

The active sprint and board each include a compact Done section. Completed
sprints and Features are available through project Reports and are excluded
from standard active views.

A Feature opens one detail view. Light/dark mode is available from the top-right
button and stored in the browser.

## Security and deployment

- Bind to loopback by default.
- Access through SSH or a private network.
- Run under a dedicated unprivileged operating-system account where practical.
- Use authenticated sessions, CSRF protection, idempotency keys, and optimistic
  record versions.
- Keep secrets outside SQLite and project artifacts.
- Resolve all filesystem paths beneath the configured project root.

Keep the application, data, repositories, worktrees, configuration, and secrets
under explicit platform-appropriate directories. Defaults follow macOS and Linux
filesystem conventions; every resolved project path must remain beneath its
configured root.

## Serial implementation plan

1. Project, Feature, Sprint, and ranking models.
2. Five-state engineering derivation and tests.
3. PR binding, webhook ingestion, and reconciliation.
4. Browser authentication and shell.
5. Backlog, Board, Feature detail, Approvals, and project Reports.
6. Serial engineering execution.
7. macOS and Linux deployment, backup, and restore.

## Approval

Approving this document approves the modular-monolith stack, minimal data model,
three primary project pages, five engineering states, one-PR rule, and seven
implementation slices.
