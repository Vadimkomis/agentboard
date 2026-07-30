# AgentBoard v0 Technical Design

Status: Approved

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
- Jinja2 server-rendered HTML and small local JavaScript enhancements
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
- start independent validation;
- record a validator result;
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

### ValidationRun

`id`, `feature_id`, `pull_request_id`, `assignment_id`, `assignment_digest`,
`subject_revision`, `validator_id`, `validator_session_id`,
`implementation_worker_ids`, `implementation_session_ids`, `status`, `outcome`,
`assignment_json`, `result_json`, `failure_signatures`, `started_at`,
`completed_at`, `created_at`

Statuses are `queued`, `running`, and `completed`. A completed run has the
contract outcome `pass`, `fail`, or `error`. Assignment and result payloads are
retained as immutable evidence. A result is current only when
`subject_revision` equals the active primary PR's exact head revision.

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
  failed checks, or candidate validation failure requiring rework.
- **In Review:** implementation finished; checks or validation are pending or
  running, or validation ended in an infrastructure or protocol error requiring
  attention.
- **Human Review:** checks and validation pass for the exact PR head.
- **Ready to Merge:** exact head approved and currently mergeable; shown in the
  Sprint view's Done column.
- **Done:** GitHub confirms merge; remains in the Sprint view's Done column
  until the sprint closes.

Done is terminal. Ready to Merge and Done remain distinct durable states even
though the Sprint view groups both in one column.

Closing a sprint:

1. requires an explicit destination for every incomplete Feature;
2. marks the Sprint completed;
3. removes its Done Features from standard active sprint and backlog queries;
4. preserves Feature, Sprint, PR, merge, approval, and audit records;
5. makes those records available to completed-sprint project reports.

Reports are read models over preserved SQLite records, not copied archive data.

UI drag-and-drop cannot set engineering state.

## Independent validation

AgentBoard consumes the standalone `independent-validator/v1` assignment and
result contract supplied by `ai-playbook`. AgentBoard owns the integration
boundary:

1. Read and freeze the active primary PR's exact head revision.
2. Build and persist a schema-valid assignment containing approved checks,
   acceptance criteria, relevant artifacts, and that immutable revision.
3. Start a fresh validator session whose identity and session ID differ from
   every recorded implementation worker and implementation session.
4. Store the returned result before interpreting it.
5. Validate both schemas, the assignment digest, semantic pair rules, validator
   independence, and the inspected revision.
6. Accept the outcome only when the result still targets the current PR head.

A `pass` permits Human Review. A `fail` returns the Feature to Working. An
`error` withholds a candidate verdict, leaves the Feature in In Review with an
attention marker, and may be retried. Repeated stable failure signatures stop
automatic retry and require owner action. A new PR commit invalidates every
earlier validation result and pull-request approval for state derivation without
deleting their audit history.

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

Webhook reconciliation and validator-result ingestion call the same state
transition use case. Notification creation therefore follows the transition
itself rather than depending on which input caused it.

## Human-attention notification delivery

The application owns a small in-process delivery loop. It selects due
`NotificationDelivery` rows, posts a bounded JSON payload to the configured
endpoint, and records success or a retryable failure. Duplicate reconciliation
cannot enqueue a second delivery because the exact Feature, revision, kind, and
destination form an idempotency key.

The payload contains stable identifiers, project and Feature names, PR number
and URL, exact head revision, and the AgentBoard review URL. AgentBoard derives
that link from a configured `review_base_url`; it never substitutes its
localhost listener address. Enabling phone delivery requires an HTTPS or trusted
private-network URL reachable by the phone. The payload contains no repository
credentials or application secrets. Requests are authenticated with a dedicated
outbound secret kept outside SQLite.

For the first dogfood deployment, the endpoint is an OpenClaw ingress that
delivers the notification to the owner's phone. AgentBoard does not know whether
OpenClaw uses WhatsApp, a native push provider, or another phone channel.

## Browser

Each selected Project has three primary pages:

1. **Backlog** — Current Sprint followed by future ranked Features.
2. **Sprint** — five engineering columns for the Current Sprint; the route is
   labeled Board only when no Sprint is active.
3. **Approvals** — design and PR decisions waiting for the owner.

The Projects catalog initially shows a plus control and reveals creation fields
only on request. It creates an isolated Project through the same atomic
application command as the CLI, with bounded form parsing, CSRF validation, and
typed validation or conflict errors. A separate two-step, exact-key
confirmation atomically deletes one Project graph while preserving every other
Project's Backlog and Sprint.

Backlog keeps completed current-Sprint work in its compact Done section. The
Sprint view combines merge-ready and completed work in its Done column.
Completed sprints and Features are available through project Reports and are
excluded from standard active views.

A Feature opens one detail view. Light/dark mode is available from the top-right
button and stored in the browser.

## Security and deployment

- Listen only on localhost by default. Remote access must be explicitly
  configured through a trusted private connection.
- Access through SSH or a private network.
- Treat `review_base_url` as separate from the listen address. Validate it at
  startup before enabling phone notifications.
- Run under a dedicated unprivileged operating-system account where practical.
- Use signed browser sessions and CSRF protection for every mutation, plus
  idempotency keys and optimistic record versions when an existing ranked or
  versioned record remains after the mutation. The session binds CSRF state and
  does not authenticate users.
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
4. Independent-validator persistence, execution, and state derivation.
5. Durable Human Review notifications and OpenClaw dogfood delivery.
6. Login-free loopback browser security and shell with signed CSRF sessions.
7. Backlog, Sprint, Feature detail, Approvals, and project Reports.
8. Serial engineering execution.
9. macOS and Linux deployment, backup, and restore.

## Approval

Approving this document approves the modular-monolith stack, minimal data model,
three primary project pages, five engineering states, one-PR rule, and nine
implementation slices.
