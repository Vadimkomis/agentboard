# AgentBoard Evals

This file is the single source of truth for behavioral evaluation contracts and
their automated test mappings. Test runners and CI are authoritative for
pass/fail results; this document does not record transient statuses.

## Browser v0 persistence foundation

- Name: Project isolation
- Description: Project-scoped reads and writes never expose or change another Project's repository facts, Features, backlog, Sprints, or audit history; the explicit Project catalog is the only multi-Project read.
- Test mapping: `tests/test_browser_application.py`, `tests/test_browser_persistence_core.py`, and `tests/test_browser_views.py` cover typed Get not-found behavior, deterministic catalog ordering, selected-workspace isolation, and temporary-SQLite isolation; corresponds to acceptance evals 4 and 6.

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
- Description: SQLite enforces unique Project keys, Project-scoped Feature and Sprint numbers and ranks, one active Sprint per Project, same-Project Sprint membership, and enabled foreign keys; browser migration rejects legacy URL-unsafe keys with an actionable error.
- Test mapping: `tests/test_browser_persistence_core.py` exercises constraints directly, including unsafe-key upgrade preflight, orphan insertion, and the active-Sprint partial unique index, and asserts rollback leaves the database usable.

- Name: Atomic audit history
- Description: Each successful state-changing use case that retains its Project and its structured AuditEvent commit in one transaction, while failed commands persist neither partial state nor an audit record; confirmed Project deletion instead removes the complete Project graph and its audit history in one transaction.
- Test mapping: `tests/test_browser_application.py` uses failure-injecting unit-of-work fakes, while `tests/test_browser_persistence_core.py` and `tests/test_browser_views.py` inject database transaction failures and prove Project version, rank, receipt, and audit writes roll back together; corresponds to acceptance eval 32.

## Browser v0 application

- Name: Browser Project creation
- Description: The Projects catalog initially exposes a plus control instead of creation fields; activating it reveals the Project key, display name, repository URL, and default branch fields, while validation errors reopen the disclosure with safe preserved values. Valid CSRF-protected submissions atomically create one isolated Project and open its Backlog.
- Test mapping: `tests/test_browser_web.py` and `tests/test_browser_web_edges.py` cover collapsed disclosure markup, successful redirect and persistence, CSRF rejection, escaped value preservation, typed validation, duplicate-key conflicts, bounded parsing, and ambiguous fields; corresponds to acceptance eval 37.

- Name: Browser Project deletion
- Description: A two-step catalog confirmation deletes one exact Project and its complete durable graph, while every other Project, Backlog, and Sprint remains unchanged; missing, mismatched, conflicting, failed-commit, and CSRF-invalid requests delete nothing.
- Test mapping: `tests/test_browser_application.py`, `tests/test_browser_persistence_core.py`, and `tests/test_browser_web.py` cover exact-key confirmation, graph removal, restart persistence, project isolation, CSRF rejection, unknown Projects, and atomic rollback; corresponds to acceptance eval 38.

- Name: Login-free loopback browser boundary
- Description: Project routes always open without authentication on supported loopback bindings; no password-authentication surface exists, while signed CSRF sessions, session expiry, bounded mutation-form parsing, strict cookies, host checks, and browser security headers protect mutations and the local application boundary.
- Test mapping: `tests/test_web_security.py`, `tests/test_browser_web.py`, `tests/test_browser_web_edges.py`, and `tests/test_browser_cli.py` cover automatic CSRF sessions, absent authentication commands and routes, security primitives, and rejection of direct non-loopback serving; corresponds to acceptance evals 36 and 37.

- Name: Representative local demo workspace
- Description: One command atomically creates a dedicated DEMO Project with a completed Sprint report, an active Sprint spanning every durable engineering state, reorderable future work, Feature history, and approval-attention examples without altering other Projects or replacing an existing DEMO Project.
- Test mapping: `tests/test_browser_cli.py` seeds a file-backed SQLite database, renders every browser view without login, verifies representative content, and proves a repeated seed leaves the exact dataset unchanged.

- Name: Project-scoped browser navigation
- Description: The Project selector and every Project route render only the selected Project's durable records, Backlog, and Sprint membership; the engineering route is labeled Sprint while that Project has an active Sprint and Board otherwise; unknown and cross-Project Feature URLs do not expose another Project.
- Test mapping: `tests/test_browser_views.py`, `tests/test_browser_web.py`, and `tests/test_browser_web_edges.py` cover deterministic Project selection, context-sensitive navigation labels, page navigation, empty states, escaped content, typed not-found behavior, and isolation; corresponds to acceptance evals 4 and 35.

- Name: Current Sprint and future-backlog presentation
- Description: Backlog renders Current Sprint above the ranked future backlog; completed current-Sprint Features appear in a separate Done section, and future work remains disjoint from active Sprint membership and completed work.
- Test mapping: `tests/test_browser_views.py` and `tests/test_browser_web.py` compare persisted read models with rendered Current Sprint, future backlog, and Done content; corresponds to acceptance evals 7, 8, 26, 27, and 35.

- Name: Exact future-backlog browser reordering
- Description: Explicit native drag handles and keyboard controls submit only the exact current future-backlog set with CSRF, an idempotency key, and the expected Project version; successful order persists while malformed, stale, conflicting, or cross-boundary submissions preserve durable state.
- Test mapping: `tests/test_browser_views.py`, `tests/test_browser_web.py`, `tests/test_browser_web_edges.py`, and `tests-js/app.test.js` cover draggable markup, order serialization, rank-only persistence, replay, optimistic concurrency, conflict rendering, invalid forms, and interaction helpers; corresponds to acceptance evals 6, 9, and 36.

- Name: Five-column Sprint view
- Description: Only current-Sprint work appears in exactly Ready for Engineering, Working, In Review, Human Review, and Done columns; Done groups merge-ready and completed Features without changing their durable states, and the shared resolver presents approved active-Sprint work with no later state as initial Ready for Engineering.
- Test mapping: `tests/test_browser_views.py` and `tests/test_browser_web.py` assert the resolver's durable-fact rules, column names and order, merge-ready/completed grouping, consistent Backlog/Sprint/detail presentation, Project isolation, explicit-state precedence, future-work exclusion, and both durable completion signals; corresponds to acceptance evals 11, 12, and 26.

- Name: Feature detail and approval attention
- Description: Feature detail renders durable Feature, active-Sprint-preferred membership, design-approval, and audit facts; Approvals surfaces only non-completed design-review and Human Review attention without fabricating an immutable revision or actionable consent.
- Test mapping: `tests/test_browser_views.py` and `tests/test_browser_web.py` cover scoped Feature lookup, active-versus-planned membership, ordered history, both terminal signals, deterministic approval attention, HTML escaping, and explicit unavailable states. Actionable exact-head approval remains mapped to the deferred GitHub and validator slices.

- Name: Completed-Sprint reports
- Description: Reports list completed Sprints with each completed Feature's key, title, owner, estimate, and completion time, attributing it only to the Sprint interval containing its durable completion timestamp.
- Test mapping: `tests/test_browser_views.py` and `tests/test_browser_web.py` cover deterministic completed-Sprint history, empty reports, owner and estimate presentation, and rollover-safe completion-time attribution; partially corresponds to acceptance evals 28 and 29. PR and merge-commit report facts remain deferred with GitHub synchronization.

- Name: Accessible local browser assets
- Description: Locally served, content-security-policy-compatible assets use the system preference initially, persist owner-selected light or dark mode, and provide responsive navigation, visible semantic states, accessible contrast and targets, and keyboard-operable backlog ordering without a frontend build service or an unused client framework.
- Test mapping: `tests/test_browser_web.py`, `tests/test_browser_web_edges.py`, and `tests-js/app.test.js` verify local asset delivery, absence of the unused HTMX asset and markup, semantic markup, persisted theme selection, non-text contrast, target sizing, interaction helpers, and responsive-navigation behavior; corresponds to acceptance evals 1 and 34.

## Deferred approved browser v0 evals

- Name: Derived engineering state
- Description: Durable PR, check, validation, approval, mergeability, and merge facts derive the approved exact-head engineering states.
- Test mapping: To be added by `feature/derived-engineering-state`; schema placeholders do not satisfy this contract.

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
