# AgentBoard Product Brief

Status: Draft for owner review

## Product

AgentBoard is a Linux-hosted control plane for planning, executing, validating,
and reviewing software-development missions across multiple projects.

It gives each project its own board while providing a portfolio view across all
projects. OpenClaw owns orchestration and authority on Linux. Coding agents may
run on trusted remote workers, including a Mac, but workers never become the
source of truth.

## Primary user

The initial product is single-owner software for Vadim. The architecture must
not prevent future multi-user support, but v0 does not require teams, billing,
or public registration.

## Core principles

1. Specification and acceptance evals precede implementation.
2. Design requires explicit human approval.
3. A worker cannot validate its own work as the final validator.
4. Runtime duration alone never fails a valid mission.
5. Every transition is deterministic, durable, and auditable.
6. Rework is bounded; repeated failure escalates to the human.
7. Linux retains authoritative state, credentials, and evidence.
8. Projects are isolated even though they share an orchestrator and workers.

## Domain hierarchy

```text
AgentBoard
└── Project
    ├── Board
    ├── Repository bindings
    ├── Project policy and pinned skills
    └── Feature
        ├── Specification
        ├── Acceptance eval contract
        ├── Design
        ├── Work items
        ├── Executions
        ├── Validation attempts
        └── Evidence and approvals
```

## Board workflow

The primary project surface is an engineering board with five visible columns:

```text
Ready for Engineering
→ Working
→ In Review
→ Human Review
→ Ready to Merge
```

Planning states—including Inbox, Clarifying, Spec Draft, Evals Draft, Design,
and Design Review—live in Backlog rather than separate board columns. Merged,
cancelled, paused, escalated, and failed items are available through filtered
views and history rather than permanent engineering columns.

The project backlog is a compact ranked list. It supports search, filtering,
priority, product stage, ownership, estimates, grouping, and safe rank
reordering. Moving an item into engineering is a guarded action requiring the
approved artifacts; reordering backlog rank never changes workflow state.

At the top of each project backlog, a Current Sprint section lists the Features
committed to that project's active sprint. The five-column engineering board is
a second projection of this same sprint membership and PR-derived state.

Every engineering Feature has one primary pull request. The board derives its
engineering status from approved workflow facts plus the pull request's draft,
review, checks, approval, mergeability, closed, and merged state. Manual card
dragging never overrides those facts.

## Functional scope

### Portfolio

- Create, archive, and reopen projects.
- Show project health, active missions, blocked work, pending approvals,
  worker consumption, and validation failures.
- Open a project-specific board.

### Projects

- Maintain a stable project identity and slug.
- Give every project its own ranked product backlog and engineering board.
- Bind one or more Git repositories and default branches.
- Store project instructions, stack profile, pinned skill versions, policies,
  concurrency limits, and worker eligibility.
- Map project artifacts to a sanitized Obsidian projection.
- Prevent records, workspaces, credentials, and outputs from crossing projects.

### Features

The primary board item is called a **Feature**.

- Capture the problem, intended outcome, scope, constraints, and exclusions.
- Define executable and reviewer-based acceptance assertions before building.
- Preserve immutable approved revisions of specification, evals, and design.
- Require explicit owner approval at design review and final review.
- Decompose approved work into dependency-aware assignments.
- Track attempts, evidence, costs, timestamps, and decisions.

### Execution and validation

- Dispatch assignments serially by default. Parallel execution is deferred
  until the serial golden path is proven reliable.
- Create an isolated Git worktree or clone for every execution.
- Run workers locally or through an authenticated remote-worker protocol.
- Require a fresh sibling validator with no worker conversation history.
- Evaluate against the approved assertions, not an agent-authored substitute.
- Detect repeated equivalent failures and stop unproductive loops.
- Escalate after the configured rework bound or on policy/security violations.

### Human interaction

- Show precisely why a mission is waiting.
- Present specification, eval, design, diff, evidence, and validation results at
  approval gates.
- Record approval identity, timestamp, artifact revision, and optional comment.
- Never infer approval from a state change, chat response, or elapsed time.
- Provide light and dark appearance modes with a persistent browser toggle.

## Deployment and persistence

One AgentBoard service runs under a dedicated unprivileged account on Linux.

```text
/srv/agentboard/app                    deployed application
/var/lib/agentboard/agentboard.db      authoritative SQLite database
/var/lib/agentboard/artifacts/         specs, evals, designs, evidence
/var/lib/agentboard/repos/             cached repository mirrors
/var/lib/agentboard/worktrees/         isolated execution worktrees
/etc/agentboard/config.yml             non-secret configuration
/etc/agentboard/secrets.env            restricted credentials
```

SQLite with WAL mode is appropriate for v0. State changes and their event-log
entries must commit in one transaction. Database and artifacts require
encrypted, tested backups.

## Obsidian boundary

Obsidian remains on the Mac. AgentBoard exports sanitized Markdown through a
versioned Git synchronization path. The SQLite database, secrets, raw execution
logs, machine addresses, personal memory, and unapproved private evidence never
sync to the Mac.

Mac-authored changes are proposed revisions. AgentBoard imports them explicitly
and never silently overwrites an approved artifact.

## Out of scope for v0

- Public SaaS hosting
- Organization administration and billing
- Mobile applications
- Arbitrary third-party plugins
- Kubernetes or distributed database operation
- Fully autonomous final acceptance
- Treating Obsidian or GitHub Issues as the authoritative workflow database

## Initial migration from the current repository

The existing `Story` model becomes a feature beneath a new `Project` model.
Repository configuration moves from stories to project-level repository
bindings. The current four-state story workflow is replaced by the guarded
mission state machine. Existing execution records are retained conceptually but
gain project identity, attempts, evidence, assertions, approvals, and durable
events.

The product interface for v0 is a secured browser application. The current
Textual TUI may remain temporarily as a development aid, but it is not the
primary product surface. State transitions must move out of UI callbacks into a
tested domain service used by the browser application.

## Decisions required before implementation

1. Define and validate the prompts, skills, and agent roles in `ai-playbook`.
2. Select the first real project used to dogfood the board after the
   `ai-playbook` foundation is ready.
