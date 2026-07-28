# AgentBoard Evals

This file is the single source of truth for behavioral evaluation contracts and
their automated test mappings. Test runners and CI are authoritative for
pass/fail results; this document does not record transient statuses.

## Browser v0 persistence foundation

- Name: Project isolation
- Description: Creating, getting, and listing multiple Projects never exposes or changes another Project's repository facts, Features, backlog, Sprints, or audit history.
- Test mapping: `tests/test_browser_application.py` and `tests/test_browser_persistence_core.py` cover typed Get not-found behavior, deterministic List ordering by stable identifier, and temporary-SQLite isolation; corresponds to acceptance evals 4 and 6.

- Name: Project-scoped numbering
- Description: Feature and Sprint numbers start and advance independently per Project, while duplicates within one Project are rejected.
- Test mapping: `tests/test_browser_application.py` and `tests/test_browser_persistence_core.py` exercise interleaved creation in two Projects plus database unique constraints on `(project_id, number)`.

- Name: Ranked backlog persistence
- Description: The future backlog contains non-completed Project Features outside the active Sprint; new Features append with integer ranks, and committed order survives a database restart.
- Test mapping: `tests/test_browser_application.py` and `tests/test_browser_persistence_core.py` cover active-Sprint exclusion, both completion signals, empty and single-Feature backlogs, stable non-rank fields, integer rank uniqueness, and restart reconstruction; corresponds to acceptance evals 5, 9, and 31.

- Name: Atomic backlog reordering
- Description: A reorder accepts exactly the current future-backlog Feature set and either exchanges its existing available Project rank slots atomically or leaves every previous rank unchanged.
- Test mapping: `tests/test_browser_application.py` and `tests/test_browser_persistence_core.py` prove active-Sprint and completed Feature ranks remain fixed, Current Sprint ranks never change, other Projects stay isolated, and invalid mixed active/future, missing, duplicate, unknown, or cross-Project requests roll back without an audit event; corresponds to acceptance eval 6.

- Name: One active Sprint per Project
- Description: Starting a planned Sprint succeeds only when its Project has no active Sprint, while another Project may independently have an active Sprint.
- Test mapping: `tests/test_browser_domain.py`, `tests/test_browser_application.py`, and `tests/test_browser_persistence_core.py` verify domain/application rejection and the SQLite partial unique index independently; corresponds to acceptance eval 3.

- Name: Cross-project Sprint membership rejection
- Description: A Feature can be added only to a Sprint owned by the same Project, and a rejected cross-Project addition persists neither membership nor audit history.
- Test mapping: `tests/test_browser_application.py` and `tests/test_browser_persistence_core.py` cover typed errors, foreign-key-backed records, duplicate membership, and unchanged Sprint ordering.

- Name: Approved-design Sprint eligibility
- Description: A Feature may enter an engineering Sprint only when it carries an approved exact design revision; a missing or blank approval is rejected.
- Test mapping: `tests/test_browser_domain.py`, `tests/test_browser_application.py`, and `tests/test_browser_persistence_core.py` use fixed design hashes and cover eligible membership, missing approval, and unchanged state after rejection; corresponds to acceptance eval 10.

- Name: Restart-safe persistence
- Description: Closing and reopening the configured database preserves Projects, Features, backlog ranks, Sprints, ranked membership, and minimal audit history.
- Test mapping: `tests/test_browser_persistence_core.py` uses temporary file-backed SQLite databases and new engine/session instances rather than metadata-only or same-session assertions; corresponds to acceptance evals 31 and 35.

- Name: Database constraints
- Description: SQLite enforces unique Project keys, Project-scoped Feature and Sprint numbers and ranks, one active Sprint per Project, same-Project Sprint membership, and enabled foreign keys.
- Test mapping: `tests/test_browser_persistence_core.py` exercises constraints directly, including orphan insertion and the active-Sprint partial unique index, and asserts rollback leaves the database usable.

- Name: Atomic audit history
- Description: Each successful state-changing use case and its structured AuditEvent commit in one transaction, while failed commands persist neither partial state nor an audit record.
- Test mapping: `tests/test_browser_application.py` uses failure-injecting unit-of-work fakes, and `tests/test_browser_persistence_core.py` injects database transaction failures; corresponds to acceptance eval 32.

## Deferred approved browser v0 evals

- Name: Derived engineering state
- Description: Durable PR, check, validation, approval, mergeability, and merge facts derive the approved exact-head engineering states.
- Test mapping: To be added by `feature/derived-engineering-state`; schema placeholders do not satisfy this contract.

- Name: Browser backlog and board
- Description: Authenticated browser views render the selected Project's backlog, current Sprint, five-column board, details, approvals, and reports from durable state.
- Test mapping: To be added by `feature/browser-backlog-board`; no browser-page coverage belongs in the persistence-foundation branch.

- Name: GitHub pull-request synchronization
- Description: Signed, idempotent webhook ingestion and periodic reconciliation preserve one primary PR and exact-head facts.
- Test mapping: To be added by `feature/github-pr-synchronization`; the legacy optional GitHub CLI behavior is separate.

- Name: Independent validator execution
- Description: AgentBoard stores and verifies independent-validator assignments and results for immutable candidate revisions.
- Test mapping: To be added by `feature/independent-validation-integration`; schema fields alone do not satisfy this contract.

- Name: Human Review notifications
- Description: Entering Human Review creates and eventually delivers one durable notification per Feature, exact head, kind, and destination.
- Test mapping: To be added by `feature/human-review-notifications`; legacy terminal and desktop notifications are separate.

- Name: Serial browser-v0 engineering worker
- Description: At most one Feature per Project has an active browser-v0 engineering execution.
- Test mapping: To be added after the browser and integration slices; the legacy Ticket orchestrator is separate.
