# AgentBoard v0 Architecture Design

Status: Draft for owner approval

## 1. Decision summary

AgentBoard v0 is one Linux-hosted, single-owner control-plane service supporting
multiple isolated projects. Each project has its own board. Features execute
serially within a project. The primary interface is a secured browser
application accessed from the Mac through a private network path.

The existing Python codebase remains the foundation. The Textual TUI is not the
primary product surface and may be removed after browser parity.

### Proposed stack

- Python 3.12
- FastAPI application and domain API
- Jinja2 server-rendered pages
- HTMX for partial updates and guarded actions
- Server-Sent Events for live status
- SQLAlchemy 2 async persistence
- SQLite in WAL mode for v0
- Alembic migrations
- Pydantic boundary schemas
- systemd service under an unprivileged Linux account

This keeps one language, one deployment unit, and one authoritative state
machine. It avoids a separate SPA toolchain while the product model is still
changing.

## 2. System boundaries

### Linux control plane

Linux owns:

- the AgentBoard application and scheduler;
- authoritative workflow and approval state;
- project and repository configuration;
- immutable artifact revisions;
- event history and validation evidence;
- secrets and worker credentials;
- repository mirrors and execution worktrees;
- backups and recovery.

### Mac

The Mac provides:

- browser access to AgentBoard;
- Obsidian over a sanitized, versioned Markdown projection;
- later, a narrowly scoped remote coding worker.

The Mac never receives the AgentBoard database, OpenClaw memory, global
credentials, unrelated project context, or approval authority through a worker.

### GitHub

GitHub remains authoritative for source repositories, commits, branches, pull
requests, and CI results. It is not the workflow database.

## 3. Runtime components

### Web application

Authenticates the owner, renders portfolio/project/feature views, validates
commands, and delegates every mutation to the application layer.

### Application service

Coordinates use cases such as create project, create feature, revise artifact,
approve design, dispatch work, record validation, request rework, and accept a
candidate.

### Domain core

Contains the state machine and invariants. It has no FastAPI, HTMX, SQLAlchemy,
GitHub, OpenClaw, filesystem, or worker dependencies.

### Persistence adapters

Store domain records in SQLite and evidence blobs on the Linux filesystem.
Repositories, files, and external APIs are accessed through explicit ports.

### Serial dispatcher

Claims at most one runnable work item per project. It persists a lease before
dispatch and reconciles expired or interrupted executions after restart.
Parallel execution is absent in v0 rather than merely hidden behind a setting.

### Projection service

Creates sanitized Markdown from approved artifacts and permitted status
metadata. Obsidian import creates proposed revisions; it never overwrites an
approved revision.

## 4. Data model

All primary identifiers are UUIDs. Human-readable slugs are labels, not
filesystem or authorization boundaries.

### Project

- `id`
- `slug`
- `name`
- `description`
- `status`: active, archived
- `serial_execution_enabled`: always true in v0
- `artifact_export_policy`
- timestamps

### ProjectRepository

- `id`
- `project_id`
- `provider`
- `remote_url`
- `default_branch`
- `local_mirror_path`
- `credential_ref`
- timestamps

A repository binding belongs to exactly one project in v0. Sharing a repository
between projects requires a later explicit isolation design.

### Feature

- `id`
- `project_id`
- `sequence_number` unique within project
- `title`
- `summary`
- `rank` unique within project
- `priority`
- `estimate`
- `owner_id`
- `state`
- `current_candidate_revision`
- `rework_count`
- `failure_signature`
- timestamps

### Sprint

- `id`
- `project_id`
- `sequence_number` unique within project
- `name`
- `goal`
- `state`: planned, active, completed, cancelled
- `starts_at`
- `ends_at`
- timestamps

Only one Sprint may be active per project.

### SprintFeature

- `sprint_id`
- `feature_id`
- `sprint_rank`
- `committed_at`
- `removed_at` nullable

Sprint membership is project-scoped and versioned through events. The
engineering board and Current Sprint list query the same active membership.

### ArtifactRevision

- `id`
- `project_id`
- `feature_id`
- `kind`: specification, eval_contract, product_design, technical_design
- `revision_number`
- `content`
- `content_hash`
- `created_by_type`
- `created_by_id`
- `supersedes_id`
- timestamp

Approved content is immutable. Editing creates a new revision.

### Approval

- `id`
- `project_id`
- `feature_id`
- `artifact_revision_id` or `candidate_revision`
- `gate`: design, final
- `decision`: approved, rejected
- `actor_id`
- `comment`
- timestamp

Approval references the exact revision. It is never represented as a mutable
boolean on the Feature row.

### WorkItem

- `id`
- `project_id`
- `feature_id`
- `sequence_number`
- `title`
- `assignment_payload`
- `state`: pending, leased, running, completed, failed, cancelled
- `allowed_repository_id`
- `allowed_paths`
- `depends_on_id`
- timestamps

The v0 dispatcher permits only the next eligible sequence number.

### Execution

- `id`
- `project_id`
- `feature_id`
- `work_item_id`
- `attempt`
- `worker_id`
- `lease_token_hash`
- `candidate_base_revision`
- `result_revision`
- `state`
- `started_at`
- `heartbeat_at`
- `finished_at`
- `failure_code`

### ValidationRun

- `id`
- `project_id`
- `feature_id`
- `candidate_revision`
- `eval_artifact_revision_id`
- `validator_id`
- `implementation_execution_ids`
- `attempt`
- `outcome`: passed, failed, error, escalated
- `evidence_manifest_hash`
- timestamp

### AssertionResult

- `id`
- `validation_run_id`
- `assertion_id`
- `outcome`
- `evidence_refs`
- `summary`

### Event

- `id`
- `project_id`
- `feature_id` nullable
- `aggregate_type`
- `aggregate_id`
- `event_type`
- `actor_type`
- `actor_id`
- `payload`
- `occurred_at`

Every successful mutation and its event commit in the same transaction.
The event table is an audit log and integration source, not the only state
representation.

### Worker

- `id`
- `name`
- `kind`: linux_local, mac_remote
- `status`
- `capabilities`
- `credential_ref`
- `last_seen_at`

Worker records are global, but leases and assignment payloads are strictly
project-scoped.

## 5. Feature state machine

The main engineering board has five visible states:

```text
Ready for Engineering
→ Working
→ In Review
→ Human Review
→ Ready to Merge
```

Planning states live in Backlog:

- Inbox
- Clarifying
- Spec Draft
- Evals Draft
- Design
- Design Review

Control/terminal/history states:

- Paused
- Cancelled
- Escalated
- Failed
- Merged

### Load-bearing guards

- `Spec Draft → Evals Draft`: a specification revision exists.
- `Evals Draft → Design`: specification and eval revisions are selected as the
  feature foundation.
- `Design → Design Review`: product and technical design revisions exist.
- `Design Review → Ready for Engineering`: explicit approval references the exact
  technical design revision and its upstream revisions are still current.
- `Ready for Engineering → Working`: a serial work plan exists and one primary
  draft pull request is created and bound to the Feature.
- `Working → In Review`: implementation reports completion for the current PR
  head and automated checks/agent validation begin.
- `In Review → Human Review`: all blocking checks and agent validation pass for
  the exact PR head revision.
- `In Review → Working`: checks fail or bounded rework is required.
- `Human Review → Ready to Merge`: the owner approves the exact validated PR
  head, required GitHub reviews are satisfied, and the PR is mergeable.
- `Human Review → Working`: changes are requested or new commits invalidate the
  reviewed candidate.
- `Ready to Merge → Human Review` or `In Review`: approval, checks, head
  revision, or mergeability becomes stale.
- `Ready to Merge → Merged`: GitHub confirms the primary PR merged.

Changing an upstream approved artifact invalidates downstream design approval,
candidate validation, and final review eligibility according to a deterministic
invalidation table.

UI code cannot set Feature state directly. It submits commands to the
application service, which asks the domain state machine to authorize the
transition.

## 6. Browser experience

### Portfolio

The landing page lists projects with:

- active Feature counts by state;
- waiting-for-you count;
- running work;
- blocked or escalated work;
- last activity;
- Open Project action.

### Project board

Each project has a focused five-column engineering board: Ready for Engineering,
Working, In Review, Human Review, and Ready to Merge. Cards show Feature number,
title, primary PR, check/review status, current reason, and next action.

Cards are not freely draggable. Selecting a card opens the Feature workspace;
guarded buttons perform legal transitions. This prevents the UI from bypassing
the domain model merely because Kanban software traditionally lets humans fling
cards around.

Planning and design work appears in a separate Backlog view with filters and
grouping rather than six additional board columns.

### Project backlog

Backlog is a compact Jira-style ranked list scoped to the selected project. It
shows Feature key, title, planning stage, priority, owner, estimate, labels, and
engineering readiness. Users may:

- search and filter without mutating state;
- group by planning stage, priority, or owner;
- reorder rank within the project;
- open the same Feature workspace used by the engineering board;
- create a Feature;
- invoke a guarded Move to Engineering action.

Rank is independent of workflow state. Dragging a backlog row changes rank
only. The Move to Engineering command separately verifies current approved
specification, eval, product-design, and technical-design revisions before
placing the Feature in Ready for Engineering.

The active sprint appears above the future backlog with its name, dates, goal,
progress, committed estimate, and Features. Those Features use engineering
state rather than planning state. The five-column board is a visual projection
of this same active sprint—not a separate collection of cards.

### Feature workspace

Tabs:

1. Overview
2. Specification
3. Acceptance Evals
4. Product Design
5. Technical Design
6. Build
7. Validation
8. History

The header always shows:

- current state;
- exact reason it is waiting;
- next permitted action;
- selected artifact revisions;
- candidate revision;
- approval and validation freshness.

### Approval inbox

A portfolio-level inbox groups required human actions:

- unresolved product decisions;
- design reviews;
- escalations;
- final candidate reviews.

Every approval screen displays the exact revision, relevant diff, upstream
references, evidence, consequences, and Approve/Reject actions.

### Project settings

- repository bindings;
- branch policy;
- local storage health;
- Obsidian projection;
- worker eligibility;
- backup status;
- archival controls.

### Appearance

A top-right button switches between light and dark themes. The browser stores
the owner's preference locally and the first render respects that preference to
avoid a theme flash.

## 7. Pull-request synchronization

Each engineering Feature has one primary `PullRequestBinding`:

- `project_id`
- `feature_id`
- `repository_id`
- `provider`
- `external_id`
- `number`
- `url`
- `head_ref`
- `head_revision`
- `base_ref`
- `draft`
- `state`
- `mergeable_state`
- `review_decision`
- `checks_summary`
- `provider_updated_at`
- `last_reconciled_at`

GitHub webhooks provide low-latency updates. A reconciliation job periodically
fetches current PR facts so missed webhooks cannot leave the board stale.
Webhook delivery identifiers are unique and idempotent. Provider timestamps and
head revisions prevent delayed events from overwriting newer facts.

The domain derives the engineering column from durable facts:

- Ready for Engineering: approved design and no active primary PR.
- Working: draft PR, active implementation, new unvalidated commits, requested
  changes, or failing checks that require rework.
- In Review: implementation complete; checks or independent validation are
  running.
- Human Review: required automated and agent checks pass for the exact head;
  owner or required GitHub review is pending.
- Ready to Merge: exact head approved, all required checks pass, and GitHub
  reports the PR mergeable.
- Merged: GitHub reports the PR merged; remove from the active board.

Closing without merge, force-push ambiguity, missing repository access, or
irreconcilable provider state produces an explicit exception requiring human
attention rather than a misleading engineering column.

## 8. HTTP and update model

HTML pages are rendered server-side. HTMX issues commands and refreshes partial
views. Server-Sent Events notify the browser that durable state changed; the
browser then reloads the affected projection.

SSE carries identifiers and revision counters, not authoritative state. A
reconnect always rebuilds the screen from SQLite.

All state-changing requests require:

- authenticated session;
- CSRF token;
- command-specific authorization;
- expected aggregate version for optimistic concurrency;
- idempotency key.

## 9. Security

### Network exposure

The service binds to `127.0.0.1` by default. Mac browser access uses an SSH
tunnel or an authenticated private network such as Tailscale. Public internet
exposure is out of scope for v0.

### Authentication

The browser requires a single-owner account with an Argon2id password hash and
a short-lived signed session cookie:

- `HttpOnly`
- `Secure` when terminated over HTTPS
- `SameSite=Strict`
- idle and absolute expiry

Recovery is a Linux-side administrative command, not an email flow.

### Process boundary

Run as a dedicated `agentboard` user with no shell login and restrictive
filesystem permissions. Secrets are referenced from a root-managed environment
file and never stored in project artifacts or Obsidian exports.

### Filesystem containment

Project storage uses UUID-derived paths beneath a configured root. Every
resolved path is checked after symlink resolution. Worktrees run under the
service account with project-scoped credentials.

## 10. Persistence and filesystem

```text
/srv/agentboard/app/
/var/lib/agentboard/
├── agentboard.db
├── evidence/<project-uuid>/<content-hash>
├── repos/<project-uuid>/<repository-uuid>.git
├── worktrees/<project-uuid>/<execution-uuid>/
└── projections/<project-uuid>/
/etc/agentboard/config.yml
/etc/agentboard/secrets.env
```

Specifications, evals, and designs are versioned in SQLite because they are
small, transactional domain artifacts. Large logs and evidence use
content-addressed files; SQLite stores their hashes and metadata.

SQLite configuration:

- WAL journal mode
- foreign keys enabled
- busy timeout
- explicit transaction boundaries
- application-level optimistic versions
- one scheduler process in v0

No runtime workspace uses `/tmp`.

## 11. Restart and reconciliation

On service start:

1. acquire the single scheduler lock;
2. find leased/running executions without a fresh heartbeat;
3. query the local process, remote worker, and Git repository as applicable;
4. record a reconciliation event;
5. resume observation, mark deterministic failure/completion, or escalate;
6. dispatch the next serial item only after state is consistent.

Elapsed time creates a stale signal, not an automatic mission failure.

## 12. Obsidian projection

AgentBoard renders a project folder containing sanitized Markdown:

```text
Projects/<project-slug>/
├── Project.md
└── Features/
    └── <feature-number>-<slug>/
        ├── Overview.md
        ├── Specification.md
        ├── Acceptance-Evals.md
        ├── Product-Design.md
        ├── Technical-Design.md
        └── Validation.md
```

The projection contains stable IDs and revision metadata in frontmatter. Git
transports it to the Mac vault. Import from Mac creates a proposed revision and
requires conflict resolution when the Linux revision advanced.

## 13. Migration from the current code

### Preserve

- Python package and CLI entry point;
- SQLAlchemy async foundation;
- useful PM/runner concepts;
- test infrastructure;
- repository clone and PR integration as references.

### Replace or restructure

- Add Project and project-scoped repository bindings.
- Replace `StoryStatus` with the guarded Feature state machine.
- Move mutations out of Textual screen callbacks.
- Replace fire-and-forget `asyncio.create_task` orchestration with durable
  leases, reconciliation, and a serial dispatcher.
- Stop deleting every execution workspace immediately; retain according to
  evidence policy.
- Move workspaces out of `/tmp`.
- Remove `--dangerously-skip-permissions` and `--full-auto` as unconditional
  defaults; permissions come from assignments and worker policy.
- Add artifact revisions, approvals, events, validation runs, assertion
  results, workers, and optimistic versions.
- Add browser application and authentication.

## 14. Implementation slices

Implementation remains serial:

1. Domain types, Project model, Feature state machine, and transition tests.
2. Artifact revisions, approvals, events, and invalidation tests.
3. SQLite migrations, project isolation, and filesystem containment.
4. Application commands and query projections.
5. Authentication and browser shell.
6. Portfolio, project board, and Feature workspace.
7. Serial dispatcher, leases, and restart reconciliation.
8. Validation records and Human Review gate.
9. Obsidian export/import boundary.
10. Linux systemd deployment, backup, restore, and security verification.

Each slice must keep the repository runnable and pass the approved acceptance
evals applicable to that slice.

## 15. Approval decisions

Approval of this design confirms:

1. FastAPI + Jinja2 + HTMX rather than a React SPA for v0.
2. A Current Sprint section and separate ranked future backlog per project,
   plus a five-column engineering-board projection of that sprint.
3. No arbitrary card dragging; engineering state is derived from guarded
   workflow and primary pull-request facts.
4. SQLite stores versioned text artifacts; large evidence stays
   content-addressed on disk.
5. Private access through SSH/Tailscale with loopback binding by default.
6. Product design and technical design are separate artifacts within the Design
   stage.
7. The ten implementation slices and their serial order.
