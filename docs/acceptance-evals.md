# AgentBoard v0 Acceptance Evals

Status: Draft for owner approval

## Simplicity

1. A clean installation runs as one application process with one SQLite
   database and no Redis, PostgreSQL, queue, or frontend build service.
2. The browser exposes only Projects, Features, Sprints, PR state, Backlog,
   Board, and Approvals.
3. Each project allows at most one active sprint and one active engineering
   execution.

## Project isolation

4. Opening Project A never returns Project B's backlog, sprint, Features,
   repository, PR facts, or approvals.
5. Backlog rank is unique and stable within a project.
6. Reordering Project A cannot change Project B.

## Backlog

7. The backlog displays Current Sprint above future ranked work.
8. Each row shows key, title, planning stage, priority, estimate, owner, and
   readiness.
9. Dragging changes rank only.
10. Moving a Feature to Ready for Engineering fails unless its exact design
    revision is approved.

## Engineering board

11. The board has exactly five columns: Ready for Engineering, Working, In
    Review, Human Review, and Ready to Merge.
12. The board and Current Sprint list show the same sprint membership and
    engineering state.
13. Starting engineering creates and binds exactly one primary draft PR.
14. Only one Feature per project may have an active engineering execution.

## GitHub synchronization

15. PR commits, draft state, checks, reviews, approval, mergeability, closure,
    reopening, and merge update durable local facts.
16. Duplicate and out-of-order webhook deliveries are idempotent.
17. Periodic reconciliation repairs state after a missed webhook.
18. New commits invalidate validation and human approval for the old head.
19. Ready to Merge requires passing checks, validation, human approval, and a
    mergeable PR for the exact head revision.
20. A merged PR removes the Feature from the active board and records the merge
    commit.

## Persistence and recovery

21. Restarting AgentBoard preserves projects, backlog ranks, sprint membership,
    Feature state, PR bindings, and approvals.
22. SQLite transitions and their audit records commit atomically.
23. An encrypted backup restores the database with foreign-key integrity.

## Browser

24. Light and dark modes are accessible and persist across sessions.
25. Browser refresh reconstructs the page from SQLite without inventing or
    losing state.
26. State-changing requests require authentication, CSRF protection,
    idempotency, and the expected record version.

## Release threshold

All 26 assertions must pass, one real Feature must travel from Backlog through a
merged PR, and the owner must approve the release candidate.
