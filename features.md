# AgentBoard — Feature Tracker

This file is the single source of truth for AgentBoard features. The legacy
Story/Ticket terminal application remains supported while the approved browser
v0 is delivered in separate, serial feature slices. The local browser
workspace slice is complete; its GitHub, validator, worker, and notification
integrations remain planned.

Status values are `planned`, `in-progress`, `completed`, and `deprecated`.

## Legacy Story/Ticket application

```gherkin
Feature: Legacy story board

  Scenario: Four-column Kanban
    Given the user opens the Textual terminal application
    When the story board is displayed
    Then stories are organized into DRAFTING, ENGINEERING, TESTING, and DONE columns with keyboard navigation
    And the status is "completed"

  Scenario: Story cards
    Given a story has tickets, assigned agent types, GTM content, or reported bugs
    When its card is displayed
    Then the card shows ticket progress, agent badges, GTM warnings, and bug counts
    And the status is "completed"

  Scenario: Board keyboard navigation
    Given the user is on the story board
    When the user invokes the documented new, open, chat, finalize, done, or heartbeat key
    Then the matching board action is performed
    And the status is "completed"

Feature: Legacy PRD editing

  Scenario: Five-section PRD editor
    Given a story is in DRAFTING or REFINING
    When the user edits its Problem, Solution, Scope, Acceptance, or GTM section
    Then the content is editable before finalization and read-only afterward
    And the status is "completed"

  Scenario: Mandatory GTM gate
    Given a story has no GTM content
    When PM finalization is considered
    Then the PM withholds a finalization suggestion and the story card shows a GTM warning
    And the status is "completed"

Feature: Legacy PM agent

  Scenario: Conversational PRD refinement
    Given the user discusses a draft story with the PM agent
    When the agent streams a response
    Then it asks focused follow-up questions to refine the PRD
    And the status is "completed"

  Scenario: GTM prompting
    Given a draft story is missing GTM details
    When the PM agent refines the story
    Then it asks about growth levers, channels, and monetization
    And the status is "completed"

  Scenario: Ticket decomposition on finalization
    Given the user finalizes a refined story
    When the PM agent decomposes it
    Then it produces structured engineering tickets and a marketing ticket
    And the status is "completed"

  Scenario: PRD anchor linking
    Given a ticket was decomposed from a story
    When the ticket is persisted
    Then it records the PRD section from which it was derived
    And the status is "completed"

  Scenario: PRD drift detection
    Given a finalized PRD section changes
    When the PM agent analyzes the change
    Then tickets anchored to affected sections are marked stale
    And the status is "completed"

  Scenario: Bug triage
    Given the user reports a bug for a story
    When the PM agent triages the report
    Then it creates a focused bug-fix ticket
    And the status is "completed"

Feature: Legacy growth agent

  Scenario: Parallel growth conversation
    Given a story exists
    When the user switches to its growth conversation
    Then an independent growth agent is available alongside the PM conversation
    And the status is "completed"

  Scenario: GTM discovery questions
    Given the user discusses launch planning with the growth agent
    When the agent refines the plan
    Then it covers the ideal customer, discovery, growth lever, pricing, and launch sequence
    And the status is "completed"

  Scenario: Independent growth finalization
    Given the growth plan is ready
    When the user finalizes it
    Then growth finalization remains independent of PM finalization
    And the status is "completed"

  Scenario: Launch document generation
    Given the growth plan is finalized
    When the growth artifact is generated
    Then LAUNCH.md contains positioning, audience, channels, copy, pricing, and a 30-day sequence
    And the status is "completed"

Feature: Legacy engineering execution

  Scenario: Dependency-aware orchestration
    Given tickets include dependency relationships
    When engineering execution runs
    Then independent tickets may run concurrently and dependent tickets wait
    And the status is "completed"

  Scenario: Claude CLI execution
    Given a ticket is assigned to the Claude runtime
    When its agent starts
    Then the legacy runner executes the Claude CLI in the isolated workspace
    And the status is "completed"

  Scenario: Codex CLI execution
    Given a ticket is assigned to the Codex runtime
    When its agent starts
    Then the legacy runner executes the Codex CLI in the isolated workspace
    And the status is "completed"

  Scenario: Per-execution workspace isolation
    Given an agent execution starts
    When its source workspace is prepared
    Then it receives a fresh Git clone under the configured temporary workspace root
    And the status is "completed"

  Scenario: Automatic commit and push
    Given a legacy agent completes its implementation
    When the runner finalizes the execution
    Then it commits the changes and pushes the execution branch
    And the status is "completed"

  Scenario: Optional GitHub pull-request creation
    Given the legacy application has GitHub credentials
    When an engineering execution pushes its branch
    Then the runner can create a pull request with the GitHub CLI
    And the status is "completed"

  Scenario: Agent-type routing
    Given the PM decomposes engineering work
    When it assigns an agent type
    Then it can route to backend, frontend, mobile, devops, QA, fullstack, docs, or marketing
    And the status is "completed"

Feature: Legacy testing loop

  Scenario: Automatic testing transition
    Given every ticket for a story is terminal
    When story progress is reconciled
    Then the story moves to TESTING
    And the status is "completed"

  Scenario: Ready-for-testing notification
    Given a story enters TESTING
    When the terminal UI observes the transition
    Then it shows an in-app notification and a supported desktop notification
    And the status is "completed"

  Scenario: Bug-report conversation
    Given a story is in the testing loop
    When the user describes a bug in its chat panel
    Then the PM agent creates a bug-fix ticket
    And the status is "completed"

  Scenario: Return to engineering after a bug
    Given a bug-fix ticket is added to a story in TESTING
    When the story state is reconciled
    Then the story returns to ENGINEERING
    And the status is "completed"

  Scenario: Mark story done
    Given the user accepts a tested story
    When the user invokes the done action
    Then the story moves to DONE
    And the status is "completed"

Feature: Legacy heartbeat

  Scenario: Periodic heartbeat
    Given the terminal application is running
    When thirty minutes elapse between checks
    Then its asynchronous heartbeat evaluates board health
    And the status is "completed"

  Scenario: Board health checks
    Given the heartbeat evaluates the board
    When it finds an empty pipeline, stale draft, stuck execution, missing GTM, or stale ticket
    Then it reports the matching board-health condition
    And the status is "completed"

  Scenario: LLM-assisted heartbeat alerts
    Given a board-health condition needs an alert
    When the heartbeat formats the alert
    Then it uses the Claude CLI when available and a local fallback otherwise
    And the status is "completed"

  Scenario: Heartbeat status display
    Given a heartbeat has completed
    When the terminal footer renders
    Then it shows the last check time and health or alert text
    And the status is "completed"

  Scenario: Heartbeat desktop notifications
    Given a heartbeat produces an alert
    When desktop notification support is available
    Then the alert is delivered with the platform notification command
    And the status is "completed"

  Scenario: Manual heartbeat
    Given the user is on the story board
    When the user invokes the heartbeat key
    Then an immediate health check runs
    And the status is "completed"

Feature: Legacy data model

  Scenario: Story PRD persistence
    Given a story contains the five PRD sections
    When it is saved and loaded
    Then Problem, Solution, Scope, Acceptance, and GTM content are preserved
    And the status is "completed"

  Scenario: PM message persistence
    Given a story has a PM conversation
    When the story is reopened
    Then its complete PM message history is available for replay
    And the status is "completed"

  Scenario: Growth message persistence
    Given a story has a growth conversation
    When the story is reopened
    Then its independent growth message history is preserved
    And the status is "completed"

  Scenario: Ticket PRD anchors
    Given a ticket belongs to a story
    When it is saved
    Then its PRD anchor and stale marker are preserved
    And the status is "completed"

  Scenario: Execution log persistence
    Given an agent execution produces output
    When execution state is saved
    Then the execution and its streamed standard-output and error log records are preserved
    And the status is "completed"

  Scenario: Legacy asynchronous SQLite persistence
    Given the terminal application stores legacy Story and Ticket records
    When it accesses the local database
    Then it uses asynchronous SQLAlchemy with SQLite
    And the status is "completed"

Feature: Legacy infrastructure and distribution

  Scenario: Local legacy database
    Given the user runs the terminal application with default configuration
    When legacy state is persisted
    Then the SQLite database is stored under the user's AgentBoard data directory
    And the status is "completed"

  Scenario: Subscription-backed CLI runtimes
    Given the user already has a supported Claude or Codex CLI session
    When the legacy application starts agent work
    Then it can use that CLI without storing an API key
    And the status is "completed"

  Scenario: Zero hosted operating services
    Given the user runs the legacy application locally
    When no agent work is executing
    Then the application requires no paid hosted infrastructure
    And the status is "completed"

  Scenario: Python package distribution
    Given a user installs AgentBoard from its Python package
    When installation completes
    Then the terminal command is available through pip or pipx
    And the status is "completed"

  Scenario: MIT licensing
    Given a user receives AgentBoard
    When they inspect its license
    Then commercial use is permitted under the MIT license
    And the status is "completed"

  Scenario: Bundled agent configurations
    Given AgentBoard is installed
    When a legacy agent type is selected
    Then bundled YAML configuration is available for each supported type
    And the status is "completed"

  Scenario: Custom agent configuration path
    Given the user configures an AI Playbook override path
    When legacy agents load their definitions
    Then they use the configured custom YAML location
    And the status is "completed"

  Scenario: Continuous integration
    Given a supported Python or browser JavaScript change is pushed
    When GitHub Actions runs CI
    Then Ruff and the Python test suite run on supported Python versions and the browser JavaScript tests run on Node
    And the status is "completed"

  Scenario: Automated package release
    Given a release tag is pushed
    When the release workflow runs
    Then it publishes the Python package and creates a GitHub release
    And the status is "completed"

  Scenario: Runtime portability
    Given the user enables either Claude, Codex, or both
    When legacy engineering work is routed
    Then the terminal application is not locked to a single agent runtime
    And the status is "completed"
```

## Approved browser v0

```gherkin
Feature: Browser v0 domain and persistence foundation

  Scenario: Isolated project records
    Given AgentBoard stores multiple projects
    When a project is created or queried by its stable identifier
    Then its unique key, repository, default branch, and timestamps remain isolated from every other project
    And the status is "completed"

  Scenario: Deterministic Project queries
    Given AgentBoard stores Projects with stable identifiers
    When a caller gets one Project or lists all Projects
    Then Get returns the requested Project or a typed not-found error and List returns Projects in identifier order
    And the status is "completed"

  Scenario: Project-scoped Feature numbering
    Given projects have independent Feature sequences
    When a Feature is appended to a project
    Then it receives the next number and integer backlog rank within only that project
    And the status is "completed"

  Scenario: Future project backlog
    Given a Project has non-completed Features and an optional active Sprint
    When its future backlog is listed
    Then it contains only non-completed Project Features outside the active Sprint
    And Features completed by timestamp or Done engineering state are excluded
    And the status is "completed"

  Scenario: Ranked future backlog
    Given a Project has a ranked future backlog and excluded active-Sprint or completed Features
    When the exact future-backlog Feature set is reordered
    Then only future Features exchange their available Project rank slots
    And excluded Feature ranks, Current Sprint ranks, non-rank fields, and every other Project remain unchanged
    And the status is "completed"

  Scenario: Planned and active Sprints
    Given each project has an independent Sprint sequence
    When a planned Sprint starts
    Then it becomes that project's only active Sprint
    And the status is "completed"

  Scenario: Ranked Sprint membership
    Given a Feature and Sprint belong to the same project
    When an exactly approved Feature is added or Sprint membership is reordered
    Then membership remains project-local with a unique integer rank within the Sprint
    And the status is "completed"

  Scenario: Atomic state and audit persistence
    Given a Project, Feature, backlog, or Sprint command changes state
    When its transaction succeeds or fails
    Then state and its minimal structured audit record commit together or both roll back
    And the status is "completed"

  Scenario: Restart-safe SQLite schema
    Given AgentBoard uses an explicitly configured browser-v0 database
    When the process restarts after committed work
    Then projects, Features, ranks, Sprints, membership, and audit history are reconstructed from SQLite
    And the status is "completed"

Feature: Browser v0 derived engineering state

  Scenario: Derive the engineering board state
    Given a Feature has durable planning, Sprint, pull-request, validation, and approval facts
    When AgentBoard derives its engineering state
    Then the result follows Ready for Engineering, Working, In Review, Human Review, Ready to Merge, or Done rules
    And the status is "planned"

Feature: Browser v0 local project workspace

  Scenario: Create a project from the catalog
    Given the owner is viewing the Projects catalog
    When the owner submits a valid key, name, repository URL, and default branch
    Then AgentBoard atomically creates the isolated Project and opens its empty Backlog
    And invalid or duplicate submissions preserve the entered values and show a safe error
    And the mutation requires the signed browser CSRF token
    And the status is "completed"

  Scenario: Login-free loopback browser
    Given AgentBoard is bound to a supported loopback address
    When AgentBoard serves the browser application on a loopback address
    Then project routes always open without requiring a login
    And no password-authentication command, configuration, route, or interface is exposed
    And a signed browser session binds CSRF tokens without representing user identity
    And direct non-loopback binding is rejected in favor of an SSH tunnel or trusted private proxy
    And the status is "completed"

  Scenario: Seed a representative local workspace
    Given the selected SQLite database does not contain a DEMO Project
    When the owner runs the demo seed command
    Then AgentBoard atomically creates representative Backlog, Sprint, Feature detail, Approvals, and Reports data
    And a repeated seed refuses to modify the existing DEMO Project
    And the status is "completed"

  Scenario: Render project-scoped browser views
    Given the persistence foundation contains durable Project, Feature, Sprint, and audit records
    When the owner opens a project in the browser
    Then Backlog, Sprint, Feature detail, Approvals, and Reports show only the selected Project's durable state
    And the active Sprint view has Ready for Engineering, Working, In Review, Human Review, and Done columns
    And Done combines merge-ready and completed current-Sprint Features without changing their durable states
    And the same route is labeled Board only when no Sprint is active
    And an approved active-Sprint Feature without a later recorded state is consistently presented as Ready for Engineering
    And the status is "completed"

  Scenario: Reorder the exact future backlog
    Given the owner is viewing the current version of a Project's future backlog
    When the owner drags a row or uses its reorder controls
    Then each reorderable row exposes a working drag handle
    And only the exact future-backlog set is reordered atomically with CSRF, idempotency, and expected-version protection
    And stale, conflicting, or invalid submissions preserve the current durable order
    And the status is "completed"

  Scenario: Show unavailable integration evidence honestly
    Given GitHub synchronization and immutable pull-request revision storage are not implemented
    When the owner opens Feature detail or Approvals
    Then AgentBoard labels pull-request evidence and revision-bound approval actions unavailable instead of inventing them
    And the status is "completed"

  Scenario: Persist accessible appearance preferences
    Given the owner uses a supported browser
    When the system preference supplies the initial appearance or the owner selects light or dark mode
    Then the responsive interface remains keyboard operable and preserves the appearance preference locally
    And pages load only the local CSS and JavaScript used by the current browser experience
    And the status is "completed"

Feature: Browser v0 GitHub synchronization

  Scenario: Reconcile one primary pull request
    Given an engineering Feature is bound to a primary GitHub pull request
    When signed webhook or reconciliation facts arrive
    Then AgentBoard durably and idempotently updates facts for the exact pull-request head
    And the status is "planned"

Feature: Browser v0 independent validation

  Scenario: Validate an immutable candidate independently
    Given an implementation candidate has an exact pull-request head
    When an independent validator assignment and result are processed
    Then AgentBoard preserves the evidence and derives state only from a valid result for that exact head
    And the status is "planned"

Feature: Browser v0 Human Review notification

  Scenario: Notify once per eligible review head
    Given a Feature first enters Human Review for an exact head and destination
    When notification delivery is reconciled
    Then one durable, retryable, secret-free delivery is sent with a reachable review link
    And the status is "planned"

Feature: Browser v0 serial engineering worker

  Scenario: Execute one engineering Feature per project
    Given a project has eligible engineering work
    When its implementation worker runs
    Then no second implementation executes concurrently for that project
    And the status is "planned"
```
