"""Codex Agent runner — executes coding tasks via Codex CLI."""

import asyncio
import os
import shutil
import time
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.execution import Execution, ExecutionLog
from src.models.project import Project
from src.models.ticket import Ticket
from src.services.event_bus import publish_event
from src.services.github_service import create_pull_request

logger = structlog.get_logger()

WORKSPACE_BASE = "/tmp/agentboard/workspaces"


async def _add_log(
    db: AsyncSession, execution_id: uuid.UUID, seq: int, log_type: str, content: str
) -> int:
    log = ExecutionLog(
        execution_id=execution_id, sequence=seq, log_type=log_type, content=content
    )
    db.add(log)
    await db.commit()
    return seq + 1


async def run_codex_agent(
    execution: Execution,
    ticket: Ticket,
    project: Project,
    openai_key: str,
    github_token: str,
    db: AsyncSession,
) -> None:
    """Run a Codex coding agent for the given execution."""
    project_id = str(project.id)
    execution_id = str(execution.id)
    workspace = os.path.join(WORKSPACE_BASE, execution_id)
    seq = 1

    try:
        execution.status = "running"
        execution.started_at = datetime.now(timezone.utc)
        execution.workspace_path = workspace
        await db.commit()

        await publish_event(
            f"project:{project_id}",
            "execution_started",
            {"execution_id": execution_id, "ticket_id": str(ticket.id)},
        )

        # Clone repo
        seq = await _add_log(db, execution.id, seq, "system", "Cloning repository...")
        os.makedirs(workspace, exist_ok=True)
        clone_proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth", "1",
            f"https://x-access-token:{github_token}@github.com/{project.repo_full_name}.git",
            workspace,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await clone_proc.communicate()
        if clone_proc.returncode != 0:
            raise RuntimeError(f"Git clone failed: {stderr.decode()}")

        # Create branch
        branch_name = ticket.branch_name or f"agentboard/{ticket.id}"
        checkout_proc = await asyncio.create_subprocess_exec(
            "git", "checkout", "-b", branch_name,
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await checkout_proc.communicate()

        # Build prompt
        prompt = (
            f"{ticket.title}\n\n"
            f"{ticket.refined_description or ticket.description or 'No description'}\n\n"
            f"Acceptance Criteria:\n{ticket.acceptance_criteria or 'Not specified'}"
        )

        seq = await _add_log(db, execution.id, seq, "system", "Starting Codex agent...")

        start_time = time.time()
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = openai_key

        # Run codex CLI
        codex_proc = await asyncio.create_subprocess_exec(
            "codex", "exec", "--prompt", prompt,
            cwd=workspace,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr_out = await codex_proc.communicate()

        if stdout:
            seq = await _add_log(db, execution.id, seq, "assistant", stdout.decode())
        if stderr_out:
            seq = await _add_log(db, execution.id, seq, "system", stderr_out.decode())

        execution.duration_seconds = int(time.time() - start_time)

        # Git add, commit, push
        seq = await _add_log(db, execution.id, seq, "system", "Committing changes...")
        for cmd in [
            ["git", "add", "-A"],
            ["git", "commit", "-m", f"feat: {ticket.title}\n\nImplemented by AgentBoard Codex"],
        ]:
            proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=workspace,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

        push_proc = await asyncio.create_subprocess_exec(
            "git", "push", "origin", branch_name,
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await push_proc.communicate()

        # Create PR
        seq = await _add_log(db, execution.id, seq, "system", "Creating pull request...")
        try:
            pr = await create_pull_request(
                project.repo_full_name, branch_name, project.default_branch,
                ticket.title,
                f"## Ticket\n{ticket.description or ticket.title}\n\n"
                f"Implemented by AgentBoard Codex agent.",
                github_token,
            )
            ticket.pr_url = pr["html_url"]
            ticket.pr_number = pr["number"]
            ticket.branch_name = branch_name
            ticket.status = "in_review"
        except Exception as e:
            seq = await _add_log(db, execution.id, seq, "error", f"PR creation failed: {e}")

        execution.status = "completed"
        execution.completed_at = datetime.now(timezone.utc)
        await db.commit()

        await publish_event(
            f"project:{project_id}", "execution_completed",
            {"execution_id": execution_id, "ticket_id": str(ticket.id), "status": "completed"},
        )

    except Exception as e:
        logger.error("codex_runner_failed", error=str(e), execution_id=execution_id)
        execution.status = "failed"
        execution.error_message = str(e)
        execution.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await _add_log(db, execution.id, seq, "error", f"Execution failed: {e}")
        await publish_event(
            f"project:{project_id}", "execution_failed",
            {"execution_id": execution_id, "ticket_id": str(ticket.id), "error": str(e)},
        )
    finally:
        if os.path.exists(workspace):
            shutil.rmtree(workspace, ignore_errors=True)
