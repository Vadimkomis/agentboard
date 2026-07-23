# AgentBoard Acceptance Eval Contract

Status: Draft for owner review

This contract defines observable outcomes for the first usable multi-project
AgentBoard release. Passing unit tests alone is insufficient.

## Evaluation rules

- Each assertion records command output or structured reviewer evidence.
- A worker that implements a change cannot serve as its final validator.
- Validators receive the approved spec, eval contract, repository revision, and
  produced evidence, but not the implementer's private conversation history.
- Required assertions must all pass before Human Review.
- Any security-isolation failure blocks release immediately.

## A. Project isolation

### A1 — Independent boards

Given two projects, each can contain missions with the same title and local
sequence number without collision. Listing either board returns only its own
missions.

### A2 — Scoped records

Stories/missions, work items, executions, events, artifacts, approvals, and
repository bindings cannot be read or mutated through another project context.

### A3 — Filesystem containment

Every repository mirror, worktree, and generated artifact resolves beneath the
owning project's configured root. Traversal and symlink escape attempts fail
closed.

### A4 — Concurrency isolation

Serial execution is enforced within a project. Work queued by another project
does not corrupt or silently cancel the running project. Global worker limits
are enforced.

## B. Workflow and approvals

### B1 — Guarded transitions

Every state transition is validated by the domain state machine. Direct jumps
that bypass required artifacts or approvals are rejected.

### B2 — Design gate

A mission cannot enter Ready to Build until a specific design revision is
explicitly approved by the owner.

### B3 — Final gate

Agent validation cannot produce Accepted. Only explicit human approval of the
validated revision can do so.

### B4 — Approval integrity

Changing an approved specification, eval contract, or design creates a new
revision and invalidates downstream approval as defined by policy.

### B5 — Atomic audit trail

Every successful transition and approval writes its event in the same database
transaction. A forced failure leaves neither a partial transition nor a
misleading event.

## C. Execution

### C1 — Isolated workspace

Each execution receives a unique worktree or clone, branch, immutable
assignment payload, and project-scoped credentials.

### C2 — Remote-worker trust boundary

A Mac worker can fetch an authorized assignment and return commits and
evidence, but cannot read the board database, OpenClaw memory, unrelated
projects, or Linux-side secrets.

### C3 — Restart recovery

If AgentBoard restarts during execution, it reconciles durable execution state
with the worker/repository and reaches a deterministic running, failed,
completed, or human-attention state without duplicating work.

### C4 — Long-running missions

No mission fails solely because it has run for a fixed wall-clock duration.
Staleness produces an alert or reconciliation action; policy violations and
explicit execution deadlines may still fail work.

## D. Validation and rework

### D1 — Fresh validator

The validator identity and attempt are different from the implementing worker.
The system rejects self-validation as the final validation record.

### D2 — Assertion traceability

Every validation result references an approved eval assertion and contains a
pass/fail/error outcome plus evidence.

### D3 — Deterministic completion

A mission enters Human Review only when all required assertions pass against
the exact candidate revision.

### D4 — Bounded rework

Equivalent repeated failures increment a loop signature. At the configured
bound, the system stops automatic rework and requests human direction.

### D5 — Candidate invalidation

Any code change after validation creates a new candidate revision and prevents
reuse of stale passing results unless an assertion is explicitly proven
revision-independent.

## E. Persistence and operations

### E1 — Linux authority

The application, database, secrets, artifacts, event log, repositories, and
worktrees operate on the Linux host. The board remains usable when the Mac is
offline, except for assignments explicitly requiring that worker.

### E2 — Durable state

Restarting the service preserves all projects, missions, artifacts, approvals,
events, and validation results.

### E3 — Backup restoration

An encrypted backup can restore the database and artifacts to a clean
installation, with referential integrity and artifact hashes intact.

### E4 — Secret handling

Secrets never appear in database exports, Obsidian projections, task prompts,
logs, or UI responses. Configuration validates restrictive file permissions.

## F. Obsidian projection

### F1 — Sanitized export

Exported Markdown contains the approved project artifacts and allowed status
metadata, but excludes secrets, raw private logs, unrelated project data, and
personal OpenClaw memory.

### F2 — Revision-safe import

Mac-authored edits import as proposed revisions. Conflicting changes are
reported and never silently overwrite an approved Linux-side artifact.

### F3 — Offline tolerance

Failure or absence of Obsidian synchronization does not block board operation,
execution reconciliation, or persistence.

## G. Portfolio usability

### G1 — Cross-project status

The portfolio view correctly reports active, blocked, approval-waiting,
validating, and escalated counts for every non-archived project.

### G2 — Action clarity

For every non-progressing mission, the project board exposes one deterministic
reason and the next permitted human or system action.

## H. Browser interface

### H1 — Project navigation

An authenticated user can open the portfolio, select a project, and view that
project's board without seeing records from another project.

### H2 — Approval interaction

The browser interface presents the exact artifact revision and evidence being
approved. Approval and rejection actions require an explicit user action and
produce an auditable event.

### H3 — Reconnect behavior

Refreshing or reconnecting the browser reconstructs the board from durable
server state without losing or inventing transitions.

### H4 — Appearance preference

The top-right appearance control switches between accessible light and dark
modes and preserves the selection across browser sessions.

## I. Engineering board and pull requests

### I1 — Focused engineering columns

The project engineering board displays only Ready for Engineering, Working, In
Review, Human Review, and Ready to Merge. Planning states are accessible in
Backlog rather than separate engineering columns.

### I2 — Primary pull request

Every Feature that enters Working has exactly one primary pull-request binding
containing repository identity, pull-request number, URL, head revision, and
last synchronized provider revision.

### I3 — Pull-request-derived status

Draft/open state, commits, checks, requested reviews, approvals, mergeability,
closure, and merge events update durable pull-request facts and deterministically
recompute the Feature's engineering board column.

### I4 — Stale and out-of-order events

Duplicate, delayed, and out-of-order GitHub events cannot regress or corrupt the
board. Provider event identifiers and revisions are idempotently recorded, and
ambiguous conflicts trigger reconciliation.

### I5 — Readiness cannot be forged

A Feature cannot enter Ready to Merge unless the exact PR head revision passed
all required checks and agent validation, received required human approval, and
is currently mergeable.

### I6 — Reopened or changed pull request

New commits, dismissed approval, failing checks, conflicts, closure, or PR
reopening deterministically move the card to the appropriate earlier state or
exception state and invalidate stale validation.

### I7 — Merge completion

When GitHub confirms the primary PR merged, the Feature leaves the active
engineering board and appears in completed history with the merge commit and
timestamp.

## J. Per-project backlog

### J1 — Project isolation

Opening a project's Backlog lists only that project's Features, counts, ranks,
filters, and planning status.

### J2 — Stable project ranking

Backlog Features have a stable rank unique within the project. Reordering two
items persists deterministically and cannot reorder another project's backlog.

### J3 — Ranking does not bypass workflow

Drag-and-drop within the backlog changes rank only. It cannot approve an
artifact, change planning state, create a PR, or place an unready Feature on the
engineering board.

### J4 — Guarded engineering handoff

The Move to Engineering action succeeds only when required specification,
eval, product-design, technical-design, and approval revisions are current. A
successful handoff places the Feature in Ready for Engineering.

### J5 — Backlog filtering

Search, product-stage, priority, owner, label, and readiness filters return
correct project-scoped results without altering rank or workflow state.

### J6 — Compact backlog summary

Every backlog row shows rank handle, Feature key, title, planning stage,
priority, owner, estimate, and engineering readiness without opening details.

### J7 — Current sprint section

The project Backlog displays its active sprint above the future backlog,
including sprint dates, goal, progress, Feature membership, estimates, and
engineering state.

### J8 — Sprint and board consistency

The Current Sprint list and engineering board are projections of the same
project-scoped sprint membership and PR facts. Adding, removing, or updating a
Feature is reflected consistently in both views.

### J9 — One active sprint per project

A project can have at most one active sprint. Starting or completing a sprint
is transactional and cannot change another project's sprint.

## Release threshold

The v0 release candidate requires:

- all security and project-isolation assertions passing;
- all workflow, approval, persistence, and validation assertions passing;
- no unresolved critical or high-severity defects;
- successful backup/restore rehearsal;
- successful dogfood of one real mission through Accepted;
- explicit owner approval of the candidate revision.
