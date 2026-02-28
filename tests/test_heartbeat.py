"""Tests for agentboard.workers.heartbeat — HeartbeatMonitor._local_check() heuristic."""

from __future__ import annotations

from agentboard.workers.heartbeat import HeartbeatMonitor

# ===================================================================
# HeartbeatMonitor._local_check() — local heuristic without LLM
# ===================================================================


class TestLocalCheckEmptyPipeline:
    """When no active stories exist, the pipeline is empty."""

    def test_no_stories_at_all(self):
        monitor = HeartbeatMonitor()
        board = {"stories": []}
        result = monitor._local_check(board)
        assert "Pipeline is empty" in result

    def test_only_done_stories(self):
        monitor = HeartbeatMonitor()
        board = {
            "stories": [
                {
                    "id": 1,
                    "title": "Completed Feature",
                    "status": "done",
                    "hours_inactive": 100,
                    "gtm_complete": True,
                    "launch_md_finalized": True,
                    "ticket_total": 3,
                    "ticket_done": 3,
                    "stuck_tickets": [],
                    "stale_tickets": [],
                }
            ]
        }
        result = monitor._local_check(board)
        assert "Pipeline is empty" in result

    def test_only_testing_stories(self):
        monitor = HeartbeatMonitor()
        board = {
            "stories": [
                {
                    "id": 1,
                    "title": "Testing Feature",
                    "status": "testing",
                    "hours_inactive": 5,
                    "gtm_complete": True,
                    "launch_md_finalized": True,
                    "ticket_total": 3,
                    "ticket_done": 3,
                    "stuck_tickets": [],
                    "stale_tickets": [],
                }
            ]
        }
        result = monitor._local_check(board)
        # testing is not in ("drafting", "refining", "engineering"), so pipeline is empty
        assert "Pipeline is empty" in result


class TestLocalCheckStuckTicket:
    """Stuck tickets should produce an alert."""

    def test_stuck_ticket_produces_alert(self):
        monitor = HeartbeatMonitor()
        board = {
            "stories": [
                {
                    "id": 1,
                    "title": "Active Feature",
                    "status": "engineering",
                    "hours_inactive": 2,
                    "gtm_complete": True,
                    "launch_md_finalized": False,
                    "ticket_total": 3,
                    "ticket_done": 1,
                    "stuck_tickets": [{"id": 10, "title": "API endpoint", "hours": 4.5}],
                    "stale_tickets": [],
                }
            ]
        }
        result = monitor._local_check(board)
        assert "stuck agent" in result.lower() or "Possible stuck" in result
        assert "API endpoint" in result
        assert "4h" in result or "5h" in result  # hours formatted as integer

    def test_multiple_stuck_tickets_returns_first(self):
        monitor = HeartbeatMonitor()
        board = {
            "stories": [
                {
                    "id": 1,
                    "title": "Big Feature",
                    "status": "engineering",
                    "hours_inactive": 1,
                    "gtm_complete": True,
                    "launch_md_finalized": False,
                    "ticket_total": 5,
                    "ticket_done": 2,
                    "stuck_tickets": [
                        {"id": 10, "title": "First stuck", "hours": 5.0},
                        {"id": 11, "title": "Second stuck", "hours": 6.0},
                    ],
                    "stale_tickets": [],
                }
            ]
        }
        result = monitor._local_check(board)
        # The code returns on the first stuck ticket found
        assert "First stuck" in result


class TestLocalCheckStaleDraft:
    """Drafts inactive for >24h should produce an alert."""

    def test_stale_draft_produces_alert(self):
        monitor = HeartbeatMonitor()
        board = {
            "stories": [
                {
                    "id": 1,
                    "title": "Forgotten Idea",
                    "status": "drafting",
                    "hours_inactive": 48,
                    "gtm_complete": False,
                    "launch_md_finalized": False,
                    "ticket_total": 0,
                    "ticket_done": 0,
                    "stuck_tickets": [],
                    "stale_tickets": [],
                }
            ]
        }
        result = monitor._local_check(board)
        assert "Forgotten Idea" in result
        assert "Drafting" in result
        assert "48h" in result
        assert "finalize" in result.lower()

    def test_refining_story_also_triggers_stale_alert(self):
        monitor = HeartbeatMonitor()
        board = {
            "stories": [
                {
                    "id": 1,
                    "title": "Refining Feature",
                    "status": "refining",
                    "hours_inactive": 30,
                    "gtm_complete": False,
                    "launch_md_finalized": False,
                    "ticket_total": 0,
                    "ticket_done": 0,
                    "stuck_tickets": [],
                    "stale_tickets": [],
                }
            ]
        }
        result = monitor._local_check(board)
        assert "Refining Feature" in result
        assert "30h" in result

    def test_draft_under_24h_no_alert(self):
        monitor = HeartbeatMonitor()
        board = {
            "stories": [
                {
                    "id": 1,
                    "title": "Fresh Draft",
                    "status": "drafting",
                    "hours_inactive": 12,
                    "gtm_complete": False,
                    "launch_md_finalized": False,
                    "ticket_total": 0,
                    "ticket_done": 0,
                    "stuck_tickets": [],
                    "stale_tickets": [],
                }
            ]
        }
        result = monitor._local_check(board)
        assert result == "HEARTBEAT_OK"


class TestLocalCheckHealthy:
    """When everything is healthy, return HEARTBEAT_OK."""

    def test_active_engineering_healthy(self):
        monitor = HeartbeatMonitor()
        board = {
            "stories": [
                {
                    "id": 1,
                    "title": "Good Feature",
                    "status": "engineering",
                    "hours_inactive": 1,
                    "gtm_complete": True,
                    "launch_md_finalized": False,
                    "ticket_total": 4,
                    "ticket_done": 2,
                    "stuck_tickets": [],
                    "stale_tickets": [],
                }
            ]
        }
        result = monitor._local_check(board)
        assert result == "HEARTBEAT_OK"

    def test_active_drafting_recently_active(self):
        monitor = HeartbeatMonitor()
        board = {
            "stories": [
                {
                    "id": 1,
                    "title": "New Idea",
                    "status": "drafting",
                    "hours_inactive": 2,
                    "gtm_complete": False,
                    "launch_md_finalized": False,
                    "ticket_total": 0,
                    "ticket_done": 0,
                    "stuck_tickets": [],
                    "stale_tickets": [],
                }
            ]
        }
        result = monitor._local_check(board)
        assert result == "HEARTBEAT_OK"

    def test_multiple_healthy_stories(self):
        monitor = HeartbeatMonitor()
        board = {
            "stories": [
                {
                    "id": 1,
                    "title": "Story A",
                    "status": "engineering",
                    "hours_inactive": 0.5,
                    "gtm_complete": True,
                    "launch_md_finalized": True,
                    "ticket_total": 3,
                    "ticket_done": 1,
                    "stuck_tickets": [],
                    "stale_tickets": [],
                },
                {
                    "id": 2,
                    "title": "Story B",
                    "status": "drafting",
                    "hours_inactive": 6,
                    "gtm_complete": False,
                    "launch_md_finalized": False,
                    "ticket_total": 0,
                    "ticket_done": 0,
                    "stuck_tickets": [],
                    "stale_tickets": [],
                },
            ]
        }
        result = monitor._local_check(board)
        assert result == "HEARTBEAT_OK"


class TestLocalCheckPriority:
    """Stuck tickets should take priority over stale drafts."""

    def test_stuck_ticket_alert_before_stale_draft(self):
        monitor = HeartbeatMonitor()
        board = {
            "stories": [
                {
                    "id": 1,
                    "title": "Engineering Story",
                    "status": "engineering",
                    "hours_inactive": 1,
                    "gtm_complete": True,
                    "launch_md_finalized": False,
                    "ticket_total": 3,
                    "ticket_done": 1,
                    "stuck_tickets": [{"id": 10, "title": "Stuck task", "hours": 5.0}],
                    "stale_tickets": [],
                },
                {
                    "id": 2,
                    "title": "Stale Draft",
                    "status": "drafting",
                    "hours_inactive": 48,
                    "gtm_complete": False,
                    "launch_md_finalized": False,
                    "ticket_total": 0,
                    "ticket_done": 0,
                    "stuck_tickets": [],
                    "stale_tickets": [],
                },
            ]
        }
        result = monitor._local_check(board)
        # Stuck ticket check comes first in the loop, so it should alert about the stuck ticket
        assert "Stuck task" in result

    def test_engineering_not_drafting_status_skips_stale_check(self):
        """Engineering stories with >24h inactivity should NOT trigger the stale draft alert."""
        monitor = HeartbeatMonitor()
        board = {
            "stories": [
                {
                    "id": 1,
                    "title": "Idle Engineering",
                    "status": "engineering",
                    "hours_inactive": 48,
                    "gtm_complete": True,
                    "launch_md_finalized": True,
                    "ticket_total": 3,
                    "ticket_done": 3,
                    "stuck_tickets": [],
                    "stale_tickets": [],
                }
            ]
        }
        result = monitor._local_check(board)
        # Engineering is active but no stuck tickets and status isn't drafting/refining
        # so the stale check doesn't apply
        assert result == "HEARTBEAT_OK"


class TestLocalCheckEdgeCases:
    def test_missing_stories_key_returns_empty_pipeline(self):
        monitor = HeartbeatMonitor()
        board = {}
        result = monitor._local_check(board)
        assert "Pipeline is empty" in result

    def test_empty_board_state(self):
        monitor = HeartbeatMonitor()
        board = {"stories": [], "timestamp": "2026-01-01T00:00:00Z"}
        result = monitor._local_check(board)
        assert "Pipeline is empty" in result

    def test_stuck_ticket_hours_formatted_as_integer(self):
        monitor = HeartbeatMonitor()
        board = {
            "stories": [
                {
                    "id": 1,
                    "title": "Feat",
                    "status": "engineering",
                    "hours_inactive": 1,
                    "gtm_complete": True,
                    "launch_md_finalized": False,
                    "ticket_total": 1,
                    "ticket_done": 0,
                    "stuck_tickets": [{"id": 10, "title": "Task X", "hours": 3.7}],
                    "stale_tickets": [],
                }
            ]
        }
        result = monitor._local_check(board)
        # .0f formatting means 3.7 becomes "4" (rounded)
        assert "4h" in result


# ===================================================================
# HeartbeatMonitor.__init__
# ===================================================================


class TestHeartbeatMonitorInit:
    def test_default_values(self):
        monitor = HeartbeatMonitor()
        assert monitor.claude_cli_path == "claude"
        assert monitor.interval_seconds == 30 * 60
        assert monitor.on_alert is None
        assert monitor.last_check is None
        assert monitor.last_status == "Not checked yet"
        assert monitor._running is False

    def test_custom_values(self):
        def callback(msg):
            pass

        monitor = HeartbeatMonitor(
            claude_cli_path="/opt/claude",
            interval_minutes=10,
            on_alert=callback,
        )
        assert monitor.claude_cli_path == "/opt/claude"
        assert monitor.interval_seconds == 600
        assert monitor.on_alert is callback
