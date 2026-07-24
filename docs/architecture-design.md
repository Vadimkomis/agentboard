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
    ├── notification delivery
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
- enqueue Human Review notification;
- record merge.

### Infrastructure

Adapters handle SQLite, GitHub, filesystem paths, the configured notification
endpoint, and later the engineering worker. Browser handlers never mutate
database models directly.

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

### NotificationDelivery

`id`, `feature_id`, `kind`, `subject_revision`, `destination`, `status`,
`attempt_count`, `next_attempt_at`, `sent_at`, `last_error`, `payload`,
`created_at`

`kind`, `feature_id`, `subject_revision`, and `destination` are unique together.
This is a durable delivery record inside SQLite, not a general-purpose queue.

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
6. When the Feature newly enters Human Review, insert its notification delivery.
7. Commit the state change, audit event, and notification delivery together.

## Human-attention notification delivery

The application owns a small in-process delivery loop. It selects due
`NotificationDelivery` rows, posts a bounded JSON payload to the configured
endpoint, and records success or a retryable failure. Duplicate reconciliation
cannot enqueue a second delivery because the exact Feature, revision, kind, and
destination form an idempotency key.

The payload contains stable identifiers, project and Feature names, PR number
and URL, exact head revision, and the AgentBoard review URL. It contains no
repository credentials or application secrets. Requests are authenticated with
a dedicated outbound secret kept outside SQLite.

For the first dogfood deployment, the endpoint is an OpenClaw ingress that
delivers the notification to the owner's phone. AgentBoard does not know whether
OpenClaw uses WhatsApp, a native push provider, or another phone channel.

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

- Listen only on localhost by default. Remote access must be explicitly
  configured through a trusted private connection.
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
4. Durable Human Review notifications and OpenClaw dogfood delivery.
5. Browser authentication and shell.
6. Backlog, Board, Feature detail, Approvals, and project Reports.
7. Serial engineering execution.
8. macOS and Linux deployment, backup, and restore.

## Approval

Approving this document approves the modular-monolith stack, minimal data model,
three primary project pages, five engineering states, one-PR rule, and eight
implementation slices.
