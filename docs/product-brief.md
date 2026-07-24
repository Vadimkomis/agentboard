# AgentBoard v0 Product Brief

Status: Draft for owner approval

## Purpose

AgentBoard is a small, Linux-hosted browser application for moving software
Features from a project backlog through a GitHub pull request.

## Core principle: simplicity

Prefer the smallest design that makes the workflow reliable and visible.

- One Linux service
- One SQLite database
- One browser interface
- One backlog per project
- One active sprint per project
- One primary PR per engineering Feature
- One serial engineering worker per project
- Two human gates: design approval and PR approval

Do not add abstractions, agents, queues, services, configuration, or workflow
states until a real use case requires them.

## Product model

Only four concepts are visible in v0:

1. **Project** — a repository and its work.
2. **Feature** — the product item being planned or built.
3. **Sprint** — the project's current engineering commitment.
4. **Pull request** — the implementation and review record for a Feature.

## Project backlog

Every project has its own ranked backlog. The page shows:

- Current Sprint at the top
- Future backlog below it
- Feature key and title
- Planning stage
- Priority
- Estimate
- Owner
- Engineering readiness

Backlog ranking is draggable. Dragging changes rank only; it cannot approve a
Feature or move it into engineering.

Planning stages stay in the backlog:

```text
Inbox → Clarifying → Spec → Evals → Design → Design Review
```

An approved design allows the owner to add the Feature to the current sprint in
Ready for Engineering.

## Engineering board

The board shows only Features in the project's current sprint:

```text
Ready for Engineering → Working → In Review → Human Review → Ready to Merge
```

Starting engineering creates and binds one draft GitHub PR. Thereafter, the
board derives state from the PR's head revision, checks, validation, reviews,
approval, and mergeability.

The board is not freely draggable. New commits or failed checks can move a card
backward. A merged PR moves the Feature to Done.

While the sprint remains active, Done Features stay visible in a compact
completed section on the sprint and board. They do not occupy an active-work
column or count toward work in progress.

When the sprint closes, its Done Features disappear from standard active-sprint
and future-backlog views. They remain permanently available in completed-sprint
project reports with their PR, merge commit, completion time, estimate, and
sprint.

## Human approvals

The owner makes two explicit decisions:

1. Approve the exact design revision before engineering.
2. Approve the exact validated PR head before merge.

New design revisions or PR commits invalidate stale approval.

## Deployment

AgentBoard runs on the Linux machine under an unprivileged account. The Mac
accesses it through a private network or SSH tunnel.

SQLite on Linux is authoritative for board state:

```text
/var/lib/agentboard/agentboard.db
```

GitHub is authoritative for repositories and PR facts.

## Deferred

- Multiple simultaneous workers per project
- General-purpose agent and skill orchestration
- Public internet hosting
- Teams, organizations, and billing
- Portfolio analytics
- Obsidian write-back
- Multiple PRs per Feature
- Custom workflows
- PostgreSQL, Redis, or distributed queues
