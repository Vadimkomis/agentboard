# AgentBoard v0 Acceptance Evals

Status: Approved

## Simplicity

1. A clean installation on either a supported macOS host or a supported Linux
   host runs as one application process with one SQLite database and no Redis,
   PostgreSQL, queue, or frontend build service.
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
20. A merged PR moves the Feature to Done and records its merge commit and
    completion time.

## Independent validation

21. Every validation assignment and result is stored with its assignment digest,
    exact subject revision, validator identity and session, and all relevant
    implementation-worker identities and sessions.
22. AgentBoard rejects self-validation, reuse of an implementation session,
    malformed results, assignment-digest mismatch, insufficient evidence, and
    any result for a revision other than the active PR head.
23. Validation pass advances the exact head to Human Review; candidate failure
    returns the Feature to Working; infrastructure or protocol error leaves it
    in In Review with explicit attention required.
24. A new PR commit makes all earlier validation results ineligible for current
    state derivation without deleting their evidence or audit history.
25. Repeated stable failure signatures stop automatic validation retries and
    require owner action.

## Done and sprint closure

26. While a sprint is active, Done Features remain in its compact completed
    section and are excluded from active-work columns and work-in-progress
    counts.
27. Closing a sprint removes its Done Features from standard active-sprint and
    future-backlog views.
28. Closing a sprint preserves Done Features in project reports with sprint,
    PR, merge commit, estimate, owner, and completion time.
29. Historical reports are derived from preserved records; sprint closure never
    deletes or rewrites completed Feature history.
30. Incomplete Features require an explicit destination before sprint closure:
    the future backlog or a planned next sprint.

## Persistence and recovery

31. Restarting AgentBoard preserves projects, backlog ranks, sprint membership,
    Feature state, PR bindings, and approvals.
32. SQLite transitions and their audit records commit atomically.
33. An encrypted backup restores the database with foreign-key integrity.

## Browser

34. Light and dark modes are accessible and persist across sessions.
35. Browser refresh reconstructs the page from SQLite without inventing or
    losing state.
36. State-changing requests require a signed browser session, CSRF protection,
    idempotency, and the expected record version; the loopback browser exposes
    no password-authentication surface.

## Human-attention notifications

37. A Feature entering Human Review creates exactly one durable notification
    delivery for its exact PR head and configured destination.
38. The notification identifies the project, Feature, PR, exact head revision,
    and review URL without containing repository credentials or application
    secrets.
39. Phone notifications cannot be enabled without a configured review base URL
    that is reachable from the phone through a trusted private connection.
40. Duplicate reconciliation for the same head does not create or send another
    notification; a later validated head may create its own delivery.
41. A transient delivery failure is recorded and retried without changing the
    Feature's engineering state or losing the pending notification.
42. In the dogfood flow, the configured endpoint delivers one phone notification
    to the owner, and its review link opens the matching Human Review action.

## Release threshold

All 42 assertions must pass, one real Feature must travel from Backlog through a
merged PR, its Human Review transition must notify the owner's phone, and the
owner must approve the release candidate.
