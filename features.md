# AgentBoard — Feature Tracker

This file is the single source of truth for AgentBoard features. AgentBoard is
a local browser application; the retired Story/Ticket terminal application is
not a supported interface. The local browser workspace slice is complete, while
its GitHub, validator, worker, and notification integrations remain planned.

Status values are `planned`, `in-progress`, `completed`, and `deprecated`.

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
    Given a Project, Feature, backlog, or Sprint command changes state while retaining its Project
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

  Scenario: Browser-only command surface
    Given AgentBoard is installed
    When the owner opens the command-line help
    Then only the browser, Project, demo-seed, and version commands are available
    And no terminal UI, Story/Ticket workflow, agent registry, or legacy configuration command is exposed
    And the status is "completed"

  Scenario: Create a project from the catalog
    Given the owner is viewing the Projects catalog with the creation fields collapsed
    When the owner activates the plus control and submits a valid key, name, repository URL, and default branch
    Then AgentBoard atomically creates the isolated Project and opens its empty Backlog
    And invalid or duplicate submissions preserve the entered values and show a safe error
    And the mutation requires the signed browser CSRF token
    And the status is "completed"

  Scenario: Delete a project from the catalog
    Given the Projects catalog contains independent Project workspaces
    When the owner opens one Project's deletion confirmation and confirms its exact key
    Then AgentBoard atomically removes only that Project, its Backlog, Sprints, Features, reports, receipts, and audit history
    And every other Project and its workspace remain unchanged
    And missing, mismatched, conflicting, or CSRF-invalid requests delete nothing
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
    And each Project has its own Backlog and Sprint membership independent of every other Project
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
