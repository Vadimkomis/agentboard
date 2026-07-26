# AgentBoard Evals

This file is the single source of truth for behavioral evaluation coverage.
Statuses are `planned`, `in-progress`, `passing`, `failing`, and `deprecated`.

## Browser v0 persistence foundation

- Name: Project isolation
- Status: passing
- Description: Creating and querying multiple Projects never exposes or changes another Project's repository facts, Features, backlog, Sprints, or audit history.
- Notes: Cover application queries with deterministic in-memory fakes and persistence queries with a temporary SQLite database; corresponds to acceptance evals 4 and 6.

- Name: Project-scoped numbering
- Status: passing
- Description: Feature and Sprint numbers start and advance independently per Project, while duplicates within one Project are rejected.
- Notes: Exercise interleaved creation in two Projects plus database unique constraints on `(project_id, number)`.

- Name: Ranked backlog persistence
- Status: passing
- Description: New Features append with contiguous integer ranks, complete reorder requests support first, middle, and last moves, and committed order survives a database restart.
- Notes: Include empty and single-Feature backlogs, stable non-rank fields, integer rank uniqueness, and restart reconstruction; corresponds to acceptance evals 5, 9, and 31.

- Name: Atomic backlog reordering
- Status: passing
- Description: A reorder accepts each Feature in the selected Project exactly once and either persists the complete collision-safe rank change or leaves every previous rank unchanged.
- Notes: Cover missing, duplicate, unknown, and cross-Project identifiers with typed errors, rollback assertions, and no audit event after failure; corresponds to acceptance eval 6.

- Name: One active Sprint per Project
- Status: passing
- Description: Starting a planned Sprint succeeds only when its Project has no active Sprint, while another Project may independently have an active Sprint.
- Notes: Verify the domain/application rejection and the SQLite partial unique index independently; cover planned creation, independent Sprint numbering, and start timestamps; corresponds to acceptance eval 3.

- Name: Cross-project Sprint membership rejection
- Status: passing
- Description: A Feature can be added only to a Sprint owned by the same Project, and a rejected cross-Project addition persists neither membership nor audit history.
- Notes: Cover typed application errors, foreign-key-backed database records, duplicate membership, and unchanged Sprint ordering.

- Name: Approved-design Sprint eligibility
- Status: passing
- Description: A Feature may enter an engineering Sprint only when it carries an approved exact design revision; a missing or blank approval is rejected.
- Notes: Use fixed design hashes and cover eligible membership, missing approval, and an unchanged Sprint after rejection; corresponds to acceptance eval 10.

- Name: Restart-safe persistence
- Status: passing
- Description: Closing and reopening the configured database preserves Projects, Features, backlog ranks, Sprints, ranked membership, and minimal audit history.
- Notes: Use a temporary file-backed SQLite database and new engine/session instances rather than metadata-only or same-session assertions; corresponds to acceptance evals 31 and 35.

- Name: Database constraints
- Status: passing
- Description: SQLite enforces unique Project keys, Project-scoped Feature and Sprint numbers and ranks, one active Sprint per Project, same-Project Sprint membership, and enabled foreign keys.
- Notes: Exercise constraints directly, including orphan insertion and the active-Sprint partial unique index, and assert rollback leaves the session/database usable.

- Name: Atomic audit history
- Status: passing
- Description: Each successful state-changing use case and its structured AuditEvent commit in one transaction, while failed commands persist neither partial state nor an audit record.
- Notes: Use failure-injecting unit-of-work fakes for handler coverage and integration transaction failures for database proof; corresponds to acceptance eval 32.

## Deferred approved browser v0 evals

- Name: Derived engineering state
- Status: planned
- Description: Durable PR, check, validation, approval, mergeability, and merge facts derive the approved exact-head engineering states.
- Notes: Deferred to `feature/derived-engineering-state`; do not treat schema placeholders as passing behavior.

- Name: Browser backlog and board
- Status: planned
- Description: Authenticated browser views render the selected Project's backlog, current Sprint, five-column board, details, approvals, and reports from durable state.
- Notes: Deferred to `feature/browser-backlog-board`; no browser-page coverage belongs in the persistence-foundation branch.

- Name: GitHub pull-request synchronization
- Status: planned
- Description: Signed, idempotent webhook ingestion and periodic reconciliation preserve one primary PR and exact-head facts.
- Notes: Deferred to `feature/github-pr-synchronization`; the legacy optional GitHub CLI behavior is separate.

- Name: Independent validator execution
- Status: planned
- Description: AgentBoard stores and verifies independent-validator assignments and results for immutable candidate revisions.
- Notes: Deferred to `feature/independent-validation-integration`; schema fields alone do not satisfy this eval.

- Name: Human Review notifications
- Status: planned
- Description: Entering Human Review creates and eventually delivers one durable notification per Feature, exact head, kind, and destination.
- Notes: Deferred to `feature/human-review-notifications`; legacy terminal and desktop notifications are separate.

- Name: Serial browser-v0 engineering worker
- Status: planned
- Description: At most one Feature per Project has an active browser-v0 engineering execution.
- Notes: Deferred until after the browser and integration slices; the legacy Ticket orchestrator is separate.
